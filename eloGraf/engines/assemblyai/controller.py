from __future__ import annotations

import base64
import json
import logging
import threading
import time
from enum import Enum, auto
from typing import Callable, Dict, List, Optional

import requests
import websocket

from eloGraf.base_controller import StreamingControllerBase
from eloGraf.status import DictationStatus
from eloGraf.input_simulator import type_text
from eloGraf.streaming_runner_base import StreamingRunnerBase
from .settings import AssemblyAISettings


class AssemblyAIRealtimeState(Enum):
    IDLE = auto()
    STARTING = auto()
    CONNECTING = auto()
    READY = auto()
    RECORDING = auto()
    TRANSCRIBING = auto()
    SUSPENDED = auto()
    FAILED = auto()


StateListener = Callable[[AssemblyAIRealtimeState], None]
OutputListener = Callable[[str], None]
ExitListener = Callable[[int], None]


STATE_MAP = {
    "idle": AssemblyAIRealtimeState.IDLE,
    "starting": AssemblyAIRealtimeState.STARTING,
    "connecting": AssemblyAIRealtimeState.CONNECTING,
    "ready": AssemblyAIRealtimeState.READY,
    "recording": AssemblyAIRealtimeState.RECORDING,
    "transcribing": AssemblyAIRealtimeState.TRANSCRIBING,
    "suspended": AssemblyAIRealtimeState.SUSPENDED,
    "failed": AssemblyAIRealtimeState.FAILED,
}


class AssemblyAIRealtimeController(StreamingControllerBase[AssemblyAIRealtimeState]):
    """Controller handling AssemblyAI realtime state transitions."""

    def __init__(self, settings: AssemblyAISettings) -> None:
        super().__init__(
            initial_state=AssemblyAIRealtimeState.IDLE,
            state_map=STATE_MAP,
            engine_name="AssemblyAIRealtime",
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

    def get_status_string(self) -> str:
        model_name = self._settings.model
        return f"AssemblyAI | Model: {model_name}"

    @property
    def dictation_status(self) -> DictationStatus:
        if self.state in (AssemblyAIRealtimeState.STARTING, AssemblyAIRealtimeState.CONNECTING):
            return DictationStatus.INITIALIZING
        elif self.state in (AssemblyAIRealtimeState.READY, AssemblyAIRealtimeState.RECORDING, AssemblyAIRealtimeState.TRANSCRIBING):
            return DictationStatus.LISTENING
        elif self.state == AssemblyAIRealtimeState.SUSPENDED:
            return DictationStatus.SUSPENDED
        elif self.state == AssemblyAIRealtimeState.FAILED:
            return DictationStatus.FAILED
        else:
            return DictationStatus.IDLE


class AssemblyAIRealtimeProcessRunner(StreamingRunnerBase):
    """Manages AssemblyAI realtime websocket session."""

    def __init__(
        self,
        controller: AssemblyAIRealtimeController,
        *,
        api_key: str,
        model: str = "default",
        language: Optional[str] = None,
        sample_rate: int = 16000,
        channels: int = 1,
        chunk_duration: float = 0.2,
        input_simulator: Optional[Callable[[str], None]] = None,
        pulse_device: Optional[str] = None,
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
        self._language = language
        self._input_simulator = input_simulator or type_text
        self._ws_thread: Optional[threading.Thread] = None
        self._ws = None
        self._audio_buffer = bytearray()
        self._sample_width_bytes = 2
        self._bytes_per_commit = max(
            int(self._sample_rate * self._chunk_duration) * self._channels * self._sample_width_bytes,
            self._sample_rate * self._channels * self._sample_width_bytes // 5,
        )
        self._token_ttl = 3600
        self._session_active = False
        self.fatal_error = False
        self._use_direct_auth = False
        self._ws_ready = threading.Event()
        self._ws_failure = threading.Event()

    def _preflight_checks(self) -> bool:
        if not self._api_key:
            logging.error("AssemblyAI API key is required")
            self._controller.emit_error("AssemblyAI API key is required")
            return False
        try:
            import websocket  # noqa: F401
        except ImportError:
            logging.error("websocket-client is required for AssemblyAI realtime")
            self._controller.emit_error("websocket-client package is required")
            return False
        return True

    def _initialize_connection(self) -> bool:
        import websocket

        token = self._generate_token()
        headers = None

        if self._use_direct_auth:
            logging.info("Using direct API key authentication for AssemblyAI realtime")
            query = [
                f"sample_rate={self._sample_rate}",
                "format_turns=true",
            ]
            if self._model and self._model != "default":
                query.append(f"model={self._model}")
            if self._language:
                query.append(f"language_code={self._language}")
            ws_url = "wss://streaming.assemblyai.com/v3/ws?" + "&".join(query)
            headers = {"Authorization": self._api_key}
        else:
            if not token:
                logging.error("AssemblyAI realtime token request failed")
                self._controller.emit_error("AssemblyAI realtime token request failed")
                return False
            query = [
                f"sample_rate={self._sample_rate}",
                f"token={token}",
            ]
            if self._model and self._model != "default":
                query.append(f"model={self._model}")
            if self._language:
                query.append(f"language_code={self._language}")
            ws_url = "wss://api.assemblyai.com/v2/realtime/ws?" + "&".join(query)

        self._ws_ready.clear()
        self._ws_failure.clear()
        self._ws = websocket.WebSocketApp(
            ws_url,
            header=headers,
            on_open=self._on_open,
            on_message=self._on_message,
            on_error=self._on_error,
            on_close=self._on_close,
        )

        self._ws_thread = threading.Thread(target=self._ws.run_forever, daemon=True)
        self._ws_thread.start()

        connected = self._ws_ready.wait(timeout=5)
        if not connected or self._ws_failure.is_set():
            return False
        return True

    def _cleanup_connection(self) -> None:
        if self._ws and self._audio_buffer:
            try:
                chunk = bytes(self._audio_buffer)
                if self._use_direct_auth:
                    import websocket

                    self._ws.send(chunk, opcode=websocket.ABNF.OPCODE_BINARY)
                else:
                    audio_payload = base64.b64encode(chunk).decode("utf-8")
                    self._ws.send(json.dumps({"audio_data": audio_payload}))
            except Exception:  # pragma: no cover
                pass

        if self._ws and self._session_active:
            try:
                if self._use_direct_auth:
                    self._ws.send(json.dumps({"type": "Terminate"}))
                else:
                    self._ws.send(json.dumps({"terminate_session": True}))
            except Exception:  # pragma: no cover - defensive
                pass

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
        self._session_active = False

    def _process_audio_chunk(self, audio_data: bytes) -> None:
        if not self._ws:
            return

        raw_audio = self._extract_raw_audio(audio_data)
        self._audio_buffer.extend(raw_audio)

        while len(self._audio_buffer) >= self._bytes_per_commit:
            chunk = bytes(self._audio_buffer[: self._bytes_per_commit])
            del self._audio_buffer[: self._bytes_per_commit]

            try:
                if self._use_direct_auth:
                    import websocket

                    self._ws.send(chunk, opcode=websocket.ABNF.OPCODE_BINARY)
                else:
                    audio_payload = base64.b64encode(chunk).decode("utf-8")
                    self._ws.send(json.dumps({"audio_data": audio_payload}))
                self._controller.set_transcribing()
            except Exception as exc:  # pragma: no cover - defensive
                logging.error("Failed to send audio chunk to AssemblyAI: %s", exc)
                break
        self._controller.set_recording()

    def _generate_token(self) -> Optional[str]:
        try:
            response = requests.post(
                "https://api.assemblyai.com/v2/realtime/token",
                headers={"Authorization": self._api_key},
                json={"expires_in": self._token_ttl},
                timeout=10,
            )
        except requests.RequestException as exc:
            logging.error("Failed to reach AssemblyAI realtime token endpoint: %s", exc)
            self._controller.emit_error(f"Failed to reach AssemblyAI realtime token endpoint: {exc}")
            self.fatal_error = True
            return None

        status = response.status_code
        if status == 401:
            logging.warning(
                "AssemblyAI realtime token endpoint returned 401; using direct API key authentication"
            )
            self._use_direct_auth = True
            return None

        if status >= 400:
            try:
                data = response.json()
            except Exception:
                data = {}
            error_message = data.get("error") or data.get("message") or response.text
            if error_message and "Model deprecated" in error_message:
                logging.warning(
                    "AssemblyAI token endpoint reports deprecated model; using direct API key authentication"
                )
                self._use_direct_auth = True
                return None
            logging.error(
                "Failed to obtain AssemblyAI realtime token (%s): %s",
                status,
                error_message,
            )
            self._controller.emit_error(
                f"Failed to obtain AssemblyAI realtime token ({status}): {error_message}"
            )
            self.fatal_error = True
            return None

        try:
            data = response.json()
        except ValueError:
            logging.warning("AssemblyAI token response not JSON; falling back to direct auth")
            self._use_direct_auth = True
            return None

        token = data.get("token")
        if not token:
            logging.warning("AssemblyAI token response missing 'token'; falling back to direct auth")
            self._use_direct_auth = True
            return None
        return token

    def _on_open(self, ws) -> None:
        logging.info("AssemblyAI Realtime WebSocket connected")
        self._controller.transition_to("connecting")
        self._ws_ready.set()
        self._controller.transition_to("ready")

    def _on_message(self, ws, message: str) -> None:
        try:
            data = json.loads(message)
        except json.JSONDecodeError:
            logging.debug("Non-JSON message from AssemblyAI: %s", message)
            return

        message_type = data.get("message_type") or data.get("type")

        if message_type in ("PartialTranscript", "Partial"):
            text = data.get("text") or data.get("transcript") or ""
            text = text.strip()
            if text:
                logging.debug("AssemblyAI partial: %s", text)
        elif message_type in ("FinalTranscript", "Final", "Turn"):
            text = data.get("text") or data.get("transcript") or ""
            text = text.strip()
            is_final = data.get("turn_is_final") or data.get("turn_is_formatted")
            if text and (message_type != "Turn" or is_final):
                self._controller.transition_to("transcribing")
                self._controller.emit_transcription(text)
                self._input_simulator(text)
        elif message_type in ("SessionBegins", "Begin"):
            self._session_active = True
            self._controller.transition_to("recording")
        elif message_type in ("SessionTerminated", "Termination"):
            self._session_active = False
        elif message_type in ("Error", "error"):
            logging.error("AssemblyAI realtime error: %s", data)
            message = None
            if isinstance(data, dict):
                message = data.get("error") or data.get("message")
            if not message:
                message = str(data)
            self._controller.emit_error(message)
        else:
            logging.debug("AssemblyAI message: %s", data)

    def _on_error(self, ws, error) -> None:
        logging.error("AssemblyAI WebSocket error: %s", error)
        self._ws_failure.set()
        if error:
            self._controller.emit_error(str(error))
        self._failure_exit = True

    def _on_close(self, ws, close_status_code, close_msg) -> None:
        logging.info("AssemblyAI WebSocket closed: %s - %s", close_status_code, close_msg)
        self._stop_event.set()
        if close_status_code not in (1000, None):
            reason = f"AssemblyAI WebSocket closed: {close_status_code} - {close_msg}"
            self._controller.emit_error(reason)
            self._failure_exit = True

    def _extract_raw_audio(self, wav_data: bytes) -> bytes:
        return wav_data[44:]
