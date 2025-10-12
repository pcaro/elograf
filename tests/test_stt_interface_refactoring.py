# ABOUTME: Tests for refactored STTController interface with explicit state transitions.
# ABOUTME: Verifies new transition_to(), emit_transcription(), emit_error() methods work across all engines.

from __future__ import annotations

import pytest

from eloGraf.nerd_controller import NerdDictationController
from eloGraf.whisper_docker_controller import WhisperDockerController

# Conditional imports for engines with optional dependencies
try:
    from eloGraf.google_cloud_speech_controller import GoogleCloudSpeechController
    HAS_GOOGLE_CLOUD = True
except ImportError:
    HAS_GOOGLE_CLOUD = False

try:
    from eloGraf.openai_realtime_controller import OpenAIRealtimeController
    HAS_OPENAI = True
except ImportError:
    HAS_OPENAI = False

try:
    from eloGraf.assemblyai_realtime_controller import AssemblyAIRealtimeController
    HAS_ASSEMBLYAI = True
except ImportError:
    HAS_ASSEMBLYAI = False


def test_nerd_controller_transition_to():
    """Test NerdDictationController.transition_to() method."""
    controller = NerdDictationController()

    states_seen = []
    controller.add_state_listener(lambda state: states_seen.append(state))

    # Should be able to transition using unified method
    controller.transition_to("loading")
    controller.transition_to("ready")
    controller.transition_to("dictating")

    assert len(states_seen) >= 3


def test_nerd_controller_emit_transcription():
    """Test NerdDictationController.emit_transcription() method."""
    controller = NerdDictationController()

    outputs = []
    controller.add_output_listener(lambda text: outputs.append(text))

    controller.emit_transcription("hello world")

    assert outputs == ["hello world"]


def test_nerd_controller_emit_error():
    """Test NerdDictationController.emit_error() method."""
    controller = NerdDictationController()

    outputs = []
    controller.add_output_listener(lambda text: outputs.append(text))

    controller.emit_error("test error")

    assert "test error" in outputs or "error" in outputs[0].lower()


def test_whisper_controller_transition_to():
    """Test WhisperDockerController.transition_to() method."""
    controller = WhisperDockerController()

    states_seen = []
    controller.add_state_listener(lambda state: states_seen.append(state))

    controller.transition_to("ready")
    controller.transition_to("recording")
    controller.transition_to("transcribing")

    assert len(states_seen) >= 3


@pytest.mark.skipif(not HAS_GOOGLE_CLOUD, reason="google-cloud-speech not available")
def test_google_cloud_controller_transition_to():
    """Test GoogleCloudSpeechController.transition_to() method."""
    controller = GoogleCloudSpeechController()

    states_seen = []
    controller.add_state_listener(lambda state: states_seen.append(state))

    controller.transition_to("connecting")
    controller.transition_to("ready")
    controller.transition_to("recording")

    assert len(states_seen) >= 3


@pytest.mark.skipif(not HAS_OPENAI, reason="openai not available")
def test_openai_controller_transition_to():
    """Test OpenAIRealtimeController.transition_to() method."""
    controller = OpenAIRealtimeController()

    states_seen = []
    controller.add_state_listener(lambda state: states_seen.append(state))

    controller.transition_to("connecting")
    controller.transition_to("ready")
    controller.transition_to("recording")

    assert len(states_seen) >= 3


@pytest.mark.skipif(not HAS_ASSEMBLYAI, reason="websocket-client not available")
def test_assemblyai_controller_transition_to():
    """Test AssemblyAIRealtimeController.transition_to() method."""
    controller = AssemblyAIRealtimeController()

    states_seen = []
    controller.add_state_listener(lambda state: states_seen.append(state))

    controller.transition_to("connecting")
    controller.transition_to("ready")
    controller.transition_to("recording")
    controller.transition_to("transcribing")

    assert len(states_seen) >= 4


@pytest.mark.skipif(not HAS_ASSEMBLYAI, reason="websocket-client not available")
def test_assemblyai_controller_emit_transcription():
    """Test AssemblyAIRealtimeController.emit_transcription() method."""
    controller = AssemblyAIRealtimeController()

    outputs = []
    controller.add_output_listener(lambda text: outputs.append(text))

    controller.emit_transcription("test transcription")

    assert outputs == ["test transcription"]


def test_all_controllers_have_unified_interface():
    """Test that all controllers implement the unified interface."""
    controllers = [
        NerdDictationController(),
        WhisperDockerController(),
    ]

    if HAS_GOOGLE_CLOUD:
        controllers.append(GoogleCloudSpeechController())
    if HAS_OPENAI:
        controllers.append(OpenAIRealtimeController())
    if HAS_ASSEMBLYAI:
        controllers.append(AssemblyAIRealtimeController())

    for controller in controllers:
        assert hasattr(controller, "transition_to")
        assert hasattr(controller, "emit_transcription")
        assert hasattr(controller, "emit_error")
        assert callable(controller.transition_to)
        assert callable(controller.emit_transcription)
        assert callable(controller.emit_error)
