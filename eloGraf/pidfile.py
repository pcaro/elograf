from __future__ import annotations

import logging
import os
from pathlib import Path


PID_FILE = Path.home() / ".config/Elograf/elograf.pid"


def write_pid_file() -> str:
    PID_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(PID_FILE, "w", encoding="utf-8") as handle:
        handle.write(str(os.getpid()))
    return PID_FILE


def remove_pid_file() -> None:
    try:
        if PID_FILE.exists():
            PID_FILE.unlink()
    except Exception as exc:
        logging.warning("Failed to remove PID file: %s", exc)
