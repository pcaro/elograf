"""Tests for OpenAI Realtime controller."""

import pytest
from eloGraf.engines.openai.controller import (
    OpenAIRealtimeController,
    OpenAIRealtimeProcessRunner,
    OpenAIRealtimeState,
)
from eloGraf.engines.openai.settings import OpenAISettings
from eloGraf.stt_factory import create_stt_engine, get_available_engines
from eloGraf.settings import Settings


def make_controller(**settings_kwargs) -> OpenAIRealtimeController:
    """Helper to build controller with optional settings overrides."""
    return OpenAIRealtimeController(OpenAISettings(**settings_kwargs))


def test_openai_settings_defaults():
    settings = OpenAISettings()
    assert settings.engine_type == "openai-realtime"
    assert settings.model == "gpt-4o-transcribe"
    assert settings.api_version == "2025-08-28"
    assert settings.sample_rate == 16000
    assert settings.channels == 1
    assert settings.vad_enabled is True
    assert settings.vad_threshold == 0.5
    assert settings.vad_prefix_padding_ms == 300
    assert settings.vad_silence_duration_ms == 200
    assert settings.language == "en-US"
    assert settings.api_key == ""


def test_openai_settings_validates_vad_threshold():
    with pytest.raises(ValueError, match="VAD threshold must be between 0 and 1"):
        OpenAISettings(vad_threshold=-0.1)
    with pytest.raises(ValueError, match="VAD threshold must be between 0 and 1"):
        OpenAISettings(vad_threshold=1.1)


def test_openai_settings_accepts_valid_vad_thresholds():
    settings_low = OpenAISettings(vad_threshold=0.0)
    settings_high = OpenAISettings(vad_threshold=1.0)
    assert settings_low.vad_threshold == 0.0
    assert settings_high.vad_threshold == 1.0


def test_controller_state_transitions():
    """Test OpenAI Realtime controller state transitions."""
    controller = make_controller()

    assert controller.state == OpenAIRealtimeState.IDLE

    controller.start()
    assert controller.state == OpenAIRealtimeState.STARTING

    controller.set_connecting()
    assert controller.state == OpenAIRealtimeState.CONNECTING

    controller.set_ready()
    assert controller.state == OpenAIRealtimeState.READY

    controller.set_recording()
    assert controller.state == OpenAIRealtimeState.RECORDING

    controller.set_transcribing()
    assert controller.state == OpenAIRealtimeState.TRANSCRIBING

    controller.handle_exit(0)
    assert controller.state == OpenAIRealtimeState.IDLE


def test_controller_suspend_resume():
    """Test suspend/resume functionality."""
    controller = make_controller()

    assert not controller.is_suspended

    controller.suspend_requested()
    assert controller.state == OpenAIRealtimeState.SUSPENDED
    assert controller.is_suspended

    controller.resume_requested()
    assert controller.state == OpenAIRealtimeState.RECORDING
    assert not controller.is_suspended


def test_controller_fail_to_start():
    """Test controller handles failure to start."""
    controller = make_controller()

    exit_codes = []
    controller.add_exit_listener(lambda code: exit_codes.append(code))

    controller.fail_to_start()

    assert controller.state == OpenAIRealtimeState.FAILED
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
    assert controller.state == OpenAIRealtimeState.IDLE

    # Failed exit
    controller.set_recording()
    controller.handle_exit(1)
    assert controller.state == OpenAIRealtimeState.FAILED


def test_runner_configuration():
    """Test runner accepts configuration parameters."""
    controller = make_controller()
    runner = OpenAIRealtimeProcessRunner(
        controller,
        api_key="sk-test-key",
        model="gpt-4o-mini-transcribe",
        api_version="2025-04-01-preview",
        sample_rate=22050,
        channels=2,
        chunk_duration=0.2,
        vad_enabled=False,
        vad_threshold=0.7,
        vad_prefix_padding_ms=500,
        vad_silence_duration_ms=300,
    )

    assert runner._api_key == "sk-test-key"
    assert runner._model == "gpt-4o-mini-transcribe"
    assert runner._api_version == "2025-04-01-preview"
    assert runner._sample_rate == 22050
    assert runner._channels == 2
    assert runner._chunk_duration == 0.2
    assert not runner._vad_enabled
    assert runner._vad_threshold == 0.7
    assert runner._vad_prefix_padding_ms == 500
    assert runner._vad_silence_duration_ms == 300


def test_runner_is_not_running_initially():
    """Test runner is not running initially."""
    controller = make_controller()
    runner = OpenAIRealtimeProcessRunner(controller, api_key="sk-test")

    assert not runner.is_running()


def test_factory_creates_openai_realtime_engine():
    """Test factory creates OpenAI Realtime engine."""
    controller, runner = create_stt_engine("openai-realtime", api_key="sk-test")

    assert isinstance(controller, OpenAIRealtimeController)
    assert isinstance(runner, OpenAIRealtimeProcessRunner)


def test_factory_raises_on_invalid_engine():
    """Test factory raises ValueError for invalid engine type."""
    with pytest.raises(ValueError, match="Unsupported STT engine type"):
        create_stt_engine("invalid-engine")


def test_get_available_engines():
    """Test get_available_engines includes OpenAI Realtime."""
    engines = get_available_engines()
    assert "openai-realtime" in engines
    assert "nerd-dictation" in engines
    assert "whisper-docker" in engines
    assert "google-cloud-speech" in engines


def test_settings_openai_fields():
    """Test settings has OpenAI Realtime fields."""
    settings = Settings()
    settings.load()

    assert hasattr(settings, 'openaiApiKey')
    assert hasattr(settings, 'openaiModel')
    assert hasattr(settings, 'openaiApiVersion')
    assert hasattr(settings, 'openaiSampleRate')
    assert hasattr(settings, 'openaiChannels')
    assert hasattr(settings, 'openaiVadEnabled')
    assert hasattr(settings, 'openaiVadThreshold')
    assert hasattr(settings, 'openaiVadPrefixPaddingMs')
    assert hasattr(settings, 'openaiVadSilenceDurationMs')

    # Test defaults
    assert settings.openaiModel == "gpt-4o-transcribe"
    assert settings.openaiApiVersion == "2025-08-28"
    assert settings.openaiSampleRate == 16000
    assert settings.openaiChannels == 1
    assert settings.openaiVadEnabled is True
    assert settings.openaiVadThreshold == 0.5
    assert settings.openaiVadPrefixPaddingMs == 300
    assert settings.openaiVadSilenceDurationMs == 200
