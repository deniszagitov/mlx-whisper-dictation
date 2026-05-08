"""Тесты macOS TTS adapter без реального AVSpeechSynthesizer."""

import builtins
from types import SimpleNamespace

import pytest
from src.domain.reader_types import TTSConfig
from src.infrastructure.tts_macos import MacOSTTSController


def test_macos_tts_controller_does_not_crash_when_avfoundation_missing(monkeypatch):
    """Отсутствие PyObjC AVFoundation не должно валить приложение при старте."""
    original_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "AVFoundation":
            raise ModuleNotFoundError(name)
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)

    controller = MacOSTTSController()

    assert controller.available_voices() == []
    assert controller.is_speaking() is False
    controller.stop()
    with pytest.raises(RuntimeError, match="AVFoundation недоступен"):
        controller.speak("текст", TTSConfig())


class FakeUtterance:
    """Фейковый AVSpeechUtterance."""

    def __init__(self, text):
        self.text = text
        self.rate = None
        self.pitch = None
        self.voice = None

    def setRate_(self, rate):
        self.rate = rate

    def setPitchMultiplier_(self, pitch):
        self.pitch = pitch

    def setVoice_(self, voice):
        self.voice = voice


class FakeVoice:
    """Фейковый AVSpeech voice."""

    def __init__(self, identifier="ru.voice", name="Milena", language="ru-RU"):
        self._identifier = identifier
        self._name = name
        self._language = language

    def identifier(self):
        return self._identifier

    def name(self):
        return self._name

    def language(self):
        return self._language


class FakeSynthesizer:
    """Фейковый AVSpeechSynthesizer."""

    def __init__(self):
        self.utterances = []

    def speakUtterance_(self, utterance):
        self.utterances.append(utterance)

    def isSpeaking(self):
        return False

    def stopSpeakingAtBoundary_(self, _boundary):
        return None


def make_fake_avfoundation():
    """Создаёт фейковый AVFoundation с минимальным контрактом для TTS."""
    voices = [FakeVoice()]
    return SimpleNamespace(
        AVSpeechUtterance=SimpleNamespace(speechUtteranceWithString_=FakeUtterance),
        AVSpeechSynthesisVoice=SimpleNamespace(
            speechVoices=lambda: voices,
            voiceWithIdentifier_=lambda identifier: next((voice for voice in voices if voice.identifier() == identifier), None),
        ),
        AVSpeechUtteranceDefaultSpeechRate=0.5,
        AVSpeechUtteranceMinimumSpeechRate=0.0,
        AVSpeechUtteranceMaximumSpeechRate=1.0,
        AVSpeechBoundaryImmediate=0,
    )


def test_macos_tts_supported_tone_updates_pitch_and_rate():
    """Поддержанные подсказки интонации меняют только AVSpeech pitch/rate."""
    synthesizer = FakeSynthesizer()
    controller = MacOSTTSController(synthesizer=synthesizer, avfoundation=make_fake_avfoundation())

    controller.speak("текст", TTSConfig(rate_multiplier=1.0, tone_instruction="вопросительно и энергично"))

    utterance = synthesizer.utterances[0]
    assert utterance.pitch > 1.0
    assert utterance.rate > 0.5


def test_macos_tts_unsupported_tone_is_logged_without_crash(caplog):
    """Неподдержанная свободная интонация не ломает Apple backend."""
    synthesizer = FakeSynthesizer()
    controller = MacOSTTSController(synthesizer=synthesizer, avfoundation=make_fake_avfoundation())
    caplog.set_level("INFO", logger="src.infrastructure.tts_macos")

    controller.speak("текст", TTSConfig(rate_multiplier=1.0, tone_instruction="с лёгким удивлением"))

    utterance = synthesizer.utterances[0]
    assert utterance.pitch is None
    assert utterance.rate == pytest.approx(0.5)
    assert "AVSpeech не поддерживает свободную интонацию TTS" in caplog.text
