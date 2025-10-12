"""Plugin definition for AssemblyAI Realtime engine."""

from __future__ import annotations

from dataclasses import asdict
from typing import Dict, Tuple, TYPE_CHECKING

from eloGraf.engine_plugin import EnginePlugin, register_plugin
from eloGraf.settings_schema import AssemblyAISettings
from eloGraf.stt_engine import STTController, STTProcessRunner

if TYPE_CHECKING:  # pragma: no cover - import for type hints only
    from eloGraf.settings import Settings
    from .controller import (
        AssemblyAIRealtimeController,
        AssemblyAIRealtimeProcessRunner,
    )


class AssemblyAIRealtimePlugin(EnginePlugin):
    """Built-in plugin for AssemblyAI Realtime streaming."""

    @property
    def name(self) -> str:
        return "assemblyai"

    @property
    def display_name(self) -> str:
        return "AssemblyAI Realtime"

    def get_settings_schema(self):  # type: ignore[override]
        return AssemblyAISettings

    def create_controller_runner(
        self, settings: AssemblyAISettings
    ) -> Tuple[STTController, STTProcessRunner]:  # type: ignore[override]
        params: Dict[str, object] = asdict(settings)
        params.pop("engine_type", None)
        device_name = params.pop("device_name", None)
        pulse_device = None
        if isinstance(device_name, str) and device_name and device_name != "default":
            pulse_device = device_name
        params["pulse_device"] = pulse_device
        from .controller import (
            AssemblyAIRealtimeController,
            AssemblyAIRealtimeProcessRunner,
        )

        controller = AssemblyAIRealtimeController()
        runner = AssemblyAIRealtimeProcessRunner(controller, **params)
        return controller, runner

    def apply_to_settings(self, app_settings: 'Settings', engine_settings: AssemblyAISettings) -> None:
        app_settings.sttEngine = self.name
        app_settings.deviceName = engine_settings.device_name
        app_settings.assemblyApiKey = engine_settings.api_key
        app_settings.assemblyModel = engine_settings.model
        app_settings.assemblyLanguage = engine_settings.language
        app_settings.assemblySampleRate = engine_settings.sample_rate
        app_settings.assemblyChannels = engine_settings.channels

    def check_availability(self):  # type: ignore[override]
        try:
            import websocket  # noqa: F401
            import requests  # noqa: F401
        except ImportError as exc:
            missing = "websocket-client" if exc.name == "websocket" else "requests"
            return False, f"python package '{missing}' is not installed"
        return True, ""


register_plugin(AssemblyAIRealtimePlugin())
