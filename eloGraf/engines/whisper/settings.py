# ABOUTME: Settings schema for Whisper Docker engine with UI metadata.
# ABOUTME: Defines WhisperSettings dataclass with field metadata for dynamic UI generation.

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class WhisperSettings:
    """Settings for Whisper Docker engine."""

    engine_type: str = field(
        default="whisper-docker",
        metadata={"label": "Engine Type", "widget": "text", "readonly": True}
    )

    device_name: str = field(
        default="default",
        metadata={
            "label": "Pulse device name",
            "widget": "text",
            "tooltip": (
                "The name of the pulse-audio device to use for recording. \n"
                "See the output of \"pactl list sources\" to find device names (using the identifier following \"Name:\")"
            ),
        }
    )

    model: str = field(
        default="base",
        metadata={
            "label": "Whisper Model",
            "widget": "dropdown",
            "tooltip": "Whisper model size (whisper-docker only)",
            "options": ["tiny", "base", "small", "medium", "large-v3"],
        }
    )

    port: int = field(
        default=9000,
        metadata={
            "label": "Whisper Port",
            "widget": "text",
            "tooltip": "API port for Whisper Docker container",
        }
    )

    language: Optional[str] = field(
        default=None,
        metadata={
            "label": "Whisper Language",
            "widget": "text",
            "tooltip": "Language code for Whisper (e.g., 'es', 'en') - leave empty for auto-detect",
        }
    )

    chunk_duration: float = field(
        default=5.0,
        metadata={
            "label": "Whisper Chunk Duration (s)",
            "widget": "text",
            "tooltip": "Audio chunk duration in seconds for Whisper processing",
        }
    )

    sample_rate: int = field(
        default=16000,
        metadata={
            "label": "Sample Rate",
            "widget": "text",
        }
    )

    channels: int = field(
        default=1,
        metadata={
            "label": "Channels",
            "widget": "text",
        }
    )

    vad_enabled: bool = field(
        default=True,
        metadata={
            "label": "VAD Enabled",
            "widget": "checkbox",
        }
    )

    vad_threshold: float = field(
        default=500.0,
        metadata={
            "label": "VAD Threshold",
            "widget": "text",
        }
    )

    auto_reconnect: bool = field(
        default=True,
        metadata={
            "label": "Auto Reconnect",
            "widget": "checkbox",
        }
    )

    def __post_init__(self):
        """Validate port is in valid range."""
        if not 1 <= self.port <= 65535:
            raise ValueError(f"Invalid port: {self.port}")
