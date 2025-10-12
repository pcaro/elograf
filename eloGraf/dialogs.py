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
from typing import List, Optional, Tuple

from subprocess import run
import json
from PyQt6.QtCore import QDir
from PyQt6.QtWidgets import (
    QDialog,
    QKeySequenceEdit,
    QLabel,
)

import eloGraf.advanced as advanced  # type: ignore

from eloGraf.ui_generator import generate_settings_tab
from eloGraf.engine_settings_registry import (
    get_all_engine_ids,
    get_engine_settings_class,
    get_engine_display_name,
)

def get_pulseaudio_sources() -> List[Tuple[str, str]]:
    """Get available PulseAudio source devices.

    Tries JSON format first (newer pactl), then falls back to text parsing,
    and finally to `pactl list sources short`.

    Returns:
        List of tuples (device_name, description)
    """
    # Try JSON output for robust parsing
    try:
        result = run(["pactl", "-f", "json", "list", "sources"], capture_output=True, text=True, timeout=5)
        if result.returncode == 0 and result.stdout.strip():
            try:
                data = json.loads(result.stdout)
                sources: List[Tuple[str, str]] = []
                for src in data or []:
                    name = src.get("name") or ""
                    props = src.get("properties", {}) or {}
                    desc = props.get("node.description") or props.get("device.description") or name
                    if name:
                        if name.endswith(".monitor") and "monitor" not in desc.lower():
                            desc = f"{desc} (monitor)"
                        sources.append((name, desc))
                if sources:
                    return sources
            except json.JSONDecodeError:
                pass
    except Exception as exc:
        logging.debug("pactl json parse failed: %s", exc)

    # Fallback to text parsing of `pactl list sources`
    try:
        result = run(["pactl", "list", "sources"], capture_output=True, text=True, timeout=5)
        if result.returncode == 0 and result.stdout:
            sources: List[Tuple[str, str]] = []
            current_name: Optional[str] = None
            current_desc: Optional[str] = None
            props_mode = False
            for raw in result.stdout.splitlines():
                line = raw.strip()
                if line.startswith("Source #"):
                    if current_name and current_desc:
                        if current_name.endswith(".monitor") and "monitor" not in current_desc.lower():
                            current_desc = f"{current_desc} (monitor)"
                        sources.append((current_name, current_desc))
                    current_name, current_desc = None, None
                    props_mode = False
                elif line.startswith("Name:"):
                    current_name = line.split(":", 1)[1].strip()
                elif line.startswith("Description:"):
                    current_desc = line.split(":", 1)[1].strip()
                elif line.startswith("Properties:"):
                    props_mode = True
                elif props_mode and "node.description" in line and "=" in line and not current_desc:
                    # node.description = "..."
                    try:
                        current_desc = line.split("=", 1)[1].strip().strip('"')
                    except Exception:
                        pass
            if current_name and current_desc:
                if current_name.endswith(".monitor") and "monitor" not in current_desc.lower():
                    current_desc = f"{current_desc} (monitor)"
                sources.append((current_name, current_desc))
            if sources:
                return sources
    except Exception as exc:
        logging.debug("pactl list sources parse failed: %s", exc)

    # Last resort: short listing
    try:
        result = run(["pactl", "list", "sources", "short"], capture_output=True, text=True, timeout=5)
        if result.returncode == 0 and result.stdout:
            sources: List[Tuple[str, str]] = []
            for line in result.stdout.splitlines():
                parts = line.split()  # index, name, driver, format, state
                if len(parts) >= 2:
                    name = parts[1]
                    desc = name
                    if name.endswith(".monitor") and "monitor" not in desc.lower():
                        desc = f"{desc} (monitor)"
                    sources.append((name, desc))
            return sources
    except Exception as exc:
        logging.debug("pactl short parse failed: %s", exc)

    return []


class AdvancedUI(QDialog):
    def __init__(self) -> None:
        super().__init__()
        self.ui = advanced.Ui_Dialog()
        self.ui.setupUi(self)
        self._add_shortcuts_config()
        self._populate_audio_devices()

        # Remove all static engine tabs from the UI file
        self._remove_static_engine_tabs()

        # Generate dynamic tabs for all engines
        self._generate_engine_tabs()

        # Update engine dropdown to include all registered engines
        self._populate_engine_dropdown()

        self.ui.stt_engine_cb.currentTextChanged.connect(self._on_stt_engine_changed)

    def _remove_static_engine_tabs(self) -> None:
        """Remove all engine tabs from the .ui file, keeping only General tab."""
        # List of tab object names to remove (engine tabs from .ui file)
        tabs_to_remove = [
            "nerd_dictation_tab",
            "whisper_docker_tab",
            "google_cloud_tab",
            "openai_tab",
        ]

        # Remove tabs by finding their index and removing from back to front
        for tab_name in tabs_to_remove:
            if hasattr(self.ui, tab_name):
                tab = getattr(self.ui, tab_name)
                idx = self.ui.tabWidget.indexOf(tab)
                if idx >= 0:
                    self.ui.tabWidget.removeTab(idx)

    def _generate_engine_tabs(self) -> None:
        """Generate tabs dynamically for all registered engines."""
        self.engine_tabs = {}

        for engine_id in get_all_engine_ids():
            settings_class = get_engine_settings_class(engine_id)
            if not settings_class:
                logging.warning(f"Could not load settings class for engine: {engine_id}")
                continue

            # Generate tab from settings metadata
            tab_widget = generate_settings_tab(settings_class)

            # Add tab to dialog
            display_name = get_engine_display_name(engine_id)
            idx = self.ui.tabWidget.addTab(tab_widget, display_name)

            # Initially disable all engine tabs (they'll be enabled when selected)
            self.ui.tabWidget.setTabEnabled(idx, False)

            # Store reference
            self.engine_tabs[engine_id] = tab_widget

    def _populate_engine_dropdown(self) -> None:
        """Populate the engine dropdown with all registered engines."""
        # Clear existing items
        self.ui.stt_engine_cb.clear()

        # Add all registered engines
        for engine_id in get_all_engine_ids():
            display_name = get_engine_display_name(engine_id)
            self.ui.stt_engine_cb.addItem(engine_id)

    def _on_stt_engine_changed(self, engine: str):
        """Handle engine selection change."""
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
        """Populate the device name combo box with available PulseAudio sources."""
        sources = get_pulseaudio_sources()
        self.ui.deviceName.clear()
        self.ui.deviceName.addItem("default", "default")

        for device_name, description in sources:
            display_text = f"{description} ({device_name})"
            self.ui.deviceName.addItem(display_text, device_name)
