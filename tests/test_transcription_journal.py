"""Тесты записи событий журнала из transcribe()/transcribe_to_text()."""

from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np
import pytest
from src.domain.constants import Config

if TYPE_CHECKING:
    from src.domain.dictation_log import DictationEvent


class FakeSettingsStore:
    """In-memory settings store достаточный для transcriber-а."""

    def load_bool(self, _key, fallback):
        return fallback

    def save_bool(self, _key, _value):
        return None

    def load_list(self, _key):
        return []

    def save_list(self, _key, _value):
        return None

    def load_int(self, _key, fallback):
        return fallback

    def save_int(self, _key, _value):
        return None

    def load_str(self, _key, fallback=None):
        return fallback

    def save_str(self, _key, _value):
        return None

    def load_max_time(self, fallback):
        return fallback

    def save_max_time(self, _value):
        return None

    def load_input_device_index(self):
        return None

    def save_input_device_index(self, _value):
        return None

    def remove_key(self, _key):
        return None


def make_audio(seconds: float = 1.0, amplitude: float = 0.05) -> np.ndarray:
    """Создаёт тестовый аудиосигнал."""
    samples = int(16000 * seconds)
    return np.full(samples, amplitude, dtype=np.float32)


def make_transcriber(app_module, journal_writer):
    """Готовит transcriber с журналом и заглушками методов вставки."""
    return app_module.SpeechTranscriber(
        "dummy-model",
        settings_store=FakeSettingsStore(),
        diagnostics_store=app_module.DiagnosticsStore(enabled=False),
        journal_writer=journal_writer,
    )


@pytest.fixture
def captured_events() -> list[DictationEvent]:
    """Список перехваченных событий журнала."""
    return []


@pytest.fixture
def writer(captured_events):
    """Заглушка журнала: складывает события в список и возвращает id."""
    counter = {"value": 0}

    def _write(event: DictationEvent) -> int:
        counter["value"] += 1
        captured_events.append(event)
        return counter["value"]

    return _write


def test_transcribe_records_event_on_success(app_module, monkeypatch, captured_events, writer):
    """После успешного распознавания журнал должен получить событие с текстом и аудио."""
    transcriber = make_transcriber(app_module, writer)
    monkeypatch.setattr(transcriber, "_run_transcription", lambda *_args: {"text": "Привет"})
    monkeypatch.setattr(transcriber, "_type_text_via_cgevent", lambda _text: None)
    monkeypatch.setattr(transcriber, "_notify_user", lambda *_args: None)

    transcriber.transcribe(make_audio(seconds=2.0), "ru")

    assert len(captured_events) == 1
    event = captured_events[0]
    assert event.text == "Привет"
    assert event.language == "ru"
    assert event.source == Config.JOURNAL_SOURCE_DICTATION
    assert event.model == "dummy-model"
    assert event.sample_rate == Config.AUDIO_SAMPLE_RATE
    assert event.duration_seconds == pytest.approx(2.0, rel=0.05)
    assert event.audio_pcm16
    assert len(event.audio_pcm16) % 2 == 0
    assert event.ended_at >= event.started_at


def test_transcribe_to_text_records_event_with_llm_source(app_module, monkeypatch, captured_events, writer):
    """transcribe_to_text должен помечать события как идущие из LLM-пайплайна."""
    transcriber = make_transcriber(app_module, writer)
    monkeypatch.setattr(transcriber, "_run_transcription", lambda *_args: {"text": "контекст для llm"})
    monkeypatch.setattr(transcriber, "_notify_user", lambda *_args: None)

    result = transcriber.transcribe_to_text(make_audio(seconds=1.5), "ru")

    assert result == "Контекст для llm"
    assert len(captured_events) == 1
    assert captured_events[0].source == Config.JOURNAL_SOURCE_LLM
    assert captured_events[0].text == "Контекст для llm"


def test_transcribe_does_not_record_when_text_is_empty(app_module, monkeypatch, captured_events, writer):
    """Пустой результат не должен попасть в журнал."""
    transcriber = make_transcriber(app_module, writer)
    monkeypatch.setattr(transcriber, "_run_transcription", lambda *_args: {"text": ""})
    monkeypatch.setattr(transcriber, "_notify_user", lambda *_args: None)

    transcriber.transcribe(make_audio(), "ru")

    assert captured_events == []


def test_transcribe_skips_journal_in_private_mode(app_module, monkeypatch, captured_events, writer):
    """Приватный режим запрещает любую персистентность распознанного текста и аудио."""
    transcriber = make_transcriber(app_module, writer)
    transcriber.preferences = transcriber.preferences.with_private_mode(True)
    monkeypatch.setattr(transcriber, "_run_transcription", lambda *_args: {"text": "секрет"})
    monkeypatch.setattr(transcriber, "_type_text_via_cgevent", lambda _text: None)
    monkeypatch.setattr(transcriber, "_notify_user", lambda *_args: None)

    transcriber.transcribe(make_audio(), "ru")

    assert captured_events == []


def test_transcribe_swallows_journal_errors(app_module, monkeypatch):
    """Ошибки журнала не должны ломать сценарий вставки текста."""
    inserted: list[str] = []

    def failing_writer(_event: DictationEvent) -> int:
        raise RuntimeError("disk full")

    transcriber = make_transcriber(app_module, failing_writer)
    monkeypatch.setattr(transcriber, "_run_transcription", lambda *_args: {"text": "Текст"})
    monkeypatch.setattr(transcriber, "_type_text_via_cgevent", inserted.append)
    monkeypatch.setattr(transcriber, "_notify_user", lambda *_args: None)

    transcriber.transcribe(make_audio(), "ru")

    assert inserted == ["Текст"]


def test_transcribe_works_without_journal_writer(app_module, monkeypatch):
    """Без journal_writer транскрипция работает по-старому."""
    inserted: list[str] = []
    transcriber = app_module.SpeechTranscriber(
        "dummy-model",
        settings_store=FakeSettingsStore(),
        diagnostics_store=app_module.DiagnosticsStore(enabled=False),
    )
    monkeypatch.setattr(transcriber, "_run_transcription", lambda *_args: {"text": "Готово"})
    monkeypatch.setattr(transcriber, "_type_text_via_cgevent", inserted.append)
    monkeypatch.setattr(transcriber, "_notify_user", lambda *_args: None)

    transcriber.transcribe(make_audio(), "ru")

    assert inserted == ["Готово"]
