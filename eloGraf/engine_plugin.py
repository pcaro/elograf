"""Plugin interface and registry for speech-to-text engines."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict, Iterable, Optional, Tuple, Type, TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover - used for type checkers only
    from PyQt6.QtWidgets import QWidget
    from eloGraf.settings_schema import EngineSettings
    from eloGraf.settings import Settings
else:  # Fallbacks to avoid importing heavy modules at runtime
    QWidget = Any  # type: ignore
    EngineSettings = Any  # type: ignore
    STTController = Any  # type: ignore
    STTProcessRunner = Any  # type: ignore
    Settings = Any  # type: ignore


class EnginePlugin(ABC):
    """Abstract base class for STT engine plugins."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Return the unique identifier for the engine."""

    @property
    def display_name(self) -> str:
        """Return human-friendly engine name for UI contexts."""
        return self.name

    @abstractmethod
    def get_settings_schema(self) -> Type[EngineSettings]:
        """Return the dataclass describing configuration for this engine."""

    @abstractmethod
    def create_controller_runner(
        self, settings: EngineSettings
    ) -> Tuple[STTController, STTProcessRunner]:
        """Create the controller and runner for this engine."""

    def get_config_widget(self, settings: EngineSettings) -> Optional[QWidget]:
        """Return an optional QWidget to configure engine-specific options."""
        return None

    def check_availability(self) -> Tuple[bool, str]:
        """Return (available, reason) indicating whether the engine can run."""
        return True, ""

    def apply_to_settings(self, app_settings: 'Settings', engine_settings: EngineSettings) -> None:
        """Apply dataclass values to the mutable Settings instance."""
        raise NotImplementedError(f"Plugin {self.name} must implement apply_to_settings()")


_PLUGINS: Dict[str, EnginePlugin] = {}
_ALIASES: Dict[str, str] = {}


def normalize_engine_name(name: str) -> str:
    """Map aliases to their canonical engine name."""
    return _ALIASES.get(name, name)


def register_plugin(plugin: EnginePlugin) -> None:
    """Register a new engine plugin."""
    canonical_name = normalize_engine_name(plugin.name)
    if canonical_name in _PLUGINS:
        raise ValueError(f"Engine plugin '{plugin.name}' already registered")
    _PLUGINS[canonical_name] = plugin


def register_plugin_alias(alias: str, target: str) -> None:
    """Register an alias that maps to an existing engine plugin."""
    target_canonical = normalize_engine_name(target)
    if target_canonical not in _PLUGINS:
        raise ValueError(f"Cannot create alias '{alias}' for unknown plugin '{target}'")
    _ALIASES[alias] = target_canonical


def get_plugin(name: str) -> EnginePlugin:
    """Retrieve plugin by name, resolving aliases."""
    canonical_name = normalize_engine_name(name)
    try:
        return _PLUGINS[canonical_name]
    except KeyError as exc:  # pragma: no cover - defensive branch
        raise ValueError(f"Unsupported STT engine type: {name}") from exc


def iter_plugins() -> Iterable[EnginePlugin]:
    """Iterate over registered plugins."""
    return _PLUGINS.values()


def list_plugin_names() -> Iterable[str]:
    """Return registered plugin names in registration order."""
    return _PLUGINS.keys()


def get_plugin_display_name(name: str) -> str:
    """Return display name for given engine name."""
    return get_plugin(name).display_name
