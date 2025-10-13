"""Plugin definition for nerd-dictation engine."""

from __future__ import annotations

import shutil
from typing import Tuple, TYPE_CHECKING

from eloGraf.engine_plugin import EnginePlugin, register_plugin
from .settings import NerdSettings
from eloGraf.stt_engine import STTController, STTProcessRunner
from .controller import NerdDictationController, NerdDictationProcessRunner

if TYPE_CHECKING:  # pragma: no cover
    from eloGraf.settings import Settings


class NerdDictationPlugin(EnginePlugin):
    """Built-in plugin for the nerd-dictation engine."""

    @property
    def name(self) -> str:
        return "nerd-dictation"

    @property
    def display_name(self) -> str:
        return "Nerd Dictation"

    def get_settings_schema(self):  # type: ignore[override]
        return NerdSettings

    def create_controller_runner(
        self, settings: NerdSettings
    ) -> Tuple[STTController, STTProcessRunner]:  # type: ignore[override]
        controller = NerdDictationController(settings)
        runner = NerdDictationProcessRunner(controller)
        return controller, runner

    def apply_to_settings(self, app_settings: 'Settings', engine_settings: NerdSettings) -> None:
        app_settings.sttEngine = self.name
        app_settings.deviceName = engine_settings.device_name
        # Apply nerd-specific settings
        app_settings.sampleRate = engine_settings.sample_rate
        app_settings.timeout = engine_settings.timeout
        app_settings.idleTime = engine_settings.idle_time
        app_settings.punctuate = engine_settings.punctuate_timeout
        app_settings.fullSentence = engine_settings.full_sentence
        app_settings.digits = engine_settings.digits
        app_settings.useSeparator = engine_settings.use_separator
        app_settings.freeCommand = engine_settings.free_command
        # TODO: handle model_path

    def check_availability(self):  # type: ignore[override]
        if shutil.which("nerd-dictation"):
            return True, ""
        return False, "nerd-dictation executable not found in PATH"


register_plugin(NerdDictationPlugin())
