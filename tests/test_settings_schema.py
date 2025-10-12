# ABOUTME: Tests for dataclass-based settings schema with validation.
# ABOUTME: Verifies type safety, defaults, and validation logic for all engine settings.

from __future__ import annotations

import os

import pytest
from PyQt6.QtWidgets import QApplication

from eloGraf.settings import Settings
from eloGraf.settings_schema import (
    EngineSettings,
    WhisperSettings,
    GoogleCloudSettings,
    OpenAISettings,
    AssemblyAISettings,
)


@pytest.fixture(scope="module")
def qt_app():
    """Create QApplication for tests that need Qt."""
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    app = QApplication.instance()
    if not app:
        app = QApplication([])
    yield app


def test_engine_settings_basic():
    """Test basic EngineSettings dataclass creation."""
    settings = EngineSettings(
        engine_type="test-engine",
        device_name="test-device"
    )
    assert settings.engine_type == "test-engine"
    assert settings.device_name == "test-device"


def test_engine_settings_default_device():
    """Test EngineSettings uses default device when not specified."""
    settings = EngineSettings(engine_type="test-engine")
    assert settings.device_name == "default"


def test_whisper_settings_defaults():
    """Test WhisperSettings with default values."""
    settings = WhisperSettings()
    assert settings.engine_type == "whisper-docker"
    assert settings.model == "base"
    assert settings.port == 9000
    assert settings.device_name == "default"


def test_whisper_settings_custom_values():
    """Test WhisperSettings with custom values."""
    settings = WhisperSettings(
        model="large",
        port=9001,
        device_name="custom-device"
    )
    assert settings.model == "large"
    assert settings.port == 9001
    assert settings.device_name == "custom-device"


def test_whisper_settings_validates_port_too_low():
    """Test WhisperSettings rejects ports below 1."""
    with pytest.raises(ValueError, match="Invalid port"):
        WhisperSettings(port=0)


def test_whisper_settings_validates_port_too_high():
    """Test WhisperSettings rejects ports above 65535."""
    with pytest.raises(ValueError, match="Invalid port"):
        WhisperSettings(port=65536)


def test_whisper_settings_accepts_valid_ports():
    """Test WhisperSettings accepts valid port range."""
    settings_low = WhisperSettings(port=1)
    settings_high = WhisperSettings(port=65535)
    assert settings_low.port == 1
    assert settings_high.port == 65535


def test_google_cloud_settings_defaults():
    """Test GoogleCloudSettings with default values."""
    settings = GoogleCloudSettings()
    assert settings.engine_type == "google-cloud-speech"
    assert settings.language_code == "en-US"
    assert settings.model == "chirp_3"
    assert settings.sample_rate == 16000
    assert settings.channels == 1
    assert settings.vad_enabled is True
    assert settings.vad_threshold == 500.0
    assert settings.credentials_path == ""
    assert settings.project_id == ""


def test_google_cloud_settings_validates_sample_rate():
    """Test GoogleCloudSettings validates sample rate."""
    with pytest.raises(ValueError, match="Invalid sample rate"):
        GoogleCloudSettings(sample_rate=7999)

    with pytest.raises(ValueError, match="Invalid sample rate"):
        GoogleCloudSettings(sample_rate=48001)


def test_google_cloud_settings_accepts_valid_sample_rates():
    """Test GoogleCloudSettings accepts valid sample rates."""
    settings_low = GoogleCloudSettings(sample_rate=8000)
    settings_high = GoogleCloudSettings(sample_rate=48000)
    assert settings_low.sample_rate == 8000
    assert settings_high.sample_rate == 48000


def test_openai_settings_defaults():
    """Test OpenAISettings with default values."""
    settings = OpenAISettings()
    assert settings.engine_type == "openai-realtime"
    assert settings.model == "gpt-4o-transcribe"
    assert settings.api_version == "2025-08-28"
    assert settings.sample_rate == 16000
    assert settings.channels == 1
    assert settings.vad_enabled is True
    assert settings.vad_threshold == 0.5
    assert settings.vad_prefix_padding_ms == 300
    assert settings.vad_silence_duration_ms == 200
    assert settings.language == "en-US"
    assert settings.api_key == ""


def test_openai_settings_validates_vad_threshold():
    """Test OpenAISettings validates VAD threshold range."""
    with pytest.raises(ValueError, match="VAD threshold must be between 0 and 1"):
        OpenAISettings(vad_threshold=-0.1)

    with pytest.raises(ValueError, match="VAD threshold must be between 0 and 1"):
        OpenAISettings(vad_threshold=1.1)


def test_openai_settings_accepts_valid_vad_thresholds():
    """Test OpenAISettings accepts valid VAD thresholds."""
    settings_low = OpenAISettings(vad_threshold=0.0)
    settings_high = OpenAISettings(vad_threshold=1.0)
    assert settings_low.vad_threshold == 0.0
    assert settings_high.vad_threshold == 1.0


def test_assembly_settings_defaults():
    """Test AssemblyAISettings with default values."""
    settings = AssemblyAISettings()
    assert settings.engine_type == "assemblyai"
    assert settings.model == "universal"
    assert settings.language == ""
    assert settings.sample_rate == 16000
    assert settings.channels == 1
    assert settings.api_key == ""


def test_assembly_settings_validates_sample_rate():
    """Test AssemblyAISettings validates sample rate."""
    with pytest.raises(ValueError, match="Invalid sample rate"):
        AssemblyAISettings(sample_rate=7999)

    with pytest.raises(ValueError, match="Invalid sample rate"):
        AssemblyAISettings(sample_rate=48001)


def test_assembly_settings_accepts_valid_sample_rates():
    """Test AssemblyAISettings accepts valid sample rates."""
    settings_low = AssemblyAISettings(sample_rate=8000)
    settings_high = AssemblyAISettings(sample_rate=48000)
    assert settings_low.sample_rate == 8000
    assert settings_high.sample_rate == 48000


def test_settings_get_whisper_engine_settings(qt_app):
    """Test Settings.get_engine_settings() returns WhisperSettings."""
    settings = Settings()
    settings.sttEngine = "whisper-docker"
    settings.whisperModel = "large"
    settings.whisperPort = 9001
    settings.deviceName = "test-device"

    engine_settings = settings.get_engine_settings()

    assert isinstance(engine_settings, WhisperSettings)
    assert engine_settings.model == "large"
    assert engine_settings.port == 9001
    assert engine_settings.device_name == "test-device"


def test_settings_get_google_cloud_engine_settings(qt_app):
    """Test Settings.get_engine_settings() returns GoogleCloudSettings."""
    settings = Settings()
    settings.sttEngine = "google-cloud"
    settings.googleCloudModel = "chirp_2"
    settings.googleCloudProjectId = "test-project"
    settings.googleCloudLanguageCode = "es-ES"

    engine_settings = settings.get_engine_settings()

    assert isinstance(engine_settings, GoogleCloudSettings)
    assert engine_settings.model == "chirp_2"
    assert engine_settings.project_id == "test-project"
    assert engine_settings.language_code == "es-ES"


def test_settings_get_openai_engine_settings(qt_app):
    """Test Settings.get_engine_settings() returns OpenAISettings."""
    settings = Settings()
    settings.sttEngine = "openai-realtime"
    settings.openaiModel = "gpt-4o-transcribe"
    settings.openaiVadThreshold = 0.7
    settings.openaiLanguage = "fr-FR"

    engine_settings = settings.get_engine_settings()

    assert isinstance(engine_settings, OpenAISettings)
    assert engine_settings.model == "gpt-4o-transcribe"
    assert engine_settings.vad_threshold == 0.7
    assert engine_settings.language == "fr-FR"


def test_settings_get_assembly_engine_settings(qt_app):
    """Test Settings.get_engine_settings() returns AssemblyAISettings."""
    settings = Settings()
    settings.sttEngine = "assemblyai"
    settings.assemblyModel = "best"
    settings.assemblySampleRate = 48000
    settings.assemblyLanguage = "es"

    engine_settings = settings.get_engine_settings()

    assert isinstance(engine_settings, AssemblyAISettings)
    assert engine_settings.model == "best"
    assert engine_settings.sample_rate == 48000
    assert engine_settings.language == "es"


def test_settings_update_from_whisper_dataclass(qt_app):
    """Test Settings.update_from_dataclass() updates whisper settings."""
    settings = Settings()
    settings.sttEngine = "whisper-docker"

    new_settings = WhisperSettings(
        model="large-v2",
        port=9002,
        device_name="custom-device"
    )

    settings.update_from_dataclass(new_settings)

    assert settings.whisperModel == "large-v2"
    assert settings.whisperPort == 9002
    assert settings.deviceName == "custom-device"


def test_settings_validation_via_dataclass(qt_app):
    """Test that dataclass validation catches invalid settings."""
    settings = Settings()
    settings.sttEngine = "whisper-docker"
    settings.whisperPort = 99999  # Invalid port

    with pytest.raises(ValueError, match="Invalid port"):
        settings.get_engine_settings()
