# ABOUTME: Tests for validation functions used in settings fields.
# ABOUTME: Each test verifies validators return None for valid input or warning messages for invalid input.

from __future__ import annotations

import os
import tempfile
import pytest


def test_validate_command_exists_with_valid_command():
    """Test validate_command_exists returns None for commands in PATH."""
    from eloGraf.validators import validate_command_exists

    # 'ls' should exist on Linux systems
    result = validate_command_exists("ls")
    assert result is None

    # Command with arguments
    result = validate_command_exists("ls -la")
    assert result is None


def test_validate_command_exists_with_invalid_command():
    """Test validate_command_exists returns warning for commands not in PATH."""
    from eloGraf.validators import validate_command_exists

    result = validate_command_exists("nonexistent_command_xyz_12345")
    assert result is not None
    assert "not found in PATH" in result
    assert "nonexistent_command_xyz_12345" in result


def test_validate_command_exists_with_empty_string():
    """Test validate_command_exists returns None for empty string."""
    from eloGraf.validators import validate_command_exists

    result = validate_command_exists("")
    assert result is None

    result = validate_command_exists("   ")
    assert result is None


def test_validate_file_exists_with_existing_file():
    """Test validate_file_exists returns None for existing files."""
    from eloGraf.validators import validate_file_exists

    # Create a temporary file
    with tempfile.NamedTemporaryFile(delete=False) as tmp:
        tmp_path = tmp.name

    try:
        result = validate_file_exists(tmp_path)
        assert result is None
    finally:
        os.unlink(tmp_path)


def test_validate_file_exists_with_nonexistent_file():
    """Test validate_file_exists returns warning for nonexistent files."""
    from eloGraf.validators import validate_file_exists

    result = validate_file_exists("/tmp/nonexistent_file_xyz_12345.txt")
    assert result is not None
    assert "File not found" in result


def test_validate_file_exists_with_directory():
    """Test validate_file_exists returns warning when path is a directory."""
    from eloGraf.validators import validate_file_exists

    result = validate_file_exists("/tmp")
    assert result is not None
    assert "File not found" in result


def test_validate_file_exists_with_empty_string():
    """Test validate_file_exists returns None for empty string."""
    from eloGraf.validators import validate_file_exists

    result = validate_file_exists("")
    assert result is None

    result = validate_file_exists("   ")
    assert result is None


def test_validate_directory_exists_with_existing_directory():
    """Test validate_directory_exists returns None for existing directories."""
    from eloGraf.validators import validate_directory_exists

    # /tmp should exist on Linux
    result = validate_directory_exists("/tmp")
    assert result is None


def test_validate_directory_exists_with_nonexistent_directory():
    """Test validate_directory_exists returns warning for nonexistent directories."""
    from eloGraf.validators import validate_directory_exists

    result = validate_directory_exists("/nonexistent_directory_xyz_12345")
    assert result is not None
    assert "Directory not found" in result


def test_validate_directory_exists_with_file():
    """Test validate_directory_exists returns warning when path is a file."""
    from eloGraf.validators import validate_directory_exists

    # Create a temporary file
    with tempfile.NamedTemporaryFile(delete=False) as tmp:
        tmp_path = tmp.name

    try:
        result = validate_directory_exists(tmp_path)
        assert result is not None
        assert "Directory not found" in result
    finally:
        os.unlink(tmp_path)


def test_validate_directory_exists_with_empty_string():
    """Test validate_directory_exists returns None for empty string."""
    from eloGraf.validators import validate_directory_exists

    result = validate_directory_exists("")
    assert result is None

    result = validate_directory_exists("   ")
    assert result is None
