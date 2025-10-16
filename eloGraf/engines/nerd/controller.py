from __future__ import annotations

import logging
import select
from enum import Enum, auto
from subprocess import PIPE, Popen, STDOUT
from typing import Callable, Dict, List, Optional, Sequence, Tuple

from eloGraf.base_controller import EnumStateController
from eloGraf.status import DictationStatus
from eloGraf.stt_engine import STTProcessRunner
from .settings import NerdSettings


class NerdDictationState(Enum):
    IDLE = auto()
    STARTING = auto()
    LOADING = auto()
    READY = auto()
    DICTATING = auto()
    SUSPENDED = auto()
    STOPPING = auto()
    FAILED = auto()


StateListener = Callable[[NerdDictationState], None]
OutputListener = Callable[[str], None]
ExitListener = Callable[[int], None]


STATE_MAP = {
    "idle": NerdDictationState.IDLE,
    "starting": NerdDictationState.STARTING,
    "loading": NerdDictationState.LOADING,
    "ready": NerdDictationState.READY,
    "dictating": NerdDictationState.DICTATING,
    "suspended": NerdDictationState.SUSPENDED,
    "stopping": NerdDictationState.STOPPING,
    "failed": NerdDictationState.FAILED,
}


class NerdDictationController(EnumStateController[NerdDictationState]):
    """Pure controller that interprets nerd-dictation output into states."""

    def __init__(self, settings: NerdSettings) -> None:
        super().__init__(
            initial_state=NerdDictationState.IDLE,
            state_map=STATE_MAP,
            engine_name="NerdDictation",
        )
        self._settings = settings
        self._stop_requested = False

    def start(self) -> None:
        self._stop_requested = False
        self._set_state(NerdDictationState.STARTING)

    def stop_requested(self) -> None:
        self._stop_requested = True
        self._set_state(NerdDictationState.STOPPING)

    def suspend_requested(self) -> None:
        self._stop_requested = False
        self._set_state(NerdDictationState.SUSPENDED)

    def resume_requested(self) -> None:
        self._stop_requested = False
        self._set_state(NerdDictationState.STARTING)

    def fail_to_start(self) -> None:
        self._stop_requested = False
        super().fail_to_start()

    def handle_output(self, line: str) -> None:
        self._emit_output(line)
        lower = line.lower()
        if "loading model" in lower:
            self._set_state(NerdDictationState.LOADING)
        elif any(token in lower for token in ("model loaded", "listening", "ready")):
            self._set_state(NerdDictationState.READY)
        elif "dictation started" in lower:
            self._set_state(NerdDictationState.DICTATING)
        elif any(token in lower for token in ("dictation ended", "dictation stopped")):
            self._set_state(NerdDictationState.IDLE)
        elif "suspended" in lower:
            self._set_state(NerdDictationState.SUSPENDED)
        elif "resumed" in lower:
            self._set_state(NerdDictationState.DICTATING)

    def handle_exit(self, return_code: int) -> None:
        if return_code == 0 and self._stop_requested:
            self._set_state(NerdDictationState.IDLE)
        elif return_code == 0 and self._state != NerdDictationState.IDLE:
            self._set_state(NerdDictationState.IDLE)
        else:
            self._set_state(NerdDictationState.FAILED)
        self._emit_exit(return_code)
        self._stop_requested = False

    def get_status_string(self) -> str:
        model_name = self._settings.model_path
        return f"Nerd-Dictation | Model: {model_name or 'Not Selected'}"

    @property
    def dictation_status(self) -> DictationStatus:
        # self.state is the internal NerdDictationState
        if self.state in (NerdDictationState.STARTING, NerdDictationState.LOADING):
            return DictationStatus.INITIALIZING
        elif self.state in (NerdDictationState.READY, NerdDictationState.DICTATING):
            return DictationStatus.LISTENING
        elif self.state == NerdDictationState.SUSPENDED:
            return DictationStatus.SUSPENDED
        elif self.state == NerdDictationState.FAILED:
            return DictationStatus.FAILED
        else:
            return DictationStatus.IDLE


class NerdDictationProcessRunner(STTProcessRunner):
    """Launch nerd-dictation and feed output into the controller."""

    def __init__(
        self,
        controller: NerdDictationController,
        *,
        process_factory: Optional[Callable[[Sequence[str], Optional[Dict[str, str]]], Popen]] = None,
        select_fn: Optional[
            Callable[[Sequence, Sequence, Sequence, float], Tuple[Sequence, Sequence, Sequence]]
        ] = None,
        stop_command: Optional[Sequence[str]] = None,
        stop_runner: Optional[Callable[[], None]] = None,
        suspend_runner: Optional[Callable[[], None]] = None,
        resume_runner: Optional[Callable[[], None]] = None,
    ) -> None:
        self._controller = controller
        self._process_factory = process_factory or self._default_factory
        self._select = select_fn or select.select
        self._stop_command = list(stop_command) if stop_command else ["nerd-dictation", "end"]
        self._suspend_command = ["nerd-dictation", "suspend"]
        self._resume_command = ["nerd-dictation", "resume"]
        if stop_runner is None:
            self._stop_runner = lambda: Popen(self._stop_command)
        else:
            self._stop_runner = stop_runner
        self._suspend_runner = suspend_runner or (lambda: Popen(self._suspend_command))
        self._resume_runner = resume_runner or (lambda: Popen(self._resume_command))
        self._process: Optional[Popen] = None

    def start(self, command: Sequence[str], env: Optional[Dict[str, str]] = None) -> bool:
        if self.is_running():
            logging.warning("nerd-dictation is already running")
            return False

        logging.info(f"[NerdDictation] Starting with command: {' '.join(command)}")

        try:
            process = self._process_factory(list(command), env)
        except Exception as exc:
            logging.error("Failed to start nerd-dictation: %s", exc)
            self._controller.fail_to_start()
            return False

        self._process = process
        self._controller.start()
        return True

    def stop(self) -> None:
        if not self.is_running():
            return

        self._controller.stop_requested()
        try:
            self._stop_runner()
        except Exception as exc:
            logging.error("Failed to send stop command to nerd-dictation: %s", exc)

    def suspend(self) -> None:
        if not self.is_running():
            return

        self._controller.suspend_requested()
        try:
            self._suspend_runner()
        except Exception as exc:
            logging.error("Failed to send suspend command to nerd-dictation: %s", exc)

    def resume(self) -> None:
        if not self.is_running():
            return

        self._controller.resume_requested()
        try:
            self._resume_runner()
        except Exception as exc:
            logging.error("Failed to send resume command to nerd-dictation: %s", exc)

    def poll(self) -> None:
        if not self._process:
            return

        stdout = getattr(self._process, "stdout", None)
        if stdout:
            try:
                while True:
                    ready = self._select([stdout], [], [], 0)[0]
                    if not ready:
                        break
                    line = stdout.readline()
                    if not line:
                        break
                    line = line.strip()
                    if not line:
                        continue
                    self._controller.handle_output(line)
            except (OSError, ValueError, TypeError) as exc:
                logging.debug("Error while reading nerd-dictation output: %s", exc)

        if self._process and self._process.poll() is not None:
            return_code = self._process.returncode or 0
            if stdout:
                try:
                    stdout.close()
                except Exception:
                    pass
            self._process = None
            self._controller.handle_exit(return_code)

    def is_running(self) -> bool:
        return self._process is not None and self._process.poll() is None

    @staticmethod
    def _default_factory(command: Sequence[str], env: Optional[Dict[str, str]]) -> Popen:
        return Popen(
            list(command),
            env=env,
            stdout=PIPE,
            stderr=STDOUT,
            text=True,
            bufsize=1,
        )
