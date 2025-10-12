# ABOUTME: Compatibility wrapper for legacy custom dialog imports.
# ABOUTME: Re-exports nerd-dictation custom UI from its new package location.

from __future__ import annotations

from eloGraf.engines.nerd.ui.custom import Ui_Dialog  # noqa: F401

__all__ = ["Ui_Dialog"]
