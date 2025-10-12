# ABOUTME: Controller and runner for Google Cloud Speech-to-Text API STT engine.
# ABOUTME: Implements STT interfaces for Google Cloud Speech-to-Text V2 streaming recognition.

from __future__ import annotations

import io
import logging
import os
import queue
import threading
import time
from enum import Enum, auto
from pathlib import Path
from typing import Callable, Dict, List, Optional

from eloGraf.base_controller import StreamingControllerBase
from eloGraf.input_simulator import type_text
from eloGraf.streaming_runner_base import StreamingRunnerBase


class GoogleCloudSpeechState(Enum):
    IDLE = auto()
    STARTING = auto()
    CONNECTING = auto()
    READY = auto()
    RECORDING = auto()
    TRANSCRIBING = auto()
    SUSPENDED = auto()
    FAILED = auto()


StateListener = Callable[[GoogleCloudSpeechState], None]
OutputListener = Callable[[str], None]
ExitListener = Callable[[int], None]


STATE_MAP = {
    "idle": GoogleCloudSpeechState.IDLE,
    "starting": GoogleCloudSpeechState.STARTING,
    "connecting": GoogleCloudSpeechState.CONNECTING,
    "ready": GoogleCloudSpeechState.READY,
    "recording": GoogleCloudSpeechState.RECORDING,
    "transcribing": GoogleCloudSpeechState.TRANSCRIBING,
    "suspended": GoogleCloudSpeechState.SUSPENDED,
    "failed": GoogleCloudSpeechState.FAILED,
}


class GoogleCloudSpeechController(StreamingControllerBase[GoogleCloudSpeechState]):
    """Controller for Google Cloud Speech API that interprets states."""

    def __init__(self) -> None:
        super().__init__(
            initial_state=GoogleCloudSpeechState.IDLE,
            state_map=STATE_MAP,
            engine_name="GoogleCloudSpeech",
        )
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


class GoogleCloudSpeechProcessRunner(StreamingRunnerBase):
    """Manages Google Cloud Speech API streaming recognition."""

    def __init__(
        self,
        controller: GoogleCloudSpeechController,
        *,
        credentials_path: Optional[str] = None,
        project_id: Optional[str] = None,
        language_code: str = "en-US",
        model: str = "chirp_3",
        sample_rate: int = 16000,
        channels: int = 1,
        chunk_duration: float = 0.1,
        vad_enabled: bool = True,
        vad_threshold: float = 500.0,
        input_simulator: Optional[Callable[[str], None]] = None,
    ) -> None:
        super().__init__(
            controller,
            sample_rate=sample_rate,
            channels=channels,
            chunk_duration=chunk_duration,
            input_simulator=input_simulator or type_text,
        )
        self._controller = controller
        self._credentials_path = credentials_path
        self._project_id = project_id
        self._language_code = language_code
        self._model = model
        self._vad_enabled = vad_enabled
        self._vad_threshold = vad_threshold
        self._input_simulator = input_simulator or type_text

        self._audio_queue: Optional[queue.Queue[Optional[bytes]]] = None
        self._response_thread: Optional[threading.Thread] = None
        self._client = None
        self._recognizer: Optional[str] = None
        self._streaming_config = None
        self._speech_types = None

    def _verify_credentials(self) -> bool:
        """Verify Google Cloud credentials are available."""
        if self._credentials_path:
            if not Path(self._credentials_path).exists():
                logging.error(f"Credentials file not found: {self._credentials_path}")
                return False
            os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = self._credentials_path
            logging.info(f"Using credentials from: {self._credentials_path}")
        else:
            # Check if Application Default Credentials are available
            if "GOOGLE_APPLICATION_CREDENTIALS" not in os.environ:
                logging.warning(
                    "GOOGLE_APPLICATION_CREDENTIALS not set. "
                    "Attempting to use Application Default Credentials."
                )
        return True

    def _preflight_checks(self) -> bool:
        return self._verify_credentials()

    def _initialize_connection(self) -> bool:
        try:
            from google.cloud.speech_v2 import SpeechClient
            from google.cloud.speech_v2.types import cloud_speech as cloud_speech_types
        except ImportError:
            logging.error(
                "google-cloud-speech is not installed. Install with: pip install google-cloud-speech"
            )
            self._controller.emit_error("google-cloud-speech package is required")
            return False

        self._speech_types = cloud_speech_types
        self._client = SpeechClient()
        self._controller.transition_to("connecting")

        try:
            self._recognizer = self._resolve_recognizer_name()
        except Exception as exc:
            logging.exception("Failed to determine project ID")
            self._controller.emit_error(f"Failed to determine project ID: {exc}")
            return False

        recognition_config = cloud_speech_types.RecognitionConfig(
            auto_decoding_config=cloud_speech_types.AutoDetectDecodingConfig(),
            language_codes=[self._language_code],
            model=self._model,
        )

        self._streaming_config = cloud_speech_types.StreamingRecognitionConfig(
            config=recognition_config,
        )

        self._audio_queue = queue.Queue()
        self._response_thread = threading.Thread(target=self._response_loop, daemon=True)
        self._response_thread.start()
        self._controller.set_ready()
        return True

    def _process_audio_chunk(self, audio_data: bytes) -> None:
        if self._vad_enabled:
            audio_level = self._calculate_audio_level(audio_data)
            if audio_level < self._vad_threshold:
                return

        raw_audio = self._extract_raw_audio(audio_data)
        max_chunk_size = 25 * 1024
        if len(raw_audio) > max_chunk_size:
            raw_audio = raw_audio[:max_chunk_size]

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
        self._client = None
        self._streaming_config = None
        self._recognizer = None

    # ------------------------------------------------------------------
    # Streaming helpers
    # ------------------------------------------------------------------

    def _resolve_recognizer_name(self) -> str:
        if self._project_id:
            return f"projects/{self._project_id}/locations/global/recognizers/_"

        from google.auth import default

        credentials, project_id = default()
        if not project_id:
            raise ValueError("Could not determine project ID")
        logging.info("Using project: %s", project_id)
        return f"projects/{project_id}/locations/global/recognizers/_"

    def _request_generator(self):
        assert self._speech_types is not None
        assert self._recognizer is not None
        assert self._streaming_config is not None

        yield self._speech_types.StreamingRecognizeRequest(
            recognizer=self._recognizer,
            streaming_config=self._streaming_config,
        )

        while True:
            if self._audio_queue is None:
                break
            chunk = self._audio_queue.get()
            if chunk is None:
                break
            if self._stop_event.is_set():
                break
            yield self._speech_types.StreamingRecognizeRequest(audio=chunk)

    def _response_loop(self) -> None:
        if not self._client or not self._speech_types:
            return

        try:
            responses = self._client.streaming_recognize(requests=self._request_generator())
            for response in responses:
                if self._stop_event.is_set():
                    break
                for result in response.results:
                    if not result.alternatives:
                        continue
                    transcript = result.alternatives[0].transcript
                    if result.is_final and transcript.strip():
                        self._controller.emit_transcription(transcript)
                        self._input_simulator(transcript)
                self._controller.set_recording()
        except Exception as exc:  # pragma: no cover - defensive
            logging.exception("Streaming loop error")
            self._controller.emit_error(f"Streaming loop error: {exc}")
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
        # WAV header is typically 44 bytes
        return wav_data[44:]

class AudioRecorder:
    """Records audio chunks from the microphone using pyaudio."""

    def __init__(self, sample_rate: int = 16000, channels: int = 1):
        try:
            import pyaudio
            import wave
        except ImportError:
            raise RuntimeError("pyaudio is required for audio recording. Install with: pip install pyaudio")

        self._sample_rate = sample_rate
        self._channels = channels
        self._pyaudio = pyaudio.PyAudio()
        self._format = pyaudio.paInt16

    def record_chunk(self, duration: float = 0.1) -> bytes:
        """Record audio for specified duration and return WAV bytes."""
        import wave

        stream = self._pyaudio.open(
            format=self._format,
            channels=self._channels,
            rate=self._sample_rate,
            input=True,
            frames_per_buffer=1024,
        )

        frames = []
        chunk_count = int(self._sample_rate / 1024 * duration)

        for _ in range(chunk_count):
            data = stream.read(1024)
            frames.append(data)

        stream.stop_stream()
        stream.close()

        # Create WAV file in memory
        wav_buffer = io.BytesIO()
        with wave.open(wav_buffer, 'wb') as wav_file:
            wav_file.setnchannels(self._channels)
            wav_file.setsampwidth(self._pyaudio.get_sample_size(self._format))
            wav_file.setframerate(self._sample_rate)
            wav_file.writeframes(b''.join(frames))

        return wav_buffer.getvalue()

    def __del__(self):
        if hasattr(self, '_pyaudio'):
            self._pyaudio.terminate()
