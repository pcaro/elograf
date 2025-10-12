# ABOUTME: Settings schema for AssemblyAI Realtime engine with UI metadata.
# ABOUTME: Defines AssemblyAISettings dataclass with field metadata for dynamic UI generation.

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class AssemblyAISettings:
    """Settings for AssemblyAI Realtime engine."""

    engine_type: str = field(
        default="assemblyai",
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

    api_key: str = field(
        default="",
        metadata={
            "label": "API Key",
            "widget": "password",
        }
    )

    model: str = field(
        default="universal",
        metadata={
            "label": "Model",
            "widget": "text",
        }
    )

    language: str = field(
        default="",
        metadata={
            "label": "Language",
            "widget": "text",
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

    def __post_init__(self):
        """Validate sample rate is in valid range."""
        if not 8000 <= self.sample_rate <= 48000:
            raise ValueError(f"Invalid sample rate: {self.sample_rate}")
