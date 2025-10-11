import pytest
from unittest.mock import Mock, patch, MagicMock
from eloGraf.whisper_docker_controller import (
    WhisperDockerController,
    WhisperDockerProcessRunner,
    WhisperDockerState,
)


def test_controller_state_transitions():
    controller = WhisperDockerController()
    states = []

    def capture_state(state):
        states.append(state)

    controller.add_state_listener(capture_state)

    assert controller.state == WhisperDockerState.IDLE

    controller.start()
    assert controller.state == WhisperDockerState.STARTING
    assert states[-1] == WhisperDockerState.STARTING

    controller.set_ready()
    assert controller.state == WhisperDockerState.READY
    assert states[-1] == WhisperDockerState.READY

    controller.set_recording()
    assert controller.state == WhisperDockerState.RECORDING
    assert states[-1] == WhisperDockerState.RECORDING

    controller.set_transcribing()
    assert controller.state == WhisperDockerState.TRANSCRIBING
    assert states[-1] == WhisperDockerState.TRANSCRIBING


def test_controller_fail_to_start():
    controller = WhisperDockerController()
    exit_codes = []

    controller.add_exit_listener(lambda code: exit_codes.append(code))
    controller.fail_to_start()

    assert controller.state == WhisperDockerState.FAILED
    assert exit_codes == [1]


def test_controller_output_listener():
    controller = WhisperDockerController()
    outputs = []

    controller.add_output_listener(lambda line: outputs.append(line))
    controller.handle_output("test output")

    assert outputs == ["test output"]


def test_controller_handle_exit():
    controller = WhisperDockerController()
    exit_codes = []

    controller.add_exit_listener(lambda code: exit_codes.append(code))

    controller.handle_exit(0)
    assert controller.state == WhisperDockerState.IDLE
    assert exit_codes == [0]

    controller.handle_exit(1)
    assert controller.state == WhisperDockerState.FAILED
    assert exit_codes == [0, 1]


@patch('eloGraf.whisper_docker_controller.run')
@patch('eloGraf.whisper_docker_controller.requests')
def test_runner_start_container_not_running(mock_requests, mock_run):
    controller = WhisperDockerController()
    runner = WhisperDockerProcessRunner(controller, container_name="test-whisper")

    # Mock Docker ps showing container doesn't exist
    mock_run.return_value = Mock(stdout="", returncode=0)

    # Mock API health check
    mock_response = Mock()
    mock_response.status_code = 200
    mock_requests.get.return_value = mock_response

    result = runner.start([], env={})

    assert result == True
    assert controller.state == WhisperDockerState.READY


@patch('eloGraf.whisper_docker_controller.run')
def test_runner_is_container_running(mock_run):
    controller = WhisperDockerController()
    runner = WhisperDockerProcessRunner(controller, container_name="test-whisper")

    # Mock container is running
    mock_run.return_value = Mock(stdout="test-whisper\n", returncode=0)

    assert runner._is_container_running() == True

    # Mock container not running
    mock_run.return_value = Mock(stdout="", returncode=0)

    assert runner._is_container_running() == False


def test_runner_stop():
    controller = WhisperDockerController()
    runner = WhisperDockerProcessRunner(controller)

    # Start a mock recording thread
    runner._recording_thread = Mock()
    runner._recording_thread.is_alive.return_value = True
    runner._recording_thread.join = Mock()

    runner.stop()

    assert runner._stop_recording.is_set()
    assert controller.state == WhisperDockerState.IDLE


def test_factory_creates_whisper_docker_engine():
    from eloGraf.stt_factory import create_stt_engine

    controller, runner = create_stt_engine("whisper-docker")

    assert isinstance(controller, WhisperDockerController)
    assert isinstance(runner, WhisperDockerProcessRunner)


def test_factory_creates_nerd_dictation_engine():
    from eloGraf.stt_factory import create_stt_engine
    from eloGraf.nerd_controller import NerdDictationController, NerdDictationProcessRunner

    controller, runner = create_stt_engine("nerd-dictation")

    assert isinstance(controller, NerdDictationController)
    assert isinstance(runner, NerdDictationProcessRunner)


def test_factory_raises_on_invalid_engine():
    from eloGraf.stt_factory import create_stt_engine

    with pytest.raises(ValueError, match="Unsupported STT engine type"):
        create_stt_engine("invalid-engine")


def test_get_available_engines():
    from eloGraf.stt_factory import get_available_engines

    engines = get_available_engines()

    assert "nerd-dictation" in engines
    assert "whisper-docker" in engines


def test_settings_stt_engine_defaults():
    from eloGraf.settings import Settings
    from PyQt6.QtCore import QSettings

    # Create temporary settings
    backend = QSettings("TestOrg", "TestApp")
    settings = Settings(backend)

    # Check defaults
    assert settings.sttEngine == "nerd-dictation"
    assert settings.whisperModel == "base"
    assert settings.whisperLanguage == ""
    assert settings.whisperPort == 9000
