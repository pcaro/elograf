# ABOUTME: Tests for dynamic UI generation from settings metadata.
# ABOUTME: Validates widget creation and data binding for engine settings tabs.

from __future__ import annotations

import os
import dataclasses
import pytest
from PyQt6.QtWidgets import QApplication, QLineEdit, QCheckBox, QComboBox, QSlider, QPushButton


@pytest.fixture(scope="module")
def qt_app():
    """Create QApplication for tests that need Qt."""
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    app = QApplication.instance()
    if not app:
        app = QApplication([])
    yield app


def test_create_text_widget_from_metadata(qt_app):
    """Test creating a text input widget from field metadata."""
    from eloGraf.ui_generator import create_widget_from_field

    from dataclasses import dataclass, field

    @dataclass
    class TestSettings:
        test_field: str = field(
            default="default_value",
            metadata={"label": "Test Field", "widget": "text"}
        )

    fields = dataclasses.fields(TestSettings)
    test_field = fields[0]

    widget = create_widget_from_field(test_field, "default_value")

    assert isinstance(widget, QLineEdit)
    assert widget.text() == "default_value"


def test_create_password_widget_from_metadata(qt_app):
    """Test creating a password input widget from field metadata."""
    from eloGraf.ui_generator import create_widget_from_field
    from dataclasses import dataclass, field
    from PyQt6.QtWidgets import QLineEdit

    @dataclass
    class TestSettings:
        api_key: str = field(
            default="",
            metadata={"label": "API Key", "widget": "password"}
        )

    fields = dataclasses.fields(TestSettings)
    api_key_field = fields[0]

    widget = create_widget_from_field(api_key_field, "secret123")

    assert isinstance(widget, QLineEdit)
    assert widget.echoMode() == QLineEdit.EchoMode.Password
    assert widget.text() == "secret123"


def test_create_checkbox_widget_from_metadata(qt_app):
    """Test creating a checkbox widget from field metadata."""
    from eloGraf.ui_generator import create_widget_from_field

    from dataclasses import dataclass, field

    @dataclass
    class TestSettings:
        enabled: bool = field(
            default=False,
            metadata={"label": "Enabled", "widget": "checkbox"}
        )

    fields = dataclasses.fields(TestSettings)
    enabled_field = fields[0]

    widget = create_widget_from_field(enabled_field, True)

    assert isinstance(widget, QCheckBox)
    assert widget.isChecked() is True


def test_create_dropdown_widget_from_metadata(qt_app):
    """Test creating a dropdown widget from field metadata."""
    from eloGraf.ui_generator import create_widget_from_field

    from dataclasses import dataclass, field

    @dataclass
    class TestSettings:
        model: str = field(
            default="base",
            metadata={
                "label": "Model",
                "widget": "dropdown",
                "options": ["tiny", "base", "large"]
            }
        )

    fields = dataclasses.fields(TestSettings)
    model_field = fields[0]

    widget = create_widget_from_field(model_field, "large")

    assert isinstance(widget, QComboBox)
    assert widget.count() == 3
    assert widget.itemText(0) == "tiny"
    assert widget.itemText(1) == "base"
    assert widget.itemText(2) == "large"
    assert widget.currentText() == "large"


def test_create_slider_widget_from_metadata(qt_app):
    """Test creating a slider widget from field metadata."""
    from eloGraf.ui_generator import create_widget_from_field

    from dataclasses import dataclass, field

    @dataclass
    class TestSettings:
        timeout: int = field(
            default=0,
            metadata={
                "label": "Timeout",
                "widget": "slider",
                "range": [0, 100],
                "step": 1
            }
        )

    fields = dataclasses.fields(TestSettings)
    timeout_field = fields[0]

    widget = create_widget_from_field(timeout_field, 50)

    # Slider returns a container widget with slider and label
    assert widget is not None


def test_create_action_button_from_metadata(qt_app):
    """Test creating an action button from field metadata."""
    from eloGraf.ui_generator import create_widget_from_field

    from dataclasses import dataclass, field

    def mock_callback():
        pass

    @dataclass
    class TestSettings:
        action: str = field(
            default="",
            metadata={
                "widget": "action_button",
                "button_text": "Click Me",
                "on_click": mock_callback
            }
        )

    fields = dataclasses.fields(TestSettings)
    action_field = fields[0]

    widget = create_widget_from_field(action_field, "")

    assert isinstance(widget, QPushButton)
    assert widget.text() == "Click Me"


def test_generate_settings_tab_uses_instance_values(qt_app):
    """Tabs should reflect values from an existing settings instance."""
    from eloGraf.ui_generator import generate_settings_tab
    from eloGraf.engines.openai.settings import OpenAISettings

    instance = OpenAISettings(api_key="secret", language="es")
    tab = generate_settings_tab(OpenAISettings, instance)

    api_widget = tab.widgets_map["api_key"]
    language_widget = tab.widgets_map["language"]

    assert api_widget.text() == "secret"
    assert language_widget.text() == "es"


def test_readonly_text_widget(qt_app):
    """Test creating a readonly text widget."""
    from eloGraf.ui_generator import create_widget_from_field

    from dataclasses import dataclass, field

    @dataclass
    class TestSettings:
        path: str = field(
            default="/path/to/model",
            metadata={
                "label": "Model Path",
                "widget": "text",
                "readonly": True
            }
        )

    fields = dataclasses.fields(TestSettings)
    path_field = fields[0]

    widget = create_widget_from_field(path_field, "/path/to/model")

    assert isinstance(widget, QLineEdit)
    assert widget.isReadOnly() is True
    assert widget.text() == "/path/to/model"


def test_generate_tab_for_engine_settings(qt_app):
    """Test generating a complete tab for engine settings."""
    from eloGraf.ui_generator import generate_settings_tab
    from eloGraf.engines.nerd.settings import NerdSettings

    tab_widget = generate_settings_tab(NerdSettings)

    assert tab_widget is not None
    # Tab should have a form layout with widgets for each field
    layout = tab_widget.layout()
    assert layout is not None


def test_read_values_from_widgets(qt_app):
    """Test reading values back from widgets into a dataclass."""
    from eloGraf.ui_generator import generate_settings_tab, read_settings_from_tab
    from eloGraf.engines.nerd.settings import NerdSettings

    # Create tab with default values
    tab_widget = generate_settings_tab(NerdSettings)

    # Read values back
    settings = read_settings_from_tab(tab_widget, NerdSettings)

    assert isinstance(settings, NerdSettings)
    # Should have default values
    assert settings.sample_rate == 44100
    assert settings.timeout == 0
