import pytest

from eloGraf.engines.assemblyai.settings import AssemblyAISettings


def test_assembly_settings_defaults():
    settings = AssemblyAISettings()
    assert settings.engine_type == "assemblyai"
    assert settings.model == "universal"
    assert settings.language == ""
    assert settings.sample_rate == 16000
    assert settings.channels == 1
    assert settings.api_key == ""


def test_assembly_settings_validates_sample_rate():
    with pytest.raises(ValueError, match="Invalid sample rate"):
        AssemblyAISettings(sample_rate=7999)
    with pytest.raises(ValueError, match="Invalid sample rate"):
        AssemblyAISettings(sample_rate=48001)


def test_assembly_settings_accepts_valid_sample_rates():
    settings_low = AssemblyAISettings(sample_rate=8000)
    settings_high = AssemblyAISettings(sample_rate=48000)
    assert settings_low.sample_rate == 8000
    assert settings_high.sample_rate == 48000
