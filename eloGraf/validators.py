# ABOUTME: Validation functions for settings fields.
# ABOUTME: Each validator returns None if valid, or a warning message string.

from __future__ import annotations

from typing import Optional
import shutil
import os
from pathlib import Path


def validate_command_exists(value: str) -> Optional[str]:
    """Validate that command exists in PATH.

    Args:
        value: Command string (e.g., "xdotool" or "xdotool type")

    Returns:
        None if valid, warning message if command not found
    """
    if not value or not value.strip():
        return None  # Empty is valid

    parts = value.split()
    command = parts[0]

    if not shutil.which(command):
        return f"Command '{command}' not found in PATH"

    return None


def validate_file_exists(value: str) -> Optional[str]:
    """Validate that file exists.

    Args:
        value: File path

    Returns:
        None if valid, warning message if file not found
    """
    if not value or not value.strip():
        return None  # Empty is valid

    if not Path(value).is_file():
        return f"File not found: {value}"

    return None


def validate_directory_exists(value: str) -> Optional[str]:
    """Validate that directory exists.

    Args:
        value: Directory path

    Returns:
        None if valid, warning message if directory not found
    """
    if not value or not value.strip():
        return None  # Empty is valid

    if not Path(value).is_dir():
        return f"Directory not found: {value}"

    return None
