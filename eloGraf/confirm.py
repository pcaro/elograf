# ABOUTME: Compatibility wrapper for legacy confirm dialog imports.
# ABOUTME: Re-exports nerd-dictation confirm UI from its new package location.

from __future__ import annotations

from eloGraf.engines.nerd.ui.confirm import Ui_Dialog  # noqa: F401

__all__ = ["Ui_Dialog"]
