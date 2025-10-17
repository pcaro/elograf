# ABOUTME: Manages STT engine lifecycle, configuration, and failure recovery.
# ABOUTME: Handles creation, refresh, and retry logic for speech-to-text engines.

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Callable, Optional, Tuple

from PyQt6.QtCore import QTimer

from eloGraf.settings import Settings
from eloGraf.stt_engine import STTController, STTProcessRunner
from eloGraf.engine_plugin import normalize_engine_name
from eloGraf.stt_factory import create_stt_engine
from eloGraf.status import DictationStatus


class FailureType(Enum):
    TRANSIENT = "transient"
    CONFIG = "configuration"
    AUTH = "auth"
    RATE_LIMIT = "rate_limit"
    UNKNOWN = "unknown"


FALLBACK_CHAIN = {
    "openai-realtime": ["whisper-docker", "nerd-dictation"],
    "google-cloud-speech": ["openai-realtime", "whisper-docker", "nerd-dictation"],
    "whisper-docker": ["nerd-dictation"],
    "assemblyai": ["openai-realtime", "whisper-docker", "nerd-dictation"],
}

_CIRCUIT_OPEN_SECONDS = 15


class EngineManager:
    """Manages STT engine lifecycle and configuration."""

    def __init__(
        self,
        settings: Settings,
        temporary_engine: Optional[str] = None,
        max_retries: int = 5,
        retry_delay_ms: int = 2000,
        refresh_timeout_ms: int = 5000,
    ):
        """
        Initialize engine manager.

        Args:
            settings: Application settings
            temporary_engine: Override engine type (for CLI usage)
            max_retries: Maximum number of retry attempts on failure
            retry_delay_ms: Base delay between retries in milliseconds
        """
        self._settings = settings
        self._cli_override = temporary_engine is not None
        self._user_engine = normalize_engine_name(settings.sttEngine)
        self._fallback_chain = [
            self._user_engine,
            *[engine for engine in FALLBACK_CHAIN.get(self._user_engine, []) if engine != self._user_engine],
        ]
        self._fallback_index = 0
        self._temporary_engine: Optional[str] = None
        self._circuit_open_until: Optional[datetime] = None
        self._max_retries = max_retries
        self._retry_delay_ms = retry_delay_ms

        self._controller: Optional[STTController] = None
        self._runner: Optional[STTProcessRunner] = None
        self._failure_count = 0
        self._retry_scheduled = False
        self._pending_refresh = False
        self._refresh_timeout_ms = refresh_timeout_ms
        self._refresh_timeout_timer: Optional[QTimer] = None
        self._last_stop_callback: Optional[Callable[[], None]] = None
        self._last_poll_timer: Optional[QTimer] = None

        if temporary_engine:
            self._set_active_engine(temporary_engine, as_temporary=True)

        # Callbacks (set by client code)
        self.on_state_change: Optional[Callable[[DictationStatus], None]] = None
        self.on_output: Optional[Callable[[str], None]] = None
        self.on_exit: Optional[Callable[[int], None]] = None
        self.on_refresh_complete: Optional[Callable[[], None]] = None

    def _handle_internal_state_change(self, internal_state: object) -> None:
        if self.on_state_change and self._controller:
            self.on_state_change(self._controller.dictation_status)

    @property
    def controller(self) -> Optional[STTController]:
        """Get current STT controller."""
        return self._controller

    @property
    def runner(self) -> Optional[STTProcessRunner]:
        """Get current STT process runner."""
        return self._runner

    @property
    def active_engine_type(self) -> str:
        """Get the currently active engine type."""
        raw = self._temporary_engine if self._temporary_engine else self._user_engine
        return normalize_engine_name(raw)

    def create_engine(self) -> Tuple[STTController, STTProcessRunner]:
        """
        Create STT engine based on current settings.

        Returns:
            Tuple of (controller, runner)

        Raises:
            ValueError: If engine type is not supported
            RuntimeError: If engine creation fails
        """
        # Unregister callbacks from old controller to prevent race condition
        # where old controller's exit handler fires after new engine is created
        if self._controller and self.on_exit:
            self._controller.remove_exit_listener(self.on_exit)

        engine_type = self.active_engine_type
        engine_settings = self._settings.get_engine_settings(engine_type)

        logging.info("Creating %s STT engine", engine_type)

        controller, runner = create_stt_engine(engine_type, settings=engine_settings)

        # Register callbacks if set
        if self.on_state_change:
            controller.add_state_listener(self._handle_internal_state_change)
        if self.on_output:
            controller.add_output_listener(self.on_output)
        if self.on_exit:
            controller.add_exit_listener(self.on_exit)

        self._controller = controller
        self._runner = runner

        return controller, runner

    def refresh_engine(
        self,
        stop_callback: Optional[Callable[[], None]] = None,
        poll_timer: Optional[QTimer] = None,
    ) -> None:
        """
        Refresh STT engine with updated settings.

        If engine is running, stops it first and schedules refresh for after exit.

        Args:
            stop_callback: Function to stop running engine
            poll_timer: QTimer used for polling (will be disconnected/reconnected)
        """
        self._retry_scheduled = False
        self._sync_user_engine()

        if stop_callback:
            self._last_stop_callback = stop_callback
        if poll_timer:
            self._last_poll_timer = poll_timer

        # If engine is running, stop it first
        if self._runner and self._runner.is_running():
            logging.info("STT engine running; stopping before applying new settings")
            self._pending_refresh = True
            if stop_callback:
                stop_callback()
            else:
                try:
                    self._runner.stop()
                except Exception as exc:  # pragma: no cover - defensive
                    logging.error("Failed to stop STT engine gracefully: %s", exc)
            self._start_refresh_timeout()
            return

        logging.info("Refreshing STT engine with updated settings")

        self._cancel_refresh_timeout()
        was_active = poll_timer.isActive() if poll_timer else False
        self._pending_refresh = False

        # Stop polling timer
        if poll_timer:
            poll_timer.stop()

        # Disconnect old runner from timer
        disconnected = False
        if poll_timer and self._runner:
            try:
                poll_timer.timeout.disconnect(self._runner.poll)
                disconnected = True
            except (TypeError, RuntimeError):
                pass

        # Try to create new engine
        try:
            self.create_engine()
        except Exception:
            # Rollback on failure - reconnect old runner
            if disconnected and self._runner and poll_timer:
                try:
                    poll_timer.timeout.connect(self._runner.poll)
                    if was_active:
                        poll_timer.start()
                except (TypeError, RuntimeError):
                    pass
            raise

        # Connect new runner to timer
        if poll_timer and self._runner:
            poll_timer.timeout.connect(self._runner.poll)

        # Notify completion
        if self.on_refresh_complete:
            self.on_refresh_complete()

    def handle_exit(self, return_code: int, on_fatal_error: Optional[Callable[[], None]] = None) -> None:
        """
        Handle engine exit and implement retry logic.

        Args:
            return_code: Exit code from engine (0 = success, non-zero = failure)
            on_fatal_error: Callback to invoke if retries exhausted
        """
        self._cancel_refresh_timeout()
        failure = return_code != 0

        if failure:
            failure_type = self._classify_failure(return_code)
            logging.warning(
                "STT engine exited with code %s (%s failure)",
                return_code,
                failure_type.value,
            )

            self._failure_count += 1

            if self._failure_count >= self._max_retries:
                if self._engage_circuit_breaker(failure_type, on_fatal_error):
                    return

            # Schedule retry with exponential backoff
            delay_ms = min(10000, self._failure_count * self._retry_delay_ms)
            logging.info(
                "Retrying STT engine in %.1f seconds (attempt %d/%d)",
                delay_ms / 1000,
                self._failure_count,
                self._max_retries,
            )

            if not self._retry_scheduled:
                self._retry_scheduled = True
                QTimer.singleShot(delay_ms, lambda: self.refresh_engine())

        else:
            # Success - reset failure counter
            self._failure_count = 0

            # If refresh was pending, do it now
            if self._pending_refresh:
                self._pending_refresh = False
                self.refresh_engine()
            elif self._should_restore_user_engine():
                self._restore_user_engine()

    def _start_refresh_timeout(self) -> None:
        """Start (or restart) the safety timer guarding pending refreshes."""
        if self._refresh_timeout_ms <= 0:
            return

        if not self._refresh_timeout_timer:
            self._refresh_timeout_timer = QTimer()
            self._refresh_timeout_timer.setSingleShot(True)
            self._refresh_timeout_timer.timeout.connect(self._on_refresh_timeout)

        self._refresh_timeout_timer.start(self._refresh_timeout_ms)

    def _cancel_refresh_timeout(self) -> None:
        """Stop the refresh safety timer if it is active."""
        if self._refresh_timeout_timer and self._refresh_timeout_timer.isActive():
            self._refresh_timeout_timer.stop()

    def _on_refresh_timeout(self) -> None:
        """Force refresh continuation when the engine fails to stop."""
        if not self._pending_refresh:
            return

        if not self._runner or not self._runner.is_running():
            self._pending_refresh = False
            return

        logging.warning("STT engine stop timed out; forcing refresh")

        try:
            self._runner.stop()
        except Exception as exc:  # pragma: no cover - defensive
            logging.error("Failed to stop STT engine gracefully after timeout: %s", exc)

        if self._runner:
            try:
                self._runner.force_stop()
            except Exception as exc:  # pragma: no cover - defensive
                logging.error("Failed to force stop STT engine: %s", exc)

        self._pending_refresh = False
        self._cancel_refresh_timeout()
        self.refresh_engine(
            stop_callback=self._last_stop_callback,
            poll_timer=self._last_poll_timer,
        )

    def _sync_user_engine(self) -> None:
        configured = normalize_engine_name(self._settings.sttEngine)
        if configured != self._user_engine:
            self._user_engine = configured
            self._fallback_chain = [
                self._user_engine,
                *[engine for engine in FALLBACK_CHAIN.get(self._user_engine, []) if engine != self._user_engine],
            ]
            if not self._cli_override:
                self._temporary_engine = None
                self._fallback_index = 0
            else:
                if self._temporary_engine and self._temporary_engine not in self._fallback_chain:
                    self._fallback_chain.append(self._temporary_engine)
                    self._fallback_index = self._fallback_chain.index(self._temporary_engine)
            self._circuit_open_until = None

    def _set_active_engine(self, engine_name: str, *, as_temporary: bool) -> None:
        normalized = normalize_engine_name(engine_name)
        if normalized not in self._fallback_chain:
            self._fallback_chain.append(normalized)
        self._fallback_index = self._fallback_chain.index(normalized)
        self._temporary_engine = normalized if as_temporary or normalized != self._user_engine else None

    def _next_fallback_engine(self) -> Optional[str]:
        if self._fallback_index + 1 >= len(self._fallback_chain):
            return None
        self._fallback_index += 1
        fallback = self._fallback_chain[self._fallback_index]
        self._temporary_engine = fallback
        return fallback

    def _classify_failure(self, return_code: int) -> FailureType:
        runner = self._runner
        if runner:
            explicit = getattr(runner, "failure_type", None)
            if isinstance(explicit, FailureType):
                return explicit
            if isinstance(explicit, str):
                try:
                    return FailureType(explicit)
                except ValueError:
                    pass
            if getattr(runner, "fatal_error", False):
                return FailureType.CONFIG
            last_error = getattr(runner, "last_error_message", "")
            if isinstance(last_error, str):
                lowered = last_error.lower()
                if "unauthorized" in lowered or "forbidden" in lowered:
                    return FailureType.AUTH
                if "rate limit" in lowered or "too many requests" in lowered:
                    return FailureType.RATE_LIMIT
        if return_code in (401, 403):
            return FailureType.AUTH
        if return_code == 429:
            return FailureType.RATE_LIMIT
        return FailureType.TRANSIENT

    def _engage_circuit_breaker(
        self,
        failure_type: FailureType,
        on_fatal_error: Optional[Callable[[], None]],
    ) -> bool:
        self._retry_scheduled = False
        self._circuit_open_until = datetime.now() + timedelta(seconds=_CIRCUIT_OPEN_SECONDS)
        fallback = self._next_fallback_engine()
        if fallback:
            logging.warning(
                "Switching to fallback STT engine '%s' after repeated %s failures",
                fallback,
                failure_type.value,
            )
            self._failure_count = 0
            self._pending_refresh = False
            self.refresh_engine()
            return True

        logging.error(
            "No fallback engines available for '%s'; circuit open for %d seconds",
            self.active_engine_type,
            _CIRCUIT_OPEN_SECONDS,
        )
        if on_fatal_error:
            on_fatal_error()
        return True

    def _should_restore_user_engine(self) -> bool:
        if self._temporary_engine is None:
            return False
        if self._cli_override:
            return False
        if not self._circuit_open_until:
            return False
        return datetime.now() >= self._circuit_open_until

    def _restore_user_engine(self) -> None:
        logging.info(
            "Circuit breaker window elapsed; attempting to restore primary engine '%s'",
            self._user_engine,
        )
        self._fallback_index = 0
        self._temporary_engine = None
        self._circuit_open_until = None
        self.refresh_engine()
