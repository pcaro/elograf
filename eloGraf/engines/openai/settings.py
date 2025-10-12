# ABOUTME: Settings schema for OpenAI Realtime API engine with UI metadata.
# ABOUTME: Defines OpenAISettings dataclass with field metadata for dynamic UI generation.

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class OpenAISettings:
    """Settings for OpenAI Realtime API engine."""

    engine_type: str = field(
        default="openai-realtime",
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
        default="gpt-4o-transcribe",
        metadata={
            "label": "Model",
            "widget": "dropdown",
            "options": ["gpt-4o-realtime-preview", "gpt-4o-mini-realtime-preview"],
        }
    )

    api_version: str = field(
        default="2025-08-28",
        metadata={
            "label": "API Version",
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

    vad_enabled: bool = field(
        default=True,
        metadata={
            "label": "VAD Enabled",
            "widget": "checkbox",
        }
    )

    vad_threshold: float = field(
        default=0.5,
        metadata={
            "label": "VAD Threshold",
            "widget": "text",
        }
    )

    vad_prefix_padding_ms: int = field(
        default=300,
        metadata={
            "label": "VAD Prefix Padding (ms)",
            "widget": "text",
        }
    )

    vad_silence_duration_ms: int = field(
        default=200,
        metadata={
            "label": "VAD Silence Duration (ms)",
            "widget": "text",
        }
    )

    language: str = field(
        default="en-US",
        metadata={
            "label": "Language",
            "widget": "text",
        }
    )

    def __post_init__(self):
        """Validate VAD threshold is between 0 and 1."""
        if not 0.0 <= self.vad_threshold <= 1.0:
            raise ValueError(f"VAD threshold must be between 0 and 1, got {self.vad_threshold}")
