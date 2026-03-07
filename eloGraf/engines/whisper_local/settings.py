"""Settings for WhisperLocal engine."""
import dataclasses
from dataclasses import dataclass
from typing import Optional
from eloGraf.base_settings import EngineSettings


@dataclass
class WhisperLocalSettings(EngineSettings):
    """Configuration for WhisperLocal STT engine."""
    
    engine_type: str = dataclasses.field(
        default="whisper-local",
        metadata={"hidden": True}
    )
    
    # Model settings
    model_size: str = dataclasses.field(
        default="base",
        metadata={
            "label": "Model Size",
            "widget": "dropdown",
            "options": ["tiny", "base", "small", "medium", "large-v3"],
            "tooltip": (
                "Size of the Whisper model to use.\n"
                "- tiny: Fastest, but least accurate.\n"
                "- base: Good balance for most CPUs.\n"
                "- small: Recommended for decent accuracy on modern CPUs.\n"
                "- medium: Requires a powerful CPU or GPU.\n"
                "- large-v3: Maximum accuracy, requires GPU with 8GB+ VRAM."
            ),
        }
    )
    
    language: str = dataclasses.field(
        default="auto",
        metadata={
            "label": "Language",
            "widget": "text",
            "tooltip": "Language code (e.g. 'en', 'es', 'fr') or 'auto' for autodetection.",
        }
    )
    
    device: str = dataclasses.field(
        default="auto",
        metadata={
            "label": "Device",
            "widget": "dropdown",
            "options": ["auto", "cuda", "cpu"],
            "tooltip": "Device to run inference on (GPU/CUDA or CPU).",
        }
    )
    
    compute_type: str = dataclasses.field(
        default="auto",
        metadata={
            "label": "Compute Type",
            "widget": "dropdown",
            "options": ["auto", "int8", "float16", "float32"],
            "tooltip": (
                "Data type for computation.\n"
                "- int8: Fastest on CPU, uses less memory.\n"
                "- float16: Recommended for NVIDIA GPUs.\n"
                "- float32: Maximum precision, but slower."
            ),
        }
    )
    
    # VAD settings
    vad_threshold: float = dataclasses.field(
        default=0.5,
        metadata={
            "label": "VAD Threshold",
            "widget": "text",
            "tooltip": "Voice Activity Detection threshold (0.0 to 1.0). Higher = more strict.",
        }
    )
    
    # Context settings
    context_limit_chars: int = dataclasses.field(
        default=100,
        metadata={
            "label": "Context Limit (chars)",
            "widget": "text",
            "tooltip": "Character limit for previous text used as context (max 100).",
        }
    )
    
    auto_reset_context: bool = dataclasses.field(
        default=True,
        metadata={
            "label": "Auto Reset Context",
            "widget": "checkbox",
            "tooltip": "Automatically reset context after a long pause (30s).",
        }
    )
    
    reset_context_action: str = dataclasses.field(
        default="",
        repr=False,
        metadata={
            "widget": "action_button",
            "button_text": "Reset Context",
            "tooltip": "Clears the current context (useful when changing topics).",
        }
    )
    
    # Text formatting
    locale: str = dataclasses.field(
        default="en_US",
        metadata={
            "label": "Locale",
            "widget": "text",
            "tooltip": "Locale for number and text formatting (e.g. en_US, es_ES).",
        }
    )
    
    # Performance
    max_queue_depth: int = dataclasses.field(
        default=2,
        metadata={
            "label": "Max Queue Depth",
            "widget": "text",
            "tooltip": "Maximum number of audio segments waiting for transcription.",
        }
    )
