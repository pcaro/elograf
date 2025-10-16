# ABOUTME: Tests for PulseAudio device persistence in the UI dialog.
# ABOUTME: Verifies deviceName dropdown correctly stores and retrieves device selections.

import os
import pytest
from PyQt6.QtCore import QSettings
from PyQt6.QtWidgets import QApplication

from eloGraf.dialogs import AdvancedUI
from eloGraf.settings import Settings


@pytest.fixture(scope="module")
def qt_app():
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    yield app


def test_device_combobox_has_data_set(qt_app):
    """Test that deviceName combobox items have data properly set."""
    settings = Settings()
    settings.deviceName = "default"

    dialog = AdvancedUI(settings)

    # Verify combobox has items
    assert dialog.ui.deviceName.count() > 0, "deviceName combobox should have at least one item"

    # Verify each item has data set (not None)
    for i in range(dialog.ui.deviceName.count()):
        data = dialog.ui.deviceName.itemData(i)
        assert data is not None, f"Item {i} should have data set, but got None"
        assert data != "", f"Item {i} should have non-empty data, but got empty string"


def test_device_selection_persists_via_dialog(qt_app, tmp_path):
    """Test that changing deviceName in dialog and saving actually persists the selection."""
    # Create test settings with custom device
    settings_file = tmp_path / "test_settings.ini"
    backend = QSettings(str(settings_file), QSettings.Format.IniFormat)
    backend.clear()
    backend.sync()

    settings = Settings(backend)
    settings.deviceName = "default"
    settings.save()
    backend.sync()

    # Create dialog and simulate selecting a different device
    dialog = AdvancedUI(settings)

    # Find a non-default device if available
    test_device = None
    for i in range(dialog.ui.deviceName.count()):
        data = dialog.ui.deviceName.itemData(i)
        if data and data != "default":
            test_device = data
            dialog.ui.deviceName.setCurrentIndex(i)
            break

    # If no other devices available, skip test
    if not test_device:
        pytest.skip("No non-default audio devices available for testing")

    # Simulate what tray_icon.py does when saving settings
    device_data = dialog.ui.deviceName.currentData()
    settings.deviceName = device_data if device_data else "default"
    settings.save()
    backend.sync()

    # Reload settings and verify device was saved
    settings2 = Settings(QSettings(str(settings_file), QSettings.Format.IniFormat))
    settings2.load()

    assert settings2.deviceName == test_device, \
        f"Expected deviceName to be '{test_device}', but got '{settings2.deviceName}'"
