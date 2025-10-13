import pytest
from unittest.mock import Mock, patch
from eloGraf.engines.whisper.controller import (
    WhisperDockerController,
    WhisperDockerProcessRunner,
    WhisperDockerState,
)
from eloGraf.engines.whisper.settings import WhisperSettings


def make_controller(**settings_kwargs) -> WhisperDockerController:
    return WhisperDockerController(WhisperSettings(**settings_kwargs))


def test_whisper_settings_defaults():
    settings = WhisperSettings()
    assert settings.engine_type == "whisper-docker"
    assert settings.model == "base"
    assert settings.port == 9000
    assert settings.device_name == "default"


def test_whisper_settings_custom_values():
    settings = WhisperSettings(model="large", port=9001, device_name="custom-device")
    assert settings.model == "large"
    assert settings.port == 9001
    assert settings.device_name == "custom-device"


def test_whisper_settings_validates_port_too_low():
    with pytest.raises(ValueError, match="Invalid port"):
        WhisperSettings(port=0)


def test_whisper_settings_validates_port_too_high():
    with pytest.raises(ValueError, match="Invalid port"):
        WhisperSettings(port=65536)


def test_whisper_settings_accepts_valid_ports():
    settings_low = WhisperSettings(port=1)
    settings_high = WhisperSettings(port=65535)
    assert settings_low.port == 1
    assert settings_high.port == 65535


def test_controller_state_transitions():
    controller = make_controller()
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
    controller = make_controller()
    exit_codes = []

    controller.add_exit_listener(lambda code: exit_codes.append(code))
    controller.fail_to_start()

    assert controller.state == WhisperDockerState.FAILED
    assert exit_codes == [1]


def test_controller_output_listener():
    controller = make_controller()
    outputs = []

    controller.add_output_listener(lambda line: outputs.append(line))
    controller.handle_output("test output")

    assert outputs == ["test output"]


def test_controller_handle_exit():
    controller = make_controller()
    exit_codes = []

    controller.add_exit_listener(lambda code: exit_codes.append(code))

    controller.handle_exit(0)
    assert controller.state == WhisperDockerState.IDLE
    assert exit_codes == [0]

    controller.handle_exit(1)
    assert controller.state == WhisperDockerState.FAILED
    assert exit_codes == [0, 1]


@patch('eloGraf.engines.whisper.controller.run')
@patch('eloGraf.engines.whisper.controller.requests')
def test_runner_start_container_not_running(mock_requests, mock_run):
    controller = make_controller()
    runner = WhisperDockerProcessRunner(controller, container_name="test-whisper")

    # Mock Docker ps showing container doesn't exist
    mock_run.return_value = Mock(stdout="", returncode=0)

    # Mock API health check
    mock_response = Mock()
    mock_response.status_code = 200
    mock_requests.get.return_value = mock_response

    assert runner._preflight_checks() is True
    assert runner._initialize_connection() is True
    assert controller.state == WhisperDockerState.READY


@patch('eloGraf.engines.whisper.controller.run')
def test_runner_is_container_running(mock_run):
    controller = make_controller()
    runner = WhisperDockerProcessRunner(controller, container_name="test-whisper")

    # Mock container is running
    mock_run.return_value = Mock(stdout="test-whisper\n", returncode=0)

    assert runner._is_container_running() == True

    # Mock container not running
    mock_run.return_value = Mock(stdout="", returncode=0)

    assert runner._is_container_running() == False


def test_runner_stop():
    controller = make_controller()
    runner = WhisperDockerProcessRunner(controller)

    mock_thread = Mock()
    mock_thread.is_alive.return_value = True
    mock_thread.join = Mock()
    runner._runner_thread = mock_thread
    runner._audio_recorder = Mock()

    runner.stop()

    assert runner._stop_event.is_set()
    mock_thread.join.assert_called_once()
    assert controller.state == WhisperDockerState.IDLE


def test_factory_creates_whisper_docker_engine():
    from eloGraf.stt_factory import create_stt_engine

    controller, runner = create_stt_engine("whisper-docker")

    assert isinstance(controller, WhisperDockerController)
    assert isinstance(runner, WhisperDockerProcessRunner)


def test_factory_creates_nerd_dictation_engine():
    from eloGraf.stt_factory import create_stt_engine
    from eloGraf.engines.nerd.controller import NerdDictationController, NerdDictationProcessRunner

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
