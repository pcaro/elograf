from __future__ import annotations

import os

import pytest
from PyQt6.QtCore import QSettings
from PyQt6.QtWidgets import QApplication

from eloGraf.engines.assemblyai.settings import AssemblyAISettings
from eloGraf.engines.google.settings import GoogleCloudSettings
from eloGraf.engines.openai.settings import OpenAISettings
from eloGraf.engines.whisper.settings import WhisperSettings
from eloGraf.settings import DEFAULT_RATE, Settings


@pytest.fixture(scope="module")
def qt_app():
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    yield app


def _make_backend(tmp_path):
    path = tmp_path / "settings.ini"
    backend = QSettings(str(path), QSettings.Format.IniFormat)
    backend.clear()
    backend.sync()
    return backend, path


def test_load_defaults_when_backend_empty(tmp_path):
    backend, _ = _make_backend(tmp_path)
    settings = Settings(backend)

    settings.load()

    assert settings.precommand == ""
    assert settings.postcommand == ""
    assert settings.sampleRate == DEFAULT_RATE
    assert settings.timeout == 0
    assert settings.fullSentence is False
    assert settings.beginShortcut == ""
    assert settings.endShortcut == ""
    assert settings.suspendShortcut == ""
    assert settings.resumeShortcut == ""
    assert settings.toggleShortcut == ""
    assert settings.models == []


def test_save_persists_custom_values(tmp_path):
    backend, path = _make_backend(tmp_path)
    settings = Settings(backend)
    settings.precommand = "echo start"
    settings.postcommand = "echo stop"
    settings.sampleRate = DEFAULT_RATE + 1
    settings.timeout = 42
    settings.fullSentence = True
    settings.digits = True
    settings.deviceName = "usb-mic"
    settings.freeCommand = "--foo bar"
    settings.beginShortcut = "Ctrl+Alt+B"
    settings.endShortcut = "Ctrl+Alt+E"
    settings.suspendShortcut = "Ctrl+Alt+S"
    settings.resumeShortcut = "Ctrl+Alt+R"
    settings.toggleShortcut = "Ctrl+Alt+T"

    settings.save()
    backend.sync()

    reloaded = QSettings(str(path), QSettings.Format.IniFormat)
    assert reloaded.value("Precommand") == "echo start"
    assert reloaded.value("Postcommand") == "echo stop"
    assert reloaded.value("SampleRate", type=int) == DEFAULT_RATE + 1
    assert reloaded.value("Timeout", type=int) == 42
    assert reloaded.value("FullSentence", type=int) == 1
    assert reloaded.value("Digits", type=int) == 1
    assert reloaded.value("DeviceName") == "usb-mic"
    assert reloaded.value("FreeCommand") == "--foo bar"
    assert reloaded.value("BeginShortcut") == "Ctrl+Alt+B"
    assert reloaded.value("EndShortcut") == "Ctrl+Alt+E"
    assert reloaded.value("SuspendShortcut") == "Ctrl+Alt+S"
    assert reloaded.value("ResumeShortcut") == "Ctrl+Alt+R"
    assert reloaded.value("ToggleShortcut") == "Ctrl+Alt+T"


def test_add_and_remove_model_updates_backend(tmp_path):
    backend, path = _make_backend(tmp_path)
    settings = Settings(backend)
    settings.load()

    settings.add_model("en", "vosk-en", "1.0", "1 GB", "Vosk", "/models/en")
    backend.sync()

    loaded = Settings(QSettings(str(path), QSettings.Format.IniFormat))
    loaded.load()
    assert loaded.models == [
        {
            "language": "en",
            "name": "vosk-en",
            "version": "1.0",
            "size": "1 GB",
            "type": "Vosk",
            "location": "/models/en",
        }
    ]

    settings.remove_model(0)
    backend.sync()

    loaded_again = Settings(QSettings(str(path), QSettings.Format.IniFormat))
    loaded_again.load()
    assert loaded_again.models == []


def test_settings_get_whisper_engine_settings(qt_app):
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
    settings = Settings()
    settings.sttEngine = "whisper-docker"

    new_settings = WhisperSettings(model="large-v2", port=9002, device_name="custom-device")

    settings.update_from_dataclass(new_settings)

    assert settings.whisperModel == "large-v2"
    assert settings.whisperPort == 9002
    assert settings.deviceName == "custom-device"


def test_settings_validation_via_dataclass(qt_app):
    settings = Settings()
    settings.sttEngine = "whisper-docker"
    settings.whisperPort = 99999

    with pytest.raises(ValueError, match="Invalid port"):
        settings.get_engine_settings()
