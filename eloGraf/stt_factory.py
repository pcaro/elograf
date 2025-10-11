# ABOUTME: Factory functions for creating STT engine controllers and runners.
# ABOUTME: Allows selection between different speech-to-text engines (nerd-dictation, Whisper Docker, etc.).

from __future__ import annotations

import logging
from typing import Optional, Tuple

from eloGraf.stt_engine import STTController, STTProcessRunner


def create_stt_engine(
    engine_type: str = "nerd-dictation",
    **kwargs
) -> Tuple[STTController, STTProcessRunner]:
    """
    Create an STT controller and runner for the specified engine type.

    Args:
        engine_type: Type of STT engine ("nerd-dictation", "whisper-docker", "google-cloud-speech", or "openai-realtime")
        **kwargs: Additional engine-specific configuration

    Returns:
        Tuple of (STTController, STTProcessRunner)

    Raises:
        ValueError: If engine_type is not supported
    """
    if engine_type == "nerd-dictation":
        return _create_nerd_dictation_engine(**kwargs)
    elif engine_type == "whisper-docker":
        return _create_whisper_docker_engine(**kwargs)
    elif engine_type == "google-cloud-speech":
        return _create_google_cloud_speech_engine(**kwargs)
    elif engine_type == "openai-realtime":
        return _create_openai_realtime_engine(**kwargs)
    else:
        raise ValueError(f"Unsupported STT engine type: {engine_type}")


def _create_nerd_dictation_engine(**kwargs) -> Tuple[STTController, STTProcessRunner]:
    """Create nerd-dictation controller and runner."""
    from eloGraf.nerd_controller import NerdDictationController, NerdDictationProcessRunner

    controller = NerdDictationController()
    runner = NerdDictationProcessRunner(controller, **kwargs)

    logging.info("Created nerd-dictation STT engine")
    return controller, runner


def _create_whisper_docker_engine(**kwargs) -> Tuple[STTController, STTProcessRunner]:
    """Create Whisper Docker controller and runner."""
    from eloGraf.whisper_docker_controller import WhisperDockerController, WhisperDockerProcessRunner

    controller = WhisperDockerController()
    runner = WhisperDockerProcessRunner(controller, **kwargs)

    logging.info("Created Whisper Docker STT engine")
    return controller, runner


def _create_google_cloud_speech_engine(**kwargs) -> Tuple[STTController, STTProcessRunner]:
    """Create Google Cloud Speech controller and runner."""
    from eloGraf.google_cloud_speech_controller import (
        GoogleCloudSpeechController,
        GoogleCloudSpeechProcessRunner
    )

    controller = GoogleCloudSpeechController()
    runner = GoogleCloudSpeechProcessRunner(controller, **kwargs)

    logging.info("Created Google Cloud Speech STT engine")
    return controller, runner


def _create_openai_realtime_engine(**kwargs) -> Tuple[STTController, STTProcessRunner]:
    """Create OpenAI Realtime API controller and runner."""
    from eloGraf.openai_realtime_controller import (
        OpenAIRealtimeController,
        OpenAIRealtimeProcessRunner
    )

    controller = OpenAIRealtimeController()
    runner = OpenAIRealtimeProcessRunner(controller, **kwargs)

    logging.info("Created OpenAI Realtime STT engine")
    return controller, runner


def get_available_engines() -> list[str]:
    """
    Get list of available STT engines.

    Returns:
        List of engine names
    """
    return ["nerd-dictation", "whisper-docker", "google-cloud-speech", "openai-realtime"]


def is_engine_available(engine_type: str) -> bool:
    """
    Check if an STT engine is available on the system.

    Args:
        engine_type: Type of STT engine to check

    Returns:
        True if engine is available, False otherwise
    """
    if engine_type == "nerd-dictation":
        return _check_nerd_dictation_available()
    elif engine_type == "whisper-docker":
        return _check_docker_available()
    elif engine_type == "google-cloud-speech":
        return _check_google_cloud_speech_available()
    elif engine_type == "openai-realtime":
        return _check_openai_realtime_available()
    else:
        return False


def _check_nerd_dictation_available() -> bool:
    """Check if nerd-dictation is installed."""
    import shutil
    return shutil.which("nerd-dictation") is not None


def _check_docker_available() -> bool:
    """Check if Docker is available."""
    import shutil
    return shutil.which("docker") is not None


def _check_google_cloud_speech_available() -> bool:
    """Check if google-cloud-speech library is installed."""
    try:
        import google.cloud.speech_v2
        return True
    except ImportError:
        return False


def _check_openai_realtime_available() -> bool:
    """Check if websocket-client library is installed."""
    try:
        import websocket
        return True
    except ImportError:
        return False
