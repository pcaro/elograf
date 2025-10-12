"""Common utilities for STT controllers built around enum state machines."""

from __future__ import annotations

import logging
from enum import Enum
from typing import Callable, Dict, Generic, List, TypeVar

from eloGraf.stt_engine import STTController


StateEnum = TypeVar("StateEnum", bound=Enum)


class EnumStateController(STTController, Generic[StateEnum]):
    """Shared implementation for controllers that manage enum-based states."""

    def __init__(
        self,
        *,
        initial_state: StateEnum,
        state_map: Dict[str, StateEnum],
        engine_name: str,
        failed_state_key: str = "failed",
        error_prefix: str = "ERROR",
    ) -> None:
        self._state = initial_state
        self._state_map = {key.lower(): value for key, value in state_map.items()}
        self._engine_name = engine_name
        self._failed_state_key = failed_state_key.lower()
        self._error_prefix = error_prefix

        self._state_listeners: List[Callable[[StateEnum], None]] = []
        self._output_listeners: List[Callable[[str], None]] = []
        self._exit_listeners: List[Callable[[int], None]] = []

    # ------------------------------------------------------------------
    # Listener registration
    # ------------------------------------------------------------------

    @property
    def state(self) -> StateEnum:
        return self._state

    def add_state_listener(self, callback: Callable[[StateEnum], None]) -> None:
        self._state_listeners.append(callback)

    def add_output_listener(self, callback: Callable[[str], None]) -> None:
        self._output_listeners.append(callback)

    def add_exit_listener(self, callback: Callable[[int], None]) -> None:
        self._exit_listeners.append(callback)

    def remove_exit_listener(self, callback: Callable[[int], None]) -> None:
        try:
            self._exit_listeners.remove(callback)
        except ValueError:
            pass

    # ------------------------------------------------------------------
    # Default behaviours shared across controllers
    # ------------------------------------------------------------------

    def fail_to_start(self) -> None:
        self.transition_to(self._failed_state_key)
        self._emit_exit(1)

    def emit_transcription(self, text: str) -> None:
        self._emit_output(text)

    def emit_error(self, message: str) -> None:
        logging.error("%s error: %s", self._engine_name, message)
        self._emit_output(f"{self._error_prefix}: {message}")
        if self._failed_state_key in self._state_map:
            self.transition_to(self._failed_state_key)

    def transition_to(self, state: str) -> None:
        key = state.lower()
        mapped = self._state_map.get(key)
        if mapped is None:
            logging.warning("Unknown state '%s' for %s controller", state, self._engine_name)
            return
        self._set_state(mapped)

    # ------------------------------------------------------------------
    # Protected helpers for subclasses
    # ------------------------------------------------------------------

    def _set_state(self, state: StateEnum) -> None:
        if self._state == state:
            return
        self._state = state
        for listener in list(self._state_listeners):
            listener(state)

    def _emit_output(self, line: str) -> None:
        for listener in list(self._output_listeners):
            listener(line)

    def _emit_exit(self, return_code: int) -> None:
        for listener in list(self._exit_listeners):
            listener(return_code)


class StreamingControllerBase(EnumStateController[StateEnum]):
    """Base class for streaming STT controllers with suspend/resume support."""

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._suspended = False

    def suspend_requested(self) -> None:
        """Request suspension of audio processing."""
        self._suspended = True
        self.transition_to("suspended")

    def resume_requested(self) -> None:
        """Request resumption of audio processing."""
        self._suspended = False
        self.transition_to("recording")

    @property
    def is_suspended(self) -> bool:
        """Check if controller is in suspended state."""
        return self._suspended
