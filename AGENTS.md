# Project Description

EloGraf is a desktop utility written in Python that facilitates voice dictation on Linux by integrating with multiple speech recognition engines, including Whisper (Local), Vosk (Local), Whisper Docker, Google Cloud Speech, OpenAI Realtime, AssemblyAI Realtime, and Gemini Live API. The application offers a system tray, global shortcuts, and an advanced interface for configuring audio devices, pre/post commands, and engine-specific parameters for each STT engine.

## Main Capabilities
- Graphical launcher and CLI to start, stop, suspend, and resume dictation
- Model management and downloads from remote repositories
- Configuration persistence via QSettings and multilanguage support through Qt
- IPC integration (D-Bus/local sockets) to coordinate with other system components

## Technical Structure

The code is organized as a Python package with a modular architecture. Core application logic (UI, state management, etc.) is kept separate from the STT engine implementations. Each speech recognition engine is a self-contained sub-package within the `eloGraf/engines/` directory, which makes the system extensible and easy to maintain.

### Engine Module Structure

Each engine is a sub-package that adheres to a common contract:
- `controller.py`: Implements the engine-specific state machine and communication logic.
- `engine.py`: Defines the engine metadata for the `STTFactory`.
- `settings.py`: Defines a `dataclass` schema for the engine's configuration parameters with UI metadata.

### Abstract STT Interface and Base Implementations

To ensure consistency and reduce code duplication, the application relies on a set of abstract and concrete base classes.

**STT Interfaces (`stt_engine.py`)**
- `STTController`: An abstract interface that all engine controllers implement.
- `STTProcessRunner`: An abstract interface for classes that manage the engine's lifecycle.

**Controller Base Classes (`base_controller.py`)**
- `EnumStateController`: A generic base class that provides a shared implementation for controllers using a Python `Enum` for their state machine.
- `StreamingControllerBase`: Inherits from `EnumStateController` and adds shared logic for suspend/resume functionality, common to all streaming engines.

**Runner Base Class (`streaming_runner_base.py`)**
- `StreamingRunnerBase`: A crucial base class for all streaming runners. It correctly implements the main recording loop, thread management, and audio capture logic. Child runners inherit from it and only need to implement the engine-specific logic: `_initialize_connection()`, `_process_audio_chunk()`, and `_cleanup_connection()`.

**Audio Capture (`audio_recorder.py`)**
- `AudioRecorder`: Unified audio recording with pluggable backends (PyAudio and parec).
- `PyAudioBackend`: Cross-platform audio capture using PyAudio library.
- `ParecBackend`: Linux PulseAudio capture via parec subprocess, supports device selection.
- `get_audio_devices()`: Query available audio input devices for a given backend.

The AudioRecorder automatically selects the best available backend (prefers parec on Linux, falls back to PyAudio) and provides a consistent interface for all streaming engines.

### Lifecycle Management with EngineManager

`engine_manager.py` manages creation, refresh, and failure recovery:
- **Safe creation**: Disconnects timers and listeners before swapping engines
- **Circuit breaker**: Classifies failures and switches to fallback engines after repeated errors
- **Retry with exponential backoff**: Automatic retries with incremental delay
- **Refresh timeout**: Safety timer that forces shutdown if an engine refuses to stop

## Speech Recognition Engines

### 1. Whisper (Local)

The Whisper Local integration is implemented in the `eloGraf/engines/whisper_local/` package and provides a high-accuracy, fully offline speech recognition solution using `faster-whisper`.

#### Architecture

Runs OpenAI's Whisper models natively on the local machine using CTranslate2.

**Key Features:**
- Fully offline operation
- High accuracy with context-aware processing
- Supports multiple model sizes (tiny, base, small, medium, large-v3)
- Native execution (no Docker required)

### 2. Vosk (Local)

The Vosk Local integration is implemented in the `eloGraf/engines/vosk_local/` package and provides a lightweight, privacy-focused offline speech recognition solution.

#### Architecture

Uses the `vosk` Python library for local processing.

**Key Features:**
- Fully offline operation
- Extremely low resource usage
- Fast processing on CPU
- Compatible with many languages via Vosk models

### 3. Whisper Docker

The Whisper Docker integration is implemented in the `eloGraf/engines/whisper/` package and runs OpenAI's Whisper ASR in a Docker container as a REST API service.

#### Architecture

Uses the `onerahmet/openai-whisper-asr-webservice` Docker image, which exposes a REST API at port 9000 (configurable).

**Key Features:**
- High accuracy with Whisper models
- Automatic container lifecycle management
- Voice Activity Detection (VAD) to skip silence

### 4. Google Cloud Speech-to-Text V2

The Google Cloud Speech integration is implemented in the `eloGraf/engines/google/` package and uses Google's enterprise-grade speech recognition API with gRPC streaming.

### 5. OpenAI Realtime API

The OpenAI Realtime API integration is implemented in the `eloGraf/engines/openai/` package and uses a WebSocket-based communication model for real-time voice transcription.

### 6. AssemblyAI Realtime

The AssemblyAI integration is implemented in the `eloGraf/engines/assemblyai/` package and provides another cloud-hosted, low-latency streaming engine.

### 7. Gemini Live API

The Gemini Live API integration is implemented in the `eloGraf/engines/gemini/` package and uses Google's Gemini models for real-time speech-to-text via WebSockets.

## Testing

The project uses pytest for testing. Tests are located in the `tests/` directory.

### Running Tests

Run all tests:
```bash
uv run python -m pytest
```

### Test Structure

- `tests/engines/` - Engine-specific tests for each STT implementation
- `tests/test_*.py` - Core functionality tests (settings, audio, IPC, etc.)

## Translations

The application interface is available in multiple languages. The translation source files (`.ts`) are located in the `eloGraf/translations/` directory.

### Compiling Translations

To make new or updated translations visible in the application, the `.ts` source files must be compiled into the binary `.qm` format:

```bash
uv run pyside6-lrelease eloGraf/translations/*.ts
```
