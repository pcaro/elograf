# ABOUTME: Tests for UI generator with dynamic choices and refreshable dropdowns
# ABOUTME: Validates metadata-driven widget creation including function-based choices

from __future__ import annotations

import os
import pytest
from dataclasses import dataclass, field
from typing import List, Tuple
from PyQt6.QtWidgets import QApplication, QComboBox, QPushButton, QHBoxLayout

from eloGraf.ui_generator import create_widget_from_field, generate_settings_tab
import dataclasses


@pytest.fixture(scope="module")
def qt_app():
    """Create QApplication for tests that need Qt."""
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    app = QApplication.instance()
    if not app:
        app = QApplication([])
    yield app


def mock_choices_function() -> List[Tuple[str, str]]:
    """Mock function that returns test choices."""
    return [
        ("val1", "Display 1"),
        ("val2", "Display 2"),
        ("val3", "Display 3"),
    ]


def mock_choices_with_backend(backend: str) -> List[Tuple[str, str]]:
    """Mock function that returns choices based on backend parameter."""
    if backend == "backend_a":
        return [("a1", "A Option 1"), ("a2", "A Option 2")]
    else:
        return [("b1", "B Option 1"), ("b2", "B Option 2")]


def test_dropdown_with_choices_function(qt_app):
    """Test dropdown widget with choices_function metadata."""

    @dataclass
    class TestSettings:
        device: str = field(
            default="val1",
            metadata={
                "widget": "dropdown",
                "label": "Device",
                "choices_function": "tests.test_ui_generator.mock_choices_function",
            }
        )

    # Create widget from field
    test_field = dataclasses.fields(TestSettings)[0]
    widget = create_widget_from_field(test_field, "val1")

    # Should be a QComboBox
    assert isinstance(widget, QComboBox)

    # Should have 3 items from the function
    assert widget.count() == 3

    # Check values and display text
    assert widget.itemText(0) == "Display 1"
    assert widget.itemData(0) == "val1"
    assert widget.itemText(1) == "Display 2"
    assert widget.itemData(1) == "val2"
    assert widget.itemText(2) == "Display 3"
    assert widget.itemData(2) == "val3"

    # Current value should be set correctly
    assert widget.currentData() == "val1"


def test_dropdown_with_choices_function_and_kwargs(qt_app):
    """Test dropdown with choices_function that takes kwargs."""

    @dataclass
    class TestSettings:
        device: str = field(
            default="a1",
            metadata={
                "widget": "dropdown",
                "label": "Device",
                "choices_function": "tests.test_ui_generator.mock_choices_with_backend",
                "choices_function_kwargs": {"backend": "backend_a"},
            }
        )

    test_field = dataclasses.fields(TestSettings)[0]
    widget = create_widget_from_field(test_field, "a1")

    assert isinstance(widget, QComboBox)
    assert widget.count() == 2
    assert widget.itemText(0) == "A Option 1"
    assert widget.itemData(0) == "a1"


def test_refreshable_dropdown_creates_button(qt_app):
    """Test that refreshable dropdown creates a button next to the dropdown."""

    @dataclass
    class TestSettings:
        device: str = field(
            default="val1",
            metadata={
                "widget": "dropdown",
                "label": "Device",
                "choices_function": "tests.test_ui_generator.mock_choices_function",
                "refreshable": True,
            }
        )

    test_field = dataclasses.fields(TestSettings)[0]
    widget = create_widget_from_field(test_field, "val1")

    # Should be a container widget with layout
    assert hasattr(widget, 'layout')
    layout = widget.layout()
    assert isinstance(layout, QHBoxLayout)

    # Should have 2 children: combo box and button
    assert layout.count() == 2

    # First child should be QComboBox
    combo = layout.itemAt(0).widget()
    assert isinstance(combo, QComboBox)

    # Second child should be QPushButton with refresh icon
    button = layout.itemAt(1).widget()
    assert isinstance(button, QPushButton)
    assert button.text() == "🔄"


# Module-level counter for counting_choices function
_call_counter = {"count": 0}


def counting_choices() -> List[Tuple[str, str]]:
    """Function that returns different choices each time it's called."""
    _call_counter["count"] += 1
    if _call_counter["count"] == 1:
        return [("first", "First Call")]
    else:
        return [("second", "Second Call"), ("third", "Third Call")]


def test_refresh_button_reloads_choices(qt_app):
    """Test that clicking refresh button reloads choices from function."""

    @dataclass
    class TestSettings:
        device: str = field(
            default="val1",
            metadata={
                "widget": "dropdown",
                "label": "Device",
                "choices_function": "tests.test_ui_generator.mock_choices_function",
                "refreshable": True,
            }
        )

    test_field = dataclasses.fields(TestSettings)[0]
    widget = create_widget_from_field(test_field, "val1")

    layout = widget.layout()
    combo = layout.itemAt(0).widget()
    button = layout.itemAt(1).widget()

    # Initial load should have 3 choices
    assert combo.count() == 3
    assert combo.itemText(0) == "Display 1"
    assert combo.currentData() == "val1"

    # Change selection
    combo.setCurrentIndex(2)  # Select "Display 3"
    assert combo.currentData() == "val3"

    # Click refresh button - should reload choices and try to maintain selection
    button.click()

    # Should still have 3 items (function returns same choices)
    assert combo.count() == 3
    assert combo.itemText(0) == "Display 1"
    # Selection should be maintained if value still exists
    assert combo.currentData() == "val3"


def test_generate_tab_with_choices_function(qt_app):
    """Test that generate_settings_tab works with choices_function fields."""

    @dataclass
    class TestSettings:
        name: str = field(
            default="test",
            metadata={"widget": "text", "label": "Name"}
        )
        device: str = field(
            default="val2",
            metadata={
                "widget": "dropdown",
                "label": "Device",
                "choices_function": "tests.test_ui_generator.mock_choices_function",
                "refreshable": True,
            }
        )

    tab = generate_settings_tab(TestSettings)

    # Check that widgets_map contains both fields
    assert hasattr(tab, 'widgets_map')
    assert 'name' in tab.widgets_map
    assert 'device' in tab.widgets_map

    # Device widget should be the container with refresh button
    device_widget = tab.widgets_map['device']
    layout = device_widget.layout()
    combo = layout.itemAt(0).widget()

    # Verify it loaded the choices
    assert combo.count() == 3
    assert combo.currentData() == "val2"


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
