"""Тесты macOS TTS adapter без реального AVSpeechSynthesizer."""

import builtins

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
