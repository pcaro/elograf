"""Tests for Gemini Live API controller."""

import pytest
from eloGraf.engines.gemini.settings import GeminiSettings


def test_gemini_settings_defaults():
    settings = GeminiSettings()
    assert settings.engine_type == "gemini-live"
    assert settings.api_key == ""
    assert settings.model == "gemini-2.5-flash"
    assert settings.sample_rate == 16000
    assert settings.channels == 1
    assert settings.vad_enabled is True
    assert settings.vad_threshold == 500.0
    assert settings.language_code == "en-US"


def test_gemini_settings_validates_sample_rate():
    with pytest.raises(ValueError, match="Invalid sample rate"):
        GeminiSettings(sample_rate=7999)
    with pytest.raises(ValueError, match="Invalid sample rate"):
        GeminiSettings(sample_rate=48001)


def test_gemini_settings_accepts_valid_sample_rates():
    settings_low = GeminiSettings(sample_rate=8000)
    settings_high = GeminiSettings(sample_rate=48000)
    assert settings_low.sample_rate == 8000
    assert settings_high.sample_rate == 48000
