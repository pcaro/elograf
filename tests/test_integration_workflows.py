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
from eloGraf.tray_icon import SystemTrayIcon


class FakeState:
    def __init__(self, name: str) -> None:
        self.name = name.upper()


class FakeController(STTController):
    def __init__(self) -> None:
        self._state_listeners: List[Callable[[object], None]] = []
        self._output_listeners: List[Callable[[str], None]] = []
        self._exit_listeners: List[Callable[[int], None]] = []
        self.states: List[str] = []
        self.outputs: List[str] = []
        self.exit_codes: List[int] = []

    def add_state_listener(self, callback: Callable[[object], None]) -> None:
        self._state_listeners.append(callback)

    def add_output_listener(self, callback: Callable[[str], None]) -> None:
        self._output_listeners.append(callback)

    def add_exit_listener(self, callback: Callable[[int], None]) -> None:
        self._exit_listeners.append(callback)

    def remove_exit_listener(self, callback: Callable[[int], None]) -> None:
        try:
            self._exit_listeners.remove(callback)
        except ValueError:
            pass

    def start(self) -> None:
        self.transition_to("loading")

    def stop_requested(self) -> None:
        self.transition_to("stopping")

    def suspend_requested(self) -> None:
        self.transition_to("suspended")

    def resume_requested(self) -> None:
        self.transition_to("ready")

    def fail_to_start(self) -> None:
        self.emit_error("failed to start")

    def handle_output(self, line: str) -> None:
        for callback in self._output_listeners:
            callback(line)

    def handle_exit(self, return_code: int) -> None:
        self.exit_codes.append(return_code)
        for callback in self._exit_listeners:
            callback(return_code)

    def transition_to(self, state: str) -> None:
        state_obj = FakeState(state)
        self.states.append(state_obj.name)
        for callback in self._state_listeners:
            callback(state_obj)

    def emit_transcription(self, text: str) -> None:
        self.outputs.append(text)
        for callback in self._output_listeners:
            callback(text)

    def emit_error(self, message: str) -> None:
        self.outputs.append(message)
        for callback in self._output_listeners:
            callback(message)
        self.transition_to("failed")


class FakeRunner(STTProcessRunner):
    def __init__(self, controller: FakeController) -> None:
        self._controller = controller
        self.running = False

    def start(self, command: Sequence[str], env: Optional[dict] = None) -> bool:
        if self.running:
            return False
        self.running = True
        self._controller.start()
        self._controller.transition_to("ready")
        return True

    def stop(self) -> None:
        if not self.running:
            return
        self._controller.stop_requested()
        self.running = False
        self._controller.transition_to("idle")
        self._controller.handle_exit(0)

    def suspend(self) -> None:
        if not self.running:
            return
        self._controller.suspend_requested()

    def resume(self) -> None:
        if not self.running:
            return
        self._controller.resume_requested()

    def poll(self) -> None:
        pass

    def is_running(self) -> bool:
        return self.running

    def fail(self) -> None:
        if not self.running:
            return
        self.running = False
        self._controller.emit_error("simulated failure")
        self._controller.handle_exit(1)


class FakeSignal:
    def __init__(self) -> None:
        self.callback = None

    def connect(self, callback):
        self.callback = callback

    def emit(self, value):
        if self.callback:
            self.callback(value)


class FakeIPC:
    def __init__(self) -> None:
        self.command_received = FakeSignal()
        self.cleanup_called = False

    def start_server(self) -> bool:
        return True

    def send_command(self, command: str) -> bool:
        self.last_command = command
        return True

    def supports_global_shortcuts(self) -> bool:
        return False

    def register_global_shortcut(self, action: str, shortcut: str, callback) -> bool:
        return False

    def cleanup(self) -> None:
        self.cleanup_called = True


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
