# ABOUTME: Dynamic UI generation from dataclass field metadata.
# ABOUTME: Creates PyQt6 widgets based on field annotations for settings dialogs.

from __future__ import annotations

import dataclasses
import typing
from typing import Any, Type, get_type_hints
from dataclasses import Field
from PyQt6.QtWidgets import (
    QWidget,
    QLineEdit,
    QCheckBox,
    QComboBox,
    QSlider,
    QPushButton,
    QLabel,
    QFormLayout,
    QHBoxLayout,
    QVBoxLayout,
)
from PyQt6.QtCore import Qt


def create_widget_from_field(field: Field, value: Any) -> QWidget:
    """Create a QWidget from a dataclass field's metadata.

    Args:
        field: Dataclass field with metadata describing the widget
        value: Current value for the field

    Returns:
        QWidget configured according to field metadata
    """
    metadata = field.metadata
    widget_type = metadata.get("widget", "text")

    if widget_type == "text":
        widget = QLineEdit()
        widget.setText(str(value) if value is not None else "")
        if metadata.get("readonly", False):
            widget.setReadOnly(True)
        if "tooltip" in metadata:
            widget.setToolTip(metadata["tooltip"])
        return widget

    elif widget_type == "password":
        widget = QLineEdit()
        widget.setEchoMode(QLineEdit.EchoMode.Password)
        widget.setText(str(value) if value is not None else "")
        if "tooltip" in metadata:
            widget.setToolTip(metadata["tooltip"])
        return widget

    elif widget_type == "checkbox":
        widget = QCheckBox()
        widget.setChecked(bool(value))
        if "tooltip" in metadata:
            widget.setToolTip(metadata["tooltip"])
        return widget

    elif widget_type == "dropdown":
        widget = QComboBox()
        options = metadata.get("options", [])
        for option in options:
            widget.addItem(option)
        # Set current value
        if value in options:
            widget.setCurrentText(value)
        if "tooltip" in metadata:
            widget.setToolTip(metadata["tooltip"])
        return widget

    elif widget_type == "slider":
        container = QWidget()
        layout = QHBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)

        slider = QSlider(Qt.Orientation.Horizontal)
        value_range = metadata.get("range", [0, 100])
        step = metadata.get("step", 1)

        slider.setMinimum(value_range[0])
        slider.setMaximum(value_range[1])
        slider.setSingleStep(step)
        slider.setValue(int(value) if value is not None else value_range[0])

        display_label = QLabel(str(value))
        slider.valueChanged.connect(lambda v: display_label.setText(str(v)))

        layout.addWidget(slider)
        layout.addWidget(display_label)

        if "tooltip" in metadata:
            slider.setToolTip(metadata["tooltip"])

        # Store references for later value reading
        container.slider = slider  # type: ignore
        container.display_label = display_label  # type: ignore

        return container

    elif widget_type == "action_button":
        button = QPushButton(metadata.get("button_text", "Action"))
        callback = metadata.get("on_click")
        if callback and callable(callback):
            button.clicked.connect(callback)
        if "tooltip" in metadata:
            button.setToolTip(metadata["tooltip"])
        return button

    else:
        # Default to text input
        widget = QLineEdit()
        widget.setText(str(value) if value is not None else "")
        return widget


def generate_settings_tab(settings_class: Type) -> QWidget:
    """Generate a complete settings tab from a dataclass.

    Args:
        settings_class: Dataclass type with field metadata

    Returns:
        QWidget containing a form layout with all fields
    """
    tab = QWidget()
    layout = QVBoxLayout(tab)

    # Add help text at the top
    help_label = QLabel(
        "<i>These settings are only used when this engine is selected in the General tab.</i>"
    )
    layout.addWidget(help_label)

    # Create form layout for fields
    form_layout = QFormLayout()
    form_layout.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)

    # Create default instance to get default values
    default_instance = settings_class()

    # Store widgets for later value reading
    widgets_map = {}

    for field in dataclasses.fields(settings_class):
        # Skip fields without metadata or with repr=False (like action buttons that shouldn't show in forms)
        if not field.metadata:
            continue

        # Get default value
        default_value = getattr(default_instance, field.name)

        # Create widget
        widget = create_widget_from_field(field, default_value)

        # Store widget reference
        widgets_map[field.name] = widget

        # Add to form
        label_text = field.metadata.get("label", field.name)

        # For action buttons, don't create a label/field pair, just add the button
        if field.metadata.get("widget") == "action_button":
            # Add button spanning both columns
            form_layout.addRow(widget)
        else:
            label = QLabel(label_text)
            if "tooltip" in field.metadata:
                label.setToolTip(field.metadata["tooltip"])
            form_layout.addRow(label, widget)

    layout.addLayout(form_layout)
    layout.addStretch()

    # Store widgets map on tab for later access
    tab.widgets_map = widgets_map  # type: ignore

    return tab


def read_settings_from_tab(tab: QWidget, settings_class: Type) -> Any:
    """Read values from a settings tab and create a dataclass instance.

    Args:
        tab: QWidget created by generate_settings_tab
        settings_class: Dataclass type to instantiate

    Returns:
        Instance of settings_class with values from widgets
    """
    widgets_map = getattr(tab, 'widgets_map', {})
    values = {}

    # Get actual type hints (resolves string annotations)
    type_hints = get_type_hints(settings_class)

    for field in dataclasses.fields(settings_class):
        if field.name not in widgets_map:
            continue

        widget = widgets_map[field.name]
        widget_type = field.metadata.get("widget", "text")

        if widget_type in ("text", "password"):
            if isinstance(widget, QLineEdit):
                text_value = widget.text()
                # Get actual type from type_hints
                field_type = type_hints.get(field.name, str)

                # Handle Optional types
                if hasattr(field_type, '__origin__'):
                    # This is a generic type like Optional[str]
                    if field_type.__origin__ is typing.Union:
                        # Get the non-None type
                        field_type = next((t for t in field_type.__args__ if t is not type(None)), str)

                if field_type == int:
                    values[field.name] = int(text_value) if text_value else 0
                elif field_type == float:
                    values[field.name] = float(text_value) if text_value else 0.0
                else:
                    values[field.name] = text_value

        elif widget_type == "checkbox":
            if isinstance(widget, QCheckBox):
                values[field.name] = widget.isChecked()

        elif widget_type == "dropdown":
            if isinstance(widget, QComboBox):
                values[field.name] = widget.currentText()

        elif widget_type == "slider":
            # Widget is a container with slider attribute
            if hasattr(widget, 'slider'):
                values[field.name] = widget.slider.value()

    return settings_class(**values)
