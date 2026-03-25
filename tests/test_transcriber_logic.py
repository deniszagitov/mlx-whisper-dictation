"""Юнит-тесты основного сценария распознавания и автовставки."""

import numpy as np


def make_audio(seconds=1.0, amplitude=0.01):
    """Создает искусственный аудиосигнал заданной длины и амплитуды."""
    samples = int(16000 * seconds)
    return np.full(samples, amplitude, dtype=np.float32)


def make_transcriber(app_module, diagnostics_enabled=False):
    """Создает transcriber с управляемым diagnostics store для тестов."""
    diagnostics_store = app_module.DiagnosticsStore(root_dir=app_module.LOG_DIR, enabled=diagnostics_enabled)
    return app_module.SpeechTranscriber("dummy-model", diagnostics_store=diagnostics_store)


def test_transcribe_retries_without_language_on_empty_primary(app_module, monkeypatch):
    """При пустом первом результате приложение должно повторить распознавание без language."""
    transcriber = make_transcriber(app_module)
    calls = []
    history_added = []

    def fake_run(audio_data, language):
        calls.append(language)
        if language == "ru":
            return {"text": ""}
        return {"text": "Привет мир"}

    monkeypatch.setattr(transcriber, "_run_transcription", fake_run)
    monkeypatch.setattr(transcriber, "_add_to_history", history_added.append)
    monkeypatch.setattr(app_module, "is_accessibility_trusted", lambda: False)
    monkeypatch.setattr(app_module, "notify_user", lambda *args: None)

    transcriber.transcribe(make_audio(), "ru")

    assert calls == ["ru", None]
    assert history_added == ["Привет мир"]


def test_transcribe_inserts_via_cgevent_when_enabled(app_module, monkeypatch):
    """При включённом CGEvent текст должен вставляться через прямой ввод."""
    transcriber = make_transcriber(app_module)
    transcriber.paste_cgevent_enabled = True
    transcriber.paste_ax_enabled = False
    transcriber.paste_clipboard_enabled = False
    inserted = []

    monkeypatch.setattr(transcriber, "_run_transcription", lambda *_args: {"text": "Автовставка"})
    monkeypatch.setattr(transcriber, "_type_text_via_cgevent", inserted.append)
    monkeypatch.setattr(transcriber, "_add_to_history", lambda *_args: None)
    monkeypatch.setattr(app_module, "is_accessibility_trusted", lambda: True)
    monkeypatch.setattr(app_module, "get_input_monitoring_status", lambda: True)
    monkeypatch.setattr(app_module, "notify_user", lambda *args: None)

    transcriber.transcribe(make_audio(), "ru")

    assert inserted == ["Автовставка"]


def test_transcribe_falls_back_from_cgevent_to_clipboard(app_module, monkeypatch):
    """При ошибке CGEvent приложение должно переключиться на буфер обмена."""
    transcriber = make_transcriber(app_module)
    transcriber.paste_cgevent_enabled = True
    transcriber.paste_ax_enabled = False
    transcriber.paste_clipboard_enabled = True
    clipboard_inserted = []

    def failing_cgevent(text):
        raise RuntimeError("CGEvent failed")

    monkeypatch.setattr(transcriber, "_run_transcription", lambda *_args: {"text": "Текст"})
    monkeypatch.setattr(transcriber, "_type_text_via_cgevent", failing_cgevent)
    monkeypatch.setattr(transcriber, "_paste_via_clipboard", clipboard_inserted.append)
    monkeypatch.setattr(transcriber, "_add_to_history", lambda *_args: None)
    monkeypatch.setattr(app_module, "is_accessibility_trusted", lambda: True)
    monkeypatch.setattr(app_module, "get_input_monitoring_status", lambda: True)
    monkeypatch.setattr(app_module, "notify_user", lambda *args: None)

    transcriber.transcribe(make_audio(), "ru")

    assert clipboard_inserted == ["Текст"]


def test_transcribe_falls_back_to_history_when_accessibility_missing(app_module, monkeypatch):
    """Без Accessibility текст должен сохраниться в истории и уведомить пользователя."""
    transcriber = make_transcriber(app_module)
    history_added = []
    notifications = []
    warned = []

    monkeypatch.setattr(transcriber, "_run_transcription", lambda *_args: {"text": "Текст"})
    monkeypatch.setattr(transcriber, "_add_to_history", history_added.append)
    monkeypatch.setattr(app_module, "request_accessibility_permission", lambda: False)
    monkeypatch.setattr(app_module, "get_input_monitoring_status", lambda: True)
    monkeypatch.setattr(app_module, "is_accessibility_trusted", lambda: False)
    monkeypatch.setattr(app_module, "warn_missing_accessibility_permission", lambda: warned.append(True))
    monkeypatch.setattr(app_module, "notify_user", lambda *args: notifications.append(args))

    transcriber.transcribe(make_audio(), "ru")

    assert history_added == ["Текст"]
    assert warned == [True]
    assert notifications


def test_transcribe_falls_back_to_history_when_input_monitoring_missing(app_module, monkeypatch):
    """Без Input Monitoring текст должен сохраниться в истории."""
    transcriber = make_transcriber(app_module)
    history_added = []
    notifications = []
    warned = []

    monkeypatch.setattr(transcriber, "_run_transcription", lambda *_args: {"text": "Текст"})
    monkeypatch.setattr(transcriber, "_add_to_history", history_added.append)
    monkeypatch.setattr(app_module, "request_input_monitoring_permission", lambda: False)
    monkeypatch.setattr(app_module, "is_accessibility_trusted", lambda: True)
    monkeypatch.setattr(app_module, "get_input_monitoring_status", lambda: False)
    monkeypatch.setattr(app_module, "warn_missing_input_monitoring_permission", lambda: warned.append(True))
    monkeypatch.setattr(app_module, "notify_user", lambda *args: notifications.append(args))

    transcriber.transcribe(make_audio(), "ru")

    assert history_added == ["Текст"]
    assert warned == [True]
    assert notifications


def test_transcribe_notifies_when_all_methods_fail(app_module, monkeypatch):
    """При ошибке всех включённых методов вставки пользователь получает уведомление."""
    transcriber = make_transcriber(app_module)
    transcriber.paste_cgevent_enabled = True
    transcriber.paste_ax_enabled = False
    transcriber.paste_clipboard_enabled = False
    notifications = []

    def failing_cgevent(text):
        raise RuntimeError("CGEvent failed")

    monkeypatch.setattr(transcriber, "_run_transcription", lambda *_args: {"text": "Текст"})
    monkeypatch.setattr(transcriber, "_type_text_via_cgevent", failing_cgevent)
    monkeypatch.setattr(transcriber, "_add_to_history", lambda *_args: None)
    monkeypatch.setattr(app_module, "is_accessibility_trusted", lambda: True)
    monkeypatch.setattr(app_module, "get_input_monitoring_status", lambda: True)
    monkeypatch.setattr(app_module, "notify_user", lambda *args: notifications.append(args))

    transcriber.transcribe(make_audio(), "ru")

    assert notifications
    assert "История текста" in notifications[-1][1]


def test_transcribe_notifies_when_no_methods_enabled(app_module, monkeypatch):
    """Если ни один метод вставки не включён, пользователь получает уведомление."""
    transcriber = make_transcriber(app_module)
    transcriber.paste_cgevent_enabled = False
    transcriber.paste_ax_enabled = False
    transcriber.paste_clipboard_enabled = False
    notifications = []

    monkeypatch.setattr(transcriber, "_run_transcription", lambda *_args: {"text": "Текст"})
    monkeypatch.setattr(transcriber, "_add_to_history", lambda *_args: None)
    monkeypatch.setattr(app_module, "is_accessibility_trusted", lambda: True)
    monkeypatch.setattr(app_module, "get_input_monitoring_status", lambda: True)
    monkeypatch.setattr(app_module, "notify_user", lambda *args: notifications.append(args))

    transcriber.transcribe(make_audio(), "ru")

    assert notifications


def test_transcribe_notifies_on_empty_result(app_module, monkeypatch):
    """Пустой результат распознавания должен явно сообщаться пользователю."""
    transcriber = make_transcriber(app_module)
    notifications = []

    monkeypatch.setattr(transcriber, "_run_transcription", lambda *_args: {"text": ""})
    monkeypatch.setattr(app_module, "notify_user", lambda *args: notifications.append(args))

    transcriber.transcribe(make_audio(), None)

    assert notifications


def test_transcribe_always_adds_to_history(app_module, monkeypatch):
    """Распознанный текст всегда должен сохраняться в историю."""
    transcriber = make_transcriber(app_module)
    history_added = []

    monkeypatch.setattr(transcriber, "_run_transcription", lambda *_args: {"text": "Текст"})
    monkeypatch.setattr(transcriber, "_add_to_history", history_added.append)
    monkeypatch.setattr(transcriber, "_type_text_via_cgevent", lambda *_args: None)
    monkeypatch.setattr(app_module, "is_accessibility_trusted", lambda: True)
    monkeypatch.setattr(app_module, "get_input_monitoring_status", lambda: True)
    monkeypatch.setattr(app_module, "notify_user", lambda *args: None)

    transcriber.transcribe(make_audio(), "ru")

    assert history_added == ["Текст"]


def test_transcribe_clipboard_not_touched_when_disabled(app_module, monkeypatch):
    """Буфер обмена не должен затрагиваться, если метод 'Буфер обмена' выключен."""
    transcriber = make_transcriber(app_module)
    transcriber.paste_cgevent_enabled = True
    transcriber.paste_ax_enabled = False
    transcriber.paste_clipboard_enabled = False
    clipboard_calls = []

    monkeypatch.setattr(transcriber, "_run_transcription", lambda *_args: {"text": "Текст"})
    monkeypatch.setattr(transcriber, "_type_text_via_cgevent", lambda *_args: None)
    monkeypatch.setattr(transcriber, "_copy_text_to_clipboard", lambda *_args: clipboard_calls.append(True))
    monkeypatch.setattr(transcriber, "_add_to_history", lambda *_args: None)
    monkeypatch.setattr(app_module, "is_accessibility_trusted", lambda: True)
    monkeypatch.setattr(app_module, "get_input_monitoring_status", lambda: True)
    monkeypatch.setattr(app_module, "notify_user", lambda *args: None)

    transcriber.transcribe(make_audio(), "ru")

    assert clipboard_calls == []
