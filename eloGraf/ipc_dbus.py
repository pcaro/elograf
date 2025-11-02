#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
D-Bus implementation for IPC with global shortcuts support

Linux/Unix implementation using D-Bus for communication and
KGlobalAccel for global keyboard shortcuts.

@author: papoteur
@license: GPL v3.0
"""

import logging
import subprocess
from typing import Dict, Callable, List, Optional
from PyQt6.QtCore import pyqtSlot, Qt
from PyQt6.QtDBus import QDBusConnection, QDBusInterface, QDBusReply
from eloGraf.ipc_manager import IPCManager


class IPCDBus(IPCManager):
    """
    IPC implementation using D-Bus.

    Provides D-Bus service registration for single instance detection
    and command communication. Also supports global keyboard shortcuts
    via KGlobalAccel on KDE.
    """

    # Map modifier names to Qt key codes
    MODIFIER_MAP = {
        'ctrl': Qt.KeyboardModifier.ControlModifier.value,
        'control': Qt.KeyboardModifier.ControlModifier.value,
        'alt': Qt.KeyboardModifier.AltModifier.value,
        'shift': Qt.KeyboardModifier.ShiftModifier.value,
        'meta': Qt.KeyboardModifier.MetaModifier.value,
        'super': Qt.KeyboardModifier.MetaModifier.value,
    }

    def __init__(self, app_id: str = "elograf"):
        super().__init__(app_id)
        self.dbus_service = f"org.{app_id}.daemon"
        self.dbus_path = f"/{app_id}"
        self.registered = False
        self.shortcuts = {}  # action -> callback mapping
        self._kglobalaccel_available = None  # Cache availability check
        self._signal_connected = False  # Track if we've connected to KGlobalAccel signal
        self._context_activated = False  # Track if we've activated the shortcut context

    def is_running(self) -> bool:
        """
        Check if another instance is running via D-Bus.

        Returns:
            True if service is already registered on D-Bus
        """
        bus = QDBusConnection.sessionBus()
        iface = QDBusInterface(
            self.dbus_service,
            self.dbus_path,
            "",
            bus
        )
        return iface.isValid()

    def start_server(self) -> bool:
        """
        Register D-Bus service to receive commands.

        Returns:
            True if service was registered successfully
        """
        if self.registered:
            return True

        bus = QDBusConnection.sessionBus()

        # Register service
        if not bus.registerService(self.dbus_service):
            error_msg = bus.lastError().message()
            logging.error(f"Failed to register D-Bus service: {error_msg}")
            return False

        # Register object with all slots exported
        if not bus.registerObject(
            self.dbus_path,
            self,
            QDBusConnection.RegisterOption.ExportAllSlots
        ):
            error_msg = bus.lastError().message()
            logging.error(f"Failed to register D-Bus object: {error_msg}")
            return False

        self.registered = True
        logging.debug(f"D-Bus service '{self.dbus_service}' registered successfully")
        return True

    def send_command(self, command: str) -> bool:
        """
        Send command to running instance via D-Bus.

        Args:
            command: Command string (e.g., "begin", "end")

        Returns:
            True if command was sent successfully
        """
        bus = QDBusConnection.sessionBus()
        iface = QDBusInterface(
            self.dbus_service,
            self.dbus_path,
            "",
            bus
        )

        if not iface.isValid():
            logging.error(f"Cannot connect to D-Bus service: {bus.lastError().message()}")
            return False

        # Call the remote method
        reply = iface.call(command)

        if reply.errorName():
            logging.error(f"D-Bus call failed: {reply.errorMessage()}")
            return False

        logging.debug(f"Command '{command}' sent via D-Bus")
        return True

    @pyqtSlot()
    def begin(self):
        """D-Bus slot for 'begin' command"""
        logging.debug("D-Bus: begin command received")
        self.command_received.emit("begin")

    @pyqtSlot()
    def end(self):
        """D-Bus slot for 'end' command"""
        logging.debug("D-Bus: end command received")
        self.command_received.emit("end")

    @pyqtSlot()
    def exit(self):
        """D-Bus slot for 'exit' command"""
        logging.debug("D-Bus: exit command received")
        self.command_received.emit("exit")

    @pyqtSlot()
    def suspend(self):
        """D-Bus slot for 'suspend' command"""
        logging.debug("D-Bus: suspend command received")
        self.command_received.emit("suspend")

    @pyqtSlot()
    def resume(self):
        """D-Bus slot for 'resume' command"""
        logging.debug("D-Bus: resume command received")
        self.command_received.emit("resume")

    @pyqtSlot()
    def toggle(self):
        """D-Bus slot for 'toggle' command"""
        logging.debug("D-Bus: toggle command received")
        self.command_received.emit("toggle")

    def supports_global_shortcuts(self) -> bool:
        """
        Check if KGlobalAccel is available and working.

        Returns:
            True if KGlobalAccel D-Bus service is available
        """
        if self._kglobalaccel_available is not None:
            return self._kglobalaccel_available

        bus = QDBusConnection.sessionBus()
        iface = QDBusInterface(
            "org.kde.kglobalaccel",
            "/kglobalaccel",
            "org.kde.KGlobalAccel",
            bus
        )

        self._kglobalaccel_available = iface.isValid()
        if self._kglobalaccel_available:
            logging.info("KGlobalAccel is available for global shortcuts")
        else:
            logging.debug("KGlobalAccel not available - global shortcuts disabled")

        return self._kglobalaccel_available

    def _parse_shortcut(self, shortcut: str) -> Optional[List[int]]:
        """
        Parse Qt-style shortcut string to list of key codes.

        Args:
            shortcut: Shortcut string like "Meta+Alt+D" or "Ctrl+Shift+F1"

        Returns:
            List of Qt key codes (modifiers + key), or None if parsing fails

        Examples:
            "Meta+Alt+D" -> [Meta, Alt, Key_D]
            "Ctrl+F1" -> [Control, Key_F1]
        """
        if not shortcut:
            return None

        try:
            parts = [p.strip() for p in shortcut.split('+')]
            if not parts:
                return None

            key_codes = []
            main_key = None

            for part in parts:
                part_lower = part.lower()

                # Check if it's a modifier
                if part_lower in self.MODIFIER_MAP:
                    key_codes.append(self.MODIFIER_MAP[part_lower])
                    continue

                # It's the main key - should be last
                main_key = part

            # Convert main key to Qt key code
            if main_key:
                # Try to get Qt key enum (Qt uses uppercase for keys)
                qt_key_name = f"Key_{main_key.upper()}"
                if hasattr(Qt.Key, qt_key_name):
                    key_value = getattr(Qt.Key, qt_key_name).value
                    key_codes.append(key_value)
                else:
                    logging.warning(f"Unknown key in shortcut: {main_key}")
                    return None

            return key_codes if key_codes else None

        except Exception as e:
            logging.error(f"Failed to parse shortcut '{shortcut}': {e}")
            return None

    def register_global_shortcut(
        self,
        action: str,
        shortcut: str,
        callback: Callable
    ) -> bool:
        """
        Register global keyboard shortcut using KGlobalAccel.

        Args:
            action: Action identifier (e.g., "begin", "end")
            shortcut: Keyboard shortcut (e.g., "Meta+Alt+D")
            callback: Function to call when shortcut is pressed

        Returns:
            True if shortcut was registered successfully
        """
        if not self.supports_global_shortcuts():
            return False

        # Parse shortcut string to key codes
        key_codes = self._parse_shortcut(shortcut)
        if not key_codes:
            logging.error(f"[KGlobalAccel] Failed to parse shortcut: {shortcut}")
            return False

        # Combine all key codes into a single QKeySequence value using bitwise OR
        # Qt represents key sequences as: (modifiers | key)
        combined_key = 0
        for code in key_codes:
            combined_key |= code

        logging.debug(f"[KGlobalAccel] Parsed shortcut '{shortcut}' to key codes: {key_codes}")
        logging.debug(f"[KGlobalAccel] Combined QKeySequence value: {combined_key}")

        bus = QDBusConnection.sessionBus()
        iface = QDBusInterface(
            "org.kde.kglobalaccel",
            "/kglobalaccel",
            "org.kde.KGlobalAccel",
            bus
        )

        if not iface.isValid():
            logging.warning("KGlobalAccel interface not valid")
            return False

        component = self.app_id
        unique_name = f"{action}_dictation"
        friendly_name = f"{action.capitalize()} dictation"

        # Build actionId as QStringList (4 elements)
        # [component_id, unique_name, component_friendly, action_friendly]
        action_id = [
            component,           # Component unique ID
            unique_name,         # Action unique name
            "EloGraf",          # Component friendly name
            friendly_name        # Action friendly name
        ]

        # Flags: SetPresent (2) tells KGlobalAccel the shortcut is active
        # This is critical - without SetPresent, the component won't be marked as active
        flags = 2  # SetPresent flag

        # PyQt6 cannot properly marshal array types to D-Bus without wrapping in QVariant
        # Use dbus-send as workaround for KGlobalAccel.setShortcut
        action_id_str = ",".join(action_id)

        logging.debug(f"[KGlobalAccel] Registering shortcut: actionId={action_id}, combined_key={combined_key}, flags={flags}")

        # Use setShortcut (not setForeignShortcut) to mark component as active
        logging.debug(f"[KGlobalAccel] Using setShortcut with combined key")
        try:
            result = subprocess.run([
                "dbus-send",
                "--session",
                "--print-reply",
                "--dest=org.kde.kglobalaccel",
                "/kglobalaccel",
                "org.kde.KGlobalAccel.setShortcut",
                f"array:string:{action_id_str}",
                f"array:int32:{combined_key}",
                f"uint32:{flags}"
            ], capture_output=True, text=True, timeout=5)

            if result.returncode != 0:
                logging.error(f"[KGlobalAccel] setShortcut failed: {result.stderr}")
                return False

            logging.debug(f"[KGlobalAccel] setShortcut successful")
            logging.debug(f"[KGlobalAccel] Response: {result.stdout.strip()}")
        except subprocess.TimeoutExpired:
            logging.error(f"[KGlobalAccel] dbus-send timed out")
            return False
        except FileNotFoundError:
            logging.error(f"[KGlobalAccel] dbus-send not found - install dbus package")
            return False
        except Exception as e:
            logging.error(f"[KGlobalAccel] dbus-send error: {e}")
            return False

        # Call doRegister to activate the shortcut monitoring
        logging.debug(f"[KGlobalAccel] Calling doRegister to activate shortcut")
        try:
            result = subprocess.run([
                "dbus-send",
                "--session",
                "--print-reply",
                "--dest=org.kde.kglobalaccel",
                "/kglobalaccel",
                "org.kde.KGlobalAccel.doRegister",
                f"array:string:{action_id_str}"
            ], capture_output=True, text=True, timeout=5)

            if result.returncode != 0:
                logging.warning(f"[KGlobalAccel] doRegister failed: {result.stderr}")
                # Don't fail completely - the shortcut might still work
            else:
                logging.debug(f"[KGlobalAccel] doRegister returned: {result.stdout.strip()}")
                logging.debug(f"[KGlobalAccel] doRegister successful")
        except Exception as e:
            logging.warning(f"[KGlobalAccel] doRegister error: {e}")
            # Don't fail completely - continue with registration

        # Activate the global shortcut context (only do this once)
        if not self._context_activated:
            logging.debug(f"[KGlobalAccel] Activating global shortcut context for component '{component}'")
            try:
                result = subprocess.run([
                    "dbus-send",
                    "--session",
                    "--print-reply",
                    "--dest=org.kde.kglobalaccel",
                    "/kglobalaccel",
                    "org.kde.KGlobalAccel.activateGlobalShortcutContext",
                    f"string:{component}",
                    "string:default"  # Default context
                ], capture_output=True, text=True, timeout=5)

                if result.returncode == 0:
                    logging.debug(f"[KGlobalAccel] Context activated successfully")
                    self._context_activated = True
                else:
                    logging.warning(f"[KGlobalAccel] Context activation failed: {result.stderr}")
            except Exception as e:
                logging.warning(f"[KGlobalAccel] Context activation error: {e}")

        # Store callback
        self.shortcuts[unique_name] = callback

        # Get the actual component object path from KGlobalAccel
        logging.debug(f"[KGlobalAccel] Getting component path for '{component}'")
        component_reply = iface.call("getComponent", component)
        if component_reply.errorName():
            logging.error(f"[KGlobalAccel] getComponent failed: {component_reply.errorMessage()}")
            component_path = f"/component/{component}"
            logging.debug(f"[KGlobalAccel] Falling back to assumed path: {component_path}")
        else:
            component_path = component_reply.arguments()[0]
            logging.debug(f"[KGlobalAccel] Got component path from KGlobalAccel: {component_path}")

        # Connect to signal when shortcut is activated (only once for all shortcuts)
        if not self._signal_connected:
            logging.debug(f"[KGlobalAccel] Connecting to signal on path: {component_path}")
            logging.debug(f"[KGlobalAccel] Signal details: service='org.kde.kglobalaccel', interface='org.kde.kglobalaccel.Component', signal='globalShortcutPressed'")

            # Try connecting with explicit match rule
            connection_success = bus.connect(
                "org.kde.kglobalaccel",
                component_path,
                "org.kde.kglobalaccel.Component",
                "globalShortcutPressed",
                self._on_global_shortcut
            )

            if connection_success:
                self._signal_connected = True
                logging.debug(f"[KGlobalAccel] Successfully connected to globalShortcutPressed signal")
                logging.debug(f"[KGlobalAccel] Waiting for signals... (callback registered for: {list(self.shortcuts.keys())})")
            else:
                error = bus.lastError().message()
                logging.error(f"[KGlobalAccel] Failed to connect to globalShortcutPressed signal: {error}")
        else:
            logging.debug(f"[KGlobalAccel] Already connected to signal, skipping")
            logging.debug(f"[KGlobalAccel] Registered callbacks: {list(self.shortcuts.keys())}")

        logging.info(f"[KGlobalAccel] Global shortcut '{shortcut}' registered for action '{action}'")
        return True

    @pyqtSlot(str, str, 'qlonglong')
    def _on_global_shortcut(self, component: str, unique_name: str, timestamp: int):
        """
        Handle global shortcut activation from KGlobalAccel.

        Args:
            component: Component name
            unique_name: Unique action identifier
            timestamp: Event timestamp (milliseconds)
        """
        logging.debug(f"[KGlobalAccel] *** SHORTCUT SIGNAL RECEIVED *** component='{component}', unique_name='{unique_name}', timestamp={timestamp}")

        if unique_name in self.shortcuts:
            callback = self.shortcuts[unique_name]
            logging.debug(f"[KGlobalAccel] Executing callback for '{unique_name}'")
            try:
                callback()
                logging.debug(f"[KGlobalAccel] Callback executed successfully")
            except Exception as e:
                logging.error(f"[KGlobalAccel] Callback error: {e}")
        else:
            logging.warning(f"[KGlobalAccel] No callback registered for shortcut: {unique_name}")
            logging.debug(f"[KGlobalAccel] Available shortcuts: {list(self.shortcuts.keys())}")

    @pyqtSlot('QDBusMessage')
    def _on_global_shortcut_raw(self, msg):
        """Raw D-Bus message handler for debugging."""
        logging.debug(f"[KGlobalAccel] RAW SIGNAL RECEIVED: {msg.arguments()}")

    def cleanup(self):
        """Cleanup D-Bus resources"""
        if self.registered:
            bus = QDBusConnection.sessionBus()
            bus.unregisterObject(self.dbus_path)
            bus.unregisterService(self.dbus_service)
            logging.debug("D-Bus service unregistered")
