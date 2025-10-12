# ABOUTME: Type-safe dataclass-based settings schema with validation.
# ABOUTME: Provides structured configuration for all STT engine types with runtime validation.

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass
class EngineSettings:
    """Base settings for all STT engines."""

    engine_type: str
    device_name: str = "default"


@dataclass
class WhisperSettings(EngineSettings):
    """Settings for Whisper Docker engine."""

    engine_type: str = "whisper-docker"
    model: str = "base"
    port: int = 9000
    language: Optional[str] = None
    chunk_duration: float = 5.0
    sample_rate: int = 16000
    channels: int = 1
    vad_enabled: bool = True
    vad_threshold: float = 500.0
    auto_reconnect: bool = True

    def __post_init__(self):
        """Validate port is in valid range."""
        if not 1 <= self.port <= 65535:
            raise ValueError(f"Invalid port: {self.port}")


@dataclass
class GoogleCloudSettings(EngineSettings):
    """Settings for Google Cloud Speech-to-Text engine."""

    engine_type: str = "google-cloud-speech"
    credentials_path: str = ""
    project_id: str = ""
    language_code: str = "en-US"
    model: str = "chirp_3"
    sample_rate: int = 16000
    channels: int = 1
    vad_enabled: bool = True
    vad_threshold: float = 500.0

    def __post_init__(self):
        """Validate sample rate is in valid range."""
        if not 8000 <= self.sample_rate <= 48000:
            raise ValueError(f"Invalid sample rate: {self.sample_rate}")


@dataclass
class OpenAISettings(EngineSettings):
    """Settings for OpenAI Realtime API engine."""

    engine_type: str = "openai-realtime"
    api_key: str = ""
    model: str = "gpt-4o-transcribe"
    api_version: str = "2025-08-28"
    sample_rate: int = 16000
    channels: int = 1
    vad_enabled: bool = True
    vad_threshold: float = 0.5
    vad_prefix_padding_ms: int = 300
    vad_silence_duration_ms: int = 200
    language: str = "en-US"

    def __post_init__(self):
        """Validate VAD threshold is between 0 and 1."""
        if not 0.0 <= self.vad_threshold <= 1.0:
            raise ValueError(f"VAD threshold must be between 0 and 1, got {self.vad_threshold}")


@dataclass
class AssemblyAISettings(EngineSettings):
    """Settings for AssemblyAI Realtime engine."""

    engine_type: str = "assemblyai"
    api_key: str = ""
    model: str = "universal"
    language: str = ""
    sample_rate: int = 16000
    channels: int = 1

    def __post_init__(self):
        """Validate sample rate is in valid range."""
        if not 8000 <= self.sample_rate <= 48000:
            raise ValueError(f"Invalid sample rate: {self.sample_rate}")
