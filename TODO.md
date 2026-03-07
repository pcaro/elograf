# TODO - Future Improvements

This document tracks potential improvements and features to implement in Elograf.

## Features

### Functionality

- [ ] Add voice commands for punctuation and formatting
- [ ] Add option to capitalize first character automatically
- [x] Refresh STT engine after saving advanced settings so changes apply without restarting
- [ ] Integrate faster-whisper + whisper-streaming as a realtime engine option

### STT Engine Research

- [ ] Investigate new STT engines from https://voicewriter.io/speech-recognition-leaderboard
  - Evaluate performance, accuracy, latency, and licensing
  - Consider implementing support for top-performing engines
  - Priority engines to investigate: Deepgram Nova-2, AssemblyAI, Rev.ai, Azure Speech

### Configuration

- [ ] Configure punctuation and capitalization rules
- [ ] Import/export configuration profiles
- [ ] Auto-detect optimal model based on system resources
- [ ] Audio backend selection (parec, sox, pw-cat)

### Platform Support

- [ ] Test and improve Windows support
- [ ] Test and improve macOS support
- [ ] Add support for other Wayland compositors beyond KDE


### Documentation

- [ ] Add video tutorial
- [ ] Create FAQ section
- [ ] Add troubleshooting guide
- [ ] Translate documentation to more languages

## Technical Debt

- [ ] Add integration tests
- [ ] Set up CI/CD pipeline
- [ ] Improve error handling and logging
- [ ] Code coverage analysis

