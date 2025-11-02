# ABOUTME: Controller and runner for Gemini Live API STT engine.
# ABOUTME: Implements STT interfaces for Google Gemini Live API streaming recognition.

from __future__ import annotations

import io
import logging
import queue
import threading
from enum import Enum, auto
from typing import Callable, Optional

from eloGraf.base_controller import StreamingControllerBase
from eloGraf.status import DictationStatus
from eloGraf.input_simulator import type_text
from eloGraf.streaming_runner_base import StreamingRunnerBase
from .settings import GeminiSettings


class GeminiLiveState(Enum):
    IDLE = auto()
    STARTING = auto()
    CONNECTING = auto()
    READY = auto()
    RECORDING = auto()
    TRANSCRIBING = auto()
    SUSPENDED = auto()
    FAILED = auto()


StateListener = Callable[[GeminiLiveState], None]
OutputListener = Callable[[str], None]
ExitListener = Callable[[int], None]


STATE_MAP = {
    "idle": GeminiLiveState.IDLE,
    "starting": GeminiLiveState.STARTING,
    "connecting": GeminiLiveState.CONNECTING,
    "ready": GeminiLiveState.READY,
    "recording": GeminiLiveState.RECORDING,
    "transcribing": GeminiLiveState.TRANSCRIBING,
    "suspended": GeminiLiveState.SUSPENDED,
    "failed": GeminiLiveState.FAILED,
}


class GeminiLiveController(StreamingControllerBase[GeminiLiveState]):
    """Controller for Gemini Live API that interprets states."""

    def __init__(self, settings: GeminiSettings) -> None:
        super().__init__(
            initial_state=GeminiLiveState.IDLE,
            state_map=STATE_MAP,
            engine_name="GeminiLive",
        )
        self._settings = settings
        self._stop_requested = False

    def start(self) -> None:
        self._stop_requested = False
        self.transition_to("starting")

    def stop_requested(self) -> None:
        self._stop_requested = True

    def fail_to_start(self) -> None:
        self._stop_requested = False
        super().fail_to_start()

    def set_ready(self) -> None:
        self.transition_to("ready")

    def set_recording(self) -> None:
        self.transition_to("recording")

    def set_transcribing(self) -> None:
        self.transition_to("transcribing")

    def handle_output(self, line: str) -> None:
        self._emit_output(line)

    def handle_exit(self, return_code: int) -> None:
        if return_code == 0:
            self.transition_to("idle")
        else:
            self.transition_to("failed")
        self._emit_exit(return_code)
        self._stop_requested = False

    def get_status_string(self) -> str:
        model_name = self._settings.model
        language = self._settings.language_code
        return f"Gemini Live | Model: {model_name} | Lang: {language}"

    @property
    def dictation_status(self) -> DictationStatus:
        if self.state in (GeminiLiveState.STARTING, GeminiLiveState.CONNECTING):
            return DictationStatus.INITIALIZING
        elif self.state in (GeminiLiveState.READY, GeminiLiveState.RECORDING, GeminiLiveState.TRANSCRIBING):
            return DictationStatus.LISTENING
        elif self.state == GeminiLiveState.SUSPENDED:
            return DictationStatus.SUSPENDED
        elif self.state == GeminiLiveState.FAILED:
            return DictationStatus.FAILED
        else:
            return DictationStatus.IDLE


class GeminiLiveProcessRunner(StreamingRunnerBase):
    """Manages Gemini Live API streaming recognition."""

    def __init__(
        self,
        controller: GeminiLiveController,
        *,
        api_key: str = "",
        model: str = "gemini-2.5-flash",
        language_code: str = "en-US",
        sample_rate: int = 16000,
        channels: int = 1,
        chunk_duration: float = 0.1,
        vad_enabled: bool = True,
        vad_threshold: float = 500.0,
        pulse_device: Optional[str] = None,
        input_simulator: Optional[Callable[[str], None]] = None,
    ) -> None:
        super().__init__(
            controller,
            sample_rate=sample_rate,
            channels=channels,
            chunk_duration=chunk_duration,
            device=pulse_device,
            input_simulator=input_simulator or type_text,
        )
        self._controller = controller
        self._api_key = api_key
        self._model = model
        self._language_code = language_code
        self._vad_enabled = vad_enabled
        self._vad_threshold = vad_threshold
        self._input_simulator = input_simulator or type_text

        self._audio_queue: Optional[queue.Queue[Optional[bytes]]] = None
        self._response_thread: Optional[threading.Thread] = None
        self._send_thread: Optional[threading.Thread] = None
        self._client = None
        self._session = None

    def _verify_api_key(self) -> bool:
        """Verify API key is provided."""
        if not self._api_key:
            logging.error("Gemini API key not provided")
            return False
        return True

    def _preflight_checks(self) -> bool:
        return self._verify_api_key()

    def _initialize_connection(self) -> bool:
        try:
            from google import genai
        except ImportError:
            logging.error(
                "google-genai is not installed. Install with: pip install google-genai"
            )
            self._controller.emit_error("google-genai package is required")
            return False

        self._controller.transition_to("connecting")

        try:
            self._client = genai.Client(api_key=self._api_key)
        except Exception as exc:
            logging.exception("Failed to create Gemini client")
            self._controller.emit_error(f"Failed to create Gemini client: {exc}")
            return False

        self._audio_queue = queue.Queue()

        # Start response thread (manages async event loop)
        self._response_thread = threading.Thread(target=self._async_loop_wrapper, daemon=True)
        self._response_thread.start()

        self._controller.set_ready()
        return True

    def _process_audio_chunk(self, audio_data: bytes) -> None:
        if self._vad_enabled:
            audio_level = self._calculate_audio_level(audio_data)
            if audio_level < self._vad_threshold:
                return

        raw_audio = self._extract_raw_audio(audio_data)

        if self._audio_queue is not None:
            self._controller.set_transcribing()
            self._audio_queue.put(raw_audio)

    def _cleanup_connection(self) -> None:
        if self._audio_queue is not None:
            self._audio_queue.put(None)
        if self._response_thread:
            self._response_thread.join(timeout=2)
            self._response_thread = None
        self._audio_queue = None
        self._session = None
        self._client = None

    def _async_loop_wrapper(self) -> None:
        """Wrapper to run async event loop in a thread."""
        import asyncio
        try:
            asyncio.run(self._async_streaming_loop())
        except Exception as exc:  # pragma: no cover - defensive
            logging.exception("Async loop error")
            self._controller.emit_error(f"Async loop error: {exc}")
            self._failure_exit = True
            self._stop_event.set()

    async def _async_streaming_loop(self) -> None:
        """Main async streaming loop with bidirectional communication."""
        import asyncio
        from google import genai

        if not self._client:
            return

        try:
            # Create live session with input audio transcription enabled
            config = {
                "response_modalities": ["TEXT"],
                "speech_config": {
                    "voice_config": {"prebuilt_voice_config": {"voice_name": "Puck"}}
                },
                "input_audio_transcription": {},  # Enable transcription
            }

            async with self._client.aio.live.connect(
                model=self._model,
                config=config
            ) as session:
                self._session = session

                # Create two concurrent tasks: sending audio and receiving responses
                send_task = asyncio.create_task(self._send_audio_loop(session))
                receive_task = asyncio.create_task(self._receive_response_loop(session))

                # Wait for both tasks to complete (or one to fail)
                await asyncio.gather(send_task, receive_task, return_exceptions=True)

        except Exception as exc:  # pragma: no cover - defensive
            logging.exception("Streaming loop error")
            self._controller.emit_error(f"Streaming loop error: {exc}")
            self._failure_exit = True
            self._stop_event.set()

    async def _send_audio_loop(self, session) -> None:
        """Continuously send audio chunks from queue to Live API."""
        import asyncio
        from google.genai import types

        while True:
            if self._audio_queue is None:
                break
            if self._stop_event.is_set():
                break

            # Get audio chunk from queue (non-blocking check)
            try:
                chunk = self._audio_queue.get_nowait()
            except queue.Empty:
                await asyncio.sleep(0.01)  # Small delay to avoid busy waiting
                continue

            if chunk is None:  # Sentinel value to stop
                break

            try:
                # Send audio to Live API
                await session.send_realtime_input(
                    media=types.Blob(
                        data=chunk,
                        mime_type=f"audio/pcm;rate={self._sample_rate}"
                    )
                )
                self._controller.set_recording()
            except Exception as exc:  # pragma: no cover - defensive
                logging.error(f"Failed to send audio chunk: {exc}")
                break

    async def _receive_response_loop(self, session) -> None:
        """Continuously receive and process responses from Live API."""
        try:
            async for response in session.receive():
                if self._stop_event.is_set():
                    break

                # Check for transcription in server content
                if hasattr(response, 'server_content'):
                    for part in response.server_content.parts:
                        if hasattr(part, 'text') and part.text.strip():
                            transcript = part.text.strip()
                            self._controller.emit_transcription(transcript)
                            self._input_simulator(transcript)

        except Exception as exc:  # pragma: no cover - defensive
            logging.error(f"Response loop error: {exc}")
            self._failure_exit = True
            self._stop_event.set()

    def _calculate_audio_level(self, audio_data: bytes) -> float:
        """Calculate RMS audio level from WAV data."""
        import wave
        import struct

        try:
            wav_buffer = io.BytesIO(audio_data)
            with wave.open(wav_buffer, 'rb') as wav_file:
                frames = wav_file.readframes(wav_file.getnframes())

            sample_width = 2  # 16-bit audio
            samples = struct.unpack(f'<{len(frames) // sample_width}h', frames)
            rms = (sum(s ** 2 for s in samples) / len(samples)) ** 0.5
            return rms
        except Exception as exc:
            logging.warning(f"Error calculating audio level: {exc}")
            return float('inf')

    def _extract_raw_audio(self, wav_data: bytes) -> bytes:
        """Extract raw PCM audio from WAV file (skip 44-byte header)."""
        return wav_data[44:]
