# ABOUTME: Settings schema for Google Cloud Speech engine with UI metadata.
# ABOUTME: Defines GoogleCloudSettings dataclass with field metadata for dynamic UI generation.

from __future__ import annotations

from dataclasses import dataclass, field

from eloGraf.base_settings import EngineSettings


@dataclass
class GoogleCloudSettings(EngineSettings):
    """Settings for Google Cloud Speech-to-Text engine."""

    engine_type: str = field(
        default="google-cloud-speech",
        metadata={"hidden": True}
    )

    credentials_path: str = field(
        default="",
        metadata={
            "label": "Credentials Path",
            "widget": "text",
            "tooltip": "Filesystem path to the Google Cloud service account JSON file",
        }
    )

    project_id: str = field(
        default="",
        metadata={
            "label": "Project ID",
            "widget": "text",
            "tooltip": "GCP project identifier; leave empty to auto-detect from credentials",
        }
    )

    language_code: str = field(
        default="en-US",
        metadata={
            "label": "Language Code",
            "widget": "text",
            "tooltip": "Primary BCP-47 language code (e.g. en-US, es-ES)",
        }
    )

    model: str = field(
        default="chirp_3",
        metadata={
            "label": "Model",
            "widget": "text",
            "tooltip": "Google Cloud Speech model name (chirp_3, latest_long, latest_short, ...)",
        }
    )

    sample_rate: int = field(
        default=16000,
        metadata={
            "label": "Sample Rate",
            "widget": "text",
            "tooltip": "Sample rate in Hz for audio sent to the gRPC stream",
        }
    )

    channels: int = field(
        default=1,
        metadata={
            "label": "Channels",
            "widget": "text",
            "tooltip": "Number of audio channels (must match recorder configuration)",
        }
    )

    vad_enabled: bool = field(
        default=True,
        metadata={
            "label": "VAD Enabled",
            "widget": "checkbox",
            "tooltip": "Enable voice activity detection when streaming audio",
        }
    )

    vad_threshold: float = field(
        default=500.0,
        metadata={
            "label": "VAD Threshold",
            "widget": "text",
            "tooltip": "RMS loudness threshold used when VAD is enabled",
        }
    )

    def __post_init__(self):
        """Validate sample rate is in valid range."""
        if not 8000 <= self.sample_rate <= 48000:
            raise ValueError(f"Invalid sample rate: {self.sample_rate}")
