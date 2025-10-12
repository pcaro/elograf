# ABOUTME: Tests for AdvancedUI dialog with dynamic tab generation.
# ABOUTME: Verifies that settings tabs are created from engine metadata.

from __future__ import annotations

import os
import pytest
from PyQt6.QtWidgets import QApplication


@pytest.fixture(scope="module")
def qt_app():
    """Create QApplication for tests that need Qt."""
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    app = QApplication.instance()
    if not app:
        app = QApplication([])
    yield app


def test_advanced_dialog_creates_dynamic_tabs(qt_app):
    """Test that AdvancedUI creates tabs for all registered engines."""
    from eloGraf.dialogs import AdvancedUI
    from eloGraf.engine_settings_registry import get_all_engine_ids

    dialog = AdvancedUI()

    # Should have General tab plus one tab per engine
    expected_tab_count = 1 + len(get_all_engine_ids())

    assert dialog.ui.tabWidget.count() >= expected_tab_count

    # Check that engine tabs were created
    tab_texts = [
        dialog.ui.tabWidget.tabText(i)
        for i in range(dialog.ui.tabWidget.count())
    ]

    assert "General" in tab_texts
    assert "Nerd Dictation" in tab_texts
    assert "Whisper Docker" in tab_texts
    assert "Google Cloud" in tab_texts
    assert "OpenAI" in tab_texts
    assert "AssemblyAI" in tab_texts


def test_advanced_dialog_stores_engine_tabs(qt_app):
    """Test that AdvancedUI stores references to dynamically created tabs."""
    from eloGraf.dialogs import AdvancedUI

    dialog = AdvancedUI()

    # Should have engine_tabs dict with all engines
    assert hasattr(dialog, 'engine_tabs')
    assert isinstance(dialog.engine_tabs, dict)

    assert "nerd-dictation" in dialog.engine_tabs
    assert "whisper-docker" in dialog.engine_tabs
    assert "google-cloud-speech" in dialog.engine_tabs
    assert "openai-realtime" in dialog.engine_tabs
    assert "assemblyai" in dialog.engine_tabs


def test_engine_tab_switching(qt_app):
    """Test that selecting an engine switches to its tab."""
    from eloGraf.dialogs import AdvancedUI

    dialog = AdvancedUI()

    # Simulate selecting whisper-docker engine
    dialog._on_stt_engine_changed("whisper-docker")

    # Current tab should be whisper tab
    current_tab = dialog.ui.tabWidget.currentWidget()
    whisper_tab = dialog.engine_tabs["whisper-docker"]

    assert current_tab == whisper_tab
