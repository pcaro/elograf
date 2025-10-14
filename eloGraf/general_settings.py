# ABOUTME: GeneralSettings dataclass for validation and type safety.
# ABOUTME: Provides field metadata for UI generation and validation of general settings.

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class GeneralSettings:
    """General application settings with validation metadata."""

    stt_engine: str = field(
        default="nerd-dictation",
        metadata={
            "label": "STT Engine",
            "widget": "dropdown",
            "choices_function": "eloGraf.engine_settings_registry:get_engine_choices",
            "tooltip": "Speech-to-text engine to use for dictation",
        }
    )

    precommand: str = field(
        default="",
        metadata={
            "label": "Pre-command",
            "widget": "text",
            "validate": "eloGraf.validators:validate_command_exists",
            "tooltip": "Command to run before starting dictation",
        }
    )

    postcommand: str = field(
        default="",
        metadata={
            "label": "Post-command",
            "widget": "text",
            "validate": "eloGraf.validators:validate_command_exists",
            "tooltip": "Command to run after stopping dictation",
        }
    )

    env: str = field(
        default="",
        metadata={
            "label": "Environment variables",
            "widget": "text",
            "tooltip": "Environment variables for dictation process (e.g., LANG=en_US)",
        }
    )

    device_name: str = field(
        default="default",
        metadata={
            "label": "Audio device",
            "widget": "dropdown",
            "refreshable": True,
            "choices_function": "eloGraf.audio_recorder:get_audio_devices",
            "choices_function_kwargs": {"backend": "parec"},
            "tooltip": "PulseAudio device to use for recording",
        }
    )

    tool: str = field(
        default="XDOTOOL",
        metadata={
            "label": "Input tool",
            "widget": "dropdown",
            "options": ["XDOTOOL", "DOTOOL"],
            "tooltip": "Tool to use for keyboard input (XDOTOOL or DOTOOL)",
        }
    )

    keyboard: str = field(
        default="",
        metadata={
            "label": "Keyboard layout",
            "widget": "text",
            "tooltip": "Keyboard layout for DOTOOL (e.g., 'us', 'de')",
        }
    )

    direct_click: bool = field(
        default=True,
        metadata={
            "label": "Direct click toggle",
            "widget": "checkbox",
            "tooltip": "Toggle dictation by clicking the tray icon",
        }
    )
