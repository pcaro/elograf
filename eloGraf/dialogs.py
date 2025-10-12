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

from subprocess import Popen, run, PIPE
import json
from zipfile import ZipFile
from PyQt6.QtCore import QCoreApplication, QDir, QSize, Qt, QTimer
from PyQt6.QtGui import QIcon, QStandardItem, QStandardItemModel
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QKeySequenceEdit,
    QLabel,
    QGridLayout,
    QLineEdit,
    QProgressBar,
    QPushButton,
    QSizePolicy,
    QTableView,
    QWidget,
    QVBoxLayout,
)

import eloGraf.advanced as advanced  # type: ignore
import eloGraf.confirm as confirm  # type: ignore
import eloGraf.custom as custom  # type: ignore

from eloGraf.ui_generator import generate_settings_tab
from eloGraf.engine_settings_registry import (
    get_all_engine_ids,
    get_engine_settings_class,
    get_engine_display_name,
)
from eloGraf.model_repository import (
    MODEL_GLOBAL_PATH,
    MODEL_LIST,
    MODEL_USER_PATH,
    MODELS_URL,
    download_model_archive,
    download_model_list,
    filter_available_models,
    get_size,
    load_model_index,
    model_list_path,
)
from eloGraf.settings import DEFAULT_RATE, Settings
import eloGraf.version as version  # type: ignore


class Models(QStandardItemModel):
    def __init__(self) -> None:
        super().__init__(0, 5)
        headers = [
            self.tr("Language"),
            self.tr("Name"),
            self.tr("Version"),
            self.tr("Size"),
            self.tr("Class"),
        ]
        for index, label in enumerate(headers):
            self.setHeaderData(index, Qt.Orientation.Horizontal, label)


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


class ConfirmDownloadUI(QDialog):
    def __init__(self, text: str) -> None:
        super().__init__()
        self.ui = confirm.Ui_Dialog()
        self.ui.setupUi(self)
        self.ui.message.setText(text)


class CustomUI(QDialog):
    def __init__(self, index: int, settings: Settings) -> None:
        super().__init__()
        self.settings = settings
        self.ui = custom.Ui_Dialog()
        self.ui.setupUi(self)
        self.ui.filePicker.clicked.connect(self.selectCustom)
        self.index = index

    def selectCustom(self) -> None:
        current_path = self.ui.filePicker.text()
        path = current_path if os.path.isdir(current_path) else QDir.homePath()
        new_path = QFileDialog.getExistingDirectory(
            self, self.tr("Select the model path"), path
        )
        if new_path:
            self.ui.filePicker.setText(new_path)
            self.ui.nameLineEdit.setText(os.path.basename(new_path))
            size, unit = get_size(new_path)
            unit = self.tr(unit)
            self.ui.sizeLineEdit.setText(f"{size:.2f} {unit}")

    def accept(self) -> None:
        name = self.ui.nameLineEdit.text()
        language = self.ui.languageLineEdit.text()
        if not language:
            self.ui.languageLineEdit.setStyleSheet("border: 3px solid red")
            QTimer.singleShot(1000, lambda: self.ui.languageLineEdit.setStyleSheet(""))
            return
        if not name:
            self.ui.nameLineEdit.setStyleSheet("border: 3px solid red")
            QTimer.singleShot(1000, lambda: self.ui.nameLineEdit.setStyleSheet(""))
            return
        new_path = self.ui.filePicker.text()
        if os.path.exists(new_path):
            if self.index == -1:
                self.settings.add_model(
                    language,
                    name,
                    self.ui.versionLineEdit.text(),
                    self.ui.sizeLineEdit.text(),
                    self.ui.classLineEdit.text(),
                    new_path,
                )
                self.index = len(self.settings.models)
            else:
                model = self.settings.models[self.index]
                model["language"] = language
                model["name"] = name
                model["version"] = self.ui.versionLineEdit.text()
                model["size"] = self.ui.sizeLineEdit.text()
                model["type"] = self.ui.classLineEdit.text()
                model["location"] = new_path
            self.done(self.index)


class DownloadPopup(QDialog):
    def __init__(self, settings: Settings, installed: List[str], parent=None) -> None:
        super().__init__(parent)
        self.settings = settings
        self.setWindowTitle("Elograf")
        self.setWindowIcon(QIcon(":/icons/elograf/24/micro.png"))
        self.list = Models()
        raw_models = load_model_index()
        self.remote_models = filter_available_models(raw_models, installed)
        for model_data in sorted(
            self.remote_models, key=lambda item: item["lang_text"]
        ):
            language_item = QStandardItem(model_data["lang_text"])
            name_item = QStandardItem(model_data["name"])
            size_item = QStandardItem(model_data["size_text"])
            version_item = QStandardItem(model_data["version"])
            class_item = QStandardItem(model_data["type"])
            self.list.appendRow(
                [
                    language_item,
                    name_item,
                    version_item,
                    size_item,
                    class_item,
                ]
            )
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        layout = QVBoxLayout(self)
        self.table = QTableView()
        self.table.setModel(self.list)
        layout.addWidget(self.table)
        self.table.resizeColumnsToContents()
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.bar = QProgressBar()
        self.bar.setMaximum(100)
        self.bar.setMinimum(0)
        layout.addWidget(self.bar)
        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        system_button = QPushButton(self.tr("Import system wide"))
        button_box.addButton(system_button, QDialogButtonBox.ButtonRole.ActionRole)
        user_button = QPushButton(self.tr("Import in user space"))
        button_box.addButton(user_button, QDialogButtonBox.ButtonRole.ActionRole)
        layout.addWidget(button_box)
        system_button.clicked.connect(self.system)
        user_button.clicked.connect(self.user)
        button_box.rejected.connect(self.close)

    def sizeHint(self) -> QSize:  # type: ignore[override]
        width = sum(self.table.columnWidth(i) for i in range(self.list.columnCount()))
        width += self.table.verticalHeader().sizeHint().width()
        width += self.table.verticalScrollBar().sizeHint().width()
        width += self.table.frameWidth() * 2
        return QSize(width, self.height())

    def user(self) -> None:
        rc, temp_file, name = self.import_model()
        if rc:
            try:
                with ZipFile(temp_file) as archive:
                    archive.extractall(str(MODEL_USER_PATH))
            except Exception:
                logging.warning("Invalid file")
            self.register(str((MODEL_USER_PATH / name)))
            self.done(1)

    def system(self) -> None:
        rc, temp_file, name = self.import_model()
        if rc:
            while not MODEL_GLOBAL_PATH.exists():
                process = Popen(["pkexec", "mkdir", "-p", "-m=777", str(MODEL_GLOBAL_PATH)])
                if process.wait() != 0:
                    retry = ConfirmDownloadUI(
                        self.tr("The application failed to save the model. Do you want to retry?")
                    )
                    if not retry.exec():
                        break
            try:
                with ZipFile(temp_file) as archive:
                    archive.extractall(str(MODEL_GLOBAL_PATH))
                    self.register(str((MODEL_GLOBAL_PATH / name)))
            except Exception:
                warning = ConfirmDownloadUI(
                    self.tr(
                        "The model can't be saved. Check for space available or credentials for {}"
                    ).format(MODEL_GLOBAL_PATH)
                )
                warning.exec()
            self.done(1)

    def progress(self, n: int, size: int, total: int) -> None:
        if total is not None:
            self.bar.setValue(n * size * 100 // total)
        else:
            self.bar.setMaximum(0)
            self.bar.setValue(n)
        self.bar.repaint()
        QCoreApplication.processEvents()

    def import_model(self) -> Tuple[bool, str, str]:
        selection = self.table.selectionModel().selectedRows()
        if not selection:
            logging.warning("No selected model")
            return False, "", ""
        self.name = self.list.data(self.list.index(selection[0].row(), 1))
        size = self.list.data(self.list.index(selection[0].row(), 3))
        confirmation = ConfirmDownloadUI(
            self.tr("We will download the model {} of {} from {}. Do you agree?").format(
                self.name, size, MODELS_URL
            )
        )
        if not confirmation.exec():
            return False, "", ""
        url = next((model["url"] for model in self.remote_models if model["name"] == self.name), "")
        if not url:
            logging.warning("The model has no url provided")
            return False, "", ""
        try:
            temp_file = download_model_archive(url, reporthook=self.progress)
        except urllib.error.URLError:
            logging.warning("Network unavailable or bad URL")
            return False, "", ""
        return True, temp_file, self.name

    def register(self, location: str) -> None:
        existing_names = {model["name"] for model in self.settings.models}
        if self.name not in existing_names:
            selection = self.table.selectionModel().selectedRows()
            if not selection:
                return
            row = selection[0].row()
            self.settings.add_model(
                self.list.data(self.list.index(row, 0)),
                self.name,
                self.list.data(self.list.index(row, 2)),
                self.list.data(self.list.index(row, 3)),
                self.list.data(self.list.index(row, 4)),
                location,
            )


class ConfigPopup(QDialog):
    def __init__(self, current_model: str, parent=None) -> None:
        super().__init__(parent)
        self.settings = Settings()
        self.currentModel = current_model
        self.returnValue = None

        self.setWindowTitle(self.tr("Manage Models"))
        self.setWindowIcon(QIcon(":/icons/elograf/24/micro.png"))
        layout = QVBoxLayout(self)
        model_list_path()
        self.table = QTableView()
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        layout.addWidget(self.table)
        self.settings.load()
        self.list, selected = self.get_list()
        self.table.setModel(self.list)
        if selected is not None:
            self.table.selectRow(selected)

        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        remote_button = QPushButton(self.tr("Import remote model"))
        button_box.addButton(remote_button, QDialogButtonBox.ButtonRole.ActionRole)
        local_button = QPushButton(self.tr("Import local model"))
        button_box.addButton(local_button, QDialogButtonBox.ButtonRole.ActionRole)
        layout.addWidget(button_box)

        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.accept)
        local_button.clicked.connect(self.local)
        remote_button.clicked.connect(self.remote)
        self.table.doubleClicked.connect(self.edit)

        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.table.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.table.resizeColumnsToContents()
        self.table.verticalHeader().hide()
        self.button_height = button_box.sizeHint().height()

    def update_list(self, selected: int) -> None:
        self.list, _ = self.get_list()
        self.table.setModel(self.list)
        self.table.resizeColumnsToContents()
        self.list.layoutChanged.emit()
        if selected is not None:
            self.table.selectRow(selected)

    def get_list(self) -> Tuple[Models, Optional[int]]:
        model_list = Models()
        selected_index: Optional[int] = None
        for index, settings_model in enumerate(self.settings.models):
            language_item = QStandardItem(settings_model["language"])
            name_item = QStandardItem(settings_model["name"])
            version_item = QStandardItem(settings_model["version"])
            size_item = QStandardItem(settings_model["size"])
            class_item = QStandardItem(settings_model["type"])
            model_list.appendRow(
                [language_item, name_item, version_item, size_item, class_item]
            )
            if self.currentModel == name_item.text():
                selected_index = index
        return model_list, selected_index

    def accept(self) -> None:  # type: ignore[override]
        selected_indexes = self.table.selectedIndexes()
        model_name = ""
        for index in selected_indexes:
            model_name = self.list.data(self.list.index(index.row(), 1))
        self.settings.setValue("Model/name", model_name)
        self.settings.save()
        self.returnValue = [model_name]
        self.close()

    def local(self) -> None:
        dialog = CustomUI(-1, self.settings)
        rc = dialog.exec()
        if rc:
            self.update_list(rc - 1)

    def remote(self) -> None:
        index_path = model_list_path()
        if not index_path.exists():
            confirmation = ConfirmDownloadUI(
                self.tr(
                    "We will download the list of models from {}.\nDo you agree?".format(
                        MODELS_URL
                    )
                )
            )
            if confirmation.exec():
                try:
                    download_model_list()
                except urllib.error.URLError:
                    logging.warning("Network unavailable or bad URL")
                    return
            else:
                return
        installed = [model["name"] for model in self.settings.models]
        dialog = DownloadPopup(self.settings, installed)
        if dialog.exec():
            self.update_list(len(self.settings.models) - 1)

    def edit(self) -> None:
        selected_row = None
        for index in self.table.selectedIndexes():
            for i, model in enumerate(self.settings.models):
                if model["name"] == self.list.data(self.list.index(index.row(), 1)):
                    selected_row = i
                    dialog = CustomUI(i, self.settings)
                    dialog.ui.filePicker.setText(model["location"])
                    dialog.ui.languageLineEdit.setText(model["language"])
                    dialog.ui.nameLineEdit.setText(model["name"])
                    dialog.ui.sizeLineEdit.setText(model["size"])
                    dialog.ui.classLineEdit.setText(model["type"])
                    dialog.ui.versionLineEdit.setText(model["version"])
                    dialog.exec()
                    break
            break
        if selected_row is not None:
            self.update_list(selected_row)



    def setModel(self, model: str) -> None:
        self.settings.setValue("Model/name", model)
        self.settings.save()
