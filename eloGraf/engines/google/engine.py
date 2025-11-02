"""Plugin definition for Google Cloud Speech engine."""

from __future__ import annotations

from dataclasses import asdict
from typing import Dict, Tuple, TYPE_CHECKING

from eloGraf.engine_plugin import EnginePlugin, register_plugin, register_plugin_alias
from .settings import GoogleCloudSettings
from eloGraf.stt_engine import STTController, STTProcessRunner
from .controller import (
    GoogleCloudSpeechController,
    GoogleCloudSpeechProcessRunner,
)

if TYPE_CHECKING:  # pragma: no cover
    from eloGraf.settings import Settings


class GoogleCloudSpeechPlugin(EnginePlugin):
    """Built-in plugin for Google Cloud Speech-to-Text."""

    @property
    def name(self) -> str:
        return "google-cloud-speech"

    @property
    def display_name(self) -> str:
        return "Google Cloud Speech"

    def get_settings_schema(self):  # type: ignore[override]
        return GoogleCloudSettings

    def create_controller_runner(
        self, settings: GoogleCloudSettings
    ) -> Tuple[STTController, STTProcessRunner]:  # type: ignore[override]
        params: Dict[str, object] = asdict(settings)
        params.pop("engine_type", None)
        params.pop("device_name", None)
        controller = GoogleCloudSpeechController(settings)
        runner = GoogleCloudSpeechProcessRunner(controller, **params)
        return controller, runner

    def apply_to_settings(self, app_settings: 'Settings', engine_settings: GoogleCloudSettings) -> None:
        app_settings.sttEngine = self.name
        app_settings.deviceName = engine_settings.device_name
        app_settings.googleCloudCredentialsPath = engine_settings.credentials_path
        app_settings.googleCloudProjectId = engine_settings.project_id
        app_settings.googleCloudLanguageCode = engine_settings.language_code
        app_settings.googleCloudModel = engine_settings.model
        app_settings.googleCloudSampleRate = engine_settings.sample_rate
        app_settings.googleCloudChannels = engine_settings.channels
        app_settings.googleCloudVadEnabled = engine_settings.vad_enabled
        app_settings.googleCloudVadThreshold = engine_settings.vad_threshold

    def check_availability(self):  # type: ignore[override]
        try:
            import google.cloud.speech_v2  # noqa: F401
        except ImportError:
            return False, "python package 'google-cloud-speech' is not installed"
        return True, ""


plugin = GoogleCloudSpeechPlugin()
register_plugin(plugin)
register_plugin_alias("google-cloud", plugin.name)
