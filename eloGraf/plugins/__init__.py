"""Built-in STT engine plugins."""

from __future__ import annotations

# Import modules for side effects (plugin registration)
from . import nerd  # noqa: F401
from . import whisper_docker  # noqa: F401
from . import google_cloud_speech  # noqa: F401
from . import openai_realtime  # noqa: F401
from . import assemblyai  # noqa: F401

__all__ = [
    "nerd",
    "whisper_docker",
    "google_cloud_speech",
    "openai_realtime",
    "assemblyai",
]
