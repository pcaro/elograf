# ABOUTME: Tests for engine settings dataclasses with UI metadata.
# ABOUTME: Verifies metadata annotations for dynamic UI generation from settings schemas.

from __future__ import annotations

import dataclasses
import pytest


def test_whisper_settings_metadata():
    """Test WhisperSettings fields have UI metadata."""
    from eloGraf.engines.whisper.settings import WhisperSettings

    fields = dataclasses.fields(WhisperSettings)
    field_dict = {f.name: f for f in fields}

    # Check model has dropdown metadata
    model_field = field_dict["model"]
    assert model_field.metadata["widget"] == "dropdown"
    assert "options" in model_field.metadata
    assert "base" in model_field.metadata["options"]
    assert "large-v3" in model_field.metadata["options"]

    # Check vad_enabled has checkbox metadata
    vad_field = field_dict["vad_enabled"]
    assert vad_field.metadata["widget"] == "checkbox"


def test_google_settings_metadata():
    """Test GoogleCloudSettings fields have UI metadata."""
    from eloGraf.engines.google.settings import GoogleCloudSettings

    fields = dataclasses.fields(GoogleCloudSettings)
    field_dict = {f.name: f for f in fields}

    # Check credentials_path has text widget
    creds_field = field_dict["credentials_path"]
    assert creds_field.metadata["widget"] == "text"
    assert creds_field.metadata["label"] == "Credentials Path"


def test_openai_settings_metadata():
    """Test OpenAISettings fields have UI metadata."""
    from eloGraf.engines.openai.settings import OpenAISettings

    fields = dataclasses.fields(OpenAISettings)
    field_dict = {f.name: f for f in fields}

    # Check api_key has password widget
    api_key_field = field_dict["api_key"]
    assert api_key_field.metadata["widget"] == "password"

    # Check model has dropdown
    model_field = field_dict["model"]
    assert model_field.metadata["widget"] == "dropdown"
