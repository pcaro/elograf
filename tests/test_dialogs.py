#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
@author: Pablo Caro

ABOUTME: Tests for dialog functions including PulseAudio device discovery
ABOUTME: Validates audio device enumeration and selection
"""
from __future__ import annotations

import unittest
from unittest.mock import patch, MagicMock
from subprocess import CompletedProcess

from eloGraf.audio_recorder import get_audio_devices


class TestGetAudioDevices(unittest.TestCase):
    def test_parse_pactl_output(self):
        """Test parsing of pactl list sources output."""
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
            self.assertEqual(devices[0][0], "default")
            self.assertEqual(devices[0][1], "Default")
            self.assertEqual(devices[1][0], "alsa_output.pci-0000_00_1b.0.analog-stereo.monitor")
            self.assertEqual(devices[1][1], "Monitor of Built-in Audio Analog Stereo")
            self.assertEqual(devices[2][0], "alsa_input.pci-0000_00_1b.0.analog-stereo")
            self.assertEqual(devices[2][1], "Built-in Audio Analog Stereo")

    def test_pactl_not_found(self):
        """Test handling when pactl is not installed."""
        with patch('eloGraf.audio_recorder.run', side_effect=FileNotFoundError):
            devices = get_audio_devices(backend="parec")
            # Should still have default
            self.assertEqual(len(devices), 1)
            self.assertEqual(devices[0][0], "default")

    def test_pactl_timeout(self):
        """Test handling when pactl times out."""
        with patch('eloGraf.audio_recorder.run', side_effect=TimeoutError):
            devices = get_audio_devices(backend="parec")
            self.assertEqual(len(devices), 1)
            self.assertEqual(devices[0][0], "default")

    def test_pactl_failure(self):
        """Test handling when pactl returns error."""
        with patch('eloGraf.audio_recorder.run') as mock_run:
            mock_run.return_value = CompletedProcess(
                args=['pactl', 'list', 'sources'],
                returncode=1,
                stdout='',
                stderr='Connection failed'
            )

            devices = get_audio_devices(backend="parec")
            self.assertEqual(len(devices), 1)
            self.assertEqual(devices[0][0], "default")

    def test_empty_output(self):
        """Test handling of empty pactl output."""
        with patch('eloGraf.audio_recorder.run') as mock_run:
            mock_run.return_value = CompletedProcess(
                args=['pactl', 'list', 'sources'],
                returncode=0,
                stdout='',
                stderr=''
            )

            devices = get_audio_devices(backend="parec")
            self.assertEqual(len(devices), 1)
            self.assertEqual(devices[0][0], "default")


if __name__ == '__main__':
    unittest.main()
