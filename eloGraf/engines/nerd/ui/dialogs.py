# ABOUTME: Dialog management for nerd-dictation engine model selection.
# ABOUTME: Provides launch_model_selection_dialog callback for settings UI.

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover
    from PyQt6.QtWidgets import QWidget


def launch_model_selection_dialog(parent: QWidget | None = None) -> None:
    """Launch the model selection/management dialog for nerd-dictation.

    This function is called when the "Manage Models..." button is clicked
    in the nerd-dictation settings tab.

    Args:
        parent: Parent widget for the dialog
    """
    from eloGraf.dialogs import ConfigPopup
    from eloGraf.settings import Settings

    settings = Settings()
    try:
        settings.load()
    except Exception:
        pass  # ConfigPopup will handle missing settings

    model, _ = settings.current_model()
    dialog = ConfigPopup(model, parent=parent)
    dialog.exec()
