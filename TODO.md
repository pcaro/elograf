# TODO - Future Improvements

This document tracks potential improvements and features to implement in Elograf.

## Features

### User Interface

- [x] Add visual feedback when dictation starts/stops (notification or toast)
- [x] Add status indicator showing current model in use
- [x] Add suspend/resume button/menu item in system tray
- [x] Show dictation state (active/suspended/stopped) in tray icon

### Functionality

- [x] Support for multiple STT engines (nerd-dictation, Whisper Docker, Google Cloud Speech, OpenAI Realtime)
- [x] Add suspend/resume functionality for dictation (implemented for all engines)
- [x] Voice Activity Detection (VAD) for Whisper Docker, Google Cloud Speech, and OpenAI Realtime
- [x] Auto-reconnect functionality for Whisper Docker
- [x] Configurable audio quality (sample rate, channels) for all cloud-based engines
- [ ] Implement dictation history/log
- [ ] Add voice commands for punctuation and formatting
- [x] Add number-to-digits conversion option (nerd-dictation --numbers-as-digits)
- [x] Configure timeout and idle time settings
- [ ] Add option to capitalize first character automatically
- [ ] Add output mode selection (keyboard simulation vs stdout)
- [x] Refresh STT engine after saving advanced settings so changes apply without restarting
- [x] Fix OpenAI Realtime session payload to include the selected model when connecting
- [ ] Restore tray direct-click toggle behaviour or update the DirectClick setting/tests accordingly
- [ ] Integrate faster-whisper + whisper-streaming as a realtime engine option

### STT Engine Research

- [ ] Investigate new STT engines from https://voicewriter.io/speech-recognition-leaderboard
  - Evaluate performance, accuracy, latency, and licensing
  - Consider implementing support for top-performing engines
  - Priority engines to investigate: Deepgram Nova-2, AssemblyAI, Rev.ai, Azure Speech

### Configuration

- [x] GUI for configuring global keyboard shortcuts (KDE only, via D-Bus)
- [x] GUI for configuring nerd-dictation text processing options (timeout, idle time, punctuate, etc.)
- [x] Configure number conversion settings (digits enabled, separator usage)
- [x] STT Engine selection (nerd-dictation, whisper-docker, google-cloud-speech, openai-realtime)
- [x] Whisper Docker configuration (model, language, port, chunk duration, VAD settings)
- [x] Google Cloud Speech configuration (credentials, project, language, model, VAD settings)
- [x] OpenAI Realtime configuration (API key, model, language, VAD settings)
- [x] PulseAudio device selection for audio input
- [ ] Configure punctuation and capitalization rules
- [ ] Import/export configuration profiles
- [ ] Auto-detect optimal model based on system resources
- [ ] Audio backend selection (parec, sox, pw-cat)
- [x] Input simulation tool configuration (xdotool/dotool with keyboard layout)

### Platform Support

- [ ] Test and improve Windows support
- [ ] Test and improve macOS support
- [ ] Add support for other Wayland compositors beyond KDE

### Performance

- [ ] Optimize model loading time
- [ ] Add caching for frequently used models
- [ ] Reduce memory footprint

### Documentation

- [x] Document all STT engines (nerd-dictation, Whisper Docker, Google Cloud Speech, OpenAI Realtime)
- [x] Document architecture with state machines and component interactions
- [x] Update installation instructions with dependency requirements for all engines
- [x] Document configuration options for each STT engine
- [ ] Add video tutorial
- [ ] Create FAQ section
- [ ] Add troubleshooting guide
- [ ] Translate documentation to more languages

## Technical Debt

- [x] Add unit tests for all STT engines (nerd-dictation, Whisper Docker, Google Cloud Speech, OpenAI Realtime)
- [x] Implement abstract base classes for STT engine architecture (STTController, STTProcessRunner)
- [x] Create factory pattern for STT engine instantiation
- [ ] Add integration tests
- [ ] Set up CI/CD pipeline
- [ ] Improve error handling and logging
- [ ] Code coverage analysis

To propose a new feature or report a bug, please open an issue on GitHub.
