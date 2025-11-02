# ABOUTME: Base settings dataclass for all STT engines.
# ABOUTME: Provides common fields shared across all engine configurations.

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class EngineSettings:
    """Base settings for all STT engines."""

    engine_type: str
    device_name: str = "default"
