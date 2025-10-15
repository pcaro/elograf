# ABOUTME: Tests for first-time audio detection logging in StreamingRunnerBase.
# ABOUTME: Verifies that audio level is logged only on the first chunk.

from __future__ import annotations

import logging
from unittest.mock import MagicMock, patch

import pytest

from eloGraf.streaming_runner_base import StreamingRunnerBase


class MockStreamingRunner(StreamingRunnerBase):
    """Minimal concrete implementation for testing."""

    def _preflight_checks(self) -> bool:
        return True

    def _initialize_connection(self) -> bool:
        return True

    def _process_audio_chunk(self, audio_data: bytes) -> None:
        pass

    def _cleanup_connection(self) -> None:
        pass


@pytest.fixture
def mock_controller():
    controller = MagicMock()
    controller.is_suspended = False
    return controller


def test_first_audio_detection_logged_with_audio(mock_controller, caplog):
    """Test that audio detection is logged when audio is present in first chunk."""
    runner = MockStreamingRunner(
        mock_controller,
        sample_rate=16000,
        channels=1,
        chunk_duration=0.1,
    )

    # Create a WAV chunk with audio (non-zero samples)
    # WAV header (44 bytes) + some audio data
    import struct
    import wave
    import io

    wav_buffer = io.BytesIO()
    with wave.open(wav_buffer, 'wb') as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)  # 16-bit
        wav_file.setframerate(16000)
        # Create audio samples with amplitude 1000 (should trigger "audio detected")
        samples = struct.pack('<100h', *([1000] * 100))
        wav_file.writeframes(samples)

    audio_chunk = wav_buffer.getvalue()

    with caplog.at_level(logging.INFO):
        runner._log_first_audio_detection(audio_chunk)

    # Verify audio was detected
    assert any("Audio detected" in record.message for record in caplog.records)
    assert any("RMS level" in record.message for record in caplog.records)


def test_first_audio_detection_logged_without_audio(mock_controller, caplog):
    """Test that lack of audio is logged when no audio in first chunk."""
    runner = MockStreamingRunner(
        mock_controller,
        sample_rate=16000,
        channels=1,
        chunk_duration=0.1,
    )

    # Create a WAV chunk with silence (zero samples)
    import struct
    import wave
    import io

    wav_buffer = io.BytesIO()
    with wave.open(wav_buffer, 'wb') as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(16000)
        # Create silent samples
        samples = struct.pack('<100h', *([0] * 100))
        wav_file.writeframes(samples)

    audio_chunk = wav_buffer.getvalue()

    with caplog.at_level(logging.INFO):
        runner._log_first_audio_detection(audio_chunk)

    # Verify no audio was detected
    assert any("No audio detected" in record.message for record in caplog.records)
    assert any("RMS level" in record.message for record in caplog.records)


def test_audio_detection_only_logged_once(mock_controller, caplog):
    """Test that audio detection is only logged for the first chunk."""
    runner = MockStreamingRunner(
        mock_controller,
        sample_rate=16000,
        channels=1,
        chunk_duration=0.1,
    )

    # Create a WAV chunk
    import struct
    import wave
    import io

    wav_buffer = io.BytesIO()
    with wave.open(wav_buffer, 'wb') as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(16000)
        samples = struct.pack('<100h', *([1000] * 100))
        wav_file.writeframes(samples)

    audio_chunk = wav_buffer.getvalue()

    with caplog.at_level(logging.INFO):
        # Call multiple times
        runner._log_first_audio_detection(audio_chunk)
        runner._log_first_audio_detection(audio_chunk)
        runner._log_first_audio_detection(audio_chunk)

    # Verify only one log entry was created
    audio_logs = [r for r in caplog.records if "Audio detected" in r.message or "No audio detected" in r.message]
    assert len(audio_logs) == 1


def test_audio_detection_flag_reset_on_new_start(mock_controller):
    """Test that audio detection flag is reset when starting a new recording session."""
    runner = MockStreamingRunner(
        mock_controller,
        sample_rate=16000,
        channels=1,
        chunk_duration=0.1,
    )

    # Simulate first detection
    runner._audio_detection_logged = True

    # Mock the audio recorder and other dependencies
    with patch.object(runner, '_create_audio_recorder'), \
         patch.object(runner, '_initialize_connection', return_value=True), \
         patch.object(runner, '_preflight_checks', return_value=True), \
         patch('threading.Thread'):  # Prevent thread from actually starting

        # Start should reset the flag
        runner.start([])

        # Verify flag was reset (checked immediately after start(), before thread runs)
        assert runner._audio_detection_logged is False
