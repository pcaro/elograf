from __future__ import annotations

import base64
import json
import logging
import threading
import time
from enum import Enum, auto
from typing import Callable, Dict, List, Optional
from subprocess import Popen, PIPE
import shutil

import requests
import websocket

from eloGraf.stt_engine import STTController, STTProcessRunner


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


class AssemblyAIRealtimeController(STTController):
    """Controller handling AssemblyAI realtime state transitions."""

    def __init__(self) -> None:
        self._state = AssemblyAIRealtimeState.IDLE
        self._state_listeners: List[StateListener] = []
        self._output_listeners: List[OutputListener] = []
        self._exit_listeners: List[ExitListener] = []
        self._stop_requested = False
        self._suspended = False

    @property
    def state(self) -> AssemblyAIRealtimeState:
        return self._state

    def add_state_listener(self, callback: StateListener) -> None:
        self._state_listeners.append(callback)

    def add_output_listener(self, callback: OutputListener) -> None:
        self._output_listeners.append(callback)

    def add_exit_listener(self, callback: ExitListener) -> None:
        self._exit_listeners.append(callback)

    def start(self) -> None:
        self._stop_requested = False
        self._set_state(AssemblyAIRealtimeState.STARTING)

    def stop_requested(self) -> None:
        self._stop_requested = True

    def suspend_requested(self) -> None:
        self._suspended = True
        self._set_state(AssemblyAIRealtimeState.SUSPENDED)

    def resume_requested(self) -> None:
        self._suspended = False
        self._set_state(AssemblyAIRealtimeState.RECORDING)

    @property
    def is_suspended(self) -> bool:
        return self._suspended

    def fail_to_start(self) -> None:
        self._stop_requested = False
        self._set_state(AssemblyAIRealtimeState.FAILED)
        self._emit_exit(1)

    def set_connecting(self) -> None:
        self._set_state(AssemblyAIRealtimeState.CONNECTING)

    def set_ready(self) -> None:
        self._set_state(AssemblyAIRealtimeState.READY)

    def set_recording(self) -> None:
        self._set_state(AssemblyAIRealtimeState.RECORDING)

    def set_transcribing(self) -> None:
        self._set_state(AssemblyAIRealtimeState.TRANSCRIBING)

    def handle_output(self, line: str) -> None:
        self._emit_output(line)

    def handle_exit(self, return_code: int) -> None:
        if return_code == 0:
            self._set_state(AssemblyAIRealtimeState.IDLE)
        else:
            self._set_state(AssemblyAIRealtimeState.FAILED)
        self._emit_exit(return_code)
        self._stop_requested = False

    def _set_state(self, state: AssemblyAIRealtimeState) -> None:
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


class AssemblyAIRealtimeProcessRunner(STTProcessRunner):
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
        self._controller = controller
        self._api_key = api_key
        self._model = model
        self._language = language
        self._sample_rate = sample_rate
        self._channels = channels
        self._chunk_duration = chunk_duration
        self._input_simulator = input_simulator or self._default_input_simulator
        self._pulse_device = pulse_device
        self._ws_thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._ws = None
        self._audio_recorder: Optional[AudioRecorder] = None
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

    def start(self, command, env: Optional[Dict[str, str]] = None) -> bool:  # command unused
        if self.is_running():
            logging.warning("AssemblyAI realtime is already running")
            return False

        self._controller.start()

        if not self._api_key:
            logging.error("AssemblyAI API key is required")
            self._controller.fail_to_start()
            return False

        try:
            import websocket
        except ImportError:
            logging.error("websocket-client is required for AssemblyAI realtime")
            self._controller.fail_to_start()
            return False

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
                self._controller.fail_to_start()
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

        self._stop_event.clear()
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
            self._ws = None

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
        # WebSocket runs in background thread
        pass

    def is_running(self) -> bool:
        return self._ws_thread is not None and self._ws_thread.is_alive()

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
        self._controller.set_connecting()

        # Start audio loop
        audio_thread = threading.Thread(target=self._audio_loop, daemon=True)
        audio_thread.start()
        self._controller.set_ready()

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
                self._controller.handle_output(text)
                self._input_simulator(text)
        elif message_type in ("SessionBegins", "Begin"):
            self._session_active = True
            self._controller.set_recording()
        elif message_type in ("SessionTerminated", "Termination"):
            self._session_active = False
        elif message_type in ("Error", "error"):
            logging.error("AssemblyAI realtime error: %s", data)
        else:
            logging.debug("AssemblyAI message: %s", data)

    def _on_error(self, ws, error) -> None:
        logging.error("AssemblyAI WebSocket error: %s", error)

    def _on_close(self, ws, close_status_code, close_msg) -> None:
        logging.info("AssemblyAI WebSocket closed: %s - %s", close_status_code, close_msg)
        if not self._stop_event.is_set():
            self._controller.handle_exit(1)

    def _audio_loop(self) -> None:
        try:
            self._audio_recorder = AudioRecorder(
                sample_rate=self._sample_rate,
                channels=self._channels,
                device=self._pulse_device,
            )
            self._controller.set_recording()
            logging.info("AssemblyAI audio capture started")

            while not self._stop_event.is_set():
                if self._controller.is_suspended:
                    time.sleep(0.1)
                    continue

                audio_data = self._audio_recorder.record_chunk(duration=self._chunk_duration)
                if not audio_data:
                    continue

                raw_audio = self._extract_raw_audio(audio_data)
                self._audio_buffer.extend(raw_audio)

                if len(self._audio_buffer) >= self._bytes_per_commit and self._ws:
                    chunk = bytes(self._audio_buffer[: self._bytes_per_commit])
                    del self._audio_buffer[: self._bytes_per_commit]
                    try:
                        if self._use_direct_auth:
                            self._ws.send(chunk, opcode=websocket.ABNF.OPCODE_BINARY)
                        else:
                            audio_payload = base64.b64encode(chunk).decode("utf-8")
                            self._ws.send(json.dumps({"audio_data": audio_payload}))
                        self._controller.set_transcribing()
                    except Exception as exc:
                        logging.error("Failed to send audio chunk to AssemblyAI: %s", exc)
                        break

            # flush remaining audio
            if self._audio_buffer and self._ws:
                try:
                    chunk = bytes(self._audio_buffer)
                    if self._use_direct_auth:
                        self._ws.send(chunk, opcode=websocket.ABNF.OPCODE_BINARY)
                    else:
                        audio_payload = base64.b64encode(chunk).decode("utf-8")
                        self._ws.send(json.dumps({"audio_data": audio_payload}))
                except Exception:
                    pass
        except Exception as exc:
            logging.error("AssemblyAI audio loop error: %s", exc)
            self._controller.handle_exit(1)
        finally:
            try:
                if self._ws and self._session_active:
                    if self._use_direct_auth:
                        self._ws.send(json.dumps({"type": "Terminate"}))
                    else:
                        self._ws.send(json.dumps({"terminate_session": True}))
            except Exception:
                pass

    def _extract_raw_audio(self, wav_data: bytes) -> bytes:
        return wav_data[44:]

    @staticmethod
    def _default_input_simulator(text: str) -> None:
        from subprocess import run, CalledProcessError

        try:
            run(["dotool", "type", text], check=True)
        except (CalledProcessError, FileNotFoundError):
            try:
                run(["xdotool", "type", "--", text], check=True)
            except (CalledProcessError, FileNotFoundError):
                logging.warning("Neither dotool nor xdotool available for input simulation")


class AudioRecorder:
    """Capture audio from PulseAudio using parec."""

    def __init__(self, sample_rate: int = 16000, channels: int = 1, device: Optional[str] = None):
        if shutil.which("parec") is None:
            raise RuntimeError("parec is required for AssemblyAI realtime. Install pulseaudio-utils.")
        self._sample_rate = sample_rate
        self._channels = channels
        self._sample_width = 2
        self._device = device
        self._parec: Optional[Popen] = None
        self._start_parec()

    def _build_command(self) -> List[str]:
        command = [
            "parec",
            "--format=s16le",
            f"--rate={self._sample_rate}",
            f"--channels={self._channels}",
        ]
        if self._device and self._device != "default":
            command.append(f"--device={self._device}")
        return command

    def _start_parec(self) -> None:
        command = self._build_command()
        try:
            self._parec = Popen(command, stdout=PIPE, stderr=PIPE)
        except OSError as exc:
            raise RuntimeError(f"Failed to start parec: {exc}") from exc
        if not self._parec.stdout:
            raise RuntimeError("parec process has no stdout")

    def _read_bytes(self, size: int) -> bytes:
        if not self._parec or not self._parec.stdout:
            raise RuntimeError("parec process not running")
        data = b""
        while len(data) < size:
            chunk = self._parec.stdout.read(size - len(data))
            if not chunk:
                self._restart_parec()
                continue
            data += chunk
        return data

    def _restart_parec(self) -> None:
        if self._parec:
            try:
                self._parec.kill()
            except Exception:
                pass
            self._parec.wait(timeout=1)
        self._start_parec()

    def record_chunk(self, duration: float) -> bytes:
        bytes_needed = int(self._sample_rate * duration) * self._channels * self._sample_width
        min_bytes = self._sample_rate * self._channels * self._sample_width // 10
        if bytes_needed < min_bytes:
            bytes_needed = min_bytes
        raw_audio = self._read_bytes(bytes_needed)
        import wave
        import io

        wav_buffer = io.BytesIO()
        with wave.open(wav_buffer, 'wb') as wav_file:
            wav_file.setnchannels(self._channels)
            wav_file.setsampwidth(self._sample_width)
            wav_file.setframerate(self._sample_rate)
            wav_file.writeframes(raw_audio)
        return wav_buffer.getvalue()

    def __del__(self):
        if hasattr(self, "_parec") and self._parec:
            try:
                self._parec.kill()
            except Exception:
                pass
            try:
                self._parec.wait(timeout=1)
            except Exception:
                pass
