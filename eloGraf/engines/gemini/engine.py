# ABOUTME: Plugin definition for Gemini Live API engine.
# ABOUTME: Registers GeminiLivePlugin with engine registry and handles configuration.

from __future__ import annotations

from dataclasses import asdict
from typing import Dict, Tuple, TYPE_CHECKING

from eloGraf.engine_plugin import EnginePlugin, register_plugin
from .settings import GeminiSettings
from eloGraf.stt_engine import STTController, STTProcessRunner
from .controller import (
    GeminiLiveController,
    GeminiLiveProcessRunner,
)

if TYPE_CHECKING:  # pragma: no cover
    from eloGraf.settings import Settings


class GeminiLivePlugin(EnginePlugin):
    """Built-in plugin for Google Gemini Live API."""

    @property
    def name(self) -> str:
        return "gemini-live"

    @property
    def display_name(self) -> str:
        return "Gemini Live API"

    def get_settings_schema(self):  # type: ignore[override]
        return GeminiSettings

    def create_controller_runner(
        self, settings: GeminiSettings
    ) -> Tuple[STTController, STTProcessRunner]:  # type: ignore[override]
        params: Dict[str, object] = asdict(settings)
        params.pop("engine_type", None)
        device_name = params.pop("device_name", None)
        pulse_device = None
        if isinstance(device_name, str) and device_name and device_name != "default":
            pulse_device = device_name
        params["pulse_device"] = pulse_device
        controller = GeminiLiveController(settings)
        runner = GeminiLiveProcessRunner(controller, **params)
        return controller, runner

    def apply_to_settings(self, app_settings: 'Settings', engine_settings: GeminiSettings) -> None:
        app_settings.sttEngine = self.name
        app_settings.deviceName = engine_settings.device_name
        app_settings.geminiApiKey = engine_settings.api_key
        app_settings.geminiModel = engine_settings.model
        app_settings.geminiLanguageCode = engine_settings.language_code
        app_settings.geminiSampleRate = engine_settings.sample_rate
        app_settings.geminiChannels = engine_settings.channels
        app_settings.geminiVadEnabled = engine_settings.vad_enabled
        app_settings.geminiVadThreshold = engine_settings.vad_threshold

    def check_availability(self):  # type: ignore[override]
        try:
            import google.genai  # noqa: F401
        except ImportError:
            return False, "python package 'google-genai' is not installed"
        return True, ""


register_plugin(GeminiLivePlugin())
