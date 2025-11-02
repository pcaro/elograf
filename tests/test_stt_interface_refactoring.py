# ABOUTME: Tests for refactored STTController interface with explicit state transitions.
# ABOUTME: Verifies new transition_to(), emit_transcription(), emit_error() methods work across all engines.

from __future__ import annotations

import pytest

from eloGraf.engines.nerd.controller import NerdDictationController
from eloGraf.engines.nerd.settings import NerdSettings
from eloGraf.engines.whisper.controller import WhisperDockerController
from eloGraf.engines.whisper.settings import WhisperSettings

# Conditional imports for engines with optional dependencies
try:
    from eloGraf.engines.google.controller import GoogleCloudSpeechController
    from eloGraf.engines.google.settings import GoogleCloudSettings
    HAS_GOOGLE_CLOUD = True
except ImportError:
    HAS_GOOGLE_CLOUD = False

try:
    from eloGraf.engines.openai.controller import OpenAIRealtimeController
    from eloGraf.engines.openai.settings import OpenAISettings
    HAS_OPENAI = True
except ImportError:
    HAS_OPENAI = False

try:
    from eloGraf.engines.assemblyai.controller import AssemblyAIRealtimeController
    from eloGraf.engines.assemblyai.settings import AssemblyAISettings
    HAS_ASSEMBLYAI = True
except ImportError:
    HAS_ASSEMBLYAI = False


def make_nerd_controller(**kwargs) -> NerdDictationController:
    return NerdDictationController(NerdSettings(**kwargs))


def make_whisper_controller(**kwargs) -> WhisperDockerController:
    return WhisperDockerController(WhisperSettings(**kwargs))


if HAS_GOOGLE_CLOUD:
    def make_google_controller(**kwargs):
        return GoogleCloudSpeechController(GoogleCloudSettings(**kwargs))
else:
    def make_google_controller(**kwargs):  # pragma: no cover - guarded by skipif
        raise RuntimeError("Google Cloud controller unavailable")


if HAS_OPENAI:
    def make_openai_controller(**kwargs):
        return OpenAIRealtimeController(OpenAISettings(**kwargs))
else:
    def make_openai_controller(**kwargs):  # pragma: no cover - guarded by skipif
        raise RuntimeError("OpenAI controller unavailable")


if HAS_ASSEMBLYAI:
    def make_assembly_controller(**kwargs):
        return AssemblyAIRealtimeController(AssemblyAISettings(**kwargs))
else:
    def make_assembly_controller(**kwargs):  # pragma: no cover - guarded by skipif
        raise RuntimeError("AssemblyAI controller unavailable")


def test_nerd_controller_transition_to():
    """Test NerdDictationController.transition_to() method."""
    controller = make_nerd_controller()

    states_seen = []
    controller.add_state_listener(lambda state: states_seen.append(state))

    # Should be able to transition using unified method
    controller.transition_to("loading")
    controller.transition_to("ready")
    controller.transition_to("dictating")

    assert len(states_seen) >= 3


def test_nerd_controller_emit_transcription():
    """Test NerdDictationController.emit_transcription() method."""
    controller = make_nerd_controller()

    outputs = []
    controller.add_output_listener(lambda text: outputs.append(text))

    controller.emit_transcription("hello world")

    assert outputs == ["hello world"]


def test_nerd_controller_emit_error():
    """Test NerdDictationController.emit_error() method."""
    controller = make_nerd_controller()

    outputs = []
    controller.add_output_listener(lambda text: outputs.append(text))

    controller.emit_error("test error")

    assert "test error" in outputs or "error" in outputs[0].lower()


def test_whisper_controller_transition_to():
    """Test WhisperDockerController.transition_to() method."""
    controller = make_whisper_controller()

    states_seen = []
    controller.add_state_listener(lambda state: states_seen.append(state))

    controller.transition_to("ready")
    controller.transition_to("recording")
    controller.transition_to("transcribing")

    assert len(states_seen) >= 3


@pytest.mark.skipif(not HAS_GOOGLE_CLOUD, reason="google-cloud-speech not available")
def test_google_cloud_controller_transition_to():
    """Test GoogleCloudSpeechController.transition_to() method."""
    controller = make_google_controller()

    states_seen = []
    controller.add_state_listener(lambda state: states_seen.append(state))

    controller.transition_to("connecting")
    controller.transition_to("ready")
    controller.transition_to("recording")

    assert len(states_seen) >= 3


@pytest.mark.skipif(not HAS_OPENAI, reason="openai not available")
def test_openai_controller_transition_to():
    """Test OpenAIRealtimeController.transition_to() method."""
    controller = make_openai_controller()

    states_seen = []
    controller.add_state_listener(lambda state: states_seen.append(state))

    controller.transition_to("connecting")
    controller.transition_to("ready")
    controller.transition_to("recording")

    assert len(states_seen) >= 3


@pytest.mark.skipif(not HAS_ASSEMBLYAI, reason="websocket-client not available")
def test_assemblyai_controller_transition_to():
    """Test AssemblyAIRealtimeController.transition_to() method."""
    controller = make_assembly_controller()

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
    controller = make_assembly_controller()

    outputs = []
    controller.add_output_listener(lambda text: outputs.append(text))

    controller.emit_transcription("test transcription")

    assert outputs == ["test transcription"]


def test_all_controllers_have_unified_interface():
    """Test that all controllers implement the unified interface."""
    controllers = [
        make_nerd_controller(),
        make_whisper_controller(),
    ]

    if HAS_GOOGLE_CLOUD:
        controllers.append(make_google_controller())
    if HAS_OPENAI:
        controllers.append(make_openai_controller())
    if HAS_ASSEMBLYAI:
        controllers.append(make_assembly_controller())

    for controller in controllers:
        assert hasattr(controller, "transition_to")
        assert hasattr(controller, "emit_transcription")
        assert hasattr(controller, "emit_error")
        assert callable(controller.transition_to)
        assert callable(controller.emit_transcription)
        assert callable(controller.emit_error)
