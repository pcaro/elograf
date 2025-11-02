from __future__ import annotations

import os
from typing import Callable, List, Optional, Sequence, Tuple

import pytest
from PyQt6.QtCore import QSettings
from PyQt6.QtGui import QIcon
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication

from eloGraf.settings import Settings
from eloGraf.stt_engine import STTController, STTProcessRunner
from eloGraf.status import DictationStatus
from eloGraf.tray_icon import SystemTrayIcon
from tests.helpers import FakeController, FakeIPC, FakeRunner




@pytest.fixture(scope="module")
def qt_app():
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    app = QApplication.instance()
    if not app:
        app = QApplication([])
    yield app


@pytest.fixture
def fake_engine(monkeypatch) -> List[Tuple[FakeController, FakeRunner]]:
    created: List[Tuple[FakeController, FakeRunner]] = []

    def factory(engine_type: str = "nerd-dictation", **kwargs):
        controller = FakeController()
        runner = FakeRunner(controller)
        created.append((controller, runner))
        return controller, runner

    monkeypatch.setattr("eloGraf.engine_manager.create_stt_engine", factory)
    return created


def _create_tray(fake_engine) -> SystemTrayIcon:
    ipc = FakeIPC()
    icon = QIcon()
    tray = SystemTrayIcon(icon, False, ipc, temporary_engine="fake-engine")
    tray.settings.sttEngine = "fake-engine"
    tray.settings.models = [{"name": "fake", "location": "/tmp/fake-model"}]
    return tray


def test_full_engine_workflow(fake_engine, qt_app):
    tray = _create_tray(fake_engine)
    controller, runner = fake_engine[-1]

    tray.begin()
    assert runner.is_running() is True
    assert tray.dictating is True
    assert controller.states[-1] == "READY"

    tray.suspend()
    assert tray.suspended is True
    assert controller.states[-1] == "SUSPENDED"

    tray.resume()
    assert tray.suspended is False
    assert controller.states[-1] == "READY"

    tray.end()
    assert runner.is_running() is False
    assert tray.dictating is False
    assert controller.exit_codes[-1] == 0


def test_settings_persistence_roundtrip(qt_app):
    backend = QSettings(QSettings.Format.IniFormat, QSettings.Scope.UserScope, "ElografIntegration", "PersistenceTest")
    backend.clear()

    settings = Settings(backend)
    settings.sttEngine = "openai-realtime"
    settings.openaiLanguage = "es"
    settings.deviceName = "test-device"
    settings.add_model("es", "fake-model", "1.0", "1GB", "vosk", "/tmp/fake-model")
    settings.save()

    reload_backend = QSettings(QSettings.Format.IniFormat, QSettings.Scope.UserScope, "ElografIntegration", "PersistenceTest")
    reloaded = Settings(reload_backend)
    reloaded.load()

    assert reloaded.sttEngine == "openai-realtime"
    assert reloaded.openaiLanguage == "es"
    assert reloaded.deviceName == "test-device"
    assert reloaded.models == [{
        "name": "fake-model",
        "language": "es",
        "version": "1.0",
        "size": "1GB",
        "type": "vosk",
        "location": "/tmp/fake-model",
    }]

    reload_backend.clear()


def test_error_recovery_triggers_retry(fake_engine, qt_app):
    tray = _create_tray(fake_engine)
    tray._engine_manager._retry_delay_ms = 1

    initial_controller, initial_runner = fake_engine[-1]

    tray.begin()
    assert initial_runner.is_running() is True

    initial_runner.fail()
    assert tray.dictating is False
    assert initial_controller.exit_codes[-1] == 1

    QTest.qWait(10)
    qt_app.processEvents()
    QTest.qWait(10)
    qt_app.processEvents()

    assert len(fake_engine) >= 2
    _, new_runner = fake_engine[-1]
    assert tray.dictation_runner is new_runner
    assert new_runner.is_running() is False
