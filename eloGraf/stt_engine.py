# ABOUTME: Abstract interfaces for speech-to-text engine controllers and process runners.
# ABOUTME: Defines base contracts for integrating different STT engines (nerd-dictation, Docker, Whisper, etc.).

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Callable, Dict, Optional, Sequence

StateListener = Callable[[object], None]
OutputListener = Callable[[str], None]
ExitListener = Callable[[int], None]


class STTController(ABC):
    """Abstract controller that interprets STT engine output into states."""

    @abstractmethod
    def add_state_listener(self, callback: StateListener) -> None:
        """Register a callback to be notified of state changes."""
        pass

    @abstractmethod
    def add_output_listener(self, callback: OutputListener) -> None:
        """Register a callback to receive raw output lines from the STT process."""
        pass

    @abstractmethod
    def add_exit_listener(self, callback: ExitListener) -> None:
        """Register a callback to be notified when the process exits."""
        pass

    @abstractmethod
    def start(self) -> None:
        """Signal that the STT process is starting."""
        pass

    @abstractmethod
    def stop_requested(self) -> None:
        """Signal that a stop has been requested."""
        pass

    @abstractmethod
    def suspend_requested(self) -> None:
        """Signal that a suspend has been requested."""
        pass

    @abstractmethod
    def resume_requested(self) -> None:
        """Signal that a resume has been requested."""
        pass

    @abstractmethod
    def fail_to_start(self) -> None:
        """Signal that the process failed to start."""
        pass

    @abstractmethod
    def handle_output(self, line: str) -> None:
        """Process a line of output from the STT engine."""
        pass

    @abstractmethod
    def handle_exit(self, return_code: int) -> None:
        """Handle process termination with the given return code."""
        pass

    @abstractmethod
    def transition_to(self, state: str) -> None:
        """
        Transition to a named state.

        State names are engine-specific but typically include:
        - 'idle', 'starting', 'loading', 'ready', 'recording', 'transcribing',
          'suspended', 'stopping', 'failed', 'connecting'

        Args:
            state: String identifier for the target state (case-insensitive).
        """
        pass

    @abstractmethod
    def emit_transcription(self, text: str) -> None:
        """
        Emit transcribed text to output listeners.

        This method should be used to send final transcription results
        to all registered output listeners.

        Args:
            text: The transcribed text to emit.
        """
        pass

    @abstractmethod
    def emit_error(self, message: str) -> None:
        """
        Emit error message and transition to failed state.

        This method should log the error, notify output listeners,
        and transition the controller to a failed state.

        Args:
            message: The error message to emit.
        """
        pass


class STTProcessRunner(ABC):
    """Abstract process runner that manages the STT engine lifecycle."""

    @abstractmethod
    def start(self, command: Sequence[str], env: Optional[Dict[str, str]] = None) -> bool:
        """
        Start the STT process with the given command and environment.

        Returns:
            True if the process started successfully, False otherwise.
        """
        pass

    @abstractmethod
    def stop(self) -> None:
        """Request the STT process to stop."""
        pass

    @abstractmethod
    def suspend(self) -> None:
        """Request the STT process to suspend (pause recognition)."""
        pass

    @abstractmethod
    def resume(self) -> None:
        """Request the STT process to resume (continue recognition)."""
        pass

    @abstractmethod
    def poll(self) -> None:
        """
        Poll for new output from the process and handle termination.

        Should be called periodically to read output and detect when the process exits.
        """
        pass

    @abstractmethod
    def is_running(self) -> bool:
        """
        Check if the STT process is currently running.

        Returns:
            True if the process is running, False otherwise.
        """
        pass
