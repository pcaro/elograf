"""Integration tests for WhisperLocal engine."""
import time
import pytest
from unittest.mock import Mock, patch, MagicMock


def test_whisper_local_plugin_registration():
    """Plugin should be registered."""
    from eloGraf.stt_factory import get_available_engines
    
    engines = get_available_engines()
    assert "whisper-local" in engines


def test_whisper_local_create_engine():
    """Should be able to create controller and runner."""
    from eloGraf.stt_factory import create_stt_engine
    from eloGraf.engines.whisper_local.settings import WhisperLocalSettings
    
    settings = WhisperLocalSettings()
    
    # Mock model and VAD to avoid loading heavy deps
    with patch('eloGraf.engines.whisper_local.inference_backend.WhisperModel'), \
         patch('eloGraf.vad_processor.SileroVADProcessor._load_model'):
        
        controller, runner = create_stt_engine("whisper-local", settings=settings)
        
        assert controller is not None
        assert runner is not None
        assert controller._engine_name == "WhisperLocal"


def test_whisper_local_full_lifecycle():
    """Test full cycle: start -> suspend -> resume -> stop."""
    from eloGraf.engines.whisper_local.runner import WhisperLocalRunner
    from eloGraf.engines.whisper_local.controller import WhisperLocalController
    from eloGraf.engines.whisper_local.settings import WhisperLocalSettings
    from eloGraf.engines.whisper_local.controller import WhisperLocalState
    
    settings = WhisperLocalSettings(
        model_size="tiny",
        auto_reset_context=True,
    )
    
    # Mock backend, pipeline and capture to test runner logic in isolation
    with patch('eloGraf.engines.whisper_local.runner.WhisperInferenceBackend') as mock_backend_class, \
         patch('eloGraf.engines.whisper_local.runner.AudioPipeline') as mock_pipeline_class, \
         patch('eloGraf.engines.whisper_local.runner.AudioCapture') as mock_capture_class:
        
        mock_backend = MagicMock()
        mock_backend.is_loaded = False # Initially not loaded
        
        # Make load_model take a bit of time to test state transitions
        def slow_load(*args, **kwargs):
            time.sleep(0.2)
            mock_backend.is_loaded = True
            
        mock_backend.load_model.side_effect = slow_load
        mock_backend_class.return_value = mock_backend
        
        mock_pipeline = MagicMock()
        mock_pipeline_class.return_value = mock_pipeline
        
        controller = WhisperLocalController(settings)
        runner = WhisperLocalRunner(controller, settings)
        
        # Start (loads in background thread)
        # We need to mock _is_model_cached to avoid disk check
        with patch.object(runner, '_is_model_cached', return_value=True):
            assert runner.start()
        
        assert controller.state == WhisperLocalState.LOADING
        
        # Simulate background load completion
        mock_backend.is_loaded = True
        # runner._load_model_task will transition state when it finishes backend.load_model
        
        # Wait for loading to finish (short wait)
        max_wait = 2.0
        start_t = time.time()
        while controller.state == WhisperLocalState.LOADING and (time.time() - start_t < max_wait):
            time.sleep(0.1)
            
        assert controller.state == WhisperLocalState.READY
        
        # Suspend
        runner.suspend()
        assert controller.state == WhisperLocalState.SUSPENDED
        
        # Resume
        runner.resume()
        assert controller.state == WhisperLocalState.READY
        
        # Context Reset
        runner.reset_context()
        mock_backend.reset_context.assert_called_once()
        
        # Stop
        runner.stop()
        assert controller.state == WhisperLocalState.IDLE
        mock_backend.unload_model.assert_called_once()


def test_whisper_local_context_manager():
    """Test context management logic in isolation."""
    from eloGraf.engines.whisper_local.inference_backend import ContextManager
    
    cm = ContextManager(max_chars=50, auto_reset_seconds=0.5)
    
    cm.add("Hello world")
    assert cm.get() == " Hello world"
    
    cm.add("and some more text")
    # Result should fit in 50 chars and keep whole words if possible
    context = cm.get()
    assert len(context) <= 50
    assert "more text" in context
    
    # Test auto-reset
    time.sleep(0.6)
    assert cm.get() is None
    
    # Test manual reset
    cm.add("Fresh context")
    assert cm.get() == " Fresh context"
    cm.reset()
    assert cm.get() is None
