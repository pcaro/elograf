# Project Description

EloGraf is a desktop utility written in Python that facilitates voice dictation on Linux by integrating with multiple speech recognition engines, including nerd-dictation, Whisper Docker, Google Cloud Speech, and OpenAI Realtime. The application offers a system tray, global shortcuts, and an advanced interface for configuring audio devices, pre/post commands, and engine-specific parameters for each STT engine.

## Main Capabilities
- Graphical launcher and CLI to start, stop, suspend, and resume dictation
- Model management and downloads from remote repositories
- Configuration persistence via QSettings and multilanguage support through Qt
- IPC integration (D-Bus/local sockets) to coordinate with other system components

## Technical Structure
The code is organized as a Python package with Qt interface (PyQt6), specific controllers for each voice engine, a `SystemTrayIcon` that coordinates the dictation flow, and a battery of unit/functional tests in `tests/`. Distribution is managed with `pyproject.toml` and `setup.cfg`.

### Abstract STT Interface

All engines implement a common interface defined in `stt_engine.py`:

**STTController (ABC)**:
- `add_state_listener()`: Register callback for state changes
- `add_output_listener()`: Register callback for transcriptions
- `add_exit_listener()`: Register callback for process exit
- `remove_exit_listener()`: Unregister exit callback (prevents race conditions)
- `start()`, `stop_requested()`, `suspend_requested()`, `resume_requested()`: Lifecycle control

**STTProcessRunner (ABC)**:
- `start()`, `stop()`, `suspend()`, `resume()`: Process management
- `poll()`: Event polling
- `is_running()`: Process status

#### Race Condition Prevention

The `remove_exit_listener()` method was added to resolve a race condition in engine refresh: when a new engine is created, the previous engine's process may terminate late and fire its exit handler, incorrectly incrementing the failure counter for the new engine. `EngineManager` now unregisters callbacks from the old controller before creating the new one, ensuring that old process events don't affect the new engine's state.

### Lifecycle Management with EngineManager

`engine_manager.py` manages creation, refresh, and failure recovery:
- **Safe creation**: Unregisters old listeners before creating new engine
- **Circuit breaker**: Switches to fallback engine after repeated failures
- **Retry with exponential backoff**: Automatic retries with incremental delay
- **Refresh timeout**: Safety timer for engine shutdown deadlocks

## Speech Recognition Engines

### OpenAI Realtime API

The OpenAI Realtime API integration is implemented in `openai_realtime_controller.py` and uses a WebSocket-based communication model for real-time voice transcription.

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

1. **Capture**: Audio captured from PulseAudio via `parec`
   - Format: PCM 16-bit, 16kHz, mono
   - Chunks of 200ms (6400 bytes)
   - Dedicated thread continuously reads from parec

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
