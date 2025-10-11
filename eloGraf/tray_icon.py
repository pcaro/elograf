from __future__ import annotations

import logging
import os
from subprocess import Popen
from typing import Any, Dict, Tuple

from PyQt6.QtCore import QCoreApplication, QTimer
from PyQt6.QtGui import QColor, QIcon, QPainter, QPixmap
from PyQt6.QtWidgets import QApplication, QMenu, QSystemTrayIcon

from eloGraf.dialogs import AdvancedUI
from eloGraf.dictation import CommandBuildError, build_dictation_command
from eloGraf.ipc_manager import IPCManager
from eloGraf.stt_engine import STTController, STTProcessRunner
from eloGraf.stt_factory import create_stt_engine
from eloGraf.nerd_controller import NerdDictationState
from eloGraf.whisper_docker_controller import WhisperDockerState
from eloGraf.google_cloud_speech_controller import GoogleCloudSpeechState
from eloGraf.openai_realtime_controller import OpenAIRealtimeState
from eloGraf.settings import DEFAULT_RATE, Settings
from eloGraf.pidfile import remove_pid_file
from eloGraf.state_machine import DictationStateMachine, IconState

class SystemTrayIcon(QSystemTrayIcon):
    """Tray icon controller with model-aware tooltip."""

    def _update_tooltip(self) -> None:
        name, _ = self.currentModel()
        tooltip = "EloGraf"
        if name:
            tooltip += f"\nModel: {name}"
        self.setToolTip(tooltip)

    def __init__(self, icon: QIcon, start: bool, ipc: IPCManager, parent=None) -> None:
        QSystemTrayIcon.__init__(self, icon, parent)
        self.settings = Settings()
        try:
            self.settings.load()
        except Exception as exc:
            logging.warning("Failed to load settings: %s", exc)
        self.ipc = ipc
        self.direct_click_enabled = self.settings.directClick

        menu = QMenu(parent)

        self.toggleAction = menu.addAction(self.tr("Toggle dictation"))
        self.suspendAction = menu.addAction(self.tr("Suspend dictation"))
        self.resumeAction = menu.addAction(self.tr("Resume dictation"))
        self.toggleAction.triggered.connect(self.controller_toggle)
        self.suspendAction.triggered.connect(self.suspend)
        self.resumeAction.triggered.connect(self.resume)
        self.toggleAction.setEnabled(True)
        self.suspendAction.setEnabled(False)
        self.resumeAction.setEnabled(False)
        configAction = menu.addAction(self.tr("Configuration"))
        exitAction = menu.addAction(self.tr("Exit"))
        self.setContextMenu(menu)

        if self.direct_click_enabled:
            self.activated.connect(self.commute)

        self.state_machine = DictationStateMachine()
        self.state_machine.on_state = lambda state: self._apply_state(state.icon_state, state.dictating, state.suspended)
        exitAction.triggered.connect(self.exit)
        configAction.triggered.connect(self.config)
        self.nomicro = QIcon.fromTheme("microphone-sensitivity-muted")
        if self.nomicro.isNull():
            self.nomicro = QIcon(":/icons/elograf/24/nomicro.png")
        self.micro = QIcon.fromTheme("audio-input-microphone")
        if self.micro.isNull():
            self.micro = QIcon(":/icons/elograf/24/micro.png")
        self.setIcon(self.nomicro)

        self.dictation_timer = QTimer(self)
        self.dictation_timer.setInterval(200)
        self._pending_engine_refresh = False
        self._create_stt_engine()

        self.dictating = False
        self.suspended = False
        self._postcommand_ran = True
        self.state_machine.set_idle()
        self._update_action_states()
        self._update_tooltip()

        # Connect IPC command handler
        self.ipc.command_received.connect(self._handle_ipc_command)

        # Start IPC server
        if not self.ipc.start_server():
            logging.error("Failed to start IPC server")

        # Register global shortcuts if supported
        self._register_global_shortcuts()

        if start:
            self.dictate()
            self.dictating = True

    def _get_loading_icon(self):
        """Get microphone icon with red loading indicator"""
        from PyQt6.QtGui import QPixmap, QPainter, QColor
        from PyQt6.QtCore import Qt

        # Get base icon as pixmap
        pixmap = self.micro.pixmap(24, 24)
        painter = QPainter(pixmap)

        # Draw red line at bottom
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(255, 0, 0))  # Red
        painter.drawRect(0, 22, 24, 2)  # 2px red line at bottom

        painter.end()
        return QIcon(pixmap)

    def _get_ready_icon(self):
        """Get microphone icon with green ready indicator"""
        from PyQt6.QtGui import QPixmap, QPainter, QColor
        from PyQt6.QtCore import Qt

        # Get base icon as pixmap
        pixmap = self.micro.pixmap(24, 24)
        painter = QPainter(pixmap)

        # Draw green line at bottom
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(0, 255, 0))  # Green
        painter.drawRect(0, 22, 24, 2)  # 2px green line at bottom

        painter.end()
        return QIcon(pixmap)

    def _get_suspended_icon(self):
        """Get microphone icon with orange suspended indicator"""
        from PyQt6.QtGui import QPixmap, QPainter, QColor
        from PyQt6.QtCore import Qt

        pixmap = self.micro.pixmap(24, 24)
        painter = QPainter(pixmap)

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(255, 165, 0))
        painter.drawRect(0, 22, 24, 2)

        painter.end()
        return QIcon(pixmap)

    def _build_engine_kwargs(self, engine_type: str) -> Dict[str, Any]:
        if engine_type == "whisper-docker":
            return {
                "model": self.settings.whisperModel,
                "language": self.settings.whisperLanguage if self.settings.whisperLanguage else None,
                "api_port": self.settings.whisperPort,
                "chunk_duration": self.settings.whisperChunkDuration,
                "sample_rate": self.settings.whisperSampleRate,
                "channels": self.settings.whisperChannels,
                "vad_enabled": self.settings.whisperVadEnabled,
                "vad_threshold": self.settings.whisperVadThreshold,
                "auto_reconnect": self.settings.whisperAutoReconnect,
            }
        if engine_type == "google-cloud-speech":
            return {
                "credentials_path": self.settings.googleCloudCredentialsPath if self.settings.googleCloudCredentialsPath else None,
                "project_id": self.settings.googleCloudProjectId if self.settings.googleCloudProjectId else None,
                "language_code": self.settings.googleCloudLanguageCode,
                "model": self.settings.googleCloudModel,
                "sample_rate": self.settings.googleCloudSampleRate,
                "channels": self.settings.googleCloudChannels,
                "vad_enabled": self.settings.googleCloudVadEnabled,
                "vad_threshold": self.settings.googleCloudVadThreshold,
            }
        if engine_type == "openai-realtime":
            return {
                "api_key": self.settings.openaiApiKey,
                "model": self.settings.openaiModel,
                "api_version": self.settings.openaiApiVersion,
                "sample_rate": self.settings.openaiSampleRate,
                "channels": self.settings.openaiChannels,
                "vad_enabled": self.settings.openaiVadEnabled,
                "vad_threshold": self.settings.openaiVadThreshold,
                "vad_prefix_padding_ms": self.settings.openaiVadPrefixPaddingMs,
                "vad_silence_duration_ms": self.settings.openaiVadSilenceDurationMs,
                "language": self.settings.openaiLanguage,
            }
        return {}

    def _create_stt_engine(self) -> None:
        engine_type = self.settings.sttEngine
        engine_kwargs = self._build_engine_kwargs(engine_type)
        controller, runner = create_stt_engine(engine_type, **engine_kwargs)
        controller.add_state_listener(self._handle_dictation_state)
        controller.add_output_listener(self._handle_dictation_output)
        controller.add_exit_listener(self._handle_dictation_exit)
        self.dictation_controller = controller
        self.dictation_runner = runner
        self.dictation_timer.timeout.connect(self.dictation_runner.poll)

    def _refresh_stt_engine(self) -> None:
        runner = getattr(self, "dictation_runner", None)
        if runner and runner.is_running():
            logging.info("STT engine running; stopping before applying new settings")
            self.stop_dictate()
            self._pending_engine_refresh = True
            return

        logging.info("Refreshing STT engine with updated settings")
        was_active = self.dictation_timer.isActive()
        self._pending_engine_refresh = False
        self.dictation_timer.stop()
        disconnected = False
        if runner:
            try:
                self.dictation_timer.timeout.disconnect(runner.poll)
                disconnected = True
            except (TypeError, RuntimeError):
                pass
        try:
            self._create_stt_engine()
        except Exception:
            if disconnected and runner:
                try:
                    self.dictation_timer.timeout.connect(runner.poll)
                    if was_active:
                        self.dictation_timer.start()
                except (TypeError, RuntimeError):
                    pass
            raise
        self._update_action_states()

    def _apply_state(self, icon_state: IconState, dictating: bool, suspended: bool) -> None:
        self.dictating = dictating
        self.suspended = suspended
        if icon_state == IconState.LOADING:
            self.setIcon(self._get_loading_icon())
        elif icon_state == IconState.READY:
            self.setIcon(self._get_ready_icon())
        elif icon_state == IconState.SUSPENDED:
            self.setIcon(self._get_suspended_icon())
        else:
            self.setIcon(self.nomicro)
        self._update_tooltip()
        # update toggle label
        if hasattr(self, "toggleAction"):
            if suspended:
                self.toggleAction.setText(self.tr("Resume dictation"))
            elif dictating:
                self.toggleAction.setText(self.tr("Suspend dictation"))
            else:
                self.toggleAction.setText(self.tr("Start dictation"))
        self._update_action_states()

    def _handle_dictation_state(self, state) -> None:
        # Handle both NerdDictationState and WhisperDockerState
        state_name = state.name if hasattr(state, 'name') else str(state)

        if state_name in ('STARTING', 'LOADING'):
            self.state_machine.set_loading()
        elif state_name in ('READY', 'DICTATING', 'RECORDING', 'TRANSCRIBING'):
            self.state_machine.set_ready()
        elif state_name == 'SUSPENDED':
            self.state_machine.set_suspended()
        elif state_name in ('STOPPING', 'IDLE'):
            self.state_machine.set_idle()
        elif state_name == 'FAILED':
            logging.error("STT engine process failed")
            self.state_machine.set_idle()

    def _handle_dictation_output(self, line: str) -> None:
        logging.info(f"STT engine: {line}")

    def _handle_dictation_exit(self, return_code: int) -> None:
        if return_code != 0:
            logging.warning(f"STT engine exited with code {return_code}")
        if self.dictation_timer.isActive():
            self.dictation_timer.stop()
        self.dictating = False
        self.suspended = False
        self._update_action_states()
        self._update_tooltip()
        self._run_postcommand_once()
        if getattr(self, "_pending_engine_refresh", False):
            self._refresh_stt_engine()

    def _run_postcommand_once(self) -> None:
        if self._postcommand_ran:
            return

        if hasattr(self.settings, "postcommand") and self.settings.postcommand:
            try:
                Popen(self.settings.postcommand.split())
            except Exception as exc:
                logging.error("Failed to run postcommand: %s", exc)

        self._postcommand_ran = True

    def _update_action_states(self) -> None:
        state = getattr(self, "state_machine", None)
        snapshot = state.state if state else None
        if hasattr(self, "suspendAction") and snapshot:
            self.suspendAction.setEnabled(self.dictation_runner.is_running() and not snapshot.suspended)
        if hasattr(self, "resumeAction") and snapshot:
            self.resumeAction.setEnabled(snapshot.suspended)

    def _register_global_shortcuts(self):
        """Register global keyboard shortcuts if IPC supports it"""
        if not self.ipc.supports_global_shortcuts():
            logging.debug("IPC does not support global shortcuts")
            return

        # Register begin shortcut
        if self.settings.beginShortcut:
            success = self.ipc.register_global_shortcut(
                "begin",
                self.settings.beginShortcut,
                self.begin
            )
            if success:
                logging.info(f"Global shortcut registered: {self.settings.beginShortcut} -> begin")
            else:
                logging.warning(f"Failed to register global shortcut for 'begin'")

        # Register end shortcut
        if self.settings.endShortcut:
            success = self.ipc.register_global_shortcut(
                "end",
                self.settings.endShortcut,
                self.end
            )
            if success:
                logging.info(f"Global shortcut registered: {self.settings.endShortcut} -> end")
            else:
                logging.warning(f"Failed to register global shortcut for 'end'")

        if self.settings.toggleShortcut:
            success = self.ipc.register_global_shortcut(
                "toggle",
                self.settings.toggleShortcut,
                self.controller_toggle
            )
            if success:
                logging.info(f"Global shortcut registered: {self.settings.toggleShortcut} -> toggle")
            else:
                logging.warning("Failed to register global shortcut for 'toggle'")

        if self.settings.suspendShortcut:
            success = self.ipc.register_global_shortcut(
                "suspend",
                self.settings.suspendShortcut,
                self.suspend
            )
            if success:
                logging.info(f"Global shortcut registered: {self.settings.suspendShortcut} -> suspend")
            else:
                logging.warning("Failed to register global shortcut for 'suspend'")

        if self.settings.resumeShortcut:
            success = self.ipc.register_global_shortcut(
                "resume",
                self.settings.resumeShortcut,
                self.resume
            )
            if success:
                logging.info(f"Global shortcut registered: {self.settings.resumeShortcut} -> resume")
            else:
                logging.warning("Failed to register global shortcut for 'resume'")

    def _handle_ipc_command(self, command: str):
        """
        Handle commands received from other instances via IPC.

        Args:
            command: Command string (e.g., "begin", "end", "exit")
        """
        logging.info(f"Received IPC command: {command}")
        if command == "begin":
            self.begin()
        elif command == "end":
            self.end()
        elif command == "exit":
            self.exit()
        elif command == "suspend":
            self.suspend()
        elif command == "resume":
            self.resume()
        elif command == "toggle":
            self.controller_toggle()
        else:
            logging.warning(f"Unknown IPC command: {command}")

    def currentModel(self) -> Tuple[str, str]:
        return self.settings.current_model()

    def exit(self) -> None:
        """Clean exit: stop dictation, cleanup IPC, and exit"""
        logging.info("Exiting Elograf...")
        if self.dictating:
            self.stop_dictate()
        # Cleanup resources
        remove_pid_file()
        self.ipc.cleanup()
        QCoreApplication.exit()

    def dictate(self) -> None:
        model, location = self.currentModel()
        if model == "" or not location:
            self.show_config_dialog()
            model, location = self.currentModel()
            if not model or not location:
                logging.info("No model selected, exiting dictate.")
                self.state_machine.set_idle()
                return
        if not location:
            logging.warning("Selected model has no location configured")
            self.state_machine.set_idle()
            return
        logging.debug(f"Start dictation with model {model} located in {location}")
        if self.settings.precommand:
            parts = self.settings.precommand.split()
            if parts:
                Popen(parts)
        self._postcommand_ran = False
        try:
            cmd, env = build_dictation_command(self.settings, location)
        except CommandBuildError as exc:
            logging.warning("Failed to build STT command: %s", exc)
            self.state_machine.set_idle()
            self._postcommand_ran = True
            return
        logging.debug(
            "Starting STT engine with the command {}".format(" ".join(cmd))
        )
        if self.dictation_runner.start(cmd, env=env):
            self.state_machine.set_loading()
        else:
            self.state_machine.set_idle()
            self._postcommand_ran = True
            return

        if not self.dictation_timer.isActive():
            self.dictation_timer.start()
        self._update_tooltip()
        logging.info("Loading model, please wait...")

    def suspend(self) -> None:
        logging.debug("Suspend dictation")
        if self.suspended:
            logging.info("Dictation already suspended")
            return
        if self.dictation_runner.is_running():
            self.dictation_runner.suspend()
            self.state_machine.set_suspended()
        else:
            logging.info("No running dictation to suspend")

    def resume(self) -> None:
        logging.debug("Resume dictation")
        if not self.dictation_runner.is_running():
            logging.info("No dictation process to resume; starting a new one")
            self.state_machine.set_ready()
            self.dictate()
            return
        self.dictation_runner.resume()
        self.state_machine.set_ready()

    def stop_dictate(self) -> None:
        if self.dictation_runner.is_running():
            logging.debug("Stopping STT engine")
            self.dictation_runner.stop()
        self.state_machine.set_idle()

    def commute(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        """Handle direct click on tray icon when direct_click_enabled is True."""
        if reason != QSystemTrayIcon.ActivationReason.Trigger:
            return
        self.controller_toggle()

    def controller_toggle(self) -> None:
        action = self.state_machine.toggle()
        getattr(self, action)()

    def toggle(self) -> None:
        self.controller_toggle()

    def begin(self) -> None:
        """Start dictation"""
        logging.debug("Begin dictation")
        if self.suspended:
            self.resume()
            return
        if not self.state_machine.state.dictating:
            self.dictate()
        else:
            logging.info("Dictation already started")

    def end(self) -> None:
        """Stop dictation"""
        logging.debug("End dictation")
        if self.dictating:
            self.stop_dictate()
        self.state_machine.set_idle()

    def show_config_dialog(self) -> None:
        adv_window = AdvancedUI()

        # General settings
        adv_window.ui.precommand.setText(self.settings.precommand)
        adv_window.ui.postcommand.setText(self.settings.postcommand)
        adv_window.ui.env.setText(self.settings.env)
        adv_window.ui.tool_cb.setCurrentText(self.settings.tool)
        adv_window.ui.keyboard_le.setText(self.settings.keyboard)
        index = adv_window.ui.deviceName.findData(self.settings.deviceName)
        if index >= 0:
            adv_window.ui.deviceName.setCurrentIndex(index)
        adv_window.ui.direct_click_cb.setChecked(self.settings.directClick)

        # Nerd-Dictation settings
        adv_window.ui.sampleRate.setText(str(self.settings.sampleRate))
        adv_window.ui.timeout.setValue(self.settings.timeout)
        adv_window.ui.timeoutDisplay.setText(str(self.settings.timeout))
        adv_window.ui.idleTime.setValue(self.settings.idleTime)
        adv_window.ui.idleDisplay.setText(str(self.settings.idleTime))
        adv_window.ui.punctuate.setValue(self.settings.punctuate)
        adv_window.ui.punctuateDisplay.setText(str(self.settings.punctuate))
        adv_window.ui.fullSentence.setChecked(self.settings.fullSentence)
        adv_window.ui.digits.setChecked(self.settings.digits)
        adv_window.ui.useSeparator.setChecked(self.settings.useSeparator)
        adv_window.ui.freecommand.setText(self.settings.freeCommand)

        # Whisper Docker settings
        adv_window.ui.whisper_model_cb.setCurrentText(self.settings.whisperModel)
        adv_window.ui.whisper_language_le.setText(self.settings.whisperLanguage)
        adv_window.ui.whisper_port_le.setText(str(self.settings.whisperPort))
        adv_window.ui.whisper_chunk_le.setText(str(self.settings.whisperChunkDuration))
        adv_window.ui.whisper_sample_rate_le.setText(str(self.settings.whisperSampleRate))
        adv_window.ui.whisper_channels_le.setText(str(self.settings.whisperChannels))
        adv_window.ui.whisper_vad_cb.setChecked(self.settings.whisperVadEnabled)
        adv_window.ui.whisper_vad_threshold_le.setText(str(self.settings.whisperVadThreshold))
        adv_window.ui.whisper_auto_reconnect_cb.setChecked(self.settings.whisperAutoReconnect)

        # Google Cloud Speech settings
        adv_window.ui.gcs_credentials_le.setText(self.settings.googleCloudCredentialsPath)
        adv_window.ui.gcs_project_id_le.setText(self.settings.googleCloudProjectId)
        adv_window.ui.gcs_language_code_le.setText(self.settings.googleCloudLanguageCode)
        adv_window.ui.gcs_model_le.setText(self.settings.googleCloudModel)
        adv_window.ui.gcs_sample_rate_le.setText(str(self.settings.googleCloudSampleRate))
        adv_window.ui.gcs_channels_le.setText(str(self.settings.googleCloudChannels))
        adv_window.ui.gcs_vad_cb.setChecked(self.settings.googleCloudVadEnabled)
        adv_window.ui.gcs_vad_threshold_le.setText(str(self.settings.googleCloudVadThreshold))

        # OpenAI Realtime settings
        adv_window.ui.openai_api_key_le.setText(self.settings.openaiApiKey)
        adv_window.ui.openai_model_le.setText(self.settings.openaiModel)
        adv_window.ui.openai_api_version_le.setText(self.settings.openaiApiVersion)
        adv_window.ui.openai_sample_rate_le.setText(str(self.settings.openaiSampleRate))
        adv_window.ui.openai_channels_le.setText(str(self.settings.openaiChannels))
        adv_window.ui.openai_vad_cb.setChecked(self.settings.openaiVadEnabled)
        adv_window.ui.openai_vad_threshold_le.setText(str(self.settings.openaiVadThreshold))
        adv_window.ui.openai_vad_prefix_le.setText(str(self.settings.openaiVadPrefixPaddingMs))
        adv_window.ui.openai_vad_silence_le.setText(str(self.settings.openaiVadSilenceDurationMs))
        adv_window.ui.openai_language_le.setText(self.settings.openaiLanguage)

        # Shortcuts
        adv_window.beginShortcut.setKeySequence(self.settings.beginShortcut)
        adv_window.endShortcut.setKeySequence(self.settings.endShortcut)
        adv_window.toggleShortcut.setKeySequence(self.settings.toggleShortcut)
        adv_window.suspendShortcut.setKeySequence(self.settings.suspendShortcut)
        adv_window.resumeShortcut.setKeySequence(self.settings.resumeShortcut)

        # Set STT engine and initial tab
        adv_window.ui.stt_engine_cb.setCurrentText(self.settings.sttEngine)
        adv_window._on_stt_engine_changed(self.settings.sttEngine)

        if adv_window.exec():
            # General settings
            self.settings.precommand = adv_window.ui.precommand.text()
            self.settings.postcommand = adv_window.ui.postcommand.text()
            self.settings.env = adv_window.ui.env.text()
            self.settings.tool = adv_window.ui.tool_cb.currentText()
            self.settings.keyboard = adv_window.ui.keyboard_le.text()
            device_data = adv_window.ui.deviceName.currentData()
            self.settings.deviceName = device_data if device_data else "default"
            self.settings.directClick = adv_window.ui.direct_click_cb.isChecked()

            # Nerd-Dictation settings
            try:
                self.settings.sampleRate = int(adv_window.ui.sampleRate.text())
            except (ValueError, TypeError):
                self.settings.sampleRate = DEFAULT_RATE
            self.settings.timeout = adv_window.ui.timeout.value()
            self.settings.idleTime = adv_window.ui.idleTime.value()
            self.settings.punctuate = adv_window.ui.punctuate.value()
            self.settings.fullSentence = adv_window.ui.fullSentence.isChecked()
            self.settings.digits = adv_window.ui.digits.isChecked()
            self.settings.useSeparator = adv_window.ui.useSeparator.isChecked()
            self.settings.freeCommand = adv_window.ui.freecommand.text()

            # Whisper Docker settings
            self.settings.whisperModel = adv_window.ui.whisper_model_cb.currentText()
            self.settings.whisperLanguage = adv_window.ui.whisper_language_le.text()
            try:
                self.settings.whisperPort = int(adv_window.ui.whisper_port_le.text())
            except (ValueError, TypeError):
                self.settings.whisperPort = 9000
            try:
                self.settings.whisperChunkDuration = float(adv_window.ui.whisper_chunk_le.text())
            except (ValueError, TypeError):
                self.settings.whisperChunkDuration = 5.0
            try:
                self.settings.whisperSampleRate = int(adv_window.ui.whisper_sample_rate_le.text())
            except (ValueError, TypeError):
                self.settings.whisperSampleRate = 16000
            try:
                self.settings.whisperChannels = int(adv_window.ui.whisper_channels_le.text())
            except (ValueError, TypeError):
                self.settings.whisperChannels = 1
            self.settings.whisperVadEnabled = adv_window.ui.whisper_vad_cb.isChecked()
            try:
                self.settings.whisperVadThreshold = float(adv_window.ui.whisper_vad_threshold_le.text())
            except (ValueError, TypeError):
                self.settings.whisperVadThreshold = 500.0
            self.settings.whisperAutoReconnect = adv_window.ui.whisper_auto_reconnect_cb.isChecked()

            # Google Cloud Speech settings
            self.settings.googleCloudCredentialsPath = adv_window.ui.gcs_credentials_le.text()
            self.settings.googleCloudProjectId = adv_window.ui.gcs_project_id_le.text()
            self.settings.googleCloudLanguageCode = adv_window.ui.gcs_language_code_le.text()
            self.settings.googleCloudModel = adv_window.ui.gcs_model_le.text()
            try:
                self.settings.googleCloudSampleRate = int(adv_window.ui.gcs_sample_rate_le.text())
            except (ValueError, TypeError):
                self.settings.googleCloudSampleRate = 16000
            try:
                self.settings.googleCloudChannels = int(adv_window.ui.gcs_channels_le.text())
            except (ValueError, TypeError):
                self.settings.googleCloudChannels = 1
            self.settings.googleCloudVadEnabled = adv_window.ui.gcs_vad_cb.isChecked()
            try:
                self.settings.googleCloudVadThreshold = float(adv_window.ui.gcs_vad_threshold_le.text())
            except (ValueError, TypeError):
                self.settings.googleCloudVadThreshold = 500.0

            # OpenAI Realtime settings
            self.settings.openaiApiKey = adv_window.ui.openai_api_key_le.text()
            self.settings.openaiModel = adv_window.ui.openai_model_le.text()
            self.settings.openaiApiVersion = adv_window.ui.openai_api_version_le.text()
            try:
                self.settings.openaiSampleRate = int(adv_window.ui.openai_sample_rate_le.text())
            except (ValueError, TypeError):
                self.settings.openaiSampleRate = 16000
            try:
                self.settings.openaiChannels = int(adv_window.ui.openai_channels_le.text())
            except (ValueError, TypeError):
                self.settings.openaiChannels = 1
            self.settings.openaiVadEnabled = adv_window.ui.openai_vad_cb.isChecked()
            try:
                self.settings.openaiVadThreshold = float(adv_window.ui.openai_vad_threshold_le.text())
            except (ValueError, TypeError):
                self.settings.openaiVadThreshold = 0.5
            try:
                self.settings.openaiVadPrefixPaddingMs = int(adv_window.ui.openai_vad_prefix_le.text())
            except (ValueError, TypeError):
                self.settings.openaiVadPrefixPaddingMs = 300
            try:
                self.settings.openaiVadSilenceDurationMs = int(adv_window.ui.openai_vad_silence_le.text())
            except (ValueError, TypeError):
                self.settings.openaiVadSilenceDurationMs = 200
            self.settings.openaiLanguage = adv_window.ui.openai_language_le.text()

            # Shortcuts
            self.settings.beginShortcut = adv_window.beginShortcut.keySequence().toString()
            self.settings.endShortcut = adv_window.endShortcut.keySequence().toString()
            self.settings.toggleShortcut = adv_window.toggleShortcut.keySequence().toString()
            self.settings.suspendShortcut = adv_window.suspendShortcut.keySequence().toString()
            self.settings.resumeShortcut = adv_window.resumeShortcut.keySequence().toString()

            # STT Engine
            self.settings.sttEngine = adv_window.ui.stt_engine_cb.currentText()

            self.settings.save()
            self.settings.load()

            # Update direct click connection if setting changed
            old_direct_click = self.direct_click_enabled
            self.direct_click_enabled = self.settings.directClick
            if old_direct_click != self.direct_click_enabled:
                try:
                    self.activated.disconnect(self.commute)
                except (TypeError, RuntimeError):
                    pass
                if self.direct_click_enabled:
                    self.activated.connect(self.commute)

            self._refresh_stt_engine()

    def config(self) -> None:
        self.show_config_dialog()

    def setModel(self, model: str) -> None:
        self.settings.setValue("Model/name", model)
        if self.dictating:
            logging.debug("Reload dictate process")
            self.stop_dictate()
            self.dictate()

