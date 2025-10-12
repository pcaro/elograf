from __future__ import annotations

import os
from datetime import datetime, timedelta
from typing import Dict, Optional, Sequence, Tuple

import pytest
from PyQt6.QtWidgets import QApplication

from eloGraf.engine_manager import EngineManager
from eloGraf.stt_engine import STTController, STTProcessRunner


class DummySettings:
    def __init__(self) -> None:
        self.sttEngine = "dummy"

    def get_engine_settings(self, engine_type: str):
        return {}


class DummyController(STTController):
    def __init__(self) -> None:
        self._exit_listeners: list = []

    def add_state_listener(self, callback) -> None:
        pass

    def add_output_listener(self, callback) -> None:
        pass

    def add_exit_listener(self, callback) -> None:
        self._exit_listeners.append(callback)

    def remove_exit_listener(self, callback) -> None:
        try:
            self._exit_listeners.remove(callback)
        except ValueError:
            pass

    def start(self) -> None:
        pass

    def stop_requested(self) -> None:
        pass

    def suspend_requested(self) -> None:
        pass

    def resume_requested(self) -> None:
        pass

    def fail_to_start(self) -> None:
        pass

    def handle_output(self, line: str) -> None:
        pass

    def handle_exit(self, return_code: int) -> None:
        for listener in self._exit_listeners:
            listener(return_code)

    def transition_to(self, state: str) -> None:
        pass

    def emit_transcription(self, text: str) -> None:
        pass

    def emit_error(self, message: str) -> None:
        pass


class HangingRunner(STTProcessRunner):
    def __init__(self) -> None:
        self.running = True
        self.stop_calls = 0
        self.force_stop_calls = 0

    def start(self, command: Sequence[str], env: Optional[Dict[str, str]] = None) -> bool:
        self.running = True
        return True

    def stop(self) -> None:
        self.stop_calls += 1

    def force_stop(self) -> None:
        self.force_stop_calls += 1
        self.running = False

    def suspend(self) -> None:
        pass

    def resume(self) -> None:
        pass

    def poll(self) -> None:
        pass

    def is_running(self) -> bool:
        return self.running


class AutoStoppingRunner(STTProcessRunner):
    def __init__(self) -> None:
        self.running = True
        self.stop_calls = 0

    def start(self, command: Sequence[str], env: Optional[Dict[str, str]] = None) -> bool:
        self.running = True
        return True

    def stop(self) -> None:
        self.stop_calls += 1
        self.running = False

    def suspend(self) -> None:
        pass

    def resume(self) -> None:
        pass

    def poll(self) -> None:
        pass

    def is_running(self) -> bool:
        return self.running


class DummyRunner(STTProcessRunner):
    def __init__(self) -> None:
        self.running = False

    def start(self, command: Sequence[str], env: Optional[Dict[str, str]] = None) -> bool:
        self.running = True
        return True

    def stop(self) -> None:
        self.running = False

    def suspend(self) -> None:
        pass

    def resume(self) -> None:
        pass

    def poll(self) -> None:
        pass

    def is_running(self) -> bool:
        return self.running


@pytest.fixture(scope="module")
def qt_app():
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    app = QApplication.instance()
    if not app:
        app = QApplication([])
    yield app


def test_refresh_timeout_forces_new_engine(monkeypatch, qt_app):
    settings = DummySettings()
    manager = EngineManager(settings, refresh_timeout_ms=1)
    hanging_runner = HangingRunner()
    manager._runner = hanging_runner
    manager._controller = DummyController()

    created_runners: list[DummyRunner] = []

    def fake_create_engine(engine_type: str, settings) -> Tuple[DummyController, DummyRunner]:
        runner = DummyRunner()
        created_runners.append(runner)
        return DummyController(), runner

    monkeypatch.setattr("eloGraf.engine_manager.create_stt_engine", fake_create_engine)

    manager.refresh_engine(stop_callback=hanging_runner.stop, poll_timer=None)
    assert manager._pending_refresh is True
    assert hanging_runner.stop_calls == 1

    manager._on_refresh_timeout()

    assert hanging_runner.force_stop_calls == 1
    assert created_runners, "Refresh should create a new runner after forcing stop"
    assert manager._runner is created_runners[-1]
    assert manager._pending_refresh is False
    if manager._refresh_timeout_timer:
        assert not manager._refresh_timeout_timer.isActive()


def test_refresh_timeout_cancels_after_success(monkeypatch, qt_app):
    settings = DummySettings()
    manager = EngineManager(settings, refresh_timeout_ms=50)
    auto_runner = AutoStoppingRunner()
    manager._runner = auto_runner
    manager._controller = DummyController()

    created_runners: list[DummyRunner] = []

    def fake_create_engine(engine_type: str, settings) -> Tuple[DummyController, DummyRunner]:
        runner = DummyRunner()
        created_runners.append(runner)
        return DummyController(), runner

    monkeypatch.setattr("eloGraf.engine_manager.create_stt_engine", fake_create_engine)

    manager.refresh_engine(stop_callback=auto_runner.stop, poll_timer=None)
    assert manager._pending_refresh is True
    assert auto_runner.stop_calls == 1
    assert manager._refresh_timeout_timer and manager._refresh_timeout_timer.isActive()

    manager.handle_exit(0)

    assert manager._pending_refresh is False
    assert created_runners, "Successful exit should trigger refresh"
    assert manager._runner is created_runners[-1]
    assert manager._refresh_timeout_timer and not manager._refresh_timeout_timer.isActive()


def test_circuit_breaker_switches_to_fallback(monkeypatch, qt_app):
    settings = DummySettings()
    settings.sttEngine = "openai-realtime"
    manager = EngineManager(settings, max_retries=2, retry_delay_ms=1)

    created_engines: list[str] = []

    def fake_create_engine(engine_type: str, settings) -> Tuple[DummyController, DummyRunner]:
        created_engines.append(engine_type)
        controller = DummyController()
        runner = DummyRunner()
        manager._controller = controller
        manager._runner = runner
        return controller, runner

    monkeypatch.setattr("eloGraf.engine_manager.create_stt_engine", fake_create_engine)

    manager.create_engine()
    assert created_engines[-1] == "openai-realtime"

    manager.handle_exit(1)
    manager.handle_exit(1)

    assert manager.active_engine_type == "whisper-docker"
    assert created_engines[-1] == "whisper-docker"
    assert manager._failure_count == 0


def test_circuit_breaker_calls_fatal_without_fallback(monkeypatch, qt_app):
    settings = DummySettings()
    settings.sttEngine = "nerd-dictation"
    manager = EngineManager(settings, max_retries=1, retry_delay_ms=1)

    created_engines: list[str] = []

    def fake_create_engine(engine_type: str, settings) -> Tuple[DummyController, DummyRunner]:
        created_engines.append(engine_type)
        controller = DummyController()
        runner = DummyRunner()
        manager._controller = controller
        manager._runner = runner
        return controller, runner

    monkeypatch.setattr("eloGraf.engine_manager.create_stt_engine", fake_create_engine)

    manager.create_engine()
    fatal_called = False

    def on_fatal():
        nonlocal fatal_called
        fatal_called = True

    manager.handle_exit(1, on_fatal_error=on_fatal)

    assert fatal_called is True
    assert manager._temporary_engine is None
    assert manager._circuit_open_until is not None
    assert created_engines == ["nerd-dictation"]


def test_circuit_breaker_restores_primary_after_window(monkeypatch, qt_app):
    settings = DummySettings()
    settings.sttEngine = "openai-realtime"
    manager = EngineManager(settings, max_retries=1, retry_delay_ms=1)

    created_engines: list[str] = []

    def fake_create_engine(engine_type: str, settings) -> Tuple[DummyController, DummyRunner]:
        created_engines.append(engine_type)
        controller = DummyController()
        runner = DummyRunner()
        manager._controller = controller
        manager._runner = runner
        return controller, runner

    monkeypatch.setattr("eloGraf.engine_manager.create_stt_engine", fake_create_engine)

    manager.create_engine()
    manager.handle_exit(1)
    assert manager.active_engine_type == "whisper-docker"
    fallback_runner = manager._runner
    assert fallback_runner is not None

    manager._circuit_open_until = datetime.now() - timedelta(seconds=1)
    manager.handle_exit(0)

    assert manager.active_engine_type == "openai-realtime"
    assert manager._temporary_engine is None
    assert created_engines[-1] == "openai-realtime"


def test_old_controller_exit_after_refresh_doesnt_affect_new_engine(monkeypatch, qt_app):
    """Test that old controller exit events don't affect new engine after refresh."""
    settings = DummySettings()
    manager = EngineManager(settings, max_retries=2, retry_delay_ms=1)

    # Set up the exit callback that tray_icon would normally set
    manager.on_exit = lambda return_code: manager.handle_exit(return_code)

    created_controllers: list[DummyController] = []

    def fake_create_engine(engine_type: str, settings) -> Tuple[DummyController, DummyRunner]:
        controller = DummyController()
        runner = DummyRunner()
        created_controllers.append(controller)
        manager._controller = controller
        manager._runner = runner
        return controller, runner

    monkeypatch.setattr("eloGraf.engine_manager.create_stt_engine", fake_create_engine)

    # Create initial engine
    manager.create_engine()
    old_controller = created_controllers[0]
    assert manager._failure_count == 0
    assert len(old_controller._exit_listeners) == 1, "Old controller should have exit listener"

    # Simulate refresh by directly creating new engine (bypassing the stop logic)
    manager.create_engine()
    new_controller = created_controllers[1]
    assert new_controller is not old_controller
    assert manager._controller is new_controller
    assert manager._failure_count == 0
    assert len(new_controller._exit_listeners) == 1, "New controller should have exit listener"

    # Simulate old controller's exit handler firing AFTER new engine created
    # This mimics the race: old process exits late, fires its registered callback
    old_controller.handle_exit(1)  # Old engine exited with error

    # BUG: Without fix, this increments failure_count for the NEW engine
    # Expected: failure_count should remain 0 (old controller events ignored)
    assert manager._failure_count == 0, "Old controller exit should not affect new engine"
    assert manager._controller is new_controller, "Should still have new controller"
