"""Plugin definition for nerd-dictation engine."""

from __future__ import annotations

import shutil
from typing import Tuple, TYPE_CHECKING

from eloGraf.engine_plugin import EnginePlugin, register_plugin
from eloGraf.settings_schema import EngineSettings
from eloGraf.stt_engine import STTController, STTProcessRunner
from eloGraf.nerd_controller import NerdDictationController, NerdDictationProcessRunner

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
        return EngineSettings

    def create_controller_runner(
        self, settings: EngineSettings
    ) -> Tuple[STTController, STTProcessRunner]:  # type: ignore[override]
        controller = NerdDictationController()
        runner = NerdDictationProcessRunner(controller)
        return controller, runner

    def apply_to_settings(self, app_settings: 'Settings', engine_settings: EngineSettings) -> None:
        app_settings.sttEngine = self.name
        if hasattr(engine_settings, 'device_name'):
            app_settings.deviceName = engine_settings.device_name

    def check_availability(self):  # type: ignore[override]
        if shutil.which("nerd-dictation"):
            return True, ""
        return False, "nerd-dictation executable not found in PATH"


register_plugin(NerdDictationPlugin())
