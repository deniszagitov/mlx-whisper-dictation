"""Юнит-тесты логики распознавания и fallback-поведения."""

import importlib.util
from pathlib import Path

import numpy as np

MODULE_PATH = Path(__file__).resolve().parent.parent / "whisper-dictation.py"
SPEC = importlib.util.spec_from_file_location("whisper_dictation_app", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def make_audio(seconds=1.0, amplitude=0.01):
    """Создает искусственный аудиосигнал заданной длины и амплитуды."""
    samples = int(16000 * seconds)
    return np.full(samples, amplitude, dtype=np.float32)


def test_transcribe_retries_without_language_on_empty_primary(monkeypatch):
    """При пустом первом результате приложение должно повторить распознавание без language."""
    transcriber = MODULE.SpeechTranscriber("dummy-model")
    calls = []
    clipboard = []

    def fake_run(audio_data, language):
        calls.append(language)
        if language == "ru":
            return {"text": ""}
        return {"text": "Привет мир"}

    monkeypatch.setattr(transcriber, "_run_transcription", fake_run)
    monkeypatch.setattr(transcriber, "_copy_text_to_clipboard", clipboard.append)
    monkeypatch.setattr(MODULE, "is_accessibility_trusted", lambda: False)
    monkeypatch.setattr(MODULE, "notify_user", lambda *args: None)

    transcriber.transcribe(make_audio(), "ru")

    assert calls == ["ru", None]
    assert clipboard == ["Привет мир"]


def test_transcribe_keeps_known_hallucination_for_diagnostics(monkeypatch):
    """Типичная галлюцинация на тихом сигнале должна сохраняться для диагностики."""
    transcriber = MODULE.SpeechTranscriber("dummy-model")
    clipboard = []
    notifications = []

    monkeypatch.setattr(transcriber, "_run_transcription", lambda *_args: {"text": "Продолжение следует..."})
    monkeypatch.setattr(transcriber, "_copy_text_to_clipboard", clipboard.append)
    monkeypatch.setattr(MODULE, "is_accessibility_trusted", lambda: False)
    monkeypatch.setattr(MODULE, "notify_user", lambda *args: notifications.append(args))

    transcriber.transcribe(make_audio(amplitude=0.001), "ru")

    assert clipboard == ["Продолжение следует..."]
    assert notifications


def test_transcribe_copies_primary_result(monkeypatch):
    """Непустой результат первого прохода должен сразу попадать в буфер обмена."""
    transcriber = MODULE.SpeechTranscriber("dummy-model")
    clipboard = []

    monkeypatch.setattr(transcriber, "_run_transcription", lambda *_args: {"text": "Тест"})
    monkeypatch.setattr(transcriber, "_copy_text_to_clipboard", clipboard.append)
    monkeypatch.setattr(MODULE, "is_accessibility_trusted", lambda: False)
    monkeypatch.setattr(MODULE, "notify_user", lambda *args: None)

    transcriber.transcribe(make_audio(), "ru")

    assert clipboard == ["Тест"]


def test_transcribe_notifies_on_too_short_audio(monkeypatch):
    """Даже короткая запись должна всё равно отправляться на распознавание."""
    transcriber = MODULE.SpeechTranscriber("dummy-model")
    calls = []

    def fake_run(audio_data, language):
        calls.append((len(audio_data), language))
        return {"text": "короткая фраза"}

    monkeypatch.setattr(transcriber, "_run_transcription", fake_run)
    monkeypatch.setattr(transcriber, "_copy_text_to_clipboard", lambda *_args: None)
    monkeypatch.setattr(MODULE, "is_accessibility_trusted", lambda: False)
    monkeypatch.setattr(MODULE, "notify_user", lambda *args: None)

    transcriber.transcribe(make_audio(seconds=0.1), "ru")

    assert calls


def test_transcribe_notifies_on_too_quiet_audio(monkeypatch):
    """Даже очень тихая запись должна всё равно отправляться на распознавание."""
    transcriber = MODULE.SpeechTranscriber("dummy-model")
    calls = []

    def fake_run(audio_data, language):
        calls.append((float(np.sqrt(np.mean(audio_data**2))), language))
        return {"text": "тихая фраза"}

    monkeypatch.setattr(transcriber, "_run_transcription", fake_run)
    monkeypatch.setattr(transcriber, "_copy_text_to_clipboard", lambda *_args: None)
    monkeypatch.setattr(MODULE, "is_accessibility_trusted", lambda: False)
    monkeypatch.setattr(MODULE, "notify_user", lambda *args: None)

    transcriber.transcribe(make_audio(amplitude=0.0001), "ru")

    assert calls


def test_transcribe_saves_debug_artifacts(monkeypatch, tmp_path):
    """Распознавание должно сохранять wav и результат транскрибации в папку логов."""
    transcriber = MODULE.SpeechTranscriber("dummy-model")

    monkeypatch.setattr(MODULE, "LOG_DIR", tmp_path)
    monkeypatch.setattr(transcriber, "_run_transcription", lambda *_args: {"text": "Проверка артефактов"})
    monkeypatch.setattr(transcriber, "_copy_text_to_clipboard", lambda *_args: None)
    monkeypatch.setattr(MODULE, "is_accessibility_trusted", lambda: False)
    monkeypatch.setattr(MODULE, "notify_user", lambda *args: None)

    transcriber.transcribe(make_audio(), "ru")

    wav_files = list((tmp_path / "recordings").glob("*.wav"))
    recording_metadata = list((tmp_path / "recordings").glob("*.json"))
    transcript_json = list((tmp_path / "transcriptions").glob("*.json"))
    transcript_text = list((tmp_path / "transcriptions").glob("*.txt"))

    assert len(wav_files) == 1
    assert len(recording_metadata) == 1
    assert len(transcript_json) == 1
    assert len(transcript_text) == 1
