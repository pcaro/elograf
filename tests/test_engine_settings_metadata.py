# ABOUTME: Tests for engine settings dataclasses with UI metadata.
# ABOUTME: Verifies metadata annotations for dynamic UI generation from settings schemas.

from __future__ import annotations

import dataclasses
import pytest


def test_nerd_settings_has_all_fields():
    """Test NerdSettings dataclass has all expected fields from nerd UI."""
    from eloGraf.engines.nerd.settings import NerdSettings

    settings = NerdSettings()

    # Verify all fields exist
    assert hasattr(settings, 'sample_rate')
    assert hasattr(settings, 'timeout')
    assert hasattr(settings, 'idle_time')
    assert hasattr(settings, 'punctuate_timeout')
    assert hasattr(settings, 'full_sentence')
    assert hasattr(settings, 'digits')
    assert hasattr(settings, 'use_separator')
    assert hasattr(settings, 'free_command')
    assert hasattr(settings, 'model_path')


def test_nerd_settings_defaults():
    """Test NerdSettings has correct default values."""
    from eloGraf.engines.nerd.settings import NerdSettings

    settings = NerdSettings()

    assert settings.sample_rate == 44100
    assert settings.timeout == 0
    assert settings.idle_time == 100
    assert settings.punctuate_timeout == 0
    assert settings.full_sentence is False
    assert settings.digits is False
    assert settings.use_separator is False
    assert settings.free_command == ""
    assert settings.model_path == ""


def test_nerd_settings_field_metadata_exists():
    """Test NerdSettings fields have UI metadata."""
    from eloGraf.engines.nerd.settings import NerdSettings

    fields = dataclasses.fields(NerdSettings)
    field_dict = {f.name: f for f in fields}

    # Check sample_rate has metadata
    sample_rate_field = field_dict['sample_rate']
    assert 'label' in sample_rate_field.metadata
    assert 'widget' in sample_rate_field.metadata
    assert sample_rate_field.metadata['label'] == "Sample rate (Hz)"
    assert sample_rate_field.metadata['widget'] == "text"

    # Check timeout has slider metadata
    timeout_field = field_dict['timeout']
    assert timeout_field.metadata['widget'] == "slider"
    assert 'range' in timeout_field.metadata
    assert 'step' in timeout_field.metadata

    # Check full_sentence has checkbox metadata
    full_sentence_field = field_dict['full_sentence']
    assert full_sentence_field.metadata['widget'] == "checkbox"

    # Check model_path is readonly
    model_path_field = field_dict['model_path']
    assert model_path_field.metadata.get('readonly') is True


def test_nerd_settings_has_manage_models_action():
    """Test NerdSettings has action button metadata for model management."""
    from eloGraf.engines.nerd.settings import NerdSettings

    fields = dataclasses.fields(NerdSettings)
    field_dict = {f.name: f for f in fields}

    # Should have a manage_models_action field
    assert 'manage_models_action' in field_dict
    action_field = field_dict['manage_models_action']

    assert action_field.metadata['widget'] == "action_button"
    assert action_field.metadata['button_text'] == "Manage Models..."
    assert 'on_click' in action_field.metadata
    assert callable(action_field.metadata['on_click'])


def test_whisper_settings_metadata():
    """Test WhisperSettings fields have UI metadata."""
    from eloGraf.engines.whisper.settings import WhisperSettings

    fields = dataclasses.fields(WhisperSettings)
    field_dict = {f.name: f for f in fields}

    # Check model has dropdown metadata
    model_field = field_dict['model']
    assert model_field.metadata['widget'] == "dropdown"
    assert 'options' in model_field.metadata
    assert "base" in model_field.metadata['options']
    assert "large-v3" in model_field.metadata['options']

    # Check vad_enabled has checkbox metadata
    vad_field = field_dict['vad_enabled']
    assert vad_field.metadata['widget'] == "checkbox"


def test_google_settings_metadata():
    """Test GoogleCloudSettings fields have UI metadata."""
    from eloGraf.engines.google.settings import GoogleCloudSettings

    fields = dataclasses.fields(GoogleCloudSettings)
    field_dict = {f.name: f for f in fields}

    # Check credentials_path has text widget
    creds_field = field_dict['credentials_path']
    assert creds_field.metadata['widget'] == "text"
    assert creds_field.metadata['label'] == "Credentials Path"


def test_openai_settings_metadata():
    """Test OpenAISettings fields have UI metadata."""
    from eloGraf.engines.openai.settings import OpenAISettings

    fields = dataclasses.fields(OpenAISettings)
    field_dict = {f.name: f for f in fields}

    # Check api_key has password widget
    api_key_field = field_dict['api_key']
    assert api_key_field.metadata['widget'] == "password"

    # Check model has dropdown
    model_field = field_dict['model']
    assert model_field.metadata['widget'] == "dropdown"


def test_assemblyai_settings_metadata():
    """Test AssemblyAISettings fields have UI metadata."""
    from eloGraf.engines.assemblyai.settings import AssemblyAISettings

    fields = dataclasses.fields(AssemblyAISettings)
    field_dict = {f.name: f for f in fields}

    # Check api_key has password widget
    api_key_field = field_dict['api_key']
    assert api_key_field.metadata['widget'] == "password"
