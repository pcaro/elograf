# ABOUTME: Centralized factory for tray icons by state.
# ABOUTME: Generates and caches microphone icons with status indicators.

from __future__ import annotations

from typing import Dict

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QIcon, QPainter, QPixmap

from .state_machine import IconState


class IconFactory:
    """Produces and caches tray icons for the different dictation states."""

    def __init__(
        self,
        base_icon: QIcon,
        idle_icon: QIcon,
        *,
        size: int = 24,
        palette: Dict[IconState, QColor] | None = None,
    ) -> None:
        self._base_icon = base_icon
        self._idle_icon = idle_icon
        self._size = size
        self._cache: Dict[IconState, QIcon] = {}
        self._palette = palette or {
            IconState.LOADING: QColor(255, 0, 0),       # Red
            IconState.READY: QColor(0, 255, 0),         # Green
            IconState.SUSPENDED: QColor(255, 165, 0),   # Orange
        }

    def get_icon(self, state: IconState) -> QIcon:
        """Return an icon representing the requested state."""
        if state == IconState.IDLE:
            return self._idle_icon

        if state not in self._cache:
            color = self._palette.get(state)
            if color is None:
                return self._idle_icon

            pixmap = QPixmap(self._base_icon.pixmap(self._size, self._size))
            painter = QPainter(pixmap)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(color)
            painter.drawRect(0, self._size - 2, self._size, 2)
            painter.end()

            self._cache[state] = QIcon(pixmap)
        return self._cache[state]
