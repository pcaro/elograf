import io

import pytest

from eloGraf.engines.nerd.controller import (
    NerdDictationController,
    NerdDictationProcessRunner,
    NerdDictationState,
)
from eloGraf.engines.nerd.settings import NerdSettings


def make_controller(**settings_kwargs) -> NerdDictationController:
    return NerdDictationController(NerdSettings(**settings_kwargs))


class FakeProcess:
    def __init__(self, output_lines, return_code=0):
        content = "\n".join(output_lines)
        if content and not content.endswith("\n"):
            content += "\n"
        self.stdout = io.StringIO(content)
        self._return_code = return_code
        self.returncode = None

    def poll(self):
        return self.returncode

    def finish(self):
        self.returncode = self._return_code


class SelectStub:
    def __init__(self, process):
        self.process = process

    def __call__(self, rlist, wlist, xlist, timeout):
        stdout = rlist[0]
        current_pos = stdout.tell()
        stdout.seek(0, io.SEEK_END)
        end_pos = stdout.tell()
        stdout.seek(current_pos)
        if current_pos < end_pos:
            return (rlist, [], [])
        return ([], [], [])


def test_state_transitions_from_output():
    controller = make_controller()
    states = []
    outputs = []
    exits = []
    controller.add_state_listener(states.append)
    controller.add_output_listener(outputs.append)
    controller.add_exit_listener(exits.append)

    controller.start()
    controller.handle_output("Loading model...")
    controller.handle_output("Model loaded.")
    controller.handle_output("Dictation started")
    controller.handle_output("Dictation ended")
    controller.stop_requested()
    controller.handle_exit(0)

    assert NerdDictationState.LOADING in states
    assert NerdDictationState.READY in states
    assert NerdDictationState.DICTATING in states
    assert NerdDictationState.IDLE in states
    assert outputs == [
        "Loading model...",
        "Model loaded.",
        "Dictation started",
        "Dictation ended",
    ]
    assert exits == [0]
    assert controller.state == NerdDictationState.IDLE


def test_fail_to_start_marks_failed():
    controller = make_controller()
    states = []
    exits = []
    controller.add_state_listener(states.append)
    controller.add_exit_listener(exits.append)

    controller.fail_to_start()

    assert NerdDictationState.FAILED in states
    assert exits == [1]
    assert controller.state == NerdDictationState.FAILED


def test_runner_reads_output_and_handles_exit():
    controller = make_controller()
    states = []
    outputs = []
    exits = []
    controller.add_state_listener(states.append)
    controller.add_output_listener(outputs.append)
    controller.add_exit_listener(exits.append)

    process = FakeProcess(
        [
            "Loading model...",
            "Model loaded.",
            "Dictation started",
            "Dictation ended",
        ],
        return_code=0,
    )
    select_stub = SelectStub(process)

    runner = NerdDictationProcessRunner(
        controller,
        process_factory=lambda cmd, env: process,
        select_fn=select_stub,
        stop_runner=lambda: None,
    )

    assert runner.start(["nerd-dictation", "begin"])
    runner.poll()

    assert runner.is_running()
    assert NerdDictationState.READY in states
    assert outputs == [
        "Loading model...",
        "Model loaded.",
        "Dictation started",
        "Dictation ended",
    ]

    process.finish()
    runner.poll()

    assert not runner.is_running()
    assert NerdDictationState.IDLE in states
    assert exits == [0]


def test_runner_stop_requests_process():
    controller = make_controller()
    states = []
    controller.add_state_listener(states.append)

    process = FakeProcess(["Model loaded."])
    select_stub = SelectStub(process)
    stop_calls = []

    runner = NerdDictationProcessRunner(
        controller,
        process_factory=lambda cmd, env: process,
        select_fn=select_stub,
        stop_runner=lambda: stop_calls.append(True),
    )

    assert runner.start(["nerd-dictation", "begin"])
    runner.stop()

    assert NerdDictationState.STOPPING in states
    assert stop_calls == [True]

    process.finish()
    runner.poll()
    runner.stop()
    assert stop_calls == [True]


def test_runner_handles_start_failure(caplog):
    controller = make_controller()
    states = []
    exits = []
    controller.add_state_listener(states.append)
    controller.add_exit_listener(exits.append)

    def failing_factory(cmd, env):
        raise RuntimeError("boom")

    runner = NerdDictationProcessRunner(controller, process_factory=failing_factory)

    with caplog.at_level("ERROR"):
        assert not runner.start(["nerd-dictation", "begin"])

    assert NerdDictationState.FAILED in states
    assert exits == [1]
    assert any("Failed to start nerd-dictation" in record.message for record in caplog.records)


def test_controller_handles_suspend_and_resume_output():
    controller = make_controller()
    states = []
    controller.add_state_listener(states.append)

    controller.suspend_requested()
    assert controller.state == NerdDictationState.SUSPENDED

    controller.handle_output("dictation resumed")
    assert controller.state == NerdDictationState.DICTATING


def test_runner_suspend_and_resume_commands():
    controller = make_controller()
    process = FakeProcess(["Dictation resumed"])
    select_stub = SelectStub(process)
    suspend_calls = []
    resume_calls = []

    runner = NerdDictationProcessRunner(
        controller,
        process_factory=lambda cmd, env: process,
        select_fn=select_stub,
        stop_runner=lambda: None,
        suspend_runner=lambda: suspend_calls.append(True),
        resume_runner=lambda: resume_calls.append(True),
    )

    assert runner.start(["nerd-dictation", "begin"])
    runner.suspend()
    runner.resume()

    assert suspend_calls == [True]
    assert resume_calls == [True]


def test_plugin_apply_updates_settings(tmp_path):
    from PyQt6.QtCore import QSettings

    from eloGraf.engine_plugin import get_plugin
    from eloGraf.settings import Settings
    from eloGraf.engines.nerd.settings import NerdSettings

    backend_path = tmp_path / "settings.ini"
    backend = QSettings(str(backend_path), QSettings.Format.IniFormat)
    backend.clear()
    settings = Settings(backend)

    plugin = get_plugin("nerd-dictation")
    assert plugin is not None

    nerd_settings = NerdSettings(
        device_name="usb-mic",
        sample_rate=22050,
        timeout=15,
        idle_time=50,
        punctuate_timeout=3,
        full_sentence=True,
        digits=True,
        use_separator=True,
        free_command="--extra",
    )

    plugin.apply_to_settings(settings, nerd_settings)

    assert settings.sampleRate == 22050
    assert settings.timeout == 15
    assert settings.idleTime == 50
    assert settings.punctuate == 3
    assert settings.fullSentence is True
    assert settings.digits is True
    assert settings.useSeparator is True
    assert settings.freeCommand == "--extra"
    assert settings.deviceName == "usb-mic"
