# ABOUTME: Controller and runner for OpenAI Realtime API STT engine.
# ABOUTME: Implements STT interfaces for OpenAI's GPT-4o-transcribe streaming recognition via WebSocket.

from __future__ import annotations

import io
import json
import logging
import threading
import time
import base64
from enum import Enum, auto
from subprocess import run, CalledProcessError
from typing import Callable, Dict, List, Optional, Sequence

from eloGraf.stt_engine import STTController, STTProcessRunner


class OpenAIRealtimeState(Enum):
    IDLE = auto()
    STARTING = auto()
    CONNECTING = auto()
    READY = auto()
    RECORDING = auto()
    TRANSCRIBING = auto()
    SUSPENDED = auto()
    FAILED = auto()


StateListener = Callable[[OpenAIRealtimeState], None]
OutputListener = Callable[[str], None]
ExitListener = Callable[[int], None]


class OpenAIRealtimeController(STTController):
    """Controller for OpenAI Realtime API that interprets states."""

    def __init__(self) -> None:
        self._state = OpenAIRealtimeState.IDLE
        self._state_listeners: List[StateListener] = []
        self._output_listeners: List[OutputListener] = []
        self._exit_listeners: List[ExitListener] = []
        self._stop_requested = False
        self._suspended = False

    @property
    def state(self) -> OpenAIRealtimeState:
        return self._state

    def add_state_listener(self, callback: StateListener) -> None:
        self._state_listeners.append(callback)

    def add_output_listener(self, callback: OutputListener) -> None:
        self._output_listeners.append(callback)

    def add_exit_listener(self, callback: ExitListener) -> None:
        self._exit_listeners.append(callback)

    def start(self) -> None:
        self._stop_requested = False
        self._set_state(OpenAIRealtimeState.STARTING)

    def stop_requested(self) -> None:
        self._stop_requested = True

    def suspend_requested(self) -> None:
        self._suspended = True
        self._set_state(OpenAIRealtimeState.SUSPENDED)

    def resume_requested(self) -> None:
        self._suspended = False
        self._set_state(OpenAIRealtimeState.RECORDING)

    @property
    def is_suspended(self) -> bool:
        return self._suspended

    def fail_to_start(self) -> None:
        self._stop_requested = False
        self._set_state(OpenAIRealtimeState.FAILED)
        self._emit_exit(1)

    def set_connecting(self) -> None:
        self._set_state(OpenAIRealtimeState.CONNECTING)

    def set_ready(self) -> None:
        self._set_state(OpenAIRealtimeState.READY)

    def set_recording(self) -> None:
        self._set_state(OpenAIRealtimeState.RECORDING)

    def set_transcribing(self) -> None:
        self._set_state(OpenAIRealtimeState.TRANSCRIBING)

    def handle_output(self, line: str) -> None:
        self._emit_output(line)

    def handle_exit(self, return_code: int) -> None:
        if return_code == 0:
            self._set_state(OpenAIRealtimeState.IDLE)
        else:
            self._set_state(OpenAIRealtimeState.FAILED)
        self._emit_exit(return_code)
        self._stop_requested = False

    def _set_state(self, state: OpenAIRealtimeState) -> None:
        if self._state == state:
            return
        self._state = state
        for listener in self._state_listeners:
            listener(state)

    def _emit_output(self, line: str) -> None:
        for listener in self._output_listeners:
            listener(line)

    def _emit_exit(self, return_code: int) -> None:
        for listener in self._exit_listeners:
            listener(return_code)


class OpenAIRealtimeProcessRunner(STTProcessRunner):
    """Manages OpenAI Realtime API WebSocket connection and streaming."""

    def __init__(
        self,
        controller: OpenAIRealtimeController,
        *,
        api_key: str,
        model: str = "gpt-4o-transcribe",
        api_version: str = "2025-08-28",
        sample_rate: int = 16000,
        channels: int = 1,
        chunk_duration: float = 0.1,
        vad_enabled: bool = True,
        vad_threshold: float = 0.5,
        vad_prefix_padding_ms: int = 300,
        vad_silence_duration_ms: int = 200,
        input_simulator: Optional[Callable[[str], None]] = None,
    ) -> None:
        self._controller = controller
        self._api_key = api_key
        self._model = model
        self._api_version = api_version
        self._sample_rate = sample_rate
        self._channels = channels
        self._chunk_duration = chunk_duration
        self._vad_enabled = vad_enabled
        self._vad_threshold = vad_threshold
        self._vad_prefix_padding_ms = vad_prefix_padding_ms
        self._vad_silence_duration_ms = vad_silence_duration_ms
        self._input_simulator = input_simulator or self._default_input_simulator
        self._ws_thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._ws = None
        self._audio_recorder: Optional[AudioRecorder] = None

    def start(self, command: Sequence[str], env: Optional[Dict[str, str]] = None) -> bool:
        if self.is_running():
            logging.warning("OpenAI Realtime is already running")
            return False

        self._controller.start()

        if not self._api_key:
            logging.error("OpenAI API key is required")
            self._controller.fail_to_start()
            return False

        # Verify websocket-client is installed
        try:
            import websocket
        except ImportError:
            logging.error(
                "websocket-client is not installed. "
                "Install with: pip install websocket-client"
            )
            self._controller.fail_to_start()
            return False

        # Start WebSocket thread
        self._stop_event.clear()
        self._ws_thread = threading.Thread(target=self._websocket_loop, daemon=True)
        self._ws_thread.start()

        return True

    def stop(self) -> None:
        if not self.is_running():
            return

        self._controller.stop_requested()
        self._stop_event.set()

        if self._ws:
            try:
                self._ws.close()
            except Exception:
                pass

        if self._ws_thread:
            self._ws_thread.join(timeout=2)
            self._ws_thread = None

        self._controller.handle_exit(0)

    def suspend(self) -> None:
        if self.is_running():
            self._controller.suspend_requested()

    def resume(self) -> None:
        if self.is_running():
            self._controller.resume_requested()

    def poll(self) -> None:
        # WebSocket runs in background thread, no polling needed
        pass

    def is_running(self) -> bool:
        return self._ws_thread is not None and self._ws_thread.is_alive()

    def _websocket_loop(self) -> None:
        """Main WebSocket loop for OpenAI Realtime API."""
        try:
            import websocket

            # Build WebSocket URL
            ws_url = f"wss://api.openai.com/v1/realtime?api-version={self._api_version}"

            self._controller.set_connecting()

            # Connect to WebSocket
            self._ws = websocket.WebSocketApp(
                ws_url,
                header={
                    "Authorization": f"Bearer {self._api_key}",
                    "OpenAI-Beta": "realtime=v1",
                },
                on_open=self._on_open,
                on_message=self._on_message,
                on_error=self._on_error,
                on_close=self._on_close,
            )

            # Run WebSocket (blocking call)
            self._ws.run_forever()

        except Exception as exc:
            logging.error(f"WebSocket loop error: {exc}")
            self._controller.handle_exit(1)

    def _on_open(self, ws) -> None:
        """Handle WebSocket connection opened."""
        logging.info("OpenAI Realtime WebSocket connected")

        # Configure session
        turn_detection = None
        if self._vad_enabled:
            turn_detection = {
                "type": "server_vad",
                "threshold": self._vad_threshold,
                "prefix_padding_ms": self._vad_prefix_padding_ms,
                "silence_duration_ms": self._vad_silence_duration_ms,
            }

        session_config = {
            "type": "transcription_session.update",
            "session": {
                "input_audio_format": "pcm16",
                "input_audio_transcription": {
                    "model": self._model,
                },
            }
        }

        if turn_detection:
            session_config["session"]["turn_detection"] = turn_detection

        # Send session configuration
        ws.send(json.dumps(session_config))

        self._controller.set_ready()

        # Start audio recording thread
        audio_thread = threading.Thread(target=self._audio_loop, daemon=True)
        audio_thread.start()

    def _on_message(self, ws, message) -> None:
        """Handle WebSocket message received."""
        try:
            data = json.loads(message)
            msg_type = data.get("type", "")

            if msg_type == "transcription.done":
                # Final transcription
                transcript = data.get("transcript", "").strip()
                if transcript:
                    self._controller.handle_output(f"Transcribed: {transcript}")
                    self._input_simulator(transcript)

            elif msg_type == "transcription.delta":
                # Partial transcription (optional: log for debugging)
                delta = data.get("delta", "")
                if delta:
                    logging.debug(f"Partial: {delta}")

            elif msg_type == "error":
                error = data.get("error", {})
                logging.error(f"OpenAI Realtime error: {error}")

        except Exception as exc:
            logging.error(f"Error processing message: {exc}")

    def _on_error(self, ws, error) -> None:
        """Handle WebSocket error."""
        logging.error(f"WebSocket error: {error}")

    def _on_close(self, ws, close_status_code, close_msg) -> None:
        """Handle WebSocket connection closed."""
        logging.info(f"WebSocket closed: {close_status_code} - {close_msg}")
        if not self._stop_event.is_set():
            self._controller.handle_exit(1)

    def _audio_loop(self) -> None:
        """Record and stream audio to WebSocket."""
        try:
            self._audio_recorder = AudioRecorder(
                sample_rate=self._sample_rate,
                channels=self._channels,
            )
            self._controller.set_recording()

            while not self._stop_event.is_set():
                # Check if suspended
                if self._controller.is_suspended:
                    time.sleep(0.1)
                    continue

                # Record audio chunk
                audio_data = self._audio_recorder.record_chunk(duration=self._chunk_duration)

                if self._stop_event.is_set():
                    break

                # Check if suspended again
                if self._controller.is_suspended:
                    continue

                # Extract raw PCM audio (skip WAV header)
                raw_audio = self._extract_raw_audio(audio_data)

                # Encode to base64
                audio_b64 = base64.b64encode(raw_audio).decode('utf-8')

                # Send audio to WebSocket
                audio_event = {
                    "type": "input_audio_buffer.append",
                    "audio": audio_b64,
                }

                if self._ws:
                    self._ws.send(json.dumps(audio_event))

        except Exception as exc:
            logging.error(f"Audio loop error: {exc}")
            self._controller.handle_exit(1)

    def _extract_raw_audio(self, wav_data: bytes) -> bytes:
        """Extract raw PCM audio from WAV file (skip 44-byte header)."""
        return wav_data[44:]

    @staticmethod
    def _default_input_simulator(text: str) -> None:
        """Default input simulator using dotool or xdotool."""
        try:
            # Try dotool first
            run(["dotool", "type", text], check=True)
        except (CalledProcessError, FileNotFoundError):
            try:
                # Fallback to xdotool
                run(["xdotool", "type", "--", text], check=True)
            except (CalledProcessError, FileNotFoundError):
                logging.warning("Neither dotool nor xdotool available for input simulation")


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
