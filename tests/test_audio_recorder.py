#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
@author: Pablo Caro

ABOUTME: Tests for audio recorder module including device enumeration
ABOUTME: Validates audio device discovery with backend-specific behavior
"""
from __future__ import annotations

import unittest
from unittest.mock import patch, MagicMock
from subprocess import CompletedProcess

from eloGraf.audio_recorder import get_audio_devices


class TestGetAudioDevices(unittest.TestCase):
    def test_parec_backend_returns_default_plus_devices(self):
        """Test that parec backend returns default option plus PulseAudio sources."""
        mock_output = """Source #0
	State: RUNNING
	Name: alsa_output.pci-0000_00_1b.0.analog-stereo.monitor
	Description: Monitor of Built-in Audio Analog Stereo
	Driver: PipeWire
	Sample Specification: float32le 2ch 48000Hz

Source #1
	State: SUSPENDED
	Name: alsa_input.pci-0000_00_1b.0.analog-stereo
	Description: Built-in Audio Analog Stereo
	Driver: PipeWire
	Sample Specification: float32le 2ch 48000Hz
"""

        with patch('eloGraf.audio_recorder.run') as mock_run:
            mock_run.return_value = CompletedProcess(
                args=['pactl', 'list', 'sources'],
                returncode=0,
                stdout=mock_output,
                stderr=''
            )

            devices = get_audio_devices(backend="parec")

            # Should have default + 2 devices
            self.assertEqual(len(devices), 3)

            # First should be default
            self.assertEqual(devices[0][0], "default")
            self.assertEqual(devices[0][1], "Default")

            # Then the actual devices
            self.assertEqual(devices[1][0], "alsa_output.pci-0000_00_1b.0.analog-stereo.monitor")
            self.assertEqual(devices[1][1], "Monitor of Built-in Audio Analog Stereo")
            self.assertEqual(devices[2][0], "alsa_input.pci-0000_00_1b.0.analog-stereo")
            self.assertEqual(devices[2][1], "Built-in Audio Analog Stereo")

    def test_pyaudio_backend_returns_only_default(self):
        """Test that pyaudio backend returns only default option."""
        devices = get_audio_devices(backend="pyaudio")

        # PyAudio doesn't support device selection, should only return default
        self.assertEqual(len(devices), 1)
        self.assertEqual(devices[0][0], "default")
        self.assertEqual(devices[0][1], "Default")

    def test_auto_backend_with_pactl_available(self):
        """Test that auto backend uses parec when pactl is available."""
        mock_output = """Source #0
	Name: test_device
	Description: Test Device
"""
        with patch('eloGraf.audio_recorder.shutil.which') as mock_which, \
             patch('eloGraf.audio_recorder.run') as mock_run:
            mock_which.return_value = "/usr/bin/pactl"
            mock_run.return_value = CompletedProcess(
                args=['pactl', 'list', 'sources'],
                returncode=0,
                stdout=mock_output,
                stderr=''
            )

            devices = get_audio_devices(backend="auto")

            # Should have default + devices (parec behavior)
            self.assertGreater(len(devices), 1)
            self.assertEqual(devices[0][0], "default")

    def test_auto_backend_without_pactl(self):
        """Test that auto backend falls back to pyaudio when pactl unavailable."""
        with patch('eloGraf.audio_recorder.shutil.which') as mock_which:
            mock_which.return_value = None

            devices = get_audio_devices(backend="auto")

            # Should only return default (pyaudio behavior)
            self.assertEqual(len(devices), 1)
            self.assertEqual(devices[0][0], "default")

    def test_pactl_failure_returns_only_default(self):
        """Test that pactl failure returns only default option."""
        with patch('eloGraf.audio_recorder.run') as mock_run:
            mock_run.return_value = CompletedProcess(
                args=['pactl', 'list', 'sources'],
                returncode=1,
                stdout='',
                stderr='Connection failed'
            )

            devices = get_audio_devices(backend="parec")

            # Should return just default when pactl fails
            self.assertEqual(len(devices), 1)
            self.assertEqual(devices[0][0], "default")

    def test_pactl_timeout_returns_only_default(self):
        """Test that pactl timeout returns only default option."""
        with patch('eloGraf.audio_recorder.run', side_effect=TimeoutError):
            devices = get_audio_devices(backend="parec")

            self.assertEqual(len(devices), 1)
            self.assertEqual(devices[0][0], "default")


if __name__ == '__main__':
    unittest.main()
