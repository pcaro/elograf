# ABOUTME: Tests for engine settings registry functions.
# ABOUTME: Verifies registry lookups, display names, and engine class loading.

from __future__ import annotations

import pytest
from eloGraf.engine_settings_registry import (
    get_engine_settings_class,
    get_all_engine_ids,
    get_engine_display_name,
)


def test_get_all_engine_ids_returns_list():
    """Test get_all_engine_ids returns a list of engine identifiers."""
    engine_ids = get_all_engine_ids()

    assert isinstance(engine_ids, list)
    assert len(engine_ids) > 0

    # Verify expected engines are present
    assert "nerd-dictation" in engine_ids
    assert "whisper-docker" in engine_ids
    assert "google-cloud-speech" in engine_ids
    assert "openai-realtime" in engine_ids
    assert "assemblyai" in engine_ids
    assert "gemini-live" in engine_ids


def test_get_engine_display_name_returns_human_readable():
    """Test get_engine_display_name returns human-readable names."""
    assert get_engine_display_name("nerd-dictation") == "Nerd Dictation"
    assert get_engine_display_name("whisper-docker") == "Whisper Docker"
    assert get_engine_display_name("google-cloud-speech") == "Google Cloud"
    assert get_engine_display_name("openai-realtime") == "OpenAI"
    assert get_engine_display_name("assemblyai") == "AssemblyAI"
    assert get_engine_display_name("gemini-live") == "Gemini Live API"


def test_get_engine_display_name_fallback_for_unknown():
    """Test get_engine_display_name returns engine_id for unknown engines."""
    unknown_id = "unknown-engine"
    assert get_engine_display_name(unknown_id) == unknown_id


def test_get_engine_settings_class_returns_dataclass():
    """Test get_engine_settings_class returns the correct settings class."""
    from eloGraf.engines.nerd.settings import NerdSettings
    from eloGraf.engines.whisper.settings import WhisperSettings
    from eloGraf.engines.google.settings import GoogleCloudSettings
    from eloGraf.engines.openai.settings import OpenAISettings
    from eloGraf.engines.assemblyai.settings import AssemblyAISettings
    from eloGraf.engines.gemini.settings import GeminiSettings

    assert get_engine_settings_class("nerd-dictation") == NerdSettings
    assert get_engine_settings_class("whisper-docker") == WhisperSettings
    assert get_engine_settings_class("google-cloud-speech") == GoogleCloudSettings
    assert get_engine_settings_class("openai-realtime") == OpenAISettings
    assert get_engine_settings_class("assemblyai") == AssemblyAISettings
    assert get_engine_settings_class("gemini-live") == GeminiSettings


def test_get_engine_settings_class_returns_none_for_unknown():
    """Test get_engine_settings_class returns None for unknown engines."""
    assert get_engine_settings_class("unknown-engine") is None


def test_all_engines_have_display_names():
    """Test that all registered engines have display names."""
    engine_ids = get_all_engine_ids()

    for engine_id in engine_ids:
        display_name = get_engine_display_name(engine_id)
        # Should not fall back to engine_id (should have explicit display name)
        assert display_name != engine_id, f"Engine {engine_id} missing display name"


def test_all_engines_have_settings_classes():
    """Test that all registered engines have loadable settings classes."""
    engine_ids = get_all_engine_ids()

    for engine_id in engine_ids:
        settings_class = get_engine_settings_class(engine_id)
        assert settings_class is not None, f"Engine {engine_id} has no settings class"

        # Verify it's a dataclass
        assert hasattr(settings_class, '__dataclass_fields__')

        # Verify it can be instantiated
        instance = settings_class()
        assert hasattr(instance, 'engine_type')
