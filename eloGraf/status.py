from enum import Enum, auto

class DictationStatus(Enum):
    IDLE = auto()         # Not running, ready to start.
    INITIALIZING = auto() # Getting ready (e.g., loading model, connecting).
    LISTENING = auto()    # Ready and actively listening for speech.
    SUSPENDED = auto()    # Paused by the user.
    FAILED = auto()       # An unrecoverable error has occurred.