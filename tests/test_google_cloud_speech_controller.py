"""Tests for Google Cloud Speech controller."""

import pytest
from eloGraf.google_cloud_speech_controller import (
    GoogleCloudSpeechController,
    GoogleCloudSpeechProcessRunner,
    GoogleCloudSpeechState
)
from eloGraf.stt_factory import create_stt_engine, get_available_engines
from eloGraf.settings import Settings


def test_controller_state_transitions():
    """Test Google Cloud Speech controller state transitions."""
    controller = GoogleCloudSpeechController()

    assert controller.state == GoogleCloudSpeechState.IDLE

    controller.start()
    assert controller.state == GoogleCloudSpeechState.STARTING

    controller.set_ready()
    assert controller.state == GoogleCloudSpeechState.READY

    controller.set_recording()
    assert controller.state == GoogleCloudSpeechState.RECORDING

    controller.set_transcribing()
    assert controller.state == GoogleCloudSpeechState.TRANSCRIBING

    controller.handle_exit(0)
    assert controller.state == GoogleCloudSpeechState.IDLE


def test_controller_suspend_resume():
    """Test suspend/resume functionality."""
    controller = GoogleCloudSpeechController()

    assert not controller.is_suspended

    controller.suspend_requested()
    assert controller.state == GoogleCloudSpeechState.SUSPENDED
    assert controller.is_suspended

    controller.resume_requested()
    assert controller.state == GoogleCloudSpeechState.RECORDING
    assert not controller.is_suspended


def test_controller_fail_to_start():
    """Test controller handles failure to start."""
    controller = GoogleCloudSpeechController()

    exit_codes = []
    controller.add_exit_listener(lambda code: exit_codes.append(code))

    controller.fail_to_start()

    assert controller.state == GoogleCloudSpeechState.FAILED
    assert exit_codes == [1]


def test_controller_output_listener():
    """Test output listener receives messages."""
    controller = GoogleCloudSpeechController()

    outputs = []
    controller.add_output_listener(lambda line: outputs.append(line))

    controller.handle_output("Test output")
    controller.handle_output("Another output")

    assert outputs == ["Test output", "Another output"]


def test_controller_handle_exit():
    """Test controller handles exit codes."""
    controller = GoogleCloudSpeechController()

    # Successful exit
    controller.set_recording()
    controller.handle_exit(0)
    assert controller.state == GoogleCloudSpeechState.IDLE

    # Failed exit
    controller.set_recording()
    controller.handle_exit(1)
    assert controller.state == GoogleCloudSpeechState.FAILED


def test_runner_configuration():
    """Test runner accepts configuration parameters."""
    controller = GoogleCloudSpeechController()
    runner = GoogleCloudSpeechProcessRunner(
        controller,
        credentials_path="/path/to/creds.json",
        project_id="my-project",
        language_code="es-ES",
        model="chirp_3",
        sample_rate=22050,
        channels=2,
        vad_enabled=False,
        vad_threshold=1000.0,
    )

    assert runner._credentials_path == "/path/to/creds.json"
    assert runner._project_id == "my-project"
    assert runner._language_code == "es-ES"
    assert runner._model == "chirp_3"
    assert runner._sample_rate == 22050
    assert runner._channels == 2
    assert not runner._vad_enabled
    assert runner._vad_threshold == 1000.0


def test_runner_is_not_running_initially():
    """Test runner is not running initially."""
    controller = GoogleCloudSpeechController()
    runner = GoogleCloudSpeechProcessRunner(controller)

    assert not runner.is_running()


def test_factory_creates_google_cloud_speech_engine():
    """Test factory creates Google Cloud Speech engine."""
    controller, runner = create_stt_engine("google-cloud-speech")

    assert isinstance(controller, GoogleCloudSpeechController)
    assert isinstance(runner, GoogleCloudSpeechProcessRunner)


def test_factory_raises_on_invalid_engine():
    """Test factory raises ValueError for invalid engine type."""
    with pytest.raises(ValueError, match="Unsupported STT engine type"):
        create_stt_engine("invalid-engine")


def test_get_available_engines():
    """Test get_available_engines includes Google Cloud Speech."""
    engines = get_available_engines()
    assert "google-cloud-speech" in engines
    assert "nerd-dictation" in engines
    assert "whisper-docker" in engines


def test_settings_google_cloud_fields():
    """Test settings has Google Cloud Speech fields."""
    settings = Settings()
    settings.load()

    assert hasattr(settings, 'googleCloudCredentialsPath')
    assert hasattr(settings, 'googleCloudProjectId')
    assert hasattr(settings, 'googleCloudLanguageCode')
    assert hasattr(settings, 'googleCloudModel')
    assert hasattr(settings, 'googleCloudSampleRate')
    assert hasattr(settings, 'googleCloudChannels')
    assert hasattr(settings, 'googleCloudVadEnabled')
    assert hasattr(settings, 'googleCloudVadThreshold')

    # Test defaults
    assert settings.googleCloudLanguageCode == "en-US"
    assert settings.googleCloudModel == "chirp_3"
    assert settings.googleCloudSampleRate == 16000
    assert settings.googleCloudChannels == 1
    assert settings.googleCloudVadEnabled is True
    assert settings.googleCloudVadThreshold == 500.0
