# ABOUTME: Registry mapping engine names to their settings dataclasses.
# ABOUTME: Provides centralized access to engine settings schemas for dynamic UI generation.

from __future__ import annotations

from typing import Type, Dict, Optional
import importlib


# Mapping of engine identifiers to their settings module paths
ENGINE_SETTINGS_MODULES: Dict[str, str] = {
    "nerd-dictation": "eloGraf.engines.nerd.settings",
    "whisper-docker": "eloGraf.engines.whisper.settings",
    "google-cloud-speech": "eloGraf.engines.google.settings",
    "openai-realtime": "eloGraf.engines.openai.settings",
    "assemblyai": "eloGraf.engines.assemblyai.settings",
}

# Mapping of engine identifiers to their settings class names
ENGINE_SETTINGS_CLASSES: Dict[str, str] = {
    "nerd-dictation": "NerdSettings",
    "whisper-docker": "WhisperSettings",
    "google-cloud-speech": "GoogleCloudSettings",
    "openai-realtime": "OpenAISettings",
    "assemblyai": "AssemblyAISettings",
}

# Display names for engines (for tab labels)
ENGINE_DISPLAY_NAMES: Dict[str, str] = {
    "nerd-dictation": "Nerd Dictation",
    "whisper-docker": "Whisper Docker",
    "google-cloud-speech": "Google Cloud",
    "openai-realtime": "OpenAI",
    "assemblyai": "AssemblyAI",
}


def get_engine_settings_class(engine_id: str) -> Optional[Type]:
    """Get the settings dataclass for an engine.

    Args:
        engine_id: Engine identifier (e.g., "nerd-dictation")

    Returns:
        Settings dataclass type, or None if not found
    """
    module_path = ENGINE_SETTINGS_MODULES.get(engine_id)
    class_name = ENGINE_SETTINGS_CLASSES.get(engine_id)

    if not module_path or not class_name:
        return None

    try:
        module = importlib.import_module(module_path)
        return getattr(module, class_name)
    except (ImportError, AttributeError):
        return None


def get_all_engine_ids() -> list[str]:
    """Get list of all registered engine identifiers.

    Returns:
        List of engine IDs
    """
    return list(ENGINE_SETTINGS_MODULES.keys())


def get_engine_display_name(engine_id: str) -> str:
    """Get the display name for an engine.

    Args:
        engine_id: Engine identifier

    Returns:
        Human-readable display name
    """
    return ENGINE_DISPLAY_NAMES.get(engine_id, engine_id)
