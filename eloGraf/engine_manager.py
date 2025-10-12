# ABOUTME: Manages STT engine lifecycle, configuration, and failure recovery.
# ABOUTME: Handles creation, refresh, and retry logic for speech-to-text engines.

from __future__ import annotations

import logging
from typing import Any, Callable, Optional, Tuple

from PyQt6.QtCore import QTimer

from eloGraf.settings import Settings
from eloGraf.stt_engine import STTController, STTProcessRunner
from eloGraf.engine_plugin import normalize_engine_name
from eloGraf.stt_factory import create_stt_engine


class EngineManager:
    """Manages STT engine lifecycle and configuration."""

    def __init__(
        self,
        settings: Settings,
        temporary_engine: Optional[str] = None,
        max_retries: int = 5,
        retry_delay_ms: int = 2000,
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
        self._temporary_engine = temporary_engine
        self._max_retries = max_retries
        self._retry_delay_ms = retry_delay_ms

        self._controller: Optional[STTController] = None
        self._runner: Optional[STTProcessRunner] = None
        self._failure_count = 0
        self._retry_scheduled = False
        self._pending_refresh = False

        # Callbacks (set by client code)
        self.on_state_change: Optional[Callable[[Any], None]] = None
        self.on_output: Optional[Callable[[str], None]] = None
        self.on_exit: Optional[Callable[[int], None]] = None
        self.on_refresh_complete: Optional[Callable[[], None]] = None

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
        raw = self._temporary_engine if self._temporary_engine else self._settings.sttEngine
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
        engine_type = self.active_engine_type
        engine_settings = self._settings.get_engine_settings(engine_type)

        logging.info("Creating %s STT engine", engine_type)

        controller, runner = create_stt_engine(engine_type, settings=engine_settings)

        # Register callbacks if set
        if self.on_state_change:
            controller.add_state_listener(self.on_state_change)
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

        # If engine is running, stop it first
        if self._runner and self._runner.is_running():
            logging.info("STT engine running; stopping before applying new settings")
            if stop_callback:
                stop_callback()
            self._pending_refresh = True
            return

        logging.info("Refreshing STT engine with updated settings")

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
        failure = return_code != 0

        if failure:
            logging.warning(f"STT engine exited with code {return_code}")

            # Check for fatal errors that shouldn't be retried
            if self._runner and getattr(self._runner, "fatal_error", False):
                logging.error("STT engine reported unrecoverable error; check configuration")
                self._failure_count = 0
                self._pending_refresh = False
                return

            # Increment failure counter
            self._failure_count += 1

            if self._failure_count >= self._max_retries:
                logging.error(
                    "STT engine failed %d times; giving up",
                    self._failure_count,
                )
                if on_fatal_error:
                    on_fatal_error()
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

