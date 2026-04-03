"""Юнит-тесты основного сценария распознавания и автовставки."""

import numpy as np
from src.domain.constants import Config


class FakeSettingsStore:
    """Простое in-memory хранилище настроек для тестов транскрибации."""

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


def make_audio(seconds=1.0, amplitude=0.01):
    """Создает искусственный аудиосигнал заданной длины и амплитуды."""
    samples = int(16000 * seconds)
    return np.full(samples, amplitude, dtype=np.float32)


def make_transcriber(app_module, diagnostics_enabled=False):
    """Создает transcriber с управляемым diagnostics store для тестов."""
    diagnostics_store = app_module.DiagnosticsStore(root_dir=Config.LOG_DIR, enabled=diagnostics_enabled)
    return app_module.SpeechTranscriber(
        "dummy-model",
        settings_store=FakeSettingsStore(),
        diagnostics_store=diagnostics_store,
    )


def test_transcribe_inserts_via_cgevent_when_enabled(app_module, monkeypatch):
    """При включённом CGEvent текст должен вставляться через прямой ввод."""
    transcriber = make_transcriber(app_module)
    transcriber.paste_cgevent_enabled = True
    transcriber.paste_ax_enabled = False
    transcriber.paste_clipboard_enabled = False
    inserted: list[object] = []

    monkeypatch.setattr(transcriber, "_run_transcription", lambda *_args: {"text": "Автовставка"})
    monkeypatch.setattr(transcriber, "_type_text_via_cgevent", inserted.append)
    monkeypatch.setattr(transcriber, "add_to_history", lambda *_args: None)

    transcriber.transcribe(make_audio(), "ru")

    assert inserted == ["Автовставка"]


def test_transcribe_falls_back_from_cgevent_to_clipboard(app_module, monkeypatch):
    """При ошибке CGEvent приложение должно переключиться на буфер обмена."""
    transcriber = make_transcriber(app_module)
    transcriber.paste_cgevent_enabled = True
    transcriber.paste_ax_enabled = False
    transcriber.paste_clipboard_enabled = True
    clipboard_inserted: list[object] = []

    def failing_cgevent(text):
        raise RuntimeError("CGEvent failed")

    monkeypatch.setattr(transcriber, "_run_transcription", lambda *_args: {"text": "Текст"})
    monkeypatch.setattr(transcriber, "_type_text_via_cgevent", failing_cgevent)
    monkeypatch.setattr(transcriber, "_paste_via_clipboard", clipboard_inserted.append)
    monkeypatch.setattr(transcriber, "add_to_history", lambda *_args: None)

    transcriber.transcribe(make_audio(), "ru")

    assert clipboard_inserted == ["Текст"]


def test_transcribe_falls_back_to_history_when_accessibility_missing(app_module, monkeypatch):
    """Без Accessibility текст должен попасть в clipboard fallback и уведомление."""
    transcriber = make_transcriber(app_module)
    history_added: list[object] = []
    notifications = []
    warned = []
    clipboard_saved: list[str] = []

    monkeypatch.setattr(transcriber, "_run_transcription", lambda *_args: {"text": "Текст"})
    monkeypatch.setattr(transcriber, "add_to_history", history_added.append)
    monkeypatch.setattr(transcriber, "_request_accessibility_permission", lambda: False)
    monkeypatch.setattr(transcriber, "_get_input_monitoring_status", lambda: True)
    monkeypatch.setattr(transcriber, "_is_accessibility_trusted", lambda: False)
    monkeypatch.setattr(transcriber, "_warn_missing_accessibility_permission", lambda: warned.append(True))
    monkeypatch.setattr(transcriber, "_notify_user", lambda *args: notifications.append(args))
    monkeypatch.setattr(transcriber, "_copy_to_clipboard", clipboard_saved.append)

    transcriber.transcribe(make_audio(), "ru")

    assert history_added == ["Текст"]
    assert clipboard_saved == ["Текст"]
    assert warned == [True]
    assert notifications
    assert "буфер обмена" in notifications[-1][1]


def test_transcribe_falls_back_to_history_when_input_monitoring_missing(app_module, monkeypatch):
    """Без Input Monitoring текст должен попасть в clipboard fallback."""
    transcriber = make_transcriber(app_module)
    history_added: list[object] = []
    notifications = []
    warned = []
    clipboard_saved: list[str] = []

    monkeypatch.setattr(transcriber, "_run_transcription", lambda *_args: {"text": "Текст"})
    monkeypatch.setattr(transcriber, "add_to_history", history_added.append)
    monkeypatch.setattr(transcriber, "_request_input_monitoring_permission", lambda: False)
    monkeypatch.setattr(transcriber, "_is_accessibility_trusted", lambda: True)
    monkeypatch.setattr(transcriber, "_get_input_monitoring_status", lambda: False)
    monkeypatch.setattr(transcriber, "_warn_missing_input_monitoring_permission", lambda: warned.append(True))
    monkeypatch.setattr(transcriber, "_notify_user", lambda *args: notifications.append(args))
    monkeypatch.setattr(transcriber, "_copy_to_clipboard", clipboard_saved.append)

    transcriber.transcribe(make_audio(), "ru")

    assert history_added == ["Текст"]
    assert clipboard_saved == ["Текст"]
    assert warned == [True]
    assert notifications
    assert "буфер обмена" in notifications[-1][1]


def test_transcribe_notifies_when_all_methods_fail(app_module, monkeypatch):
    """При ошибке всех методов текст остаётся в clipboard fallback и истории."""
    transcriber = make_transcriber(app_module)
    transcriber.paste_cgevent_enabled = True
    transcriber.paste_ax_enabled = False
    transcriber.paste_clipboard_enabled = False
    notifications = []
    clipboard_saved: list[str] = []

    def failing_cgevent(text):
        raise RuntimeError("CGEvent failed")

    monkeypatch.setattr(transcriber, "_run_transcription", lambda *_args: {"text": "Текст"})
    monkeypatch.setattr(transcriber, "_type_text_via_cgevent", failing_cgevent)
    monkeypatch.setattr(transcriber, "add_to_history", lambda *_args: None)
    monkeypatch.setattr(transcriber, "_notify_user", lambda *args: notifications.append(args))
    monkeypatch.setattr(transcriber, "_copy_to_clipboard", clipboard_saved.append)

    transcriber.transcribe(make_audio(), "ru")

    assert notifications
    assert clipboard_saved == ["Текст"]
    assert "буфер обмена" in notifications[-1][1]


def test_transcribe_notifies_when_no_methods_enabled(app_module, monkeypatch):
    """Если все методы выключены, текст остаётся доступен через clipboard fallback."""
    transcriber = make_transcriber(app_module)
    transcriber.paste_cgevent_enabled = False
    transcriber.paste_ax_enabled = False
    transcriber.paste_clipboard_enabled = False
    notifications = []
    clipboard_saved: list[str] = []

    monkeypatch.setattr(transcriber, "_run_transcription", lambda *_args: {"text": "Текст"})
    monkeypatch.setattr(transcriber, "add_to_history", lambda *_args: None)
    monkeypatch.setattr(transcriber, "_notify_user", lambda *args: notifications.append(args))
    monkeypatch.setattr(transcriber, "_copy_to_clipboard", clipboard_saved.append)

    transcriber.transcribe(make_audio(), "ru")

    assert notifications
    assert clipboard_saved == ["Текст"]
    assert "буфер обмена" in notifications[-1][1]


def test_transcribe_notifies_on_empty_result(app_module, monkeypatch):
    """Пустой результат распознавания должен явно сообщаться пользователю."""
    transcriber = make_transcriber(app_module)
    notifications = []

    monkeypatch.setattr(transcriber, "_run_transcription", lambda *_args: {"text": ""})
    monkeypatch.setattr(transcriber, "_notify_user", lambda *args: notifications.append(args))

    transcriber.transcribe(make_audio(), None)

    assert notifications


def test_transcribe_always_adds_to_history(app_module, monkeypatch):
    """Распознанный текст всегда должен сохраняться в историю."""
    transcriber = make_transcriber(app_module)
    history_added: list[object] = []

    monkeypatch.setattr(transcriber, "_run_transcription", lambda *_args: {"text": "Текст"})
    monkeypatch.setattr(transcriber, "add_to_history", history_added.append)
    monkeypatch.setattr(transcriber, "_type_text_via_cgevent", lambda *_args: None)

    transcriber.transcribe(make_audio(), "ru")

    assert history_added == ["Текст"]


def test_transcribe_accumulates_tokens_from_segments(app_module, monkeypatch):
    """Whisper-токены из segments должны попадать в общий счётчик."""
    transcriber = make_transcriber(app_module)
    transcriber.total_tokens = 0

    monkeypatch.setattr(
        transcriber,
        "_run_transcription",
        lambda *_args: {"text": "Текст", "segments": [{"tokens": [1, 2, 3]}, {"tokens": [4, 5]}]},
    )
    monkeypatch.setattr(transcriber, "add_to_history", lambda *_args: None)
    monkeypatch.setattr(transcriber, "_type_text_via_cgevent", lambda *_args: None)
    monkeypatch.setattr(transcriber.settings_store, "save_int", lambda *_args: None)

    transcriber.transcribe(make_audio(), "ru")

    assert transcriber.total_tokens == 5


def test_transcribe_accumulates_tokens_from_qwen_total(app_module, monkeypatch):
    """Qwen-токены из total_tokens должны попадать в общий счётчик."""
    transcriber = make_transcriber(app_module)
    transcriber.total_tokens = 2

    monkeypatch.setattr(
        transcriber,
        "_run_transcription",
        lambda *_args: {"text": "Текст", "segments": [], "total_tokens": 7},
    )
    monkeypatch.setattr(transcriber, "add_to_history", lambda *_args: None)
    monkeypatch.setattr(transcriber, "_type_text_via_cgevent", lambda *_args: None)
    monkeypatch.setattr(transcriber.settings_store, "save_int", lambda *_args: None)

    transcriber.transcribe(make_audio(), "ru")

    assert transcriber.total_tokens == 9


def test_transcribe_to_text_returns_text(app_module, monkeypatch):
    """transcribe_to_text должен вернуть распознанный текст."""
    transcriber = make_transcriber(app_module)
    transcriber.total_tokens = 0

    monkeypatch.setattr(
        transcriber,
        "_run_transcription",
        lambda *_args: {"text": "Текст", "segments": [{"tokens": [1, 2, 3]}]},
    )
    monkeypatch.setattr(transcriber.settings_store, "save_int", lambda *_args: None)
    monkeypatch.setattr(transcriber, "_notify_user", lambda *args: None)

    result = transcriber.transcribe_to_text(make_audio(), "ru")

    assert result == "Текст"
    assert transcriber.total_tokens == 3


def test_transcribe_to_text_returns_none_on_empty(app_module, monkeypatch):
    """transcribe_to_text должен вернуть None при пустом результате."""
    transcriber = make_transcriber(app_module)

    monkeypatch.setattr(transcriber, "_run_transcription", lambda *_args: {"text": ""})
    monkeypatch.setattr(transcriber, "_notify_user", lambda *args: None)

    result = transcriber.transcribe_to_text(make_audio(), "ru")

    assert result is None


def test_transcribe_to_text_returns_none_on_error(app_module, monkeypatch):
    """transcribe_to_text должен вернуть None при ошибке распознавания."""
    transcriber = make_transcriber(app_module)

    def failing_transcription(*_args):
        raise RuntimeError("Ошибка модели")

    monkeypatch.setattr(transcriber, "_run_transcription", failing_transcription)
    monkeypatch.setattr(transcriber, "_notify_user", lambda *args: None)

    result = transcriber.transcribe_to_text(make_audio(), "ru")

    assert result is None


def test_transcribe_to_text_accumulates_tokens(app_module, monkeypatch):
    """transcribe_to_text должен считать токены из сегментов Whisper."""
    transcriber = make_transcriber(app_module)
    transcriber.total_tokens = 10

    monkeypatch.setattr(
        transcriber,
        "_run_transcription",
        lambda *_args: {"text": "Текст", "segments": [{"tokens": [1, 2, 3]}, {"tokens": [4, 5]}]},
    )
    monkeypatch.setattr(transcriber.settings_store, "save_int", lambda *_args: None)
    monkeypatch.setattr(transcriber, "_notify_user", lambda *args: None)

    transcriber.transcribe_to_text(make_audio(), "ru")

    assert transcriber.total_tokens == 15


def test_transcribe_to_text_accumulates_qwen_total_tokens(app_module, monkeypatch):
    """transcribe_to_text должен учитывать total_tokens от Qwen backend-а."""
    transcriber = make_transcriber(app_module)
    transcriber.total_tokens = 10

    monkeypatch.setattr(
        transcriber,
        "_run_transcription",
        lambda *_args: {"text": "Текст", "segments": [], "total_tokens": 4},
    )
    monkeypatch.setattr(transcriber.settings_store, "save_int", lambda *_args: None)
    monkeypatch.setattr(transcriber, "_notify_user", lambda *args: None)

    transcriber.transcribe_to_text(make_audio(), "ru")

    assert transcriber.total_tokens == 14


def test_transcribe_to_text_filters_hallucination(app_module, monkeypatch):
    """transcribe_to_text должен отбрасывать галлюцинаторные результаты."""
    transcriber = make_transcriber(app_module)

    monkeypatch.setattr(
        transcriber,
        "_run_transcription",
        lambda *_args: {"text": "Thank you."},
    )
    monkeypatch.setattr(transcriber.settings_store, "save_int", lambda *_args: None)
    monkeypatch.setattr(transcriber, "_notify_user", lambda *args: None)

    # Тихое аудио + галлюцинация = None
    result = transcriber.transcribe_to_text(make_audio(amplitude=0.0001), "ru")

    assert result is None


def test_transcribe_clipboard_not_touched_when_disabled(app_module, monkeypatch):
    """Буфер обмена не должен затрагиваться, если метод 'Буфер обмена' выключен."""
    transcriber = make_transcriber(app_module)
    transcriber.paste_cgevent_enabled = True
    transcriber.paste_ax_enabled = False
    transcriber.paste_clipboard_enabled = False
    clipboard_calls = []

    monkeypatch.setattr(transcriber, "_run_transcription", lambda *_args: {"text": "Текст"})
    monkeypatch.setattr(transcriber, "_type_text_via_cgevent", lambda *_args: None)
    monkeypatch.setattr(transcriber, "_copy_to_clipboard", lambda *_args: clipboard_calls.append(True))
    monkeypatch.setattr(transcriber, "add_to_history", lambda *_args: None)

    transcriber.transcribe(make_audio(), "ru")

    assert clipboard_calls == []
