# ABOUTME: Factory helpers that leverage the plugin registry to build STT engines.
# ABOUTME: Provides discovery utilities for available speech-to-text engine plugins.

from __future__ import annotations

import logging
from typing import Iterable, Tuple, Type

from eloGraf.engine_plugin import (
    EnginePlugin,
    get_plugin,
    iter_plugins,
    list_plugin_names,
    normalize_engine_name,
)
from eloGraf.base_settings import EngineSettings
from eloGraf.stt_engine import STTController, STTProcessRunner

# Ensure built-in engines are registered on import
from eloGraf import engines as _builtin_engines  # noqa: F401


def _instantiate_settings(plugin: EnginePlugin, **kwargs) -> EngineSettings:
    """Instantiate the plugin's settings dataclass using provided kwargs."""
    schema: Type[EngineSettings] = plugin.get_settings_schema()
    settings_obj = kwargs.pop("settings", None)

    if settings_obj is not None:
        if not isinstance(settings_obj, schema):  # pragma: no cover - defensive branch
            raise TypeError(
                f"Settings object for engine '{plugin.name}' must be of type {schema.__name__}"
            )
        return settings_obj

    schema_kwargs = dict(kwargs)
    schema_kwargs.setdefault("engine_type", plugin.name)
    return schema(**schema_kwargs)  # type: ignore[call-arg]


def create_stt_engine(engine_type: str = "nerd-dictation", **kwargs) -> Tuple[STTController, STTProcessRunner]:
    """Create controller and runner for the specified engine via its plugin."""
    plugin = get_plugin(engine_type)
    settings_obj = _instantiate_settings(plugin, **kwargs)

    controller, runner = plugin.create_controller_runner(settings_obj)
    logging.info("Created %s STT engine", plugin.name)
    return controller, runner


def get_available_engines() -> list[str]:
    """Return the list of registered engine identifiers."""
    return list(list_plugin_names())


def iter_available_plugins() -> Iterable[EnginePlugin]:
    """Iterate over registered engine plugins."""
    return iter_plugins()


def is_engine_available(engine_type: str) -> bool:
    """Return True if the engine's availability check succeeds."""
    plugin = get_plugin(engine_type)
    available, _ = plugin.check_availability()
    return available


def describe_engine(engine_type: str) -> str:
    """Return the display name for an engine."""
    plugin = get_plugin(normalize_engine_name(engine_type))
    return plugin.display_name
