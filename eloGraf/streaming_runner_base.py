"""Shared base implementation for audio streaming STT runners."""

from __future__ import annotations

import logging
import threading
import time
from abc import ABC, abstractmethod
from typing import Callable, Optional, Sequence

from eloGraf.audio_recorder import AudioRecorder
from eloGraf.stt_engine import STTProcessRunner


class StreamingRunnerBase(STTProcessRunner, ABC):
    """Base class that manages audio capture and lifecycle for streaming engines."""

    def __init__(
        self,
        controller,
        *,
        sample_rate: int,
        channels: int,
        chunk_duration: float,
        device: Optional[str] = None,
        input_simulator: Optional[Callable[[str], None]] = None,
    ) -> None:
        self._controller = controller
        self._sample_rate = sample_rate
        self._channels = channels
        self._chunk_duration = max(chunk_duration, 0.01)
        self._device = device
        self._input_simulator = input_simulator

        self._runner_thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._audio_recorder: Optional[AudioRecorder] = None
        self._failure_exit = False
        self._audio_detection_logged = False

    # ------------------------------------------------------------------
    # STTProcessRunner interface
    # ------------------------------------------------------------------

    def start(self, command: Sequence[str], env: Optional[dict] = None) -> bool:
        if self.is_running():
            logging.warning("Streaming runner already active")
            return False

        if not self._preflight_checks():
            self._controller.fail_to_start()
            return False

        self._controller.start()

        if not self._initialize_connection():
            self._controller.fail_to_start()
            return False

        try:
            self._audio_recorder = self._create_audio_recorder()
        except Exception as exc:  # pragma: no cover - defensive
            logging.error("Failed to initialise audio recorder: %s", exc)
            self._controller.emit_error("Audio capture initialisation failed")
            self._controller.fail_to_start()
            self._cleanup_connection()
            return False

        self._stop_event.clear()
        self._failure_exit = False
        self._audio_detection_logged = False
        self._runner_thread = threading.Thread(target=self._runner_loop, daemon=True)
        self._runner_thread.start()
        return True

    def stop(self) -> None:
        if not self.is_running():
            return

        self._controller.stop_requested()
        self._stop_event.set()

        if self._runner_thread:
            self._runner_thread.join(timeout=3)
            self._runner_thread = None

        self._teardown_audio_recorder()
        self._cleanup_connection()

        if not self._failure_exit:
            self._controller.handle_exit(0)

    def suspend(self) -> None:
        if self.is_running():
            self._controller.suspend_requested()

    def resume(self) -> None:
        if self.is_running():
            self._controller.resume_requested()

    def poll(self) -> None:
        # Thread-based implementation; no polling required.
        pass

    def is_running(self) -> bool:
        return self._runner_thread is not None and self._runner_thread.is_alive()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _runner_loop(self) -> None:
        assert self._audio_recorder is not None
        self._dispatch_state_change("set_recording")

        try:
            while not self._stop_event.is_set():
                if self._controller.is_suspended:
                    time.sleep(0.1)
                    continue

                try:
                    audio_chunk = self._audio_recorder.record_chunk(self._chunk_duration)
                except Exception as exc:  # pragma: no cover - defensive
                    logging.error("Audio capture failed: %s", exc)
                    self._controller.emit_error("Audio capture failed")
                    self._failure_exit = True
                    break

                if not audio_chunk:
                    continue

                # Log audio detection status on first chunk
                self._log_first_audio_detection(audio_chunk)

                try:
                    self._process_audio_chunk(audio_chunk)
                except Exception as exc:  # pragma: no cover - defensive
                    logging.exception("Error while processing audio chunk")
                    self._controller.emit_error(str(exc))
                    self._failure_exit = True
                    break
        finally:
            self._stop_event.set()
            self._cleanup_connection()
            self._teardown_audio_recorder()
            if self._failure_exit:
                self._controller.handle_exit(1)

    def _create_audio_recorder(self) -> AudioRecorder:
        return AudioRecorder(
            sample_rate=self._sample_rate,
            channels=self._channels,
            device=self._device,
        )

    def _teardown_audio_recorder(self) -> None:
        if self._audio_recorder is not None:
            try:
                self._audio_recorder.close()
            except Exception:  # pragma: no cover - defensive
                pass
            self._audio_recorder = None

    def _dispatch_state_change(self, method_name: str) -> None:
        method = getattr(self._controller, method_name, None)
        if callable(method):
            method()

    def _log_first_audio_detection(self, audio_chunk: bytes) -> None:
        """Log whether audio is detected in the first chunk."""
        if self._audio_detection_logged:
            return

        self._audio_detection_logged = True

        try:
            # Extract raw PCM audio from WAV (skip 44-byte header)
            raw_audio = audio_chunk[44:] if len(audio_chunk) > 44 else audio_chunk

            # Calculate RMS (root mean square) audio level
            import struct
            samples = struct.unpack(f"<{len(raw_audio) // 2}h", raw_audio)
            rms = (sum(s ** 2 for s in samples) / len(samples)) ** 0.5 if samples else 0.0

            if rms > 100:  # Basic threshold to detect any audio
                logging.info(f"Audio detected: RMS level = {rms:.1f}")
            else:
                logging.info(f"No audio detected: RMS level = {rms:.1f}")
        except Exception as exc:
            logging.warning(f"Could not check audio level: {exc}")

    def force_stop(self) -> None:
        """
        Forcefully stop the streaming runner.

        For thread-based runners, there is no safe way to forcefully kill the
        thread. This method is a no-op, relying on the daemon thread to be
        terminated when the application exits. The stop() method with its
        timeout is the primary mechanism for stopping.
        """
        pass

    # ------------------------------------------------------------------
    # Hooks for subclasses
    # ------------------------------------------------------------------

    def _preflight_checks(self) -> bool:
        """Optional validation before starting."""
        return True

    @abstractmethod
    def _initialize_connection(self) -> bool:
        """Prepare external resources. Return False if setup fails."""

    @abstractmethod
    def _process_audio_chunk(self, audio_data: bytes) -> None:
        """Handle microphone data and interact with the remote service."""

    @abstractmethod
    def _cleanup_connection(self) -> None:
        """Release resources owned by the subclass."""
