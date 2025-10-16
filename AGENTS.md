# Project Description

EloGraf is a desktop utility written in Python that facilitates voice dictation on Linux by integrating with multiple speech recognition engines, including nerd-dictation, Whisper Docker, Google Cloud Speech, and OpenAI Realtime. The application offers a system tray, global shortcuts, and an advanced interface for configuring audio devices, pre/post commands, and engine-specific parameters for each STT engine.

## Main Capabilities
- Graphical launcher and CLI to start, stop, suspend, and resume dictation
- Model management and downloads from remote repositories
- Configuration persistence via QSettings and multilanguage support through Qt
- IPC integration (D-Bus/local sockets) to coordinate with other system components

## Technical Structure

The code is organized as a Python package with a modular architecture. Core application logic (UI, state management, etc.) is kept separate from the STT engine implementations. Each speech recognition engine is a self-contained package within the `elograf/engines/` directory, which makes the system extensible and easy to maintain.

### Engine Module Structure

Each engine is a sub-package that adheres to a common contract, typically containing:
- `controller.py`: Implements the engine-specific state machine and process runner.
- `engine.py`: Defines the engine for the `STTFactory`, making it discoverable by the application.
- `settings.py`: (Optional) Defines a `dataclass` schema for the engine's configuration parameters.

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

### 1. nerd-dictation (Default)

The nerd-dictation integration is implemented in the `elograf/engines/nerd/` package and provides a local, privacy-focused CLI-based speech recognition solution.

#### Architecture

nerd-dictation is an external command-line tool that EloGraf wraps and monitors. The controller, defined in `controller.py` within the package, parses stdout to detect state changes.

**Key Features:**
- Fully offline operation with no network requirements
- Local Vosk model processing
- Direct subprocess management
- State detection via output parsing

#### State Machine

States are detected by parsing nerd-dictation's stdout messages:

- **IDLE**: No dictation active
- **STARTING**: Process launching
- **LOADING**: "loading model" detected in output
- **READY**: "model loaded", "listening", or "ready" detected
- **DICTATING**: "dictation started" detected
- **SUSPENDED**: "suspended" detected
- **STOPPING**: Stop command sent
- **FAILED**: Non-zero exit or error

#### Process Management

Unlike other engines, nerd-dictation uses separate command invocations for control:

```bash
nerd-dictation begin         # Start dictation
nerd-dictation end           # Stop dictation
nerd-dictation suspend       # Pause
nerd-dictation resume        # Continue
```

EloGraf spawns the main process and monitors stdout, sending control commands via separate subprocess calls.

#### Configuration

- **Model**: Vosk model directory path
- **Sample Rate**: Audio sampling rate (default: 44100 Hz)
- **Timeout**: Auto-stop after silence period (0 = disabled)
- **Idle Time**: CPU vs responsiveness balance (default: 100ms)
- **Punctuation Timeout**: Add punctuation based on pause duration

#### Requirements

- `nerd-dictation` installed separately (not included)
- Vosk model files downloaded
- PulseAudio or ALSA for audio capture

### 2. Whisper Docker

The Whisper Docker integration is implemented in the `elograf/engines/whisper/` package and runs OpenAI's Whisper ASR in a Docker container as a REST API service.

#### Architecture

Uses the `onerahmet/openai-whisper-asr-webservice` Docker image, which exposes a REST API at port 9000 (configurable).

**Key Features:**
- High accuracy with Whisper models (tiny, base, small, medium, large-v3)
- Automatic container lifecycle management
- Voice Activity Detection (VAD) to skip silence
- Auto-reconnect on API failures
- Chunk-based transcription

#### Container Management

The runner automatically:
1. Checks if container exists and matches requested model
2. Stops/recreates container if model changed
3. Starts container if stopped
4. Waits for API readiness (up to 180s timeout)

```bash
docker run -d --name elograf-whisper \
  -p 9000:9000 \
  -e ASR_MODEL=base \
  -e ASR_ENGINE=openai_whisper \
  onerahmet/openai-whisper-asr-webservice:latest
```

#### Audio Processing Flow

1. **Record**: Captures audio chunks via AudioRecorder (configurable duration, default 5s)
2. **VAD Check**: Calculates RMS audio level, skips if below threshold
3. **Transcribe**: POSTs WAV file to `/asr` endpoint with parameters
4. **Simulate**: Types transcribed text using dotool/xdotool
5. **Retry**: Auto-reconnects and retries on failures (up to 3 attempts)

#### REST API

- **Endpoint**: `POST http://localhost:9000/asr`
- **Parameters**:
  - `output=json`: Response format
  - `language`: Optional language code (e.g., "en", "es")
- **Request**: multipart/form-data with audio_file (WAV format)
- **Response**: `{"text": "transcribed text"}`

#### Configuration

- **Model**: Whisper model size (tiny/base/small/medium/large-v3)
- **Language**: Language code or auto-detect
- **Port**: API port (default: 9000)
- **Chunk Duration**: Recording interval in seconds (default: 5.0)
- **Sample Rate**: Audio sampling rate (default: 16000 Hz)
- **Channels**: Audio channels (default: 1 = mono)
- **VAD**: Enable/disable voice activity detection
- **VAD Threshold**: RMS threshold for silence detection (default: 500.0)
- **Auto-reconnect**: Retry on API failures (default: true)

#### Requirements

- Docker installed and running
- Network access for initial image download (~2GB)
- AudioRecorder (parec or PyAudio) for audio recording

### 3. Google Cloud Speech-to-Text V2

The Google Cloud Speech integration is implemented in the `elograf/engines/google/` package and uses Google's enterprise-grade speech recognition API with gRPC streaming.

#### Architecture

Uses the `google-cloud-speech` Python library to stream audio in real-time to Google Cloud Speech-to-Text V2 API.

**Key Features:**
- Real-time streaming recognition with bidirectional gRPC
- State-of-the-art accuracy with Chirp 3 model
- Multi-language support
- Server-side processing
- Automatic project ID detection from credentials

#### Authentication

Supports two authentication methods:

1. **Service Account Key File** (recommended):
   ```python
   credentials_path = "/path/to/service-account-key.json"
   os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = credentials_path
   ```

2. **Application Default Credentials**:
   - Uses gcloud auth application-default login
   - Automatically detected if GOOGLE_APPLICATION_CREDENTIALS not set

#### Streaming Flow

1. **Setup**: Creates SpeechClient and configures recognizer
2. **Generator**: Yields audio chunks as StreamingRecognizeRequest
   - First request: Contains config (recognizer, language, model)
   - Subsequent requests: Raw PCM audio data (max 25 KB chunks)
3. **Stream**: Bidirectional gRPC stream processes audio in real-time
4. **Results**: Receives partial and final transcription results
5. **Output**: Only final results are emitted and typed

```python
# Recognition config
recognition_config = RecognitionConfig(
    auto_decoding_config=AutoDetectDecodingConfig(),
    language_codes=["en-US"],
    model="chirp_3",
)
```

#### Audio Format

- **Input**: WAV format from AudioRecorder
- **Sent**: Raw PCM (skip 44-byte WAV header)
- **Sample Rate**: 16000 Hz (default)
- **Channels**: 1 (mono)
- **Chunk Duration**: 0.1s (100ms for low latency)
- **Max Chunk Size**: 25 KB (API limit)

#### Configuration

- **Credentials Path**: Path to service account JSON file
- **Project ID**: GCP project (auto-detected if empty)
- **Language Code**: e.g., "en-US", "es-ES", "fr-FR"
- **Model**: chirp_3, latest_long, latest_short, etc.
- **Sample Rate**: Audio sampling rate (default: 16000 Hz)
- **Channels**: Audio channels (default: 1)
- **VAD**: Enable/disable voice activity detection
- **VAD Threshold**: RMS threshold (default: 500.0)

#### Requirements

- Google Cloud account with Speech-to-Text API enabled
- Service account credentials JSON file
- `google-cloud-speech` Python library
- AudioRecorder (parec or PyAudio) for audio recording

### 4. OpenAI Realtime API

The OpenAI Realtime API integration is implemented in the `elograf/engines/openai/` package and uses a WebSocket-based communication model for real-time voice transcription.

#### Architecture

The OpenAI Realtime API uses two distinct model concepts:

1. **Session model**: Defines the general behavior of the WebSocket connection
   - Available models: `gpt-4o-realtime-preview`, `gpt-4o-mini-realtime-preview`
   - Specified in the WebSocket connection URL
   - Controls the overall conversation engine

2. **Transcription model**: Defines the specific engine for transcribing audio to text
   - Available models: `whisper-1`, `gpt-4o-transcribe`, `gpt-4o-mini-transcribe`
   - Specified in the `input_audio_transcription` configuration
   - Independent of the session model

#### Session Configuration

The initial session configuration is sent via a `session.update` event:

```python
{
    "type": "session.update",
    "session": {
        "input_audio_format": "pcm16",  # Format: PCM 16-bit
        "input_audio_transcription": {
            "model": "gpt-4o-transcribe"  # Transcription model
        },
        "turn_detection": {
            "type": "server_vad",
            "threshold": 0.5,
            "prefix_padding_ms": 300,
            "silence_duration_ms": 200,
            "create_response": False  # Only transcribe, don't generate responses
        }
    }
}
```

#### Voice Activity Detection (VAD)

The server implements automatic VAD (Voice Activity Detection) which:
- Detects when the user starts and stops speaking
- Segments audio into logical fragments
- Eliminates the need for manual buffer commits
- Configurable parameters:
  - `threshold`: Energy threshold for detecting speech (0.0-1.0)
  - `prefix_padding_ms`: Milliseconds of prior audio to include
  - `silence_duration_ms`: Silence duration to consider end of phrase

#### Audio Data Flow

1. **Capture**: Audio captured via AudioRecorder (using parec backend on Linux)
   - Format: PCM 16-bit, 16kHz, mono
   - Chunks of 200ms (6400 bytes)
   - Dedicated thread continuously reads from audio recorder

2. **Send**: Each chunk is sent as an `input_audio_buffer.append` event:
```python
{
    "type": "input_audio_buffer.append",
    "audio": base64_encoded_audio
}
```

3. **Speech detection**: The server VAD sends notifications:
   - `input_audio_buffer.speech_started`: Detected speech start
     - Includes `audio_start_ms`: Start timestamp
     - Includes `item_id`: Conversation item ID
   - `input_audio_buffer.speech_stopped`: Detected speech end
     - Includes `audio_end_ms`: End timestamp
   - `input_audio_buffer.committed`: Buffer confirmed for processing
   - `conversation.item.created`: Conversation item created

4. **Transcription**: The server processes audio and sends:
   - `conversation.item.input_audio_transcription.delta`: Transcription fragments
     - Multiple deltas are received as audio is processed
     - Each delta contains `item_id`, `content_index` and `delta` (the text)
     - Example: "Hello", " good", " morning", ",", " how", " are", " you", "?"
   - `conversation.item.input_audio_transcription.completed`: Final transcription
     - Contains the complete `transcript`: "Hello good morning, how are you?"
     - Includes `usage` with token counters

5. **Input simulation**: The transcribed text is written to the system
   - Uses `dotool` (preferred) or `xdotool` (fallback)
   - Text is written where the cursor is active

#### Main Events

| Event | Direction | Purpose |
|-------|-----------|---------|
| `session.created` | Server → Client | Session created with default configuration |
| `session.update` | Client → Server | Configure session (transcription, VAD, etc.) |
| `session.updated` | Server → Client | Confirmation of updated configuration |
| `input_audio_buffer.append` | Client → Server | Send audio chunk |
| `input_audio_buffer.speech_started` | Server → Client | VAD detected speech start |
| `input_audio_buffer.speech_stopped` | Server → Client | VAD detected speech end |
| `input_audio_buffer.committed` | Server → Client | Audio buffer confirmed for processing |
| `conversation.item.created` | Server → Client | Conversation item created |
| `conversation.item.input_audio_transcription.delta` | Server → Client | Transcription fragment |
| `conversation.item.input_audio_transcription.completed` | Server → Client | Complete transcription with final text |
| `error` | Server → Client | Error notification |

#### Audio Parameters

- **Sample rate**: 16000 Hz (API requirement)
- **Channels**: 1 (mono)
- **Format**: PCM 16-bit
- **Minimum chunk size**: 100ms of audio
- **Encoding for sending**: Base64

#### Configuration in EloGraf

OpenAI Realtime parameters are configured in the "OpenAI" tab of the advanced configuration dialog:

- **API Key**: OpenAI authentication key
- **Model**: Session model selection (dropdown with regular and mini options)
- **Language**: Language code for transcription (e.g., "es", "en-US")
- **VAD Threshold**: Speech detection sensitivity
- **VAD Prefix Padding**: Prior context in milliseconds
- **VAD Silence Duration**: Silence duration for segmentation
- **Sample Rate**: Sampling rate (16000 Hz)
- **Channels**: Number of channels (1 = mono)

#### Implementation

The `OpenAIRealtimeController` inherits from `BaseSTTEngine` and implements:

1. **WebSocket connection**: Establishes connection to `wss://api.openai.com/v1/realtime`
2. **Audio thread**: Captures audio from PulseAudio in separate thread
3. **Reception thread**: Processes server events in separate thread
4. **Error handling**: Optional automatic reconnection
5. **Input simulation**: Sends transcribed text to the system via `ydotool` or `xdotool`

#### Complete Flow Example

A real example of transcribing "Hello good morning, how are you?":

1. Client sends audio chunks continuously (every 200ms)
2. Server detects speech: `input_audio_buffer.speech_started` (audio_start_ms: 308)
3. Client continues sending audio while user speaks
4. Server detects silence: `input_audio_buffer.speech_stopped` (audio_end_ms: 2368)
5. Server confirms: `input_audio_buffer.committed`
6. Server creates item: `conversation.item.created`
7. Server sends incremental transcription:
   - Delta: "Hello"
   - Delta: " good"
   - Delta: " morning"
   - Delta: ","
   - Delta: " how"
   - Delta: " are"
   - Delta: " you"
   - Delta: "?"
8. Server sends complete transcription: `conversation.item.input_audio_transcription.completed`
   - transcript: "Hello good morning, how are you?"
   - usage: 31 total tokens (21 input, 10 output)
9. Client writes the text to the system using `dotool`/`xdotool`

**Example duration**: ~2 seconds of audio, nearly instant processing

#### Approximate Costs

- **gpt-4o-realtime-preview**: ~$5-10 per hour of audio
- **gpt-4o-mini-realtime-preview**: ~$1-2 per hour of audio

Mini models are more economical but may have lower accuracy with accents or background noise.

### 5. AssemblyAI Realtime

The AssemblyAI integration is implemented in the `elograf/engines/assemblyai/` package and provides another cloud-hosted, low-latency streaming engine with optional live transcript formatting.

#### Architecture

AssemblyAI exposes a secured WebSocket endpoint that accepts PCM16 audio frames and returns interim/final transcripts. EloGraf wraps the session with two threads: one for the WebSocket client and one for continuous audio capture via AudioRecorder from `audio_recorder.py`.

- **Authentication**: Either request short-lived streaming tokens via REST or authenticate directly with the API key in the WebSocket headers.
- **Session lifecycle**: Controller transitions through `STARTING → CONNECTING → READY → RECORDING/TRANSCRIBING` states and handles suspend/resume semantics.
- **Backpressure handling**: The runner batches audio into ~200 ms chunks, base64-encodes the buffer, and sends `{"audio_data": "..."}` payloads while respecting server pacing.

#### Streaming Flow

1. **Token acquisition**: Optional REST call to `https://api.assemblyai.com/v2/realtime/token` to fetch a temporary streaming token.
2. **WebSocket handshake**: Connect to `wss://streaming.assemblyai.com/v3/ws` with sample rate, model, and language query parameters; authenticate via header or token.
3. **Audio loop**: Capture PCM16 audio (default 16 kHz mono), accumulate bytes until threshold, base64 encode, and send via WebSocket.
4. **Transcription events**: Listen for `message_type = "FinalTranscript"` and `"PartialTranscript"` events; emit text to listeners and type into the focused application.
5. **Heartbeat & keep-alive**: Periodically send `{"event": "ping"}` frames to keep the session active.

#### Configuration

- **API Key**: Required for token generation or direct auth
- **Model**: Defaults to `"default"`, other AssemblyAI streaming models supported
- **Language**: Optional BCP-47 code (e.g., `"en"`, `"es"`)
- **Sample Rate**: Defaults to 16000 Hz; must match capture settings
- **Channels**: Mono (1) recommended
- **Chunk Duration**: Controls audio buffer size before sending (default 0.2 s)

#### Failure Handling

- Captures REST/WebSocket errors and marks `fatal_error` for irrecoverable authentication/config issues.
- Emits descriptive messages via `emit_error()` so the tray icon and EngineManager can surface the failure and trigger fallbacks.

#### Requirements

- `websocket-client` Python package
- Internet connectivity
- Valid AssemblyAI API key with realtime access enabled
- AudioRecorder (parec or PyAudio) for audio recording

## Testing

The project uses pytest for testing. Tests are located in the `tests/` directory.

### Running Tests

Run all tests:
```bash
uv run python -m pytest
```

Run tests with verbose output:
```bash
uv run python -m pytest -v
```

Run tests for a specific engine:
```bash
uv run python -m pytest tests/engines/test_nerd.py -v
uv run python -m pytest tests/engines/test_gemini.py -v
```

Run tests with coverage:
```bash
uv run python -m pytest --cov=eloGraf --cov-report=html
```

### Test Structure

- `tests/engines/` - Engine-specific tests for each STT implementation
- `tests/test_*.py` - Core functionality tests (settings, audio, IPC, etc.)

Each engine test typically covers:
- State transitions
- Output parsing
- Process lifecycle management
- Error handling
- Configuration application
