"""Runner for WhisperLocal engine using AudioPipeline + ThreadedInferenceRunner."""
import logging
import threading
from pathlib import Path
from typing import Optional, Sequence, Callable

from eloGraf.threaded_runner import ThreadedInferenceRunner
from eloGraf.audio_pipeline import AudioPipeline, AudioCapture, AudioBuffer
from eloGraf.vad_processor import SileroVADProcessor
from eloGraf.text_formatter import TextFormatter
from eloGraf.input_simulator import type_text
from .inference_backend import WhisperInferenceBackend
from .settings import WhisperLocalSettings
from .controller import WhisperLocalController


class WhisperLocalRunner:
    """Runner for Whisper using AudioPipeline + ThreadedInferenceRunner."""

    def __init__(
        self,
        controller: WhisperLocalController,
        settings: WhisperLocalSettings,
        input_simulator: Optional[Callable[[str], None]] = None,
    ):
        self._controller = controller
        self._settings = settings
        self._input_simulator = input_simulator or type_text

        
        # Create InferenceBackend
        self._backend = WhisperInferenceBackend()
        
        # Configure VAD
        # Whisper needs more context than Vosk, so we use slightly larger timeouts
        self._vad = SileroVADProcessor(
            threshold=settings.vad_threshold,
            min_speech_duration_ms=300,  # 300ms minimum speech
            silence_timeout_ms=600,      # 600ms silence to cut
        )
        
        # Create AudioPipeline
        self._pipeline = AudioPipeline(
            capture=AudioCapture(device=settings.device_name),
            vad=self._vad,
            buffer=AudioBuffer(
                max_duration=60.0,  # Whisper can process up to 30s comfortably
                sample_rate=16000
            ),
            speech_callback=self._on_speech_end,
            controller=controller
        )
        
        # Text formatter
        self._formatter = TextFormatter(locale=settings.locale)
        
        # Compose threaded runner
        self._runner = ThreadedInferenceRunner(
            controller=controller,
            inference_backend=self._backend,
            audio_pipeline=self._pipeline,
            text_formatter=self._formatter,
            max_queue_depth=settings.max_queue_depth,
        )
        
        # Connect input simulator
        if self._input_simulator:
            self._runner.transcription_callback = self._input_simulator
            
        self._load_thread: Optional[threading.Thread] = None
    
    def start(self, command: Sequence[str] = None, env: Optional[dict] = None) -> bool:
        """Starts the Whisper engine.
        
        Args:
            command: Ignored (kept for interface compatibility)
            env: Ignored (kept for interface compatibility)
        """
        if self._load_thread and self._load_thread.is_alive():
            logging.warning("Whisper model is still loading...")
            return True
            
        self._controller.transition_to("loading")
        
        # Check if model is cached (optional, to inform user)
        if not self._is_model_cached(self._settings.model_size):
            self._controller.transition_to("downloading_model")
            self._controller._emit_output(f"Downloading Whisper '{self._settings.model_size}' model from HuggingFace...")
        
        # Load model in a separate thread to not block UI
        self._load_thread = threading.Thread(target=self._load_model_task, daemon=True)
        self._load_thread.start()
        
        return True

    def _load_model_task(self):
        """Background task to load the model."""
        try:
            self._backend.load_model(
                self._settings.model_size,
                device=self._settings.device,
                compute_type=self._settings.compute_type,
                context_limit_chars=self._settings.context_limit_chars,
                auto_reset_seconds=30.0 if self._settings.auto_reset_context else 999999,
                language=self._settings.language,
            )
            
            # Once loaded, start the runner (capture and inference threads)
            self._runner.start()
            self._controller.transition_to("ready")
            logging.debug("Whisper engine started and ready")
            
        except Exception as exc:
            logging.exception("Failed to load Whisper model")
            self._controller.emit_error(f"Error loading model: {exc}")
            self._controller.transition_to("failed")

    def stop(self) -> None:
        """Stops the engine."""
        self._runner.stop()
        self._backend.unload_model()
        self._controller.transition_to("idle")

    def suspend(self) -> None:
        """Suspends listening."""
        self._runner.suspend()
        self._controller.transition_to("suspended")

    def resume(self) -> None:
        """Resumes listening."""
        self._runner.resume()
        self._controller.transition_to("ready")

    def reset_context(self) -> None:
        """Manual context reset."""
        self._backend.reset_context()
        self._controller._emit_output("Whisper context reset")

    def poll(self) -> None:
        """No-op for threaded implementation."""
        pass

    def is_running(self) -> bool:
        """Check if engine is running (model loaded)."""
        return self._backend.is_loaded

    def force_stop(self) -> None:
        """Force stop."""
        self.stop()

    def _on_speech_end(self, audio: bytes) -> None:
        """Callback when VAD detects end of speech."""
        # ThreadedInferenceRunner already handles the transition to 'transcribing'
        # but we can add extra logic here if needed.
        pass

    def _is_model_cached(self, model_size: str) -> bool:
        """Checks if model is in HuggingFace cache."""
        cache_dir = Path.home() / ".cache" / "huggingface" / "hub"
        # faster-whisper pattern usually: models--Systran--faster-whisper-{model_size}
        pattern = f"models--Systran--faster-whisper-{model_size}"
        try:
            return any(cache_dir.glob(f"**/{pattern}*"))
        except Exception:
            return False
