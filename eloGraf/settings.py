from __future__ import annotations

import logging
from typing import Dict, List, Optional

from PyQt6.QtCore import QSettings

DEFAULT_RATE: int = 44100


class Settings:
    """Wrapper around QSettings storing Elograf preferences and models."""

    def __init__(self, backend: Optional[QSettings] = None) -> None:
        self._backend = backend or QSettings("Elograf", "Elograf")
        self.models: List[Dict[str, str]] = []
        self.precommand: str = ""
        self.postcommand: str = ""
        self.sampleRate: int = DEFAULT_RATE
        self.timeout: int = 0
        self.idleTime: int = 100
        self.punctuate: int = 0
        self.fullSentence: bool = False
        self.digits: bool = False
        self.useSeparator: bool = False
        self.freeCommand: str = ""
        self.tool: str = ""
        self.env: str = ""
        self.deviceName: str = "default"
        self.directClick: bool = True
        self.keyboard: str = ""
        self.beginShortcut: str = ""
        self.endShortcut: str = ""
        self.suspendShortcut: str = ""
        self.resumeShortcut: str = ""
        self.toggleShortcut: str = ""
        self.sttEngine: str = "nerd-dictation"
        self.whisperModel: str = "base"
        self.whisperLanguage: str = ""
        self.whisperPort: int = 9000
        self.whisperChunkDuration: float = 5.0
        self.whisperSampleRate: int = 16000
        self.whisperChannels: int = 1
        self.whisperVadEnabled: bool = True
        self.whisperVadThreshold: float = 500.0
        self.whisperAutoReconnect: bool = True
        self.googleCloudCredentialsPath: str = ""
        self.googleCloudProjectId: str = ""
        self.googleCloudLanguageCode: str = "en-US"
        self.googleCloudModel: str = "chirp_3"
        self.googleCloudSampleRate: int = 16000
        self.googleCloudChannels: int = 1
        self.googleCloudVadEnabled: bool = True
        self.googleCloudVadThreshold: float = 500.0
        self.openaiApiKey: str = ""
        self.openaiModel: str = "gpt-4o-transcribe"
        self.openaiApiVersion: str = "2025-08-28"
        self.openaiSampleRate: int = 16000
        self.openaiChannels: int = 1
        self.openaiVadEnabled: bool = True
        self.openaiVadThreshold: float = 0.5
        self.openaiVadPrefixPaddingMs: int = 300
        self.openaiVadSilenceDurationMs: int = 200
        self.openaiLanguage: str = "en-US"

    def load(self) -> None:
        backend = self._backend
        self.precommand = backend.value("Precommand", "", type=str)
        self.postcommand = backend.value("Postcommand", "", type=str)
        self.sampleRate = backend.value("SampleRate", DEFAULT_RATE, type=int)
        self.timeout = backend.value("Timeout", 0, type=int)
        self.idleTime = backend.value("IdleTime", 100, type=int)
        self.punctuate = backend.value("Punctuate", 0, type=int)
        self.fullSentence = backend.value("FullSentence", False, type=bool)
        self.digits = backend.value("Digits", False, type=bool)
        self.useSeparator = backend.value("UseSeparator", False, type=bool)
        self.freeCommand = backend.value("FreeCommand", "", type=str)
        self.tool = backend.value("Tool", "", type=str)
        self.env = backend.value("Env", "", type=str)
        self.deviceName = backend.value("DeviceName", "default", type=str)
        self.directClick = backend.value("DirectClick", True, type=bool)
        self.keyboard = backend.value("Keyboard", "", type=str)
        self.beginShortcut = backend.value("BeginShortcut", "", type=str)
        self.endShortcut = backend.value("EndShortcut", "", type=str)
        self.suspendShortcut = backend.value("SuspendShortcut", "", type=str)
        self.resumeShortcut = backend.value("ResumeShortcut", "", type=str)
        self.toggleShortcut = backend.value("ToggleShortcut", "", type=str)
        self.sttEngine = backend.value("STTEngine", "nerd-dictation", type=str)
        self.whisperModel = backend.value("WhisperModel", "base", type=str)
        self.whisperLanguage = backend.value("WhisperLanguage", "", type=str)
        self.whisperPort = backend.value("WhisperPort", 9000, type=int)
        self.whisperChunkDuration = backend.value("WhisperChunkDuration", 5.0, type=float)
        self.whisperSampleRate = backend.value("WhisperSampleRate", 16000, type=int)
        self.whisperChannels = backend.value("WhisperChannels", 1, type=int)
        self.whisperVadEnabled = backend.value("WhisperVadEnabled", True, type=bool)
        self.whisperVadThreshold = backend.value("WhisperVadThreshold", 500.0, type=float)
        self.whisperAutoReconnect = backend.value("WhisperAutoReconnect", True, type=bool)
        self.googleCloudCredentialsPath = backend.value("GoogleCloudCredentialsPath", "", type=str)
        self.googleCloudProjectId = backend.value("GoogleCloudProjectId", "", type=str)
        self.googleCloudLanguageCode = backend.value("GoogleCloudLanguageCode", "en-US", type=str)
        self.googleCloudModel = backend.value("GoogleCloudModel", "chirp_3", type=str)
        self.googleCloudSampleRate = backend.value("GoogleCloudSampleRate", 16000, type=int)
        self.googleCloudChannels = backend.value("GoogleCloudChannels", 1, type=int)
        self.googleCloudVadEnabled = backend.value("GoogleCloudVadEnabled", True, type=bool)
        self.googleCloudVadThreshold = backend.value("GoogleCloudVadThreshold", 500.0, type=float)
        self.openaiApiKey = backend.value("OpenaiApiKey", "", type=str)
        self.openaiModel = backend.value("OpenaiModel", "gpt-4o-realtime-preview", type=str)
        if self.openaiModel in {"gpt-4o-transcribe", "gpt-4o-mini-transcribe"}:
            logging.info(
                "Migrating OpenAI model %s to gpt-4o-realtime-preview for realtime mode",
                self.openaiModel,
            )
            self.openaiModel = "gpt-4o-realtime-preview"
            backend.setValue("OpenaiModel", self.openaiModel)
        self.openaiApiVersion = backend.value("OpenaiApiVersion", "2025-08-28", type=str)
        self.openaiSampleRate = backend.value("OpenaiSampleRate", 16000, type=int)
        self.openaiChannels = backend.value("OpenaiChannels", 1, type=int)
        self.openaiVadEnabled = backend.value("OpenaiVadEnabled", True, type=bool)
        self.openaiVadThreshold = backend.value("OpenaiVadThreshold", 0.5, type=float)
        self.openaiVadPrefixPaddingMs = backend.value("OpenaiVadPrefixPaddingMs", 300, type=int)
        self.openaiVadSilenceDurationMs = backend.value("OpenaiVadSilenceDurationMs", 200, type=int)
        self.openaiLanguage = backend.value("OpenaiLanguage", "en-US", type=str)

        self.models = []
        count = backend.beginReadArray("Models")
        for index in range(count):
            backend.setArrayIndex(index)
            entry = {
                "name": backend.value("name", ""),
                "language": backend.value("language", ""),
                "size": backend.value("size", ""),
                "type": backend.value("type", ""),
                "version": backend.value("version", ""),
                "location": backend.value("location", ""),
            }
            self.models.append(entry)
        backend.endArray()

    def save(self) -> None:
        backend = self._backend
        self._set_or_remove("Precommand", self.precommand)
        self._set_or_remove("Postcommand", self.postcommand)
        if self.timeout == 0:
            backend.remove("Timeout")
        else:
            backend.setValue("Timeout", self.timeout)
        if self.sampleRate == DEFAULT_RATE:
            backend.remove("SampleRate")
        else:
            backend.setValue("SampleRate", self.sampleRate)
        if self.idleTime == 100:
            backend.remove("IdleTime")
        else:
            backend.setValue("IdleTime", self.idleTime)
        if self.punctuate == 0:
            backend.remove("Punctuate")
        else:
            backend.setValue("Punctuate", self.punctuate)

        backend.setValue("FullSentence", int(self.fullSentence))
        backend.setValue("Digits", int(self.digits))
        backend.setValue("UseSeparator", int(self.useSeparator))
        backend.setValue("DirectClick", int(self.directClick))
        backend.setValue("Tool", self.tool)
        self._set_or_remove("FreeCommand", self.freeCommand)
        self._set_or_remove("Env", self.env)
        self._set_or_remove("Keyboard", self.keyboard)
        self._set_or_remove("BeginShortcut", self.beginShortcut)
        self._set_or_remove("EndShortcut", self.endShortcut)
        self._set_or_remove("SuspendShortcut", self.suspendShortcut)
        self._set_or_remove("ResumeShortcut", self.resumeShortcut)
        self._set_or_remove("ToggleShortcut", self.toggleShortcut)
        backend.setValue("STTEngine", self.sttEngine)
        backend.setValue("WhisperModel", self.whisperModel)
        self._set_or_remove("WhisperLanguage", self.whisperLanguage)
        if self.whisperPort == 9000:
            backend.remove("WhisperPort")
        else:
            backend.setValue("WhisperPort", self.whisperPort)
        if self.whisperChunkDuration == 5.0:
            backend.remove("WhisperChunkDuration")
        else:
            backend.setValue("WhisperChunkDuration", self.whisperChunkDuration)
        if self.whisperSampleRate == 16000:
            backend.remove("WhisperSampleRate")
        else:
            backend.setValue("WhisperSampleRate", self.whisperSampleRate)
        if self.whisperChannels == 1:
            backend.remove("WhisperChannels")
        else:
            backend.setValue("WhisperChannels", self.whisperChannels)
        backend.setValue("WhisperVadEnabled", int(self.whisperVadEnabled))
        if self.whisperVadThreshold == 500.0:
            backend.remove("WhisperVadThreshold")
        else:
            backend.setValue("WhisperVadThreshold", self.whisperVadThreshold)
        backend.setValue("WhisperAutoReconnect", int(self.whisperAutoReconnect))
        self._set_or_remove("GoogleCloudCredentialsPath", self.googleCloudCredentialsPath)
        self._set_or_remove("GoogleCloudProjectId", self.googleCloudProjectId)
        if self.googleCloudLanguageCode == "en-US":
            backend.remove("GoogleCloudLanguageCode")
        else:
            backend.setValue("GoogleCloudLanguageCode", self.googleCloudLanguageCode)
        if self.googleCloudModel == "chirp_3":
            backend.remove("GoogleCloudModel")
        else:
            backend.setValue("GoogleCloudModel", self.googleCloudModel)
        if self.googleCloudSampleRate == 16000:
            backend.remove("GoogleCloudSampleRate")
        else:
            backend.setValue("GoogleCloudSampleRate", self.googleCloudSampleRate)
        if self.googleCloudChannels == 1:
            backend.remove("GoogleCloudChannels")
        else:
            backend.setValue("GoogleCloudChannels", self.googleCloudChannels)
        backend.setValue("GoogleCloudVadEnabled", int(self.googleCloudVadEnabled))
        if self.googleCloudVadThreshold == 500.0:
            backend.remove("GoogleCloudVadThreshold")
        else:
            backend.setValue("GoogleCloudVadThreshold", self.googleCloudVadThreshold)
        self._set_or_remove("OpenaiApiKey", self.openaiApiKey)
        if self.openaiModel == "gpt-4o-transcribe":
            backend.remove("OpenaiModel")
        else:
            backend.setValue("OpenaiModel", self.openaiModel)
        if self.openaiApiVersion == "2025-08-28":
            backend.remove("OpenaiApiVersion")
        else:
            backend.setValue("OpenaiApiVersion", self.openaiApiVersion)
        if self.openaiSampleRate == 16000:
            backend.remove("OpenaiSampleRate")
        else:
            backend.setValue("OpenaiSampleRate", self.openaiSampleRate)
        if self.openaiChannels == 1:
            backend.remove("OpenaiChannels")
        else:
            backend.setValue("OpenaiChannels", self.openaiChannels)
        backend.setValue("OpenaiVadEnabled", int(self.openaiVadEnabled))
        if self.openaiVadThreshold == 0.5:
            backend.remove("OpenaiVadThreshold")
        else:
            backend.setValue("OpenaiVadThreshold", self.openaiVadThreshold)
        if self.openaiVadPrefixPaddingMs == 300:
            backend.remove("OpenaiVadPrefixPaddingMs")
        else:
            backend.setValue("OpenaiVadPrefixPaddingMs", self.openaiVadPrefixPaddingMs)
        if self.openaiVadSilenceDurationMs == 200:
            backend.remove("OpenaiVadSilenceDurationMs")
        else:
            backend.setValue("OpenaiVadSilenceDurationMs", self.openaiVadSilenceDurationMs)
        if self.openaiLanguage == "en-US":
            backend.remove("OpenaiLanguage")
        else:
            backend.setValue("OpenaiLanguage", self.openaiLanguage)
        if self.deviceName == "default":
            backend.remove("DeviceName")
        else:
            backend.setValue("DeviceName", self.deviceName)

    def add_model(self, language, name, version, size, mclass, location) -> None:
        entry = {
            "name": name,
            "language": language,
            "size": size,
            "type": mclass,
            "version": version,
            "location": location,
        }
        self.models.append(entry)
        self.write_models()

    def remove_model(self, index) -> None:
        del self.models[index]
        self.write_models()

    def write_models(self) -> None:
        backend = self._backend
        count = backend.beginReadArray("Models")
        backend.endArray()
        backend.beginWriteArray("Models")
        for idx in range(count):
            backend.setArrayIndex(idx)
            backend.remove(str(idx))
        backend.endArray()

        backend.beginWriteArray("Models")
        for idx, model in enumerate(self.models):
            backend.setArrayIndex(idx)
            backend.setValue("language", model.get("language", ""))
            backend.setValue("name", model.get("name", ""))
            backend.setValue("version", model.get("version", ""))
            backend.setValue("size", model.get("size", ""))
            backend.setValue("type", model.get("type", ""))
            backend.setValue("location", model.get("location", ""))
        backend.endArray()

    def setValue(self, key: str, value) -> None:  # noqa: N802 - Qt naming
        self._backend.setValue(key, value)

    def value(self, key: str, default=None, type=None):  # noqa: N802
        if type is None:
            return self._backend.value(key, default)
        return self._backend.value(key, default, type=type)

    def contains(self, key: str) -> bool:  # noqa: N802
        return self._backend.contains(key)

    def remove(self, key: str) -> None:  # noqa: N802
        self._backend.remove(key)

    def beginReadArray(self, prefix: str) -> int:  # noqa: N802
        return self._backend.beginReadArray(prefix)

    def beginWriteArray(self, prefix: str) -> None:  # noqa: N802
        self._backend.beginWriteArray(prefix)

    def endArray(self) -> None:  # noqa: N802
        self._backend.endArray()

    def setArrayIndex(self, index: int) -> None:  # noqa: N802
        self._backend.setArrayIndex(index)

    def _set_or_remove(self, key: str, value: str) -> None:
        backend = self._backend
        if value:
            backend.setValue(key, value)
        else:
            backend.remove(key)

    def current_model(self):
        name = ""
        location = ""
        if self.contains("Model/name"):
            name = self.value("Model/name")
            for entry in self.models:
                if entry.get("name") == name:
                    location = entry.get("location", "")
                    break
        if not location:
            for entry in self.models:
                loc = entry.get("location", "")
                if loc:
                    name = entry.get("name", name)
                    location = loc
                    break
        return name, location
