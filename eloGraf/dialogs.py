#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
@author: papoteur
@co-author: Pablo Caro

ABOUTME: Dialog windows for Elograf including model management and configuration
ABOUTME: Contains Advanced settings dialog with PulseAudio device selection
"""
from __future__ import annotations

import logging
import os
import urllib.error
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from PyQt6.QtCore import QDir
from PyQt6.QtWidgets import (
    QDialog,
    QKeySequenceEdit,
    QLabel,
    QLineEdit,
    QPushButton,
    QWidget,
    QHBoxLayout,
    QComboBox,
)

import eloGraf.advanced as advanced  # type: ignore

from eloGraf.ui_generator import generate_settings_tab, read_settings_from_tab
from eloGraf.engine_settings_registry import (
    get_all_engine_ids,
    get_engine_settings_class,
    get_engine_display_name,
)
from eloGraf.engines.nerd.ui.dialogs import launch_model_selection_dialog
from eloGraf.audio_recorder import get_audio_devices

from eloGraf.settings import Settings


class AdvancedUI(QDialog):
    def __init__(self, settings: Settings | None = None) -> None:
        super().__init__()
        self.ui = advanced.Ui_Dialog()
        self.ui.setupUi(self)
        self._settings_ref = settings
        self.engine_tabs: Dict[str, QWidget] = {}
        self.engine_settings_classes: Dict[str, type] = {}
        self._add_shortcuts_config()
        self._populate_audio_devices()

        # Generate dynamic tabs for all engines
        self._generate_engine_tabs()

        # Update engine dropdown to include all registered engines
        self._populate_engine_dropdown()

        self.ui.stt_engine_cb.currentIndexChanged.connect(self._on_stt_engine_changed)


    def _generate_engine_tabs(self) -> None:
        """Generate tabs dynamically for all registered engines."""
        self.engine_tabs = {}

        for engine_id in get_all_engine_ids():
            settings_class = get_engine_settings_class(engine_id)
            if not settings_class:
                logging.warning(f"Could not load settings class for engine: {engine_id}")
                continue

            # Generate tab from settings metadata
            instance = None
            if self._settings_ref is not None:
                try:
                    instance = self._settings_ref.get_engine_settings(engine_id)
                except Exception as exc:  # pragma: no cover - defensive
                    logging.debug("Failed to load settings for %s: %s", engine_id, exc)
            tab_widget = generate_settings_tab(settings_class, instance)

            # Add tab to dialog
            display_name = get_engine_display_name(engine_id)
            idx = self.ui.tabWidget.addTab(tab_widget, display_name)

            # Initially disable all engine tabs (they'll be enabled when selected)
            self.ui.tabWidget.setTabEnabled(idx, False)

            # Store reference
            self.engine_tabs[engine_id] = tab_widget
            self.engine_settings_classes[engine_id] = settings_class

            if engine_id == "nerd-dictation":
                button = tab_widget.widgets_map.get("manage_models_action")
                if isinstance(button, QPushButton):
                    try:
                        button.clicked.disconnect()
                    except (TypeError, RuntimeError):
                        pass
                    button.clicked.connect(lambda _checked=False, tab=tab_widget: self._handle_nerd_models(tab))

    def _populate_engine_dropdown(self) -> None:
        """Populate the engine dropdown with all registered engines."""
        # Clear existing items
        self.ui.stt_engine_cb.clear()

        # Add all registered engines with display names
        for engine_id in get_all_engine_ids():
            display_name = get_engine_display_name(engine_id)
            self.ui.stt_engine_cb.addItem(display_name, engine_id)

    def get_engine_settings_dataclass(self, engine_id: str):
        """Return dataclass instance built from the current tab values."""
        tab = self.engine_tabs.get(engine_id)
        settings_class = self.engine_settings_classes.get(engine_id)
        if not tab or not settings_class:
            return None
        return read_settings_from_tab(tab, settings_class)

    def _handle_nerd_models(self, tab: QWidget) -> None:
        launch_model_selection_dialog(self)
        settings_obj = self._settings_ref or Settings()
        try:
            settings_obj.load()
        except Exception:
            return
        _, location = settings_obj.current_model()
        path_widget = getattr(tab, "widgets_map", {}).get("model_path")
        if isinstance(path_widget, QLineEdit):
            path_widget.setText(location)

    def _on_stt_engine_changed(self, _index: int):
        """Handle engine selection change."""
        # Get engine ID from dropdown data
        engine = self.ui.stt_engine_cb.currentData()
        if not engine:
            return

        # Switch to the appropriate tab
        if engine in self.engine_tabs:
            self.ui.tabWidget.setCurrentWidget(self.engine_tabs[engine])

        # Enable/disable tabs based on selected engine
        for engine_name, tab in self.engine_tabs.items():
            enabled = (engine_name == engine)
            idx = self.ui.tabWidget.indexOf(tab)
            if idx >= 0:
                self.ui.tabWidget.setTabEnabled(idx, enabled)

    def _add_shortcuts_config(self) -> None:
        # This is a bit of a hack, but it's the easiest way to add the shortcuts
        # to the general tab without redoing the whole UI file.
        layout = self.ui.general_grid_layout
        row_count = layout.rowCount()

        label_begin = QLabel(self.tr("Global shortcut: Begin"))
        label_begin.setToolTip(self.tr("Global keyboard shortcut to begin dictation (KDE only)"))
        self.beginShortcut = QKeySequenceEdit()
        layout.addWidget(label_begin, row_count, 0)
        layout.addWidget(self.beginShortcut, row_count, 1)

        label_end = QLabel(self.tr("Global shortcut: End"))
        label_end.setToolTip(self.tr("Global keyboard shortcut to end dictation (KDE only)"))
        self.endShortcut = QKeySequenceEdit()
        layout.addWidget(label_end, row_count + 1, 0)
        layout.addWidget(self.endShortcut, row_count + 1, 1)

        label_toggle = QLabel(self.tr("Global shortcut: Toggle"))
        label_toggle.setToolTip(self.tr("Global keyboard shortcut to toggle dictation (KDE only)"))
        self.toggleShortcut = QKeySequenceEdit()
        layout.addWidget(label_toggle, row_count + 2, 0)
        layout.addWidget(self.toggleShortcut, row_count + 2, 1)

        label_suspend = QLabel(self.tr("Global shortcut: Suspend"))
        label_suspend.setToolTip(self.tr("Global keyboard shortcut to suspend dictation (KDE only)"))
        self.suspendShortcut = QKeySequenceEdit()
        layout.addWidget(label_suspend, row_count + 3, 0)
        layout.addWidget(self.suspendShortcut, row_count + 3, 1)

        label_resume = QLabel(self.tr("Global shortcut: Resume"))
        label_resume.setToolTip(self.tr("Global keyboard shortcut to resume dictation (KDE only)"))
        self.resumeShortcut = QKeySequenceEdit()
        layout.addWidget(label_resume, row_count + 4, 0)
        layout.addWidget(self.resumeShortcut, row_count + 4, 1)


    def _populate_audio_devices(self) -> None:
        """Populate the device name combo box with available audio devices and add refresh button."""
        # Get the layout where deviceName is located
        layout = self.ui.general_grid_layout

        # Find the deviceName combobox row
        device_combo = self.ui.deviceName

        # Populate initial devices
        self._refresh_audio_devices()

        # Create refresh button
        refresh_button = QPushButton("🔄")
        refresh_button.setMaximumWidth(40)
        refresh_button.setToolTip("Refresh audio device list")
        refresh_button.clicked.connect(self._refresh_audio_devices)

        # Add refresh button next to the combobox (row 3, column 2)
        layout.addWidget(refresh_button, 3, 2, 1, 1)

    def _refresh_audio_devices(self) -> None:
        """Refresh the audio devices list in the dropdown."""
        devices = get_audio_devices(backend="parec")
        combo = self.ui.deviceName

        # Save current selection
        current_value = combo.currentData() or combo.currentText()

        # Repopulate
        combo.clear()
        for device_value, display_name in devices:
            combo.addItem(display_name, device_value)

        # Restore selection if it still exists
        index = combo.findData(current_value)
        if index >= 0:
            combo.setCurrentIndex(index)
        elif current_value:
            # Fallback to text matching
            index = combo.findText(current_value)
            if index >= 0:
                combo.setCurrentIndex(index)

    def show_validation_warnings_dialog(
        self,
        general_warnings: dict[str, str],
        engine_warnings: dict[str, str],
        engine_id: str
    ) -> bool:
        """Show dialog with validation warnings and ask user to confirm.

        Args:
            general_warnings: Warnings from General tab
            engine_warnings: Warnings from engine tab
            engine_id: Current engine identifier

        Returns:
            True if user wants to save anyway, False to go back and fix
        """
        from PyQt6.QtWidgets import QMessageBox

        warning_lines = []

        if general_warnings:
            warning_lines.append("**General Settings:**")
            for field, message in general_warnings.items():
                warning_lines.append(f"  • {message}")

        if engine_warnings:
            engine_name = get_engine_display_name(engine_id)
            warning_lines.append(f"\n**{engine_name}:**")
            for field, message in engine_warnings.items():
                warning_lines.append(f"  • {message}")

        message = (
            "⚠️ The following warnings were found:\n\n" +
            "\n".join(warning_lines) +
            "\n\nDo you want to save anyway?"
        )

        reply = QMessageBox.warning(
            self,
            "Validation Warnings",
            message,
            QMessageBox.StandardButton.Save | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel
        )

        return reply == QMessageBox.StandardButton.Save

    def add_tab_warning_icon(self, tab_widget: QWidget, has_warnings: bool) -> None:
        """Add or remove warning icon from tab label.

        Args:
            tab_widget: The tab widget
            has_warnings: True to add icon, False to remove
        """
        tab_index = self.ui.tabWidget.indexOf(tab_widget)
        if tab_index < 0:
            return

        original_text = self.ui.tabWidget.tabText(tab_index)

        # Remove existing warning icon if present
        if original_text.startswith("⚠️ "):
            original_text = original_text[3:]

        # Add warning icon if needed
        if has_warnings:
            new_text = f"⚠️ {original_text}"
        else:
            new_text = original_text

        self.ui.tabWidget.setTabText(tab_index, new_text)
