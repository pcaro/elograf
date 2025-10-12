# ABOUTME: Settings schema for nerd-dictation engine with UI metadata.
# ABOUTME: Defines NerdSettings dataclass with field metadata for dynamic UI generation.

from __future__ import annotations

from dataclasses import dataclass, field

from eloGraf.base_settings import EngineSettings
from .ui.dialogs import launch_model_selection_dialog


@dataclass
class NerdSettings(EngineSettings):
    """Settings for nerd-dictation engine."""

    engine_type: str = field(
        default="nerd-dictation",
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

    sample_rate: int = field(
        default=44100,
        metadata={
            "label": "Sample rate (Hz)",
            "widget": "text",
            "tooltip": "The sample rate to use for recording (in Hz). Defaults to 44100",
        }
    )

    timeout: int = field(
        default=0,
        metadata={
            "label": "Timeout (s)",
            "widget": "slider",
            "tooltip": (
                "Time out recording when no speech is processed for the time in seconds.\n"
                "This can be used to avoid having to explicitly exit\n"
                "(zero disables)"
            ),
            "range": [0, 100],
            "step": 1,
        }
    )

    idle_time: int = field(
        default=100,
        metadata={
            "label": "Idle time (ms)",
            "widget": "slider",
            "tooltip": (
                "Time to idle between processing audio from the recording.\n"
                "Setting to zero is the most responsive at the cost of high CPU usage.\n"
                "The default value is 0.1 (processing 10 times a second),\n"
                "which is quite responsive in practice"
            ),
            "range": [0, 500],
            "step": 1,
        }
    )

    punctuate_timeout: int = field(
        default=0,
        metadata={
            "label": "Punctuate from previous timeout (s)",
            "widget": "slider",
            "tooltip": (
                "The time-out in seconds for detecting the state of dictation from the previous recording,\n"
                "this can be useful so punctuation it is added before entering the dictation (zero disables)"
            ),
            "range": [0, 100],
            "step": 1,
        }
    )

    full_sentence: bool = field(
        default=False,
        metadata={
            "label": "Full sentence",
            "widget": "checkbox",
            "tooltip": (
                "Capitalize the first character.\n"
                "This is also used to add either a comma or a full stop when dictation is performed according to previous delay"
            ),
        }
    )

    digits: bool = field(
        default=False,
        metadata={
            "label": "Numbers as digits",
            "widget": "checkbox",
            "tooltip": "Convert numbers into digits instead of using whole words",
        }
    )

    use_separator: bool = field(
        default=False,
        metadata={
            "label": "Use separator for numbers",
            "widget": "checkbox",
            "tooltip": "Use a comma separators for numbers",
        }
    )

    free_command: str = field(
        default="",
        metadata={
            "label": "Free option",
            "widget": "text",
            "tooltip": "Add option to add on the comamnd line of the dictation tool",
        }
    )

    model_path: str = field(
        default="",
        metadata={
            "label": "Model Path",
            "widget": "text",
            "readonly": True,
        }
    )

    manage_models_action: str = field(
        default="",
        repr=False,
        metadata={
            "widget": "action_button",
            "button_text": "Manage Models...",
            "on_click": launch_model_selection_dialog,
        }
    )
