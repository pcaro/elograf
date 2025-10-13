"""Tests for Gemini Live API controller."""

import pytest
from eloGraf.engines.gemini.settings import GeminiSettings
from eloGraf.engines.gemini.controller import (
    GeminiLiveController,
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
