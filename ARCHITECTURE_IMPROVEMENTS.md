# Elograf Architecture Review & Improvement Recommendations

**Date:** 2025-10-12
**Reviewer:** Claude
**Scope:** Core architectural design, scalability, maintainability

---

## Executive Summary

Elograf implements a well-designed abstraction layer for multiple STT engines using the Controller/Runner pattern. The architecture is fundamentally sound but has accumulated technical debt as it scaled from a single-engine wrapper to supporting 5+ STT backends. This review identifies 6 high-to-medium priority architectural issues and provides concrete refactoring recommendations.

**Overall Assessment:** Medium-Low maintainability with clear improvement path

---

## Critical Architectural Problems


**Problem:** `SystemTrayIcon` class has grown to 842 lines and violates Single Responsibility Principle.

**Location:** `eloGraf/tray_icon.py:25-842`

**Responsibilities (8+):**

1. **UI Rendering**: Icon drawing, tooltip, menu management (lines 153-206)
2. **Settings Management**: Load, save, validation (lines 617-833)
3. **Engine Lifecycle**: Creation, refresh, retry logic (lines 264-398)
4. **IPC Handling**: Command routing (lines 482-503)
5. **Global Shortcuts**: Registration via D-Bus (lines 419-480)
6. **State Machine**: Coordination (lines 103-104, 310-354)
7. **Command Building**: nerd-dictation subprocess construction (lines 518-557)
8. **Configuration Dialog**: Massive UI population/extraction (lines 617-833)

**Impact:**
- **Untestable**: Cannot test UI without entire application
- **Fragile**: Changes to one feature risk breaking others
- **Poor cohesion**: Settings code is 200+ lines in a UI class
- **High coupling**: Knows intimate details of all 5 engines

**Evidence of Over-Complexity:**

```python
def _build_engine_kwargs(self, engine_type: str) -> Dict[str, Any]:
    # 54 lines of if/elif for each engine's configuration
    # Should be: engine.get_config() or config_manager.get_engine_config(type)
```

```python
def show_config_dialog(self) -> None:
    # 217 lines of setting/getting form values
    # Should be: config_dialog.show(self.settings) / config_dialog.get_values()
```

**Recommendation:**

**Refactor into 5 Focused Classes:**

```python
# eloGraf/engine_manager.py
class EngineManager:
    """Manages STT engine lifecycle and configuration."""

    def __init__(self, settings: Settings):
        self._settings = settings
        self._controller: Optional[STTController] = None
        self._runner: Optional[STTProcessRunner] = None
        self._failure_count = 0

    def create_engine(self) -> Tuple[STTController, STTProcessRunner]:
        """Create engine based on current settings."""
        engine_type = self._settings.sttEngine
        kwargs = self._build_engine_kwargs(engine_type)
        return create_stt_engine(engine_type, **kwargs)

    def refresh_engine(self, stop_callback: Callable) -> None:
        """Refresh engine with new settings."""
        # Current _refresh_stt_engine logic

    def _build_engine_kwargs(self, engine_type: str) -> Dict[str, Any]:
        # Moved from SystemTrayIcon


# eloGraf/configuration_manager.py
class ConfigurationManager:
    """Handles settings persistence and dialog coordination."""

    def __init__(self, settings: Settings):
        self._settings = settings

    def show_config_dialog(self, parent: QWidget) -> bool:
        """Show configuration dialog and save if accepted."""
        dialog = AdvancedUI()
        self._populate_dialog(dialog)

        if dialog.exec():
            self._extract_dialog_values(dialog)
            self._settings.save()
            return True
        return False

    def _populate_dialog(self, dialog: AdvancedUI) -> None:
        # Current lines 617-695

    def _extract_dialog_values(self, dialog: AdvancedUI) -> None:
        # Current lines 697-815


# eloGraf/ipc_command_handler.py
class IPCCommandHandler:
    """Routes IPC commands to appropriate actions."""

    def __init__(self, action_map: Dict[str, Callable]):
        self._actions = action_map

    def handle_command(self, command: str) -> None:
        """Handle command from IPC."""
        if command in self._actions:
            self._actions[command]()
        else:
            logging.warning(f"Unknown IPC command: {command}")


# eloGraf/tray_icon_ui.py
class TrayIconUI:
    """Handles system tray icon rendering and menu."""

    def __init__(self, parent: QWidget):
        self._icon = QSystemTrayIcon(parent)
        self._current_state = None
        self._cached_icons = {}

    def update_for_state(self, icon_state: IconState) -> None:
        """Update icon based on state."""
        # Current _apply_state icon logic

    def update_tooltip(self, engine_info: EngineInfo) -> None:
        """Update tooltip with engine details."""
        # Current _update_tooltip logic


# eloGraf/tray_icon.py (refactored)
class SystemTrayIcon(QSystemTrayIcon):
    """Orchestrates tray icon functionality."""

    def __init__(self, icon: QIcon, start: bool, ipc: IPCManager,
                 parent=None, temporary_engine: str = None):
        super().__init__(icon, parent)

        self.settings = Settings()
        self.settings.load()

        # Delegate responsibilities
        self._ui = TrayIconUI(parent)
        self._engine_manager = EngineManager(self.settings)
        self._config_manager = ConfigurationManager(self.settings)
        self._ipc_handler = IPCCommandHandler({
            "begin": self.begin,
            "end": self.end,
            "suspend": self.suspend,
            "resume": self.resume,
            "toggle": self.controller_toggle,
            "exit": self.exit,
        })

        # Setup
        self._setup_menu()
        self._setup_engine()
        self._setup_ipc(ipc)

    def config(self) -> None:
        if self._config_manager.show_config_dialog(self.parent()):
            self._engine_manager.refresh_engine(self.stop_dictate)
```

**Benefits:**
- **Testable**: Each class can be tested independently
- **Maintainable**: Clear responsibility boundaries
- **Extensible**: Easy to modify one aspect without affecting others
- **Readable**: ~150 lines per class vs 842 lines monolith

**Migration Path:**
1. Extract `EngineManager` first (lowest risk)
2. Extract `ConfigurationManager` second
3. Extract `IPCCommandHandler` and `TrayIconUI`
4. Update `SystemTrayIcon` to delegate
5. Run tests after each extraction

---

### 4. No Error Recovery Strategy ⚠️ **MEDIUM PRIORITY**

**Problem:** Primitive retry-and-crash approach to engine failures.

**Current Behavior** (`tray_icon.py:358-398`):
```python
def _handle_dictation_exit(self, return_code: int) -> None:
    if failure:
        self._engine_failure_count += 1
        if self._engine_failure_count >= self._max_engine_retries:
            # EXIT THE ENTIRE APPLICATION
            QTimer.singleShot(0, lambda: QCoreApplication.exit(1))
            return
```

**Issues:**
- **User hostile**: Wrong API key = application crashes after 5 failures
- **No distinction**: Transient network errors treated same as config errors
- **No fallback**: Can't degrade to local engine when cloud services fail
- **Lost state**: User must restart, reconfigure

**Recommendation:**

**Implement Failure Classification**

```python
class EngineFailureType(Enum):
    TRANSIENT_NETWORK = auto()      # Retry automatically
    API_AUTHENTICATION = auto()      # Don't retry, show config
    MISSING_DEPENDENCY = auto()      # Don't retry, show install help
    CONTAINER_FAILED = auto()        # Retry with exponential backoff
    UNKNOWN = auto()                 # Retry limited times

class EngineManager:
    def handle_failure(self, failure_type: EngineFailureType, error_message: str) -> None:
        if failure_type == EngineFailureType.API_AUTHENTICATION:
            # Show notification: "API key invalid, please reconfigure"
            self._show_error_notification(error_message)
            self._prompt_reconfiguration()

        elif failure_type == EngineFailureType.TRANSIENT_NETWORK:
            # Retry with backoff
            self._schedule_retry(exponential_backoff=True)

        elif failure_type == EngineFailureType.MISSING_DEPENDENCY:
            # Show helpful error
            self._show_dependency_help(error_message)
            # Offer to switch to available engine
            self._prompt_engine_fallback()

        else:
            # Unknown - retry limited times then ask user
            if self._retry_count < MAX_RETRIES:
                self._schedule_retry()
            else:
                self._prompt_user_action(error_message)
```

**Circuit Breaker Pattern** (for network-based engines):

```python
class CircuitBreaker:
    """Prevents repeated calls to failing service."""

    def __init__(self, failure_threshold: int = 3, timeout: int = 60):
        self._failures = 0
        self._last_failure_time = 0
        self._state = "closed"  # closed, open, half-open

    def call(self, func: Callable) -> Any:
        if self._state == "open":
            if time.time() - self._last_failure_time > self._timeout:
                self._state = "half-open"
            else:
                raise CircuitOpenError("Service unavailable")

        try:
            result = func()
            self._on_success()
            return result
        except Exception as e:
            self._on_failure()
            raise
```

**Fallback Chain:**
```python
class EngineManager:
    def _attempt_with_fallback(self) -> bool:
        """Try preferred engine, fall back to alternatives."""

        engines_to_try = [
            self._settings.sttEngine,           # User preference
            "nerd-dictation",                    # Local fallback
            "whisper-docker",                    # Docker fallback
        ]

        for engine in engines_to_try:
            if is_engine_available(engine):
                try:
                    self.create_engine(engine)
                    return True
                except Exception:
                    continue

        # All failed
        self._show_critical_error()
        return False
```

---


**Problem:** String-based settings with no schema validation or type safety.

**Current State** (`settings.py:1-363`):

**Three different access patterns:**
```python
# Pattern 1: Property access
self.settings.whisperModel

# Pattern 2: String key access
self.settings.getValue("whisperPort", 9000)

# Pattern 3: getattr with fallback (AssemblyAI)
getattr(self.settings, "assemblyApiKey", "")
```

**Issues:**
1. **No type safety**: Can assign wrong types
2. **Typo-prone**: `self.settings.whisprModel` fails silently
3. **No validation**: Can set port to negative number
4. **No migration**: Schema changes break existing configs
5. **No documentation**: Must read code to find settings

**Evidence of Fragility:**

```python
# AssemblyAI uses getattr because settings might not exist
if hasattr(adv_window.ui, "assembly_api_key_le"):
    self.settings.assemblyApiKey = adv_window.ui.assembly_api_key_le.text()
```

This suggests AssemblyAI was retrofitted and settings schema is inconsistent.

**Recommendation:**

**Option A: Dataclass-Based Settings**

```python
from dataclasses import dataclass, field
from typing import Optional

@dataclass
class EngineSettings:
    """Base settings for all engines."""
    engine_type: str
    device_name: str = "default"

@dataclass
class NerdDictationSettings(EngineSettings):
    engine_type: str = "nerd-dictation"
    sample_rate: int = 44100
    timeout: int = 0
    idle_time: int = 100

    def __post_init__(self):
        if self.sample_rate < 8000:
            raise ValueError("Sample rate must be >= 8000")

@dataclass
class WhisperSettings(EngineSettings):
    engine_type: str = "whisper-docker"
    model: str = "base"
    port: int = 9000
    chunk_duration: float = 5.0
    sample_rate: int = 16000
    channels: int = 1
    vad_enabled: bool = True
    vad_threshold: float = 500.0
    auto_reconnect: bool = True
    language: Optional[str] = None

    def __post_init__(self):
        if not 1 <= self.port <= 65535:
            raise ValueError(f"Invalid port: {self.port}")
        if self.chunk_duration <= 0:
            raise ValueError("Chunk duration must be positive")

class Settings:
    """Type-safe settings manager."""

    def __init__(self):
        self._qsettings = QSettings("Elograf", "Elograf")
        self._engine_configs: Dict[str, EngineSettings] = {}

    def get_engine_settings(self, engine_type: str) -> EngineSettings:
        """Get type-safe settings for engine."""
        if engine_type not in self._engine_configs:
            self._engine_configs[engine_type] = self._load_engine_settings(engine_type)
        return self._engine_configs[engine_type]

    def _load_engine_settings(self, engine_type: str) -> EngineSettings:
        """Load and validate engine settings."""
        if engine_type == "whisper-docker":
            return WhisperSettings(
                device_name=self._qsettings.value("deviceName", "default"),
                model=self._qsettings.value("whisperModel", "base"),
                port=int(self._qsettings.value("whisperPort", 9000)),
                # ... etc
            )
        # ... other engines
```

**Benefits:**
- **Type safety**: IDE autocomplete, type checking
- **Validation**: `__post_init__` validates on creation
- **Documentation**: Dataclass fields are self-documenting
- **Serialization**: Easy to save/load
- **Testability**: Can create mock settings easily

**Option B: Pydantic Models** (if adding dependency is acceptable)

```python
from pydantic import BaseModel, Field, validator

class WhisperSettings(BaseModel):
    """Whisper Docker engine settings with validation."""

    model: str = Field("base", description="Whisper model size")
    port: int = Field(9000, ge=1, le=65535, description="API port")
    chunk_duration: float = Field(5.0, gt=0, description="Audio chunk size")
    sample_rate: int = Field(16000, ge=8000, description="Sample rate in Hz")

    @validator('model')
    def validate_model(cls, v):
        valid_models = ['tiny', 'base', 'small', 'medium', 'large-v3']
        if v not in valid_models:
            raise ValueError(f"Model must be one of {valid_models}")
        return v

    class Config:
        # Auto-generate JSON schema for UI
        schema_extra = {
            "example": {
                "model": "base",
                "port": 9000,
                "chunk_duration": 5.0
            }
        }
```

**Migration Path:**
1. Create parallel settings system with validation
2. Add migration function to convert old QSettings to new format
3. Update one engine at a time to use new system
4. Deprecate old string-based access
5. Add version tracking for future schema changes

---


**Problem:** Identical `_default_input_simulator()` duplicated in 4 files.

**Evidence:**

Appears in:
- `whisper_docker_controller.py:448-459`
- `openai_realtime_controller.py` (similar)
- `google_cloud_speech_controller.py` (similar)
- `assemblyai_realtime_controller.py:427-437`

All identical:
```python
@staticmethod
def _default_input_simulator(text: str) -> None:
    try:
        run(["dotool", "type", text], check=True)
    except (CalledProcessError, FileNotFoundError):
        try:
            run(["xdotool", "type", "--", text], check=True)
        except (CalledProcessError, FileNotFoundError):
            logging.warning("Neither dotool nor xdotool available")
```

**Recommendation:**

Create `eloGraf/input_simulator.py`:

```python
from subprocess import run, CalledProcessError
from typing import Optional
import logging
import shutil

class InputSimulator:
    """Simulates keyboard input using available tools."""

    def __init__(self, preferred_tool: Optional[str] = None):
        """
        Args:
            preferred_tool: 'dotool', 'xdotool', or None for auto-detect
        """
        self._tool = preferred_tool or self._detect_tool()
        if not self._tool:
            raise RuntimeError("No input simulation tool available")

    @staticmethod
    def _detect_tool() -> Optional[str]:
        """Detect available input tool."""
        if shutil.which("dotool"):
            return "dotool"
        if shutil.which("xdotool"):
            return "xdotool"
        return None

    def type_text(self, text: str) -> None:
        """Type text using configured tool."""
        if self._tool == "dotool":
            run(["dotool", "type", text], check=True)
        elif self._tool == "xdotool":
            run(["xdotool", "type", "--", text], check=True)
        else:
            raise RuntimeError("No input tool configured")

# Global singleton
_simulator: Optional[InputSimulator] = None

def get_input_simulator() -> InputSimulator:
    """Get or create input simulator singleton."""
    global _simulator
    if _simulator is None:
        _simulator = InputSimulator()
    return _simulator

def type_text(text: str) -> None:
    """Convenience function to type text."""
    get_input_simulator().type_text(text)
```

Then engines use:
```python
from eloGraf.input_simulator import type_text

self._input_simulator = input_simulator or type_text
```

---



## Scalability Concerns

```python
# eloGraf/engine_plugin.py
class EnginePlugin(ABC):
    """Plugin interface for STT engines."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Engine name (e.g., 'whisper-docker')."""
        pass

    @property
    @abstractmethod
    def display_name(self) -> str:
        """Human-readable name for UI."""
        pass

    @abstractmethod
    def get_settings_schema(self) -> Type[EngineSettings]:
        """Get settings dataclass for this engine."""
        pass

    @abstractmethod
    def create_controller_runner(
        self, settings: EngineSettings
    ) -> Tuple[STTController, STTProcessRunner]:
        """Create engine components."""
        pass

    @abstractmethod
    def get_config_widget(self, settings: EngineSettings) -> QWidget:
        """Get configuration UI widget."""
        pass

    @abstractmethod
    def check_availability(self) -> Tuple[bool, str]:
        """
        Check if engine can run.

        Returns:
            (available, reason) - reason is error message if unavailable
        """
        pass

# Usage:
class WhisperPlugin(EnginePlugin):
    name = "whisper-docker"
    display_name = "Whisper Docker"

    def get_settings_schema(self):
        return WhisperSettings

    def create_controller_runner(self, settings):
        controller = WhisperDockerController()
        runner = WhisperDockerProcessRunner(controller, **settings.dict())
        return controller, runner

# Register plugins
PLUGINS = {
    "whisper-docker": WhisperPlugin(),
    "google-cloud-speech": GoogleCloudPlugin(),
    # ...
}
```

**Benefits:**
- New engine = single file implementing interface
- Configuration UI auto-generated from settings schema
- Factory becomes simple lookup: `PLUGINS[name].create()`
- Can load engines from external packages

---

## Testing Gaps

### Current Coverage

**Good:**
- ✅ Unit tests for controllers (`test_nerd_controller.py`, etc.)
- ✅ State machine tests (`test_state_machine.py`)
- ✅ CLI tests (`test_cli.py`)

**Missing:**
- ❌ Integration tests (end-to-end engine workflows)
- ❌ `SystemTrayIcon` tests (842 lines, 0% coverage!)
- ❌ Settings persistence tests
- ❌ Configuration dialog tests
- ❌ IPC command routing tests
- ❌ Engine failure/retry logic tests

### Recommended Test Suite

```python
# tests/test_engine_manager.py
def test_engine_creation_with_valid_settings():
    """Verify engine creation with valid config."""

def test_engine_refresh_stops_running_engine():
    """Verify refresh stops current engine before creating new one."""

def test_engine_failure_increments_counter():
    """Verify failure tracking."""

# tests/test_integration.py
def test_full_dictation_workflow():
    """Start engine, record, transcribe, simulate input, stop."""

def test_engine_switching():
    """Switch from one engine to another while running."""

def test_suspend_resume_cycle():
    """Suspend engine, verify no recording, resume, verify recording."""

# tests/test_settings_persistence.py
def test_save_and_load_settings():
    """Verify settings round-trip correctly."""

def test_settings_migration_from_old_version():
    """Verify old config files are migrated."""

def test_invalid_settings_rejected():
    """Verify validation catches bad values."""
```


---

## Specific Technical Issues

### 1. Race Condition in Engine Refresh
**Location:** `tray_icon.py:277-308`

```python
def _refresh_stt_engine(self) -> None:
    if runner and runner.is_running():
        logging.info("STT engine running; stopping before applying new settings")
        self.stop_dictate()
        self._pending_engine_refresh = True
        return  # Will be called again after exit handler
```

**Problem:** If `stop_dictate()` fails or engine hangs, `_pending_engine_refresh` stays `True` forever, blocking all future refreshes.

**Solution:**
```python
def _refresh_stt_engine(self) -> None:
    if runner and runner.is_running():
        self._pending_engine_refresh = True

        # Set timeout for stop operation
        stop_timeout = QTimer()
        stop_timeout.setSingleShot(True)
        stop_timeout.timeout.connect(self._force_refresh)
        stop_timeout.start(5000)  # 5 second timeout

        self.stop_dictate()
        return

    # ... continue with refresh

def _force_refresh(self) -> None:
    """Force refresh if stop takes too long."""
    if self._pending_engine_refresh:
        logging.warning("Engine stop timed out, forcing refresh")
        self._pending_engine_refresh = False
        # Kill runner forcefully
        if hasattr(self._runner, '_stop_recording'):
            self._runner._stop_recording.set()
        # Continue with refresh
        self._refresh_stt_engine()
```

### 2. Fragile State Detection
**Location:** `nerd_controller.py:72-87`

```python
def handle_output(self, line: str) -> None:
    lower = line.lower()
    if "loading model" in lower:
        self._set_state(NerdDictationState.LOADING)
    elif any(token in lower for token in ("model loaded", "listening", "ready")):
        self._set_state(NerdDictationState.READY)
```

**Problem:** String parsing is brittle. If nerd-dictation changes output format, state detection silently breaks.

**Solution:** Add structured output mode to nerd-dictation or use exit codes for state.

### 3. Hardcoded Business Logic in UI Layer
**Location:** `tray_icon.py:233-239`

```python
model = self.settings.openaiModel or "gpt-4o-realtime-preview"
if model != "gpt-4o-realtime-preview":
    logging.warning("OpenAI Realtime requires gpt-4o-realtime-preview; overriding")
    model = "gpt-4o-realtime-preview"
```

**Problem:** Model validation should be in `OpenAIRealtimeProcessRunner.__init__()`, not in UI code.

**Solution:**
```python
# In openai_realtime_controller.py
class OpenAIRealtimeProcessRunner:
    def __init__(self, controller, *, model: str, **kwargs):
        if model != "gpt-4o-realtime-preview":
            logging.warning(f"Invalid model {model}, using gpt-4o-realtime-preview")
            model = "gpt-4o-realtime-preview"
        self._model = model
```

### 4. Unreachable Code
**Location:** `whisper_docker_controller.py:316-318`

```python
if health.status_code == 200:
    logging.info("Whisper API is ready")
    return True
elif health.status_code in (404, 405, 501):
    return True
    logging.debug("Health endpoint not ready yet: %s", health.status_code)  # UNREACHABLE!
```

**Fix:**
```python
elif health.status_code in (404, 405, 501):
    logging.debug("Health endpoint returned %s, assuming ready", health.status_code)
    return True
```

### 5. Missing Error Context
Errors are logged but not always propagated with context:

```python
except Exception as exc:
    logging.error(f"Recording loop error: {exc}")
    self._controller.handle_exit(1)
```

Should include traceback:
```python
except Exception as exc:
    logging.exception(f"Recording loop error: {exc}")  # Includes stack trace
    self._controller.handle_exit(1)
```

---

## Priority Recommendations
tests/test_stt_interface_refactoring.py
### Immediate (Do This Week)


2. **Extract EngineManager from SystemTrayIcon** (4-6 hours)
   - Move engine creation/lifecycle logic
   - Reduces tray_icon.py by ~200 lines
   - Enables testing of engine logic

### Short-term (Do This Month)

3. **Refactor SystemTrayIcon** (1-2 days)
   - Extract ConfigurationManager
   - Extract IPCCommandHandler
   - Extract TrayIconUI
   - Makes codebase significantly more maintainable

4. **Fix STTController interface inconsistency** (1 day)
   - Design unified state transition interface
   - Update all 5 engines
   - Document migration guide

### Medium-term (Do This Quarter)

5. **Implement type-safe settings** (2-3 days)
   - Create dataclass-based settings
   - Add validation
   - Migrate existing settings
   - Add version tracking

6. **Add integration test suite** (2-3 days)
   - Full engine workflows
   - Configuration persistence
   - Error recovery paths

### Long-term (Future)

7. **Design plugin architecture** (1 week)
   - Define plugin interface
   - Refactor existing engines
   - Document plugin creation
   - Enable community engines

8. **Implement circuit breaker pattern** (2-3 days)
   - Classify failure types
   - Add fallback chains
   - Improve error messaging

---

## Conclusion

Elograf has evolved from a single-engine wrapper to a multi-engine STT platform. The core abstractions are sound, but the architecture needs refactoring to match its current scope. The highest-value improvements are:

1. Breaking up the 842-line SystemTrayIcon God object
2. Unifying the STTController interface
3. Consolidating audio recording logic
4. Implementing type-safe settings

These changes will:
- **Improve testability** (isolated components)
- **Reduce bugs** (type safety, validation)
- **Accelerate development** (clear boundaries)
- **Enable scaling** (plugin architecture)

The codebase is well-documented and shows good engineering discipline. With focused refactoring, it can become highly maintainable while preserving all existing functionality.

---

**Next Steps:** Begin with EngineManager extraction from SystemTrayIcon as proof-of-concept for the larger refactoring.
