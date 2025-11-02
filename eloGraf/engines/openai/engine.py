"""Plugin definition for OpenAI Realtime engine."""

from __future__ import annotations

from dataclasses import asdict
from typing import Dict, Tuple, TYPE_CHECKING

from eloGraf.engine_plugin import EnginePlugin, register_plugin
from .settings import OpenAISettings
from eloGraf.stt_engine import STTController, STTProcessRunner
from .controller import (
    OpenAIRealtimeController,
    OpenAIRealtimeProcessRunner,
)

if TYPE_CHECKING:  # pragma: no cover
    from eloGraf.settings import Settings


class OpenAIRealtimePlugin(EnginePlugin):
    """Built-in plugin for OpenAI Realtime streaming transcription."""

    @property
    def name(self) -> str:
        return "openai-realtime"

    @property
    def display_name(self) -> str:
        return "OpenAI Realtime"

    def get_settings_schema(self):  # type: ignore[override]
        return OpenAISettings

    def create_controller_runner(
        self, settings: OpenAISettings
    ) -> Tuple[STTController, STTProcessRunner]:  # type: ignore[override]
        params: Dict[str, object] = asdict(settings)
        params.pop("engine_type", None)
        device_name = params.pop("device_name", None)
        pulse_device = None
        if isinstance(device_name, str) and device_name and device_name != "default":
            pulse_device = device_name
        params["pulse_device"] = pulse_device
        controller = OpenAIRealtimeController(settings)
        runner = OpenAIRealtimeProcessRunner(controller, **params)
        return controller, runner

    def apply_to_settings(self, app_settings: 'Settings', engine_settings: OpenAISettings) -> None:
        app_settings.sttEngine = self.name
        app_settings.deviceName = engine_settings.device_name
        app_settings.openaiApiKey = engine_settings.api_key
        app_settings.openaiModel = engine_settings.model
        app_settings.openaiApiVersion = engine_settings.api_version
        app_settings.openaiSampleRate = engine_settings.sample_rate
        app_settings.openaiChannels = engine_settings.channels
        app_settings.openaiVadEnabled = engine_settings.vad_enabled
        app_settings.openaiVadThreshold = engine_settings.vad_threshold
        app_settings.openaiVadPrefixPaddingMs = engine_settings.vad_prefix_padding_ms
        app_settings.openaiVadSilenceDurationMs = engine_settings.vad_silence_duration_ms
        app_settings.openaiLanguage = engine_settings.language

    def check_availability(self):  # type: ignore[override]
        try:
            import websocket  # noqa: F401
        except ImportError:
            return False, "python package 'websocket-client' is not installed"
        return True, ""


register_plugin(OpenAIRealtimePlugin())
