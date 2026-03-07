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
            "option_descriptions": {
                "tiny": "Fastest, but least accurate (~39 MB)",
                "base": "Good balance for most CPUs (~74 MB)",
                "small": "Recommended for decent accuracy on modern CPUs (~244 MB)",
                "medium": "Requires a powerful CPU or GPU (~769 MB)",
                "large-v3": "Maximum accuracy, requires GPU with 8GB+ VRAM (~1.5 GB)",
            },
            "tooltip": (
                "<b>Whisper Model Size</b><br><br>"
                "Select the model based on accuracy vs speed trade-off:<br><ul>"
                "<li><b>tiny:</b> Fastest, but least accurate (~39 MB)</li>"
                "<li><b>base:</b> Good balance for most CPUs (~74 MB)</li>"
                "<li><b>small:</b> Recommended for decent accuracy on modern CPUs (~244 MB)</li>"
                "<li><b>medium:</b> Requires a powerful CPU or GPU (~769 MB)</li>"
                "<li><b>large-v3:</b> Maximum accuracy, requires GPU with 8GB+ VRAM (~1.5 GB)</li>"
                "</ul>"
            ),
        }
    )
    
    language: str = dataclasses.field(
        default="auto",
        metadata={
            "label": "Language",
            "widget": "text",
            "tooltip": (
                "<b>Language Code</b><br><br>"
                "ISO 639-1 language code for transcription.<br><br>"
                "<i>Examples:</i> en, es, fr, de, it<br>"
                "<i>Leave empty or use 'auto' for automatic detection</i>"
            ),
        }
    )
    
    device: str = dataclasses.field(
        default="auto",
        metadata={
            "label": "Device",
            "widget": "dropdown",
            "options": ["auto", "cuda", "cpu"],
            "option_descriptions": {
                "auto": "Automatically select best available device",
                "cuda": "Use NVIDIA GPU for faster inference",
                "cpu": "Use CPU (slower but works on all systems)",
            },
            "tooltip": (
                "<b>Inference Device</b><br><ul>"
                "<li><b>auto:</b> Automatically select best available device</li>"
                "<li><b>cuda:</b> Use NVIDIA GPU for faster inference</li>"
                "<li><b>cpu:</b> Use CPU (slower but works on all systems)</li>"
                "</ul>"
            ),
        }
    )
    
    compute_type: str = dataclasses.field(
        default="auto",
        metadata={
            "label": "Compute Type",
            "widget": "dropdown",
            "options": ["auto", "int8", "float16", "float32"],
            "option_descriptions": {
                "auto": "Automatically select best precision for the device",
                "int8": "Fastest on CPU, uses less memory",
                "float16": "Recommended for NVIDIA GPUs (half precision)",
                "float32": "Maximum precision, but slower",
            },
            "tooltip": (
                "<b>Computation Data Type</b><br><ul>"
                "<li><b>auto:</b> Automatically select best precision for the device</li>"
                "<li><b>int8:</b> Fastest on CPU, uses less memory (quantized)</li>"
                "<li><b>float16:</b> Recommended for NVIDIA GPUs (half precision)</li>"
                "<li><b>float32:</b> Maximum precision, but slower (full precision)</li>"
                "</ul>"
            ),
        }
    )
    
    # VAD settings
    vad_threshold: float = dataclasses.field(
        default=0.5,
        metadata={
            "label": "VAD Threshold",
            "widget": "text",
            "tooltip": (
                "<b>Voice Activity Detection Threshold</b><br><br>"
                "Energy threshold for speech detection (0.0 to 1.0).<br><br>"
                "<i>Lower (0.1-0.3):</i> Detects quiet speech, more false positives<br>"
                "<i>Medium (0.4-0.6):</i> Good for normal environments<br>"
                "<i>Higher (0.7-0.9):</i> Filters noise, may miss quiet speech<br>"
                "<i>Default:</i> 0.5"
            ),
        }
    )
    
    # Context settings
    context_limit_chars: int = dataclasses.field(
        default=100,
        metadata={
            "label": "Context Limit (chars)",
            "widget": "text",
            "tooltip": (
                "<b>Context Window Size</b><br><br>"
                "Maximum characters of previous transcription to use as context.<br><br>"
                "<i>Higher values:</i> Better coherence across utterances<br>"
                "<i>Lower values:</i> Less memory usage, faster processing<br>"
                "<i>Maximum:</i> 100 characters"
            ),
        }
    )
    
    auto_reset_context: bool = dataclasses.field(
        default=True,
        metadata={
            "label": "Auto Reset Context",
            "widget": "checkbox",
            "tooltip": (
                "<b>Automatic Context Reset</b><br><br>"
                "Clears context after 30 seconds of silence.<br><br>"
                "<i>Enabled:</i> Fresh start after pauses (recommended)<br>"
                "<i>Disabled:</i> Context persists until manually reset"
            ),
        }
    )
    
    reset_context_action: str = dataclasses.field(
        default="",
        repr=False,
        metadata={
            "widget": "action_button",
            "button_text": "Reset Context",
            "tooltip": (
                "<b>Manual Context Reset</b><br><br>"
                "Immediately clears the transcription context.<br><br>"
                "<i>Use when:</i> Changing topics, starting a new paragraph, "
                "or when transcription quality degrades"
            ),
        }
    )
    
    # Text formatting
    locale: str = dataclasses.field(
        default="en_US",
        metadata={
            "label": "Locale",
            "widget": "text",
            "tooltip": (
                "<b>Locale for Formatting</b><br><br>"
                "BCP-47 locale code for number and text formatting.<br><br>"
                "<i>Examples:</i> en_US, es_ES, fr_FR, de_DE"
            ),
        }
    )
    
    # Performance
    max_queue_depth: int = dataclasses.field(
        default=2,
        metadata={
            "label": "Max Queue Depth",
            "widget": "text",
            "tooltip": (
                "<b>Audio Queue Size</b><br><br>"
                "Maximum number of audio segments waiting for transcription.<br><br>"
                "<i>Higher values:</i> Better handling of bursts of speech<br>"
                "<i>Lower values:</i> Less memory usage, more responsive<br>"
                "<i>Default:</i> 2"
            ),
        }
    )
