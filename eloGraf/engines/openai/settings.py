# ABOUTME: Settings schema for OpenAI Realtime API engine with UI metadata.
# ABOUTME: Defines OpenAISettings dataclass with field metadata for dynamic UI generation.

from __future__ import annotations

from dataclasses import dataclass, field

from eloGraf.base_settings import EngineSettings


@dataclass
class OpenAISettings(EngineSettings):
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
            "tooltip": "OpenAI API key with realtime access enabled",
        }
    )

    model: str = field(
        default="gpt-4o-transcribe",
        metadata={
            "label": "Transcription Model",
            "widget": "dropdown",
            "tooltip": (
                "Select the transcription model used inside the realtime session "
                "(mapped to the appropriate session model automatically)."
            ),
            "options": ["gpt-4o-transcribe", "gpt-4o-mini-transcribe"],
        }
    )

    api_version: str = field(
        default="2025-08-28",
        metadata={
            "label": "API Version",
            "widget": "text",
            "tooltip": "Realtime API version string appended to the WebSocket URL",
        }
    )

    sample_rate: int = field(
        default=16000,
        metadata={
            "label": "Sample Rate",
            "widget": "text",
            "tooltip": "PCM sample rate used when capturing audio for the websocket stream",
        }
    )

    channels: int = field(
        default=1,
        metadata={
            "label": "Channels",
            "widget": "text",
            "tooltip": "Number of audio channels streamed to OpenAI (mono required)",
        }
    )

    vad_enabled: bool = field(
        default=True,
        metadata={
            "label": "VAD Enabled",
            "widget": "checkbox",
            "tooltip": "Enable server-side voice activity detection to segment speech automatically",
        }
    )

    vad_threshold: float = field(
        default=0.5,
        metadata={
            "label": "VAD Threshold",
            "widget": "text",
            "tooltip": "Energy threshold between 0.0 and 1.0 for server VAD speech detection",
        }
    )

    vad_prefix_padding_ms: int = field(
        default=300,
        metadata={
            "label": "VAD Prefix Padding (ms)",
            "widget": "text",
            "tooltip": "Milliseconds of audio retained before speech start when VAD triggers",
        }
    )

    vad_silence_duration_ms: int = field(
        default=200,
        metadata={
            "label": "VAD Silence Duration (ms)",
            "widget": "text",
            "tooltip": "Silence duration in milliseconds required to finalize a segment",
        }
    )

    language: str = field(
        default="en-US",
        metadata={
            "label": "Language",
            "widget": "text",
            "tooltip": "BCP-47 language code (leave empty to let the model auto-detect)",
        }
    )

    def __post_init__(self):
        """Validate VAD threshold is between 0 and 1."""
        if not 0.0 <= self.vad_threshold <= 1.0:
            raise ValueError(f"VAD threshold must be between 0 and 1, got {self.vad_threshold}")
