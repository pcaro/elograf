# ABOUTME: Controller and runner for Whisper Docker container STT engine.
# ABOUTME: Implements STT interfaces for onerahmet/openai-whisper-asr-webservice.

from __future__ import annotations

import io
import logging
import tempfile
import threading
import time
from enum import Enum, auto
from pathlib import Path
from subprocess import run, CalledProcessError
from typing import Callable, Dict, List, Optional, Sequence

import requests

from eloGraf.audio_recorder import AudioRecorder
from eloGraf.input_simulator import type_text
from eloGraf.stt_engine import STTController, STTProcessRunner


class WhisperDockerState(Enum):
    IDLE = auto()
    STARTING = auto()
    READY = auto()
    RECORDING = auto()
    TRANSCRIBING = auto()
    SUSPENDED = auto()
    FAILED = auto()


StateListener = Callable[[WhisperDockerState], None]
OutputListener = Callable[[str], None]
ExitListener = Callable[[int], None]


class WhisperDockerController(STTController):
    """Controller for Whisper Docker container that interprets states."""

    def __init__(self) -> None:
        self._state = WhisperDockerState.IDLE
        self._state_listeners: List[StateListener] = []
        self._output_listeners: List[OutputListener] = []
        self._exit_listeners: List[ExitListener] = []
        self._stop_requested = False
        self._suspended = False

    @property
    def state(self) -> WhisperDockerState:
        return self._state

    def add_state_listener(self, callback: StateListener) -> None:
        self._state_listeners.append(callback)

    def add_output_listener(self, callback: OutputListener) -> None:
        self._output_listeners.append(callback)

    def add_exit_listener(self, callback: ExitListener) -> None:
        self._exit_listeners.append(callback)

    def start(self) -> None:
        self._stop_requested = False
        self._set_state(WhisperDockerState.STARTING)

    def stop_requested(self) -> None:
        self._stop_requested = True

    def suspend_requested(self) -> None:
        self._suspended = True
        self._set_state(WhisperDockerState.SUSPENDED)

    def resume_requested(self) -> None:
        self._suspended = False
        self._set_state(WhisperDockerState.RECORDING)

    @property
    def is_suspended(self) -> bool:
        return self._suspended

    def fail_to_start(self) -> None:
        self._stop_requested = False
        self._set_state(WhisperDockerState.FAILED)
        self._emit_exit(1)

    def set_ready(self) -> None:
        self._set_state(WhisperDockerState.READY)

    def set_recording(self) -> None:
        self._set_state(WhisperDockerState.RECORDING)

    def set_transcribing(self) -> None:
        self._set_state(WhisperDockerState.TRANSCRIBING)

    def handle_output(self, line: str) -> None:
        self._emit_output(line)

    def handle_exit(self, return_code: int) -> None:
        if return_code == 0:
            self._set_state(WhisperDockerState.IDLE)
        else:
            self._set_state(WhisperDockerState.FAILED)
        self._emit_exit(return_code)
        self._stop_requested = False

    def _set_state(self, state: WhisperDockerState) -> None:
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

    def transition_to(self, state: str) -> None:
        """Transition to a named state using string identifier."""
        state_lower = state.lower()
        state_map = {
            "idle": WhisperDockerState.IDLE,
            "starting": WhisperDockerState.STARTING,
            "ready": WhisperDockerState.READY,
            "recording": WhisperDockerState.RECORDING,
            "transcribing": WhisperDockerState.TRANSCRIBING,
            "suspended": WhisperDockerState.SUSPENDED,
            "failed": WhisperDockerState.FAILED,
        }

        if state_lower in state_map:
            self._set_state(state_map[state_lower])
        else:
            logging.warning(f"Unknown state '{state}' for WhisperDocker controller")

    def emit_transcription(self, text: str) -> None:
        """Emit transcribed text to output listeners."""
        self._emit_output(text)

    def emit_error(self, message: str) -> None:
        """Emit error message and transition to failed state."""
        logging.error(f"WhisperDocker error: {message}")
        self._emit_output(f"ERROR: {message}")
        self._set_state(WhisperDockerState.FAILED)


class WhisperDockerProcessRunner(STTProcessRunner):
    """Manages Whisper Docker container and audio recording/transcription."""

    def __init__(
        self,
        controller: WhisperDockerController,
        *,
        container_name: str = "elograf-whisper",
        api_port: int = 9000,
        model: str = "base",
        language: Optional[str] = None,
        chunk_duration: float = 5.0,
        sample_rate: int = 16000,
        channels: int = 1,
        vad_enabled: bool = True,
        vad_threshold: float = 500.0,
        auto_reconnect: bool = True,
        input_simulator: Optional[Callable[[str], None]] = None,
    ) -> None:
        self._controller = controller
        self._container_name = container_name
        self._api_port = api_port
        self._api_url = f"http://localhost:{api_port}/asr"
        self._model = model
        self._language = language
        self._chunk_duration = chunk_duration
        self._sample_rate = sample_rate
        self._channels = channels
        self._vad_enabled = vad_enabled
        self._vad_threshold = vad_threshold
        self._auto_reconnect = auto_reconnect
        self._input_simulator = input_simulator or type_text
        self._recording_thread: Optional[threading.Thread] = None
        self._stop_recording = threading.Event()
        self._audio_recorder: Optional[AudioRecorder] = None

    def start(self, command: Sequence[str], env: Optional[Dict[str, str]] = None) -> bool:
        if self.is_running():
            logging.warning("Whisper Docker is already running")
            return False

        self._controller.start()

        if not self._ensure_container_model():
            self._controller.fail_to_start()
            return False

        # Wait for API to be ready
        if not self._wait_for_api():
            self._controller.fail_to_start()
            return False

        self._controller.set_ready()

        # Start recording in background thread
        self._stop_recording.clear()
        self._recording_thread = threading.Thread(target=self._recording_loop, daemon=True)
        self._recording_thread.start()

        return True

    def stop(self) -> None:
        if not self.is_running():
            return

        self._controller.stop_requested()
        self._stop_recording.set()

        if self._recording_thread:
            self._recording_thread.join(timeout=2)
            self._recording_thread = None

        self._controller.handle_exit(0)

    def suspend(self) -> None:
        if self.is_running():
            self._controller.suspend_requested()

    def resume(self) -> None:
        if self.is_running():
            self._controller.resume_requested()

    def poll(self) -> None:
        # Whisper Docker uses background threads, no polling needed
        pass

    def is_running(self) -> bool:
        return self._recording_thread is not None and self._recording_thread.is_alive()

    def _is_container_running(self) -> bool:
        try:
            result = run(
                ["docker", "ps", "--filter", f"name={self._container_name}", "--format", "{{.Names}}"],
                capture_output=True,
                text=True,
                check=True,
            )
            return self._container_name in result.stdout
        except (CalledProcessError, FileNotFoundError):
            return False

    def _get_container_model(self) -> Optional[str]:
        """Get the model that the container is currently configured with."""
        try:
            result = run(
                ["docker", "inspect", "--format", "{{range .Config.Env}}{{println .}}{{end}}", self._container_name],
                capture_output=True,
                text=True,
                check=True,
            )
            for line in result.stdout.splitlines():
                if line.startswith("ASR_MODEL="):
                    return line.split("=", 1)[1]
            return None
        except (CalledProcessError, FileNotFoundError):
            return None

    def _ensure_container_model(self) -> bool:
        """Ensure docker container exists and matches requested model."""
        try:
            if self._is_container_running():
                current_model = self._get_container_model()
                if current_model == self._model:
                    logging.info(
                        "Whisper container already running with model '%s'",
                        self._model,
                    )
                    return True

                logging.info(
                    "Whisper container running with model '%s', recreating for '%s'",
                    current_model,
                    self._model,
                )
                run(["docker", "stop", self._container_name], check=False, capture_output=True)
                run(["docker", "rm", self._container_name], check=True)

            else:
                result = run(
                    ["docker", "ps", "-a", "--filter", f"name={self._container_name}", "--format", "{{.Names}}"],
                    capture_output=True,
                    text=True,
                    check=True,
                )
                if self._container_name in result.stdout:
                    current_model = self._get_container_model()
                    if current_model != self._model:
                        logging.info(
                            "Whisper container exists with model '%s', removing to use '%s'",
                            current_model,
                            self._model,
                        )
                        run(["docker", "rm", self._container_name], check=True)
                    else:
                        logging.info(
                            "Starting existing Whisper container with model '%s'",
                            self._model,
                        )
                        run(["docker", "start", self._container_name], check=True)
                        return True
        except (CalledProcessError, FileNotFoundError) as exc:
            logging.error(f"Failed to manage Docker container: {exc}")
            return False

        logging.info(f"Starting Whisper Docker container '{self._container_name}' with model '{self._model}'...")
        try:
            run([
                "docker", "run", "-d",
                "--name", self._container_name,
                "-p", f"{self._api_port}:9000",
                "-e", f"ASR_MODEL={self._model}",
                "-e", "ASR_ENGINE=openai_whisper",
                "onerahmet/openai-whisper-asr-webservice:latest",
            ], check=True)
            return True
        except (CalledProcessError, FileNotFoundError) as exc:
            logging.error(f"Failed to start Docker container: {exc}")
            return False

    def _wait_for_api(self, timeout: int = 180) -> bool:
        logging.info("Waiting for Whisper API to be ready...")
        start_time = time.time()

        while time.time() - start_time < timeout:
            try:
                response = requests.get(f"http://localhost:{self._api_port}/docs", timeout=2)
                if response.status_code == 200:
                    logging.info("Whisper API web UI reachable, verifying health endpoint...")
                    try:
                        health = requests.get(
                            f"http://localhost:{self._api_port}/health",
                            timeout=5,
                        )
                        if health.status_code == 200:
                            logging.info("Whisper API is ready")
                            return True
                        elif health.status_code in (404, 405, 501):
                            return True
                            logging.debug("Health endpoint not ready yet: %s", health.status_code)
                    except requests.RequestException as exc:
                        logging.debug("Health endpoint check failed (%s), assuming not ready yet", exc)
            except requests.RequestException:
                pass
            time.sleep(1)

        logging.error("Whisper API failed to start within timeout")
        return False

    def _recording_loop(self) -> None:
        try:
            self._audio_recorder = AudioRecorder(
                sample_rate=self._sample_rate,
                channels=self._channels,
                backend="pyaudio"
            )
            self._controller.set_recording()

            while not self._stop_recording.is_set():
                # Check if suspended
                if self._controller.is_suspended:
                    time.sleep(0.1)
                    continue

                # Record audio chunk
                audio_data = self._audio_recorder.record_chunk(duration=self._chunk_duration)

                if self._stop_recording.is_set():
                    break

                # Check if suspended again (might have changed during recording)
                if self._controller.is_suspended:
                    continue

                # Apply VAD if enabled
                if self._vad_enabled:
                    audio_level = self._calculate_audio_level(audio_data)
                    if audio_level < self._vad_threshold:
                        # Silent audio, skip transcription
                        continue

                # Transcribe chunk
                self._controller.set_transcribing()
                text = self._transcribe_audio(audio_data)

                if text:
                    self._controller.handle_output(f"Transcribed: {text}")
                    self._input_simulator(text)

                self._controller.set_recording()

        except Exception as exc:
            logging.error(f"Recording loop error: {exc}")
            self._controller.handle_exit(1)

    def _calculate_audio_level(self, audio_data: bytes) -> float:
        """Calculate RMS audio level from WAV data."""
        import wave
        import struct

        try:
            # Parse WAV data
            wav_buffer = io.BytesIO(audio_data)
            with wave.open(wav_buffer, 'rb') as wav_file:
                frames = wav_file.readframes(wav_file.getnframes())

            # Calculate RMS
            sample_width = 2  # 16-bit audio
            samples = struct.unpack(f'<{len(frames) // sample_width}h', frames)
            rms = (sum(s ** 2 for s in samples) / len(samples)) ** 0.5
            return rms
        except Exception as exc:
            logging.warning(f"Error calculating audio level: {exc}")
            return float('inf')  # Return high value to pass VAD on error

    def _transcribe_audio(self, audio_data: bytes) -> str:
        max_retries = 3 if self._auto_reconnect else 1

        for attempt in range(max_retries):
            try:
                # Save audio to temporary file
                with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp_file:
                    tmp_file.write(audio_data)
                    tmp_path = tmp_file.name

                try:
                    # Send to Whisper API
                    with open(tmp_path, "rb") as audio_file:
                        files = {"audio_file": audio_file}
                        params = {"output": "json"}
                        if self._language:
                            params["language"] = self._language

                        logging.debug(
                            "Sending audio chunk (%.2fs) to Whisper API (attempt %d/%d)",
                            len(audio_data) / (self._sample_rate * self._channels * 2),
                            attempt + 1,
                            max_retries,
                        )
                        response = requests.post(self._api_url, files=files, params=params, timeout=120)
                        response.raise_for_status()

                        result = response.json()
                        return result.get("text", "").strip()
                finally:
                    Path(tmp_path).unlink(missing_ok=True)

            except requests.RequestException as exc:
                if attempt < max_retries - 1:
                    logging.warning(
                        "Transcription attempt %d failed: %s. Response: %s. Retrying...",
                        attempt + 1,
                        exc,
                        getattr(exc.response, "text", "<no response>"),
                    )
                    time.sleep(1)

                    # Try to restart container if it's not running
                    if not self._is_container_running():
                        logging.info("Container not running, attempting restart...")
                        if self._start_container() and self._wait_for_api():
                            continue
                else:
                    logging.error(f"Transcription failed after {max_retries} attempts: {exc}")
            except Exception as exc:
                logging.error(f"Transcription error: {exc}")
                break

        return ""

