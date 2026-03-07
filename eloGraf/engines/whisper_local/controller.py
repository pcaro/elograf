"""Controller for WhisperLocal engine."""
from enum import Enum, auto
from eloGraf.base_controller import StreamingControllerBase
from .settings import WhisperLocalSettings


class WhisperLocalState(Enum):
    """States for WhisperLocal engine."""
    IDLE = auto()
    DOWNLOADING_MODEL = auto()
    LOADING = auto()
    READY = auto()
    RECORDING = auto()
    TRANSCRIBING = auto()
    SUSPENDED = auto()
    FAILED = auto()


STATE_MAP = {
    "idle": WhisperLocalState.IDLE,
    "downloading_model": WhisperLocalState.DOWNLOADING_MODEL,
    "loading": WhisperLocalState.LOADING,
    "ready": WhisperLocalState.READY,
    "recording": WhisperLocalState.RECORDING,
    "transcribing": WhisperLocalState.TRANSCRIBING,
    "suspended": WhisperLocalState.SUSPENDED,
    "failed": WhisperLocalState.FAILED,
}


class WhisperLocalController(StreamingControllerBase[WhisperLocalState]):
    """Controller for WhisperLocal STT engine."""
    
    def __init__(self, settings: WhisperLocalSettings):
        super().__init__(
            initial_state=WhisperLocalState.IDLE,
            state_map=STATE_MAP,
            engine_name="WhisperLocal",
        )
        self._settings = settings

    def start(self) -> None:
        """Signal that the STT process is starting."""
        self.transition_to("loading")

    def stop_requested(self) -> None:
        """Signal that a stop has been requested."""
        self.transition_to("idle")

    def handle_output(self, line: str) -> None:
        """Process a line of output from the STT engine."""
        self._emit_output(line)

    def handle_exit(self, return_code: int) -> None:
        """Handle process termination."""
        self._emit_exit(return_code)
    
    def get_status_string(self) -> str:
        """Return status string for UI."""
        return f"Whisper Local | Model: {self._settings.model_size}"
    
    @property
    def dictation_status(self):
        """Return generic dictation status."""
        from eloGraf.status import DictationStatus
        
        if self.state in (WhisperLocalState.DOWNLOADING_MODEL, WhisperLocalState.LOADING):
            return DictationStatus.INITIALIZING
        elif self.state in (WhisperLocalState.READY, WhisperLocalState.RECORDING, WhisperLocalState.TRANSCRIBING):
            return DictationStatus.LISTENING
        elif self.state == WhisperLocalState.SUSPENDED:
            return DictationStatus.SUSPENDED
        elif self.state == WhisperLocalState.FAILED:
            return DictationStatus.FAILED
        else:
            return DictationStatus.IDLE
