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
from subprocess import Popen, run, PIPE, CalledProcessError
from typing import Callable, Dict, List, Optional, Sequence

import requests

from eloGraf.stt_engine import STTController, STTProcessRunner


class WhisperDockerState(Enum):
    IDLE = auto()
    STARTING = auto()
    READY = auto()
    RECORDING = auto()
    TRANSCRIBING = auto()
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
        logging.warning("Suspend not supported by Whisper Docker engine")

    def resume_requested(self) -> None:
        logging.warning("Resume not supported by Whisper Docker engine")

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
        input_simulator: Optional[Callable[[str], None]] = None,
    ) -> None:
        self._controller = controller
        self._container_name = container_name
        self._api_port = api_port
        self._api_url = f"http://localhost:{api_port}/asr"
        self._model = model
        self._language = language
        self._input_simulator = input_simulator or self._default_input_simulator
        self._recording_thread: Optional[threading.Thread] = None
        self._stop_recording = threading.Event()
        self._audio_recorder: Optional[AudioRecorder] = None

    def start(self, command: Sequence[str], env: Optional[Dict[str, str]] = None) -> bool:
        if self.is_running():
            logging.warning("Whisper Docker is already running")
            return False

        self._controller.start()

        # Start Docker container if not running
        if not self._is_container_running():
            if not self._start_container():
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
        logging.warning("Suspend not supported by Whisper Docker engine")

    def resume(self) -> None:
        logging.warning("Resume not supported by Whisper Docker engine")

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

    def _start_container(self) -> bool:
        logging.info(f"Starting Whisper Docker container '{self._container_name}'...")
        try:
            # Check if container exists but is stopped
            result = run(
                ["docker", "ps", "-a", "--filter", f"name={self._container_name}", "--format", "{{.Names}}"],
                capture_output=True,
                text=True,
                check=True,
            )

            if self._container_name in result.stdout:
                # Container exists, just start it
                run(["docker", "start", self._container_name], check=True)
            else:
                # Create new container
                run([
                    "docker", "run", "-d",
                    "--name", self._container_name,
                    "-p", f"{self._api_port}:9000",
                    "-e", f"ASR_MODEL={self._model}",
                    "-e", "ASR_ENGINE=openai_whisper",
                    "onerahmet/openai-whisper-asr-webservice:latest"
                ], check=True)

            return True
        except (CalledProcessError, FileNotFoundError) as exc:
            logging.error(f"Failed to start Docker container: {exc}")
            return False

    def _wait_for_api(self, timeout: int = 30) -> bool:
        logging.info("Waiting for Whisper API to be ready...")
        start_time = time.time()

        while time.time() - start_time < timeout:
            try:
                response = requests.get(f"http://localhost:{self._api_port}/docs", timeout=2)
                if response.status_code == 200:
                    logging.info("Whisper API is ready")
                    return True
            except requests.RequestException:
                pass
            time.sleep(1)

        logging.error("Whisper API failed to start within timeout")
        return False

    def _recording_loop(self) -> None:
        try:
            self._audio_recorder = AudioRecorder()
            self._controller.set_recording()

            while not self._stop_recording.is_set():
                # Record audio chunk
                audio_data = self._audio_recorder.record_chunk(duration=5)

                if self._stop_recording.is_set():
                    break

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

    def _transcribe_audio(self, audio_data: bytes) -> str:
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

                    response = requests.post(self._api_url, files=files, params=params, timeout=30)
                    response.raise_for_status()

                    result = response.json()
                    return result.get("text", "").strip()
            finally:
                Path(tmp_path).unlink(missing_ok=True)

        except Exception as exc:
            logging.error(f"Transcription error: {exc}")
            return ""

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

    def record_chunk(self, duration: float = 5.0) -> bytes:
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
