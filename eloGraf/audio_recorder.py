# ABOUTME: Unified audio recording with pluggable backends (PyAudio and parec).
# ABOUTME: Provides consistent interface for capturing microphone audio as WAV data.

from __future__ import annotations

import io
import json
import logging
import shutil
import sys
from abc import ABC, abstractmethod
from subprocess import PIPE, Popen, run
from typing import List, Optional, Tuple

import wave


def _get_pulseaudio_sources() -> List[Tuple[str, str]]:
    """Get available PulseAudio source devices.

    Tries JSON format first (newer pactl), then falls back to text parsing,
    and finally to `pactl list sources short`.

    Returns:
        List of tuples (device_name, description)
    """
    # Try JSON output for robust parsing
    try:
        result = run(["pactl", "-f", "json", "list", "sources"], capture_output=True, text=True, timeout=5)
        if result.returncode == 0 and result.stdout.strip():
            try:
                data = json.loads(result.stdout)
                sources: List[Tuple[str, str]] = []
                for src in data or []:
                    name = src.get("name") or ""
                    props = src.get("properties", {}) or {}
                    desc = props.get("node.description") or props.get("device.description") or name
                    if name:
                        if name.endswith(".monitor") and "monitor" not in desc.lower():
                            desc = f"{desc} (monitor)"
                        sources.append((name, desc))
                if sources:
                    return sources
            except json.JSONDecodeError:
                pass
    except Exception as exc:
        logging.debug("pactl json parse failed: %s", exc)

    # Fallback to text parsing of `pactl list sources`
    try:
        result = run(["pactl", "list", "sources"], capture_output=True, text=True, timeout=5)
        if result.returncode == 0 and result.stdout:
            sources: List[Tuple[str, str]] = []
            current_name: Optional[str] = None
            current_desc: Optional[str] = None
            props_mode = False
            for raw in result.stdout.splitlines():
                line = raw.strip()
                if line.startswith("Source #"):
                    if current_name and current_desc:
                        if current_name.endswith(".monitor") and "monitor" not in current_desc.lower():
                            current_desc = f"{current_desc} (monitor)"
                        sources.append((current_name, current_desc))
                    current_name, current_desc = None, None
                    props_mode = False
                elif line.startswith("Name:"):
                    current_name = line.split(":", 1)[1].strip()
                elif line.startswith("Description:"):
                    current_desc = line.split(":", 1)[1].strip()
                elif line.startswith("Properties:"):
                    props_mode = True
                elif props_mode and "node.description" in line and "=" in line and not current_desc:
                    try:
                        current_desc = line.split("=", 1)[1].strip().strip('"')
                    except Exception:
                        pass
            if current_name and current_desc:
                if current_name.endswith(".monitor") and "monitor" not in current_desc.lower():
                    current_desc = f"{current_desc} (monitor)"
                sources.append((current_name, current_desc))
            if sources:
                return sources
    except Exception as exc:
        logging.debug("pactl list sources parse failed: %s", exc)

    # Last resort: short listing
    try:
        result = run(["pactl", "list", "sources", "short"], capture_output=True, text=True, timeout=5)
        if result.returncode == 0 and result.stdout:
            sources: List[Tuple[str, str]] = []
            for line in result.stdout.splitlines():
                parts = line.split()
                if len(parts) >= 2:
                    name = parts[1]
                    desc = name
                    if name.endswith(".monitor") and "monitor" not in desc.lower():
                        desc = f"{desc} (monitor)"
                    sources.append((name, desc))
            return sources
    except Exception as exc:
        logging.debug("pactl short parse failed: %s", exc)

    return []


def get_audio_devices(backend: str = "auto") -> List[Tuple[str, str]]:
    """Get available audio input devices for the specified backend.

    Args:
        backend: Audio backend to query - "parec", "pyaudio", or "auto"

    Returns:
        List of tuples (device_value, display_name). Always includes
        ("default", "Default") as the first option. For parec backend
        with PulseAudio available, includes additional device choices.
    """
    devices: List[Tuple[str, str]] = [("default", "Default")]

    # Determine actual backend if auto
    if backend == "auto":
        if sys.platform == "linux" and shutil.which("pactl"):
            backend = "parec"
        else:
            backend = "pyaudio"

    # PyAudio doesn't support device selection, return only default
    if backend == "pyaudio":
        return devices

    # For parec backend, try to get PulseAudio devices
    if backend == "parec":
        sources = _get_pulseaudio_sources()
        devices.extend(sources)

    return devices


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
