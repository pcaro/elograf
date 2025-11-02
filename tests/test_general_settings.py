# ABOUTME: Tests for GeneralSettings dataclass.
# ABOUTME: Verifies defaults, field metadata, and validation integration.

from __future__ import annotations

import dataclasses
import pytest


def test_general_settings_defaults():
    """Test GeneralSettings has correct default values."""
    from eloGraf.general_settings import GeneralSettings

    settings = GeneralSettings()

    assert settings.stt_engine == "nerd-dictation"
    assert settings.precommand == ""
    assert settings.postcommand == ""
    assert settings.env == ""
    assert settings.device_name == "default"
    assert settings.tool == "XDOTOOL"
    assert settings.keyboard == ""
    assert settings.direct_click is True


def test_general_settings_has_all_fields():
    """Test GeneralSettings has all expected fields."""
    from eloGraf.general_settings import GeneralSettings

    settings = GeneralSettings()

    assert hasattr(settings, 'stt_engine')
    assert hasattr(settings, 'precommand')
    assert hasattr(settings, 'postcommand')
    assert hasattr(settings, 'env')
    assert hasattr(settings, 'device_name')
    assert hasattr(settings, 'tool')
    assert hasattr(settings, 'keyboard')
    assert hasattr(settings, 'direct_click')


def test_general_settings_field_metadata():
    """Test GeneralSettings fields have proper metadata."""
    from eloGraf.general_settings import GeneralSettings

    fields = dataclasses.fields(GeneralSettings)
    field_dict = {f.name: f for f in fields}

    # Check precommand has validation
    precommand_field = field_dict['precommand']
    assert 'validate' in precommand_field.metadata
    assert precommand_field.metadata['validate'] == 'eloGraf.validators:validate_command_exists'
    assert precommand_field.metadata['widget'] == 'text'

    # Check postcommand has validation
    postcommand_field = field_dict['postcommand']
    assert 'validate' in postcommand_field.metadata
    assert postcommand_field.metadata['validate'] == 'eloGraf.validators:validate_command_exists'

    # Check tool has dropdown options
    tool_field = field_dict['tool']
    assert tool_field.metadata['widget'] == 'dropdown'
    assert 'options' in tool_field.metadata
    assert 'XDOTOOL' in tool_field.metadata['options']
    assert 'DOTOOL' in tool_field.metadata['options']

    # Check device_name is refreshable
    device_field = field_dict['device_name']
    assert device_field.metadata['widget'] == 'dropdown'
    assert device_field.metadata.get('refreshable') is True
    assert 'choices_function' in device_field.metadata

    # Check stt_engine has choices_function
    engine_field = field_dict['stt_engine']
    assert engine_field.metadata['widget'] == 'dropdown'
    assert 'choices_function' in engine_field.metadata

    # Check direct_click is checkbox
    direct_click_field = field_dict['direct_click']
    assert direct_click_field.metadata['widget'] == 'checkbox'


def test_general_settings_validation_warns_on_invalid_command():
    """Test that validation catches invalid commands."""
    from eloGraf.general_settings import GeneralSettings
    from eloGraf.validators import validate_command_exists

    # Test via validator directly
    result = validate_command_exists("nonexistent_command_xyz")
    assert result is not None
    assert "not found in PATH" in result

    # Create GeneralSettings with invalid command
    settings = GeneralSettings(precommand="nonexistent_command_xyz")
    assert settings.precommand == "nonexistent_command_xyz"  # Should allow setting it


def test_general_settings_custom_values():
    """Test GeneralSettings can be created with custom values."""
    from eloGraf.general_settings import GeneralSettings

    settings = GeneralSettings(
        stt_engine="whisper-docker",
        precommand="xdotool key Escape",
        postcommand="notify-send Done",
        env="LANG=en_US",
        device_name="alsa_input.usb",
        tool="DOTOOL",
        keyboard="us",
        direct_click=False,
    )

    assert settings.stt_engine == "whisper-docker"
    assert settings.precommand == "xdotool key Escape"
    assert settings.postcommand == "notify-send Done"
    assert settings.env == "LANG=en_US"
    assert settings.device_name == "alsa_input.usb"
    assert settings.tool == "DOTOOL"
    assert settings.keyboard == "us"
    assert settings.direct_click is False
