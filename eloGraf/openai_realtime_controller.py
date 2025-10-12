# ABOUTME: Controller and runner for OpenAI Realtime API STT engine.
# ABOUTME: Implements STT interfaces for OpenAI's GPT-4o-transcribe streaming recognition via WebSocket.

from __future__ import annotations

import base64
import io
import json
import logging
import shutil
import subprocess
import threading
import time
from enum import Enum, auto
from subprocess import PIPE, Popen, CalledProcessError, run
from typing import Callable, Dict, List, Optional

from eloGraf.base_controller import EnumStateController
from eloGraf.input_simulator import type_text
from eloGraf.streaming_runner_base import StreamingRunnerBase


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


STATE_MAP = {
    "idle": OpenAIRealtimeState.IDLE,
    "starting": OpenAIRealtimeState.STARTING,
    "connecting": OpenAIRealtimeState.CONNECTING,
    "ready": OpenAIRealtimeState.READY,
    "recording": OpenAIRealtimeState.RECORDING,
    "transcribing": OpenAIRealtimeState.TRANSCRIBING,
    "suspended": OpenAIRealtimeState.SUSPENDED,
    "failed": OpenAIRealtimeState.FAILED,
}


class OpenAIRealtimeController(EnumStateController[OpenAIRealtimeState]):
    """Controller for OpenAI Realtime API that interprets states."""

    def __init__(self) -> None:
        super().__init__(
            initial_state=OpenAIRealtimeState.IDLE,
            state_map=STATE_MAP,
            engine_name="OpenAIRealtime",
        )
        self._stop_requested = False
        self._suspended = False

    def start(self) -> None:
        self._stop_requested = False
        self.transition_to("starting")

    def stop_requested(self) -> None:
        self._stop_requested = True

    def suspend_requested(self) -> None:
        self._suspended = True
        self.transition_to("suspended")

    def resume_requested(self) -> None:
        self._suspended = False
        self.transition_to("recording")

    @property
    def is_suspended(self) -> bool:
        return self._suspended

    def fail_to_start(self) -> None:
        self._stop_requested = False
        super().fail_to_start()

    def set_connecting(self) -> None:
        self.transition_to("connecting")

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


class OpenAIRealtimeProcessRunner(StreamingRunnerBase):
    """Manages OpenAI Realtime API WebSocket connection and streaming."""

    def __init__(
        self,
        controller: OpenAIRealtimeController,
        *,
        api_key: str,
        model: str = "gpt-4o-transcribe",
        language: Optional[str] = None,
        api_version: str = "2025-08-28",
        sample_rate: int = 16000,
        channels: int = 1,
        chunk_duration: float = 0.1,
        vad_enabled: bool = True,
        vad_threshold: float = 0.5,
        vad_prefix_padding_ms: int = 300,
        vad_silence_duration_ms: int = 200,
        pulse_device: Optional[str] = None,
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
        self._api_key = api_key
        session_model_map = {
            "gpt-4o-transcribe": "gpt-4o-realtime-preview",
            "gpt-4o-mini-transcribe": "gpt-4o-mini-realtime-preview",
        }
        if model in session_model_map:
            self._model = model
        else:
            logging.warning(
                "OpenAI transcription model '%s' is unsupported; defaulting to gpt-4o-transcribe",
                model,
            )
            self._model = "gpt-4o-transcribe"
        self._session_model = session_model_map.get(self._model, "gpt-4o-realtime-preview")
        self._language = language
        self._api_version = api_version
        self._sample_rate = sample_rate
        self._channels = channels
        self._vad_enabled = vad_enabled
        self._vad_threshold = vad_threshold
        self._vad_prefix_padding_ms = vad_prefix_padding_ms
        self._vad_silence_duration_ms = vad_silence_duration_ms
        self._ws_thread: Optional[threading.Thread] = None
        self._ws = None
        self._audio_buffer = bytearray()
        self._sample_width_bytes = 2
        self._bytes_per_commit = max(
            1,
            int(self._sample_rate * self._chunk_duration) * self._channels * self._sample_width_bytes,
        )
        min_commit_bytes = (self._sample_rate * self._channels * self._sample_width_bytes) // 5
        if self._bytes_per_commit < min_commit_bytes:
            self._bytes_per_commit = min_commit_bytes
        self._response_active = False
        self._current_response_id: Optional[str] = None
        self._current_transcript: List[str] = []
        self._pulse_device = pulse_device
        self._ws_ready = threading.Event()
        self._ws_failure = threading.Event()

    def _preflight_checks(self) -> bool:
        if not self._api_key:
            logging.error("OpenAI API key is required")
            self._controller.emit_error("OpenAI API key is required")
            return False
        try:
            import websocket  # noqa: F401
        except ImportError:
            logging.error(
                "websocket-client is not installed. Install with: pip install websocket-client"
            )
            self._controller.emit_error("websocket-client package is required")
            return False
        return True

    def _initialize_connection(self) -> bool:
        self._ws_ready.clear()
        self._ws_failure.clear()
        self._ws_thread = threading.Thread(target=self._websocket_loop, daemon=True)
        self._ws_thread.start()

        # Wait for connection to be ready or fail
        connected = self._ws_ready.wait(timeout=5)
        if not connected or self._ws_failure.is_set():
            return False
        return True

    def _cleanup_connection(self) -> None:
        if self._ws:
            try:
                self._ws.close()
            except Exception:  # pragma: no cover - defensive
                pass
            self._ws = None

        if self._ws_thread:
            self._ws_thread.join(timeout=2)
            self._ws_thread = None
        self._ws_ready.clear()
        self._ws_failure.clear()
        self._audio_buffer.clear()

    def _create_audio_recorder(self):
        return AudioRecorder(
            sample_rate=self._sample_rate,
            channels=self._channels,
            device=self._pulse_device,
        )

    def _process_audio_chunk(self, audio_data: bytes) -> None:
        if self._ws is None or not self._ws_ready.is_set():
            return

        raw_audio = self._extract_raw_audio(audio_data)
        self._audio_buffer.extend(raw_audio)

        while len(self._audio_buffer) >= self._bytes_per_commit:
            chunk = bytes(self._audio_buffer[: self._bytes_per_commit])
            del self._audio_buffer[: self._bytes_per_commit]

            audio_event = {
                "type": "input_audio_buffer.append",
                "audio": base64.b64encode(chunk).decode("utf-8"),
            }
            try:
                self._ws.send(json.dumps(audio_event))
            except Exception as exc:  # pragma: no cover - defensive
                logging.error("Failed to send audio chunk: %s", exc)
                break

    def _websocket_loop(self) -> None:
        """Main WebSocket loop for OpenAI Realtime API."""
        try:
            import websocket

            # Build WebSocket URL
            ws_url = f"wss://api.openai.com/v1/realtime?model={self._session_model}&api-version={self._api_version}"

            self._controller.transition_to("connecting")

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
            logging.exception("WebSocket loop error")
            self._controller.emit_error(f"WebSocket loop error: {exc}")
            self._failure_exit = True
            self._ws_failure.set()
            self._stop_event.set()
        finally:
            if not self._ws_ready.is_set():
                self._ws_ready.set()
            self._ws = None

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
                "create_response": False,  # Don't create AI responses, just transcribe
            }

        transcription_model = self._model or "gpt-4o-transcribe"

        input_transcription: Dict[str, str] = {"model": transcription_model}
        if self._language:
            lang = self._language.lower()
            if len(lang) > 2 and "-" in lang:
                lang = lang.split("-", 1)[0]
            if len(lang) > 2:
                lang = lang[:2]
            input_transcription["language"] = lang

        session_config = {
            "type": "session.update",
            "session": {
                "input_audio_format": "pcm16",
                "input_audio_transcription": input_transcription,
            }
        }

        if turn_detection:
            session_config["session"]["turn_detection"] = turn_detection

        # Send session configuration
        ws.send(json.dumps(session_config))

        self._controller.transition_to("ready")
        self._ws_ready.set()

    def _on_message(self, ws, message) -> None:
        """Handle WebSocket message received."""
        try:
            data = json.loads(message)
            msg_type = data.get("type", "")

            if msg_type == "conversation.item.input_audio_transcription.completed":
                # Audio transcription completed
                transcript = data.get("transcript", "").strip()
                if transcript:
                    self._controller.transition_to("transcribing")
                    self._controller.emit_transcription(transcript)
                    self._input_simulator(transcript)

            elif msg_type == "conversation.item.input_audio_transcription.delta":
                # Partial transcription
                pass

            elif msg_type == "response.created":
                response = data.get("response", {})
                self._current_response_id = response.get("id")
                self._response_active = True
                self._current_transcript.clear()

            elif msg_type in {"response.completed", "response.errored", "response.refused", "response.cancelled"}:
                response = data.get("response", {})
                response_id = response.get("id")
                if not response_id and "response" in data:
                    response_id = data["response"].get("id")
                if not response_id:
                    response_id = data.get("response_id")
                if not response_id and self._current_response_id:
                    response_id = self._current_response_id
                if self._current_transcript and response_id == self._current_response_id:
                    final_text = "".join(self._current_transcript).strip()
                    if final_text:
                        self._controller.transition_to("transcribing")
                        self._controller.emit_transcription(final_text)
                        self._input_simulator(final_text)
                self._response_active = False
                self._current_response_id = None
                self._current_transcript.clear()

            elif msg_type == "response.output_text.delta":
                delta = data.get("delta")
                if isinstance(delta, str):
                    self._current_transcript.append(delta)

            elif msg_type == "error":
                error = data.get("error", {})
                logging.error(f"OpenAI Realtime error: {error}")
                message = error.get("message") if isinstance(error, dict) else str(error)
                if message:
                    self._controller.emit_error(message)

        except Exception as exc:
            logging.exception("Error processing message")
            self._controller.emit_error(f"Error processing message: {exc}")

    def _on_error(self, ws, error) -> None:
        """Handle WebSocket error."""
        logging.error(f"WebSocket error: {error}")
        self._ws_failure.set()
        if error:
            self._controller.emit_error(str(error))

    def _on_close(self, ws, close_status_code, close_msg) -> None:
        """Handle WebSocket connection closed."""
        logging.info(f"WebSocket closed: {close_status_code} - {close_msg}")
        self._stop_event.set()
        if close_status_code not in (1000, None):
            reason = f"WebSocket closed: {close_status_code} - {close_msg}"
            self._controller.emit_error(reason)
            self._failure_exit = True

    def _extract_raw_audio(self, wav_data: bytes) -> bytes:
        """Extract raw PCM audio from WAV file (skip 44-byte header)."""
        return wav_data[44:]

class AudioRecorder:
    """Records audio chunks from the microphone using PulseAudio's parec."""

    def __init__(self, sample_rate: int = 16000, channels: int = 1, device: Optional[str] = None):
        if shutil.which("parec") is None:
            raise RuntimeError("parec is required for audio capture. Install pulseaudio-utils or ensure parec is available.")

        self._sample_rate = sample_rate
        self._channels = channels
        self._sample_width = 2  # s16le
        self._device = device
        self._parec_process: Optional[Popen] = None
        self._start_parec()

    def _start_parec(self) -> None:
        command = [
            "parec",
            "--format=s16le",
            f"--rate={self._sample_rate}",
            f"--channels={self._channels}",
        ]

        if self._device:
            command.append(f"--device={self._device}")

        try:
            self._parec_process = Popen(
                command,
                stdout=PIPE,
                stderr=subprocess.DEVNULL,
            )
        except OSError as exc:
            raise RuntimeError(f"Failed to start parec: {exc}") from exc

        if not self._parec_process.stdout:
            raise RuntimeError("parec process has no stdout stream")

    def _read_bytes(self, size: int) -> bytes:
        if not self._parec_process or self._parec_process.stdout is None:
            raise RuntimeError("parec process is not running")

        data = b""
        while len(data) < size:
            chunk = self._parec_process.stdout.read(size - len(data))
            if not chunk:
                # parec ended unexpectedly; attempt restart once
                self._restart_parec()
                continue
            data += chunk
        return data

    def _restart_parec(self) -> None:
        if self._parec_process:
            self._parec_process.kill()
            self._parec_process.wait(timeout=1)
        self._start_parec()

    def record_chunk(self, duration: float = 0.1) -> bytes:
        """Record audio for specified duration and return WAV bytes."""
        import wave

        bytes_needed = int(self._sample_rate * duration) * self._channels * self._sample_width
        min_bytes = self._sample_rate * self._channels * self._sample_width // 10
        if bytes_needed < min_bytes:
            bytes_needed = min_bytes
        raw_audio = self._read_bytes(bytes_needed)

        wav_buffer = io.BytesIO()
        with wave.open(wav_buffer, 'wb') as wav_file:
            wav_file.setnchannels(self._channels)
            wav_file.setsampwidth(self._sample_width)
            wav_file.setframerate(self._sample_rate)
            wav_file.writeframes(raw_audio)

        return wav_buffer.getvalue()

    def __del__(self):
        if hasattr(self, "_parec_process") and self._parec_process:
            self._parec_process.kill()
            try:
                self._parec_process.wait(timeout=1)
            except Exception:
                pass
