# Centralized test helpers and mock objects
from __future__ import annotations

from typing import Callable, Dict, List, Optional, Sequence

from eloGraf.status import DictationStatus
from eloGraf.stt_engine import STTController, STTProcessRunner


class DummySettings:
    def __init__(self) -> None:
        self.sttEngine = "dummy"

    def get_engine_settings(self, engine_type: str):
        from eloGraf.base_settings import EngineSettings
        return EngineSettings(engine_type=engine_type, device_name="default")


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

    def get_status_string(self) -> str:
        return "Dummy Controller"

    @property
    def dictation_status(self) -> DictationStatus:
        return DictationStatus.IDLE


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

    def get_status_string(self) -> str:
        return "Fake Controller | Demo"

    @property
    def dictation_status(self) -> DictationStatus:
        last_state = self.states[-1] if self.states else "IDLE"
        if last_state in ("STARTING", "LOADING"):
            return DictationStatus.INITIALIZING
        elif last_state in ("READY", "DICTATING"):
            return DictationStatus.LISTENING
        elif last_state == "SUSPENDED":
            return DictationStatus.SUSPENDED
        elif last_state == "FAILED":
            return DictationStatus.FAILED
        return DictationStatus.IDLE


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
