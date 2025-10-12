"""Utilities for simulating keyboard input via external tools."""

from __future__ import annotations

import logging
import shutil
from subprocess import CalledProcessError, run
from typing import Iterable, Optional


class InputSimulator:
    """Simulates keyboard input using dotool or xdotool when available."""

    def __init__(self, preferred_tool: Optional[str] = None) -> None:
        self._preferred_tool = preferred_tool

    def type_text(self, text: str) -> None:
        """Type *text* using the first available input tool.

        Falls back from dotool to xdotool and logs a warning if neither succeeds.
        """
        for tool in self._candidate_tools():
            command = self._build_command(tool, text)
            if command is None:
                continue
            try:
                run(command, check=True)
                return
            except (CalledProcessError, FileNotFoundError):
                logging.debug("Input simulator '%s' failed; trying fallback", tool)
                continue
        logging.warning("Neither dotool nor xdotool available for input simulation")

    def _candidate_tools(self) -> Iterable[str]:
        seen = set()
        if self._preferred_tool:
            seen.add(self._preferred_tool)
            yield self._preferred_tool
        for tool in ("dotool", "xdotool"):
            if tool not in seen:
                yield tool

    @staticmethod
    def _build_command(tool: str, text: str) -> Optional[list[str]]:
        if shutil.which(tool) is None:
            return None
        if tool == "dotool":
            return ["dotool", "type", text]
        if tool == "xdotool":
            return ["xdotool", "type", "--", text]
        return None


_simulator: Optional[InputSimulator] = None


def get_input_simulator() -> InputSimulator:
    """Return a singleton input simulator instance."""
    global _simulator
    if _simulator is None:
        _simulator = InputSimulator()
    return _simulator


def type_text(text: str) -> None:
    """Convenience wrapper that types *text* using the singleton simulator."""
    get_input_simulator().type_text(text)
