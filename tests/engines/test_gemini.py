"""Tests for Gemini Live API controller."""

import pytest
from eloGraf.engines.gemini.settings import GeminiSettings
from eloGraf.engines.gemini.controller import (
    GeminiLiveController,
    GeminiLiveProcessRunner,
    GeminiLiveState,
)


def make_controller(**settings_kwargs) -> GeminiLiveController:
    return GeminiLiveController(GeminiSettings(**settings_kwargs))


def test_gemini_settings_defaults():
    settings = GeminiSettings()
    assert settings.engine_type == "gemini-live"
    assert settings.api_key == ""
    assert settings.model == "gemini-2.5-flash"
    assert settings.sample_rate == 16000
    assert settings.channels == 1
    assert settings.vad_enabled is True
    assert settings.vad_threshold == 500.0
    assert settings.language_code == "en-US"


def test_gemini_settings_validates_sample_rate():
    with pytest.raises(ValueError, match="Invalid sample rate"):
        GeminiSettings(sample_rate=7999)
    with pytest.raises(ValueError, match="Invalid sample rate"):
        GeminiSettings(sample_rate=48001)


def test_gemini_settings_accepts_valid_sample_rates():
    settings_low = GeminiSettings(sample_rate=8000)
    settings_high = GeminiSettings(sample_rate=48000)
    assert settings_low.sample_rate == 8000
    assert settings_high.sample_rate == 48000


def test_gemini_settings_validates_channels():
    with pytest.raises(ValueError, match="Gemini Live API requires mono audio"):
        GeminiSettings(channels=2)


def test_controller_state_transitions():
    """Test Gemini Live controller state transitions."""
    controller = make_controller()

    assert controller.state == GeminiLiveState.IDLE

    controller.start()
    assert controller.state == GeminiLiveState.STARTING

    controller.set_ready()
    assert controller.state == GeminiLiveState.READY

    controller.set_recording()
    assert controller.state == GeminiLiveState.RECORDING

    controller.set_transcribing()
    assert controller.state == GeminiLiveState.TRANSCRIBING

    controller.handle_exit(0)
    assert controller.state == GeminiLiveState.IDLE


def test_controller_suspend_resume():
    """Test suspend/resume functionality."""
    controller = make_controller()

    assert not controller.is_suspended

    controller.suspend_requested()
    assert controller.state == GeminiLiveState.SUSPENDED
    assert controller.is_suspended

    controller.resume_requested()
    assert controller.state == GeminiLiveState.RECORDING
    assert not controller.is_suspended


def test_controller_fail_to_start():
    """Test controller handles failure to start."""
    controller = make_controller()

    exit_codes = []
    controller.add_exit_listener(lambda code: exit_codes.append(code))

    controller.fail_to_start()

    assert controller.state == GeminiLiveState.FAILED
    assert exit_codes == [1]


def test_controller_output_listener():
    """Test output listener receives messages."""
    controller = make_controller()

    outputs = []
    controller.add_output_listener(lambda line: outputs.append(line))

    controller.handle_output("Test output")
    controller.handle_output("Another output")

    assert outputs == ["Test output", "Another output"]


def test_controller_handle_exit():
    """Test controller handles exit codes."""
    controller = make_controller()

    # Successful exit
    controller.set_recording()
    controller.handle_exit(0)
    assert controller.state == GeminiLiveState.IDLE

    # Failed exit
    controller.set_recording()
    controller.handle_exit(1)
    assert controller.state == GeminiLiveState.FAILED


def test_runner_configuration():
    """Test runner accepts configuration parameters."""
    controller = make_controller()
    runner = GeminiLiveProcessRunner(
        controller,
        api_key="test-api-key",
        model="gemini-2.0-flash",
        language_code="fr-FR",
        sample_rate=24000,
        channels=1,
        chunk_duration=0.2,
        vad_enabled=False,
        vad_threshold=1000.0,
        pulse_device="test-device",
    )

    assert runner._api_key == "test-api-key"
    assert runner._model == "gemini-2.0-flash"
    assert runner._language_code == "fr-FR"
    assert runner._sample_rate == 24000
    assert runner._channels == 1
    assert runner._chunk_duration == 0.2
    assert not runner._vad_enabled
    assert runner._vad_threshold == 1000.0
    assert runner._pulse_device == "test-device"


def test_runner_is_not_running_initially():
    """Test runner is not running initially."""
    controller = make_controller()
    runner = GeminiLiveProcessRunner(controller, api_key="test-key")

    assert not runner.is_running()


def test_factory_creates_gemini_live_engine():
    """Test factory creates Gemini Live engine."""
    from eloGraf.stt_factory import create_stt_engine

    controller, runner = create_stt_engine("gemini-live")

    assert isinstance(controller, GeminiLiveController)
    assert isinstance(runner, GeminiLiveProcessRunner)


def test_get_available_engines_includes_gemini():
    """Test get_available_engines includes Gemini Live."""
    from eloGraf.stt_factory import get_available_engines

    engines = get_available_engines()
    assert "gemini-live" in engines


def test_settings_gemini_fields():
    """Test settings has Gemini Live fields."""
    from eloGraf.settings import Settings

    settings = Settings()
    settings.load()

    assert hasattr(settings, 'geminiApiKey')
    assert hasattr(settings, 'geminiModel')
    assert hasattr(settings, 'geminiLanguageCode')
    assert hasattr(settings, 'geminiSampleRate')
    assert hasattr(settings, 'geminiChannels')
    assert hasattr(settings, 'geminiVadEnabled')
    assert hasattr(settings, 'geminiVadThreshold')

    # Test defaults
    assert settings.geminiModel == "gemini-2.5-flash"
    assert settings.geminiLanguageCode == "en-US"
    assert settings.geminiSampleRate == 16000
    assert settings.geminiChannels == 1
    assert settings.geminiVadEnabled is True
    assert settings.geminiVadThreshold == 500.0
