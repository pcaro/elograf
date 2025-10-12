# ABOUTME: Unified audio recording with pluggable backends (PyAudio and parec).
# ABOUTME: Provides consistent interface for capturing microphone audio as WAV data.

from __future__ import annotations

import io
import logging
import shutil
import sys
from abc import ABC, abstractmethod
from subprocess import PIPE, Popen
from typing import List, Optional

import wave


class AudioBackend(ABC):
    """Abstract backend for audio capture."""

    @abstractmethod
    def read_chunk(self, duration: float) -> bytes:
        """
        Read audio chunk as WAV bytes.

        Args:
            duration: Duration in seconds to record

        Returns:
            WAV-formatted audio data
        """
        pass

    @abstractmethod
    def close(self) -> None:
        """Release audio resources."""
        pass


class PyAudioBackend(AudioBackend):
    """Cross-platform audio capture via PyAudio."""

    def __init__(self, sample_rate: int = 16000, channels: int = 1):
        """
        Initialize PyAudio backend.

        Args:
            sample_rate: Sample rate in Hz (default: 16000)
            channels: Number of audio channels (default: 1)

        Raises:
            RuntimeError: If pyaudio is not installed
        """
        try:
            import pyaudio
        except ImportError:
            raise RuntimeError(
                "pyaudio is required for audio recording. Install with: pip install pyaudio"
            )

        self._sample_rate = sample_rate
        self._channels = channels
        self._pyaudio = pyaudio.PyAudio()
        self._format = pyaudio.paInt16
        self._sample_width = 2  # 16-bit = 2 bytes

    def read_chunk(self, duration: float) -> bytes:
        """Record audio for specified duration and return WAV bytes."""
        # Open stream for this chunk
        stream = self._pyaudio.open(
            format=self._format,
            channels=self._channels,
            rate=self._sample_rate,
            input=True,
            frames_per_buffer=1024,
        )

        # Calculate number of chunks to read
        frames = []
        chunk_count = int(self._sample_rate / 1024 * duration)

        for _ in range(chunk_count):
            data = stream.read(1024)
            frames.append(data)

        stream.stop_stream()
        stream.close()

        # Create WAV file in memory
        return self._create_wav(b"".join(frames))

    def _create_wav(self, raw_audio: bytes) -> bytes:
        """Wrap raw PCM audio in WAV container."""
        wav_buffer = io.BytesIO()
        with wave.open(wav_buffer, "wb") as wav_file:
            wav_file.setnchannels(self._channels)
            wav_file.setsampwidth(self._sample_width)
            wav_file.setframerate(self._sample_rate)
            wav_file.writeframes(raw_audio)
        return wav_buffer.getvalue()

    def close(self) -> None:
        """Terminate PyAudio."""
        if hasattr(self, "_pyaudio"):
            self._pyaudio.terminate()

    def __del__(self):
        self.close()


class ParecBackend(AudioBackend):
    """Linux PulseAudio audio capture via parec subprocess."""

    def __init__(
        self, sample_rate: int = 16000, channels: int = 1, device: Optional[str] = None
    ):
        """
        Initialize parec backend.

        Args:
            sample_rate: Sample rate in Hz (default: 16000)
            channels: Number of audio channels (default: 1)
            device: PulseAudio device name (default: None for default device)

        Raises:
            RuntimeError: If parec is not available
        """
        if shutil.which("parec") is None:
            raise RuntimeError(
                "parec is required for PulseAudio recording. Install pulseaudio-utils."
            )

        self._sample_rate = sample_rate
        self._channels = channels
        self._sample_width = 2  # 16-bit = 2 bytes
        self._device = device
        self._parec: Optional[Popen] = None
        self._start_parec()

    def _build_command(self) -> List[str]:
        """Build parec command with configured parameters."""
        command = [
            "parec",
            "--format=s16le",  # 16-bit little-endian PCM
            f"--rate={self._sample_rate}",
            f"--channels={self._channels}",
        ]
        if self._device and self._device != "default":
            command.append(f"--device={self._device}")
        return command

    def _start_parec(self) -> None:
        """Start parec subprocess."""
        command = self._build_command()
        try:
            self._parec = Popen(command, stdout=PIPE, stderr=PIPE)
        except OSError as exc:
            raise RuntimeError(f"Failed to start parec: {exc}") from exc

        if not self._parec.stdout:
            raise RuntimeError("parec process has no stdout")

        logging.debug(f"Started parec: {' '.join(command)}")

    def _read_bytes(self, size: int) -> bytes:
        """
        Read exact number of bytes from parec stdout.

        Args:
            size: Number of bytes to read

        Returns:
            Raw PCM audio data
        """
        if not self._parec or not self._parec.stdout:
            raise RuntimeError("parec process not running")

        data = b""
        while len(data) < size:
            chunk = self._parec.stdout.read(size - len(data))
            if not chunk:
                # parec died, try to restart
                logging.warning("parec process ended unexpectedly, restarting")
                self._restart_parec()
                continue
            data += chunk
        return data

    def _restart_parec(self) -> None:
        """Kill and restart parec subprocess."""
        if self._parec:
            try:
                self._parec.kill()
                self._parec.wait(timeout=1)
            except Exception:
                pass
        self._start_parec()

    def read_chunk(self, duration: float) -> bytes:
        """Read audio chunk and return as WAV bytes."""
        # Calculate bytes needed for requested duration
        bytes_needed = int(self._sample_rate * duration) * self._channels * self._sample_width

        # Ensure minimum chunk size (0.1 seconds)
        min_bytes = self._sample_rate * self._channels * self._sample_width // 10
        if bytes_needed < min_bytes:
            bytes_needed = min_bytes

        # Read raw audio from parec
        raw_audio = self._read_bytes(bytes_needed)

        # Wrap in WAV container
        return self._create_wav(raw_audio)

    def _create_wav(self, raw_audio: bytes) -> bytes:
        """Wrap raw PCM audio in WAV container."""
        wav_buffer = io.BytesIO()
        with wave.open(wav_buffer, "wb") as wav_file:
            wav_file.setnchannels(self._channels)
            wav_file.setsampwidth(self._sample_width)
            wav_file.setframerate(self._sample_rate)
            wav_file.writeframes(raw_audio)
        return wav_buffer.getvalue()

    def close(self) -> None:
        """Kill parec subprocess."""
        if hasattr(self, "_parec") and self._parec:
            try:
                self._parec.kill()
                self._parec.wait(timeout=1)
            except Exception:
                pass

    def __del__(self):
        self.close()


class AudioRecorder:
    """Unified audio recorder with selectable backend."""

    def __init__(
        self,
        sample_rate: int = 16000,
        channels: int = 1,
        backend: str = "auto",
        device: Optional[str] = None,
    ):
        """
        Create audio recorder with specified backend.

        Args:
            sample_rate: Sample rate in Hz (default: 16000)
            channels: Number of audio channels (default: 1)
            backend: Backend to use - "pyaudio", "parec", or "auto" (default: "auto")
            device: Device name for parec backend (ignored for pyaudio)

        Raises:
            ValueError: If backend is invalid
            RuntimeError: If requested backend is not available
        """
        if backend == "auto":
            backend = self._detect_backend()

        self._backend_name = backend
        self._backend: Optional[AudioBackend] = None

        # Create appropriate backend
        if backend == "parec":
            self._backend = ParecBackend(sample_rate, channels, device)
        elif backend == "pyaudio":
            if device and device != "default":
                logging.warning(
                    "PyAudio backend does not support device selection; ignoring device='%s'",
                    device,
                )
            self._backend = PyAudioBackend(sample_rate, channels)
        else:
            raise ValueError(f"Unknown audio backend: {backend}")

        logging.info(f"AudioRecorder initialized with {backend} backend")

    def record_chunk(self, duration: float) -> bytes:
        """
        Record audio chunk.

        Args:
            duration: Duration in seconds

        Returns:
            WAV-formatted audio data
        """
        if not self._backend:
            raise RuntimeError("AudioRecorder backend not initialized")
        return self._backend.read_chunk(duration)

    def close(self) -> None:
        """Release audio backend resources."""
        if self._backend:
            self._backend.close()

    @staticmethod
    def _detect_backend() -> str:
        """
        Auto-detect best available audio backend.

        Returns:
            Backend name ("parec" or "pyaudio")

        Raises:
            RuntimeError: If no backend is available
        """
        # Prefer parec on Linux for reliability
        if sys.platform == "linux" and shutil.which("parec"):
            logging.debug("Auto-selected parec backend (Linux with PulseAudio)")
            return "parec"

        # Try PyAudio as fallback
        try:
            import pyaudio  # noqa: F401

            logging.debug("Auto-selected pyaudio backend")
            return "pyaudio"
        except ImportError:
            pass

        # No backend available
        raise RuntimeError(
            "No audio backend available. Install either:\n"
            "  - pulseaudio-utils (for parec on Linux), or\n"
            "  - pyaudio (pip install pyaudio)"
        )

    def __del__(self):
        self.close()
