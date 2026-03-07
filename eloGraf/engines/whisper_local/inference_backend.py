"""Inference backend for faster-whisper."""
import logging
import time
import gc
from typing import Optional, Iterator, Dict, Any

import numpy as np
from eloGraf.inference_backend import InferenceBackend

try:
    from faster_whisper import WhisperModel
except ImportError:
    WhisperModel = None


class ContextManager:
    """Manages context for Whisper with limits and reset."""
    
    def __init__(
        self,
        max_chars: int = 100,
        auto_reset_seconds: float = 30.0,
    ):
        self._max_chars = max(0, min(max_chars, 200))  # 0-200 chars
        self._auto_reset = auto_reset_seconds
        self._context = ""
        self._last_update = time.time()
        self._reset_count = 0
    
    def add(self, text: str) -> None:
        """Adds text to the context."""
        if self._should_auto_reset():
            self.reset()
        
        self._context += " " + text
        self._last_update = time.time()
        
        # Keep within limit
        if len(self._context) > self._max_chars:
            # Trim keeping the end (most recent)
            # Try to cut by words if possible
            if " " in self._context:
                words = self._context.split()
                # Keep words that fit in the limit
                new_context = ""
                for word in reversed(words):
                    if len(new_context) + len(word) + 1 <= self._max_chars:
                        new_context = word + " " + new_context
                    else:
                        break
                self._context = new_context.strip()
            else:
                self._context = self._context[-self._max_chars:]
    
    def get(self) -> Optional[str]:
        """Returns context if there is something to use."""
        if self._should_auto_reset():
            self.reset()
            
        if not self._context or self._max_chars == 0:
            return None
        return self._context
    
    def reset(self) -> None:
        """Manual context reset."""
        self._context = ""
        self._reset_count += 1
        self._last_update = time.time()
        logging.debug(f"Context reset (total resets: {self._reset_count})")
    
    def _should_auto_reset(self) -> bool:
        """Checks if enough time has passed for auto-reset."""
        if self._auto_reset <= 0 or not self._context:
            return False
        return (time.time() - self._last_update) > self._auto_reset

    @property
    def stats(self) -> dict:
        return {
            'length': len(self._context),
            'limit': self._max_chars,
            'resets': self._reset_count,
            'seconds_since_update': time.time() - self._last_update,
        }


class WhisperInferenceBackend(InferenceBackend):
    """Inference backend for faster-whisper with context management."""
    
    def __init__(self):
        self._model: Optional[Any] = None
        self._model_size: Optional[str] = None
        self._context_manager: Optional[ContextManager] = None
        self._language: Optional[str] = None
        self._device: str = "auto"
        self._compute_type: str = "auto"
    
    def load_model(
        self, 
        model_path: str,
        **kwargs
    ) -> None:
        if WhisperModel is None:
            raise ImportError("faster-whisper not installed. Run: pip install faster-whisper")
            
        self._model_size = model_path
        self._device = kwargs.get('device', 'auto')
        self._compute_type = kwargs.get('compute_type', 'auto')
        
        self._context_manager = ContextManager(
            max_chars=kwargs.get('context_limit_chars', 100),
            auto_reset_seconds=kwargs.get('auto_reset_seconds', 30.0)
        )
        
        self._language = kwargs.get('language', 'auto')
        if self._language == "auto":
            self._language = None
            
        logging.info(f"Loading Whisper model '{model_path}' on {self._device} ({self._compute_type})...")
        
        self._model = WhisperModel(
            model_path,
            device=self._device,
            compute_type=self._compute_type,
        )
        logging.info(f"Whisper model '{model_path}' loaded successfully")
    
    def transcribe(self, audio: bytes) -> str:
        if not self._model:
            raise RuntimeError("Model not loaded")
        
        # Prepare limited context
        context = self._context_manager.get()
        
        # Convert PCM bytes to numpy
        audio_np = self._pcm_to_numpy(audio)
        
        # Transcribe with context
        logging.debug(f"Transcribing with Whisper (language={self._language}, context_len={len(context) if context else 0})...")
        segments, info = self._model.transcribe(
            audio_np,
            language=self._language,
            initial_prompt=context if context else None,
            condition_on_previous_text=False,
            suppress_tokens=[-1],
            temperature=0.0,
        )
        
        # Process result
        text_parts = []
        for segment in segments:
            if segment.no_speech_prob > 0.6:
                logging.debug(f"Filtering likely hallucination: '{segment.text}' (prob: {segment.no_speech_prob:.2f})")
                continue
            text_parts.append(segment.text)
        
        text = "".join(text_parts).strip()
        logging.debug(f"Transcription result: '{text}'")
        
        # Update context with new text
        if text:
            self._context_manager.add(text)
        
        return text
    
    def transcribe_streaming(self, audio: bytes) -> Iterator[str]:
        """Whisper does not support real streaming, return final result."""
        text = self.transcribe(audio)
        if text:
            yield text
    
    def unload_model(self) -> None:
        """Release model and clear VRAM if necessary."""
        self._model = None
        if self._context_manager:
            self._context_manager.reset()
        gc.collect()
        
        # Clear VRAM if using CUDA
        try:
            import torch
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
                logging.info("CUDA cache cleared")
        except ImportError:
            pass
    
    @property
    def is_loaded(self) -> bool:
        return self._model is not None
    
    def get_memory_usage(self) -> Dict[str, Optional[int]]:
        """Return RAM and VRAM usage."""
        import psutil
        import os
        process = psutil.Process(os.getpid())
        ram_mb = process.memory_info().rss // (1024 * 1024)
        
        vram_mb = None
        try:
            import torch
            if torch.cuda.is_available():
                vram_mb = torch.cuda.memory_allocated() // (1024 * 1024)
        except ImportError:
            pass
        
        return {'ram_mb': ram_mb, 'vram_mb': vram_mb}
    
    def reset_context(self) -> None:
        """Manual context reset."""
        if self._context_manager:
            self._context_manager.reset()
    
    def _pcm_to_numpy(self, audio: bytes) -> np.ndarray:
        """Convert 16-bit PCM bytes to numpy float32 [-1, 1]."""
        audio_array = np.frombuffer(audio, dtype=np.int16)
        return audio_array.astype(np.float32) / 32768.0
