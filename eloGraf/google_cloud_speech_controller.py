# ABOUTME: Controller and runner for Google Cloud Speech-to-Text API STT engine.
# ABOUTME: Implements STT interfaces for Google Cloud Speech-to-Text V2 streaming recognition.

from __future__ import annotations

import io
import logging
import os
import threading
import time
from enum import Enum, auto
from pathlib import Path
from subprocess import run, CalledProcessError
from typing import Callable, Dict, List, Optional, Sequence

from eloGraf.stt_engine import STTController, STTProcessRunner


class GoogleCloudSpeechState(Enum):
    IDLE = auto()
    STARTING = auto()
    READY = auto()
    RECORDING = auto()
    TRANSCRIBING = auto()
    SUSPENDED = auto()
    FAILED = auto()


StateListener = Callable[[GoogleCloudSpeechState], None]
OutputListener = Callable[[str], None]
ExitListener = Callable[[int], None]


class GoogleCloudSpeechController(STTController):
    """Controller for Google Cloud Speech API that interprets states."""

    def __init__(self) -> None:
        self._state = GoogleCloudSpeechState.IDLE
        self._state_listeners: List[StateListener] = []
        self._output_listeners: List[OutputListener] = []
        self._exit_listeners: List[ExitListener] = []
        self._stop_requested = False
        self._suspended = False

    @property
    def state(self) -> GoogleCloudSpeechState:
        return self._state

    def add_state_listener(self, callback: StateListener) -> None:
        self._state_listeners.append(callback)

    def add_output_listener(self, callback: OutputListener) -> None:
        self._output_listeners.append(callback)

    def add_exit_listener(self, callback: ExitListener) -> None:
        self._exit_listeners.append(callback)

    def start(self) -> None:
        self._stop_requested = False
        self._set_state(GoogleCloudSpeechState.STARTING)

    def stop_requested(self) -> None:
        self._stop_requested = True

    def suspend_requested(self) -> None:
        self._suspended = True
        self._set_state(GoogleCloudSpeechState.SUSPENDED)

    def resume_requested(self) -> None:
        self._suspended = False
        self._set_state(GoogleCloudSpeechState.RECORDING)

    @property
    def is_suspended(self) -> bool:
        return self._suspended

    def fail_to_start(self) -> None:
        self._stop_requested = False
        self._set_state(GoogleCloudSpeechState.FAILED)
        self._emit_exit(1)

    def set_ready(self) -> None:
        self._set_state(GoogleCloudSpeechState.READY)

    def set_recording(self) -> None:
        self._set_state(GoogleCloudSpeechState.RECORDING)

    def set_transcribing(self) -> None:
        self._set_state(GoogleCloudSpeechState.TRANSCRIBING)

    def handle_output(self, line: str) -> None:
        self._emit_output(line)

    def handle_exit(self, return_code: int) -> None:
        if return_code == 0:
            self._set_state(GoogleCloudSpeechState.IDLE)
        else:
            self._set_state(GoogleCloudSpeechState.FAILED)
        self._emit_exit(return_code)
        self._stop_requested = False

    def _set_state(self, state: GoogleCloudSpeechState) -> None:
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


class GoogleCloudSpeechProcessRunner(STTProcessRunner):
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
        self._controller = controller
        self._credentials_path = credentials_path
        self._project_id = project_id
        self._language_code = language_code
        self._model = model
        self._sample_rate = sample_rate
        self._channels = channels
        self._chunk_duration = chunk_duration
        self._vad_enabled = vad_enabled
        self._vad_threshold = vad_threshold
        self._input_simulator = input_simulator or self._default_input_simulator
        self._recording_thread: Optional[threading.Thread] = None
        self._stop_recording = threading.Event()
        self._audio_recorder: Optional[AudioRecorder] = None

    def start(self, command: Sequence[str], env: Optional[Dict[str, str]] = None) -> bool:
        if self.is_running():
            logging.warning("Google Cloud Speech is already running")
            return False

        self._controller.start()

        # Verify credentials
        if not self._verify_credentials():
            self._controller.fail_to_start()
            return False

        # Verify google-cloud-speech is installed
        try:
            import google.cloud.speech_v2
        except ImportError:
            logging.error(
                "google-cloud-speech is not installed. "
                "Install with: pip install google-cloud-speech"
            )
            self._controller.fail_to_start()
            return False

        self._controller.set_ready()

        # Start streaming in background thread
        self._stop_recording.clear()
        self._recording_thread = threading.Thread(target=self._streaming_loop, daemon=True)
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
        # Google Cloud Speech uses background threads, no polling needed
        pass

    def is_running(self) -> bool:
        return self._recording_thread is not None and self._recording_thread.is_alive()

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

    def _streaming_loop(self) -> None:
        """Main streaming loop for Google Cloud Speech recognition."""
        try:
            from google.cloud.speech_v2 import SpeechClient
            from google.cloud.speech_v2.types import cloud_speech as cloud_speech_types

            client = SpeechClient()

            # Build recognizer name
            if self._project_id:
                recognizer = f"projects/{self._project_id}/locations/global/recognizers/_"
            else:
                # Try to get project from credentials
                try:
                    from google.auth import default
                    credentials, project_id = default()
                    if not project_id:
                        raise ValueError("Could not determine project ID")
                    recognizer = f"projects/{project_id}/locations/global/recognizers/_"
                    logging.info(f"Using project: {project_id}")
                except Exception as exc:
                    logging.error(f"Failed to determine project ID: {exc}")
                    self._controller.handle_exit(1)
                    return

            # Configure recognition
            recognition_config = cloud_speech_types.RecognitionConfig(
                auto_decoding_config=cloud_speech_types.AutoDetectDecodingConfig(),
                language_codes=[self._language_code],
                model=self._model,
            )

            streaming_config = cloud_speech_types.StreamingRecognitionConfig(
                config=recognition_config,
            )

            self._audio_recorder = AudioRecorder(
                sample_rate=self._sample_rate,
                channels=self._channels,
            )
            self._controller.set_recording()

            # Generator for audio chunks
            def audio_generator():
                # First request with config
                yield cloud_speech_types.StreamingRecognizeRequest(
                    recognizer=recognizer,
                    streaming_config=streaming_config,
                )

                # Then audio chunks
                while not self._stop_recording.is_set():
                    # Check if suspended
                    if self._controller.is_suspended:
                        time.sleep(0.1)
                        continue

                    # Record audio chunk (small chunk for streaming)
                    audio_data = self._audio_recorder.record_chunk(
                        duration=self._chunk_duration
                    )

                    if self._stop_recording.is_set():
                        break

                    # Check if suspended again
                    if self._controller.is_suspended:
                        continue

                    # Apply VAD if enabled
                    if self._vad_enabled:
                        audio_level = self._calculate_audio_level(audio_data)
                        if audio_level < self._vad_threshold:
                            continue

                    # Extract raw PCM audio from WAV (skip header)
                    raw_audio = self._extract_raw_audio(audio_data)

                    # Limit chunk size to 25 KB
                    max_chunk_size = 25 * 1024
                    if len(raw_audio) > max_chunk_size:
                        raw_audio = raw_audio[:max_chunk_size]

                    self._controller.set_transcribing()
                    yield cloud_speech_types.StreamingRecognizeRequest(audio=raw_audio)

            # Stream audio and get responses
            responses = client.streaming_recognize(requests=audio_generator())

            self._controller.set_recording()

            # Process responses
            for response in responses:
                if self._stop_recording.is_set():
                    break

                for result in response.results:
                    if not result.alternatives:
                        continue

                    transcript = result.alternatives[0].transcript

                    # Only output final results
                    if result.is_final and transcript.strip():
                        self._controller.handle_output(f"Transcribed: {transcript}")
                        self._input_simulator(transcript)

        except Exception as exc:
            logging.error(f"Streaming loop error: {exc}")
            self._controller.handle_exit(1)

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
