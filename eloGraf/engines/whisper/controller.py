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
from typing import Callable, Dict, List, Optional

import requests

from eloGraf.base_controller import StreamingControllerBase
from eloGraf.input_simulator import type_text
from eloGraf.streaming_runner_base import StreamingRunnerBase
from .settings import WhisperSettings


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


STATE_MAP = {
    "idle": WhisperDockerState.IDLE,
    "starting": WhisperDockerState.STARTING,
    "ready": WhisperDockerState.READY,
    "recording": WhisperDockerState.RECORDING,
    "transcribing": WhisperDockerState.TRANSCRIBING,
    "suspended": WhisperDockerState.SUSPENDED,
    "failed": WhisperDockerState.FAILED,
}


class WhisperDockerController(StreamingControllerBase[WhisperDockerState]):
    """Controller for Whisper Docker container that interprets states."""

    def __init__(self, settings: WhisperSettings) -> None:
        super().__init__(
            initial_state=WhisperDockerState.IDLE,
            state_map=STATE_MAP,
            engine_name="WhisperDocker",
        )
        self._settings = settings
        self._stop_requested = False

    def start(self) -> None:
        self._stop_requested = False
        self._set_state(WhisperDockerState.STARTING)

    def stop_requested(self) -> None:
        self._stop_requested = True

    def fail_to_start(self) -> None:
        self._stop_requested = False
        super().fail_to_start()

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

    def get_status_string(self) -> str:
        model_name = self._settings.model
        language = self._settings.language or "Auto-detect"
        return f"Whisper Docker | Model: {model_name} | Lang: {language}"


class WhisperDockerProcessRunner(StreamingRunnerBase):
    """Manages Whisper Docker container and audio streaming."""

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
        super().__init__(
            controller,
            sample_rate=sample_rate,
            channels=channels,
            chunk_duration=chunk_duration,
            input_simulator=input_simulator or type_text,
        )
        self._controller = controller
        self._container_name = container_name
        self._api_port = api_port
        self._api_url = f"http://localhost:{api_port}/asr"
        self._model = model
        self._language = language
        self._vad_enabled = vad_enabled
        self._vad_threshold = vad_threshold
        self._auto_reconnect = auto_reconnect
        self._input_simulator = input_simulator or type_text

    def _preflight_checks(self) -> bool:
        if not self._ensure_container_model():
            self._controller.emit_error(
                "Failed to prepare Whisper Docker container. Ensure Docker is installed and the user has permission to run it."
            )
            return False

        if not self._wait_for_api():
            self._controller.emit_error(
                "Whisper Docker API did not start in time. Verify the container can reach port 9000 and try again."
            )
            return False

        return True

    def _initialize_connection(self) -> bool:
        self._controller.set_ready()
        return True

    def _process_audio_chunk(self, audio_data: bytes) -> None:
        if self._vad_enabled:
            audio_level = self._calculate_audio_level(audio_data)
            if audio_level < self._vad_threshold:
                return

        self._controller.set_transcribing()
        transcription = self._transcribe_audio(audio_data)
        if transcription:
            self._controller.handle_output(f"Transcribed: {transcription}")
            self._input_simulator(transcription)
        self._controller.set_recording()

    def _cleanup_connection(self) -> None:
        # Container remains available for subsequent runs.
        pass

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
            logging.error("Failed to manage Docker container: %s", exc)
            self._controller.emit_error(
                "Docker is required for Whisper Docker engine. Install Docker and ensure it is accessible."
            )
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
            logging.error("Failed to start Docker container: %s", exc)
            self._controller.emit_error(
                "Could not start Whisper Docker container. Check Docker permissions and that the image is available."
            )
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
