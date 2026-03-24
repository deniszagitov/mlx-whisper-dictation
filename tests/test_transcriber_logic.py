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
    clipboard = []

    def fake_run(audio_data, language):
        calls.append(language)
        if language == "ru":
            return {"text": ""}
        return {"text": "Привет мир"}

    monkeypatch.setattr(transcriber, "_run_transcription", fake_run)
    monkeypatch.setattr(transcriber, "_copy_text_to_clipboard", clipboard.append)
    monkeypatch.setattr(app_module, "is_accessibility_trusted", lambda: False)
    monkeypatch.setattr(app_module, "notify_user", lambda *args: None)

    transcriber.transcribe(make_audio(), "ru")

    assert calls == ["ru", None]
    assert clipboard == ["Привет мир"]


def test_transcribe_pastes_automatically_when_permissions_are_granted(app_module, monkeypatch):
    """При наличии разрешений текст должен вставляться автоматически."""
    transcriber = make_transcriber(app_module)
    clipboard = []
    pasted = []

    monkeypatch.setattr(transcriber, "_run_transcription", lambda *_args: {"text": "Автовставка"})
    monkeypatch.setattr(transcriber, "_copy_text_to_clipboard", clipboard.append)
    monkeypatch.setattr(transcriber, "_paste_text", lambda: pasted.append(True))
    monkeypatch.setattr(app_module, "is_accessibility_trusted", lambda: True)
    monkeypatch.setattr(app_module, "get_input_monitoring_status", lambda: True)
    monkeypatch.setattr(app_module, "notify_user", lambda *args: None)

    transcriber.transcribe(make_audio(), "ru")

    assert clipboard == ["Автовставка"]
    assert pasted == [True]


def test_transcribe_falls_back_to_manual_paste_when_accessibility_missing(app_module, monkeypatch):
    """Без Accessibility приложение должно оставить текст в clipboard и уведомить пользователя."""
    transcriber = make_transcriber(app_module)
    clipboard = []
    notifications = []
    warned = []

    monkeypatch.setattr(transcriber, "_run_transcription", lambda *_args: {"text": "Текст"})
    monkeypatch.setattr(transcriber, "_copy_text_to_clipboard", clipboard.append)
    monkeypatch.setattr(app_module, "request_accessibility_permission", lambda: False)
    monkeypatch.setattr(app_module, "get_input_monitoring_status", lambda: True)
    monkeypatch.setattr(app_module, "is_accessibility_trusted", lambda: False)
    monkeypatch.setattr(app_module, "warn_missing_accessibility_permission", lambda: warned.append(True))
    monkeypatch.setattr(app_module, "notify_user", lambda *args: notifications.append(args))

    transcriber.transcribe(make_audio(), "ru")

    assert clipboard == ["Текст"]
    assert warned == [True]
    assert notifications


def test_transcribe_falls_back_to_manual_paste_when_input_monitoring_missing(app_module, monkeypatch):
    """Без Input Monitoring приложение не должно пытаться вставлять текст автоматически."""
    transcriber = make_transcriber(app_module)
    clipboard = []
    notifications = []
    warned = []

    monkeypatch.setattr(transcriber, "_run_transcription", lambda *_args: {"text": "Текст"})
    monkeypatch.setattr(transcriber, "_copy_text_to_clipboard", clipboard.append)
    monkeypatch.setattr(app_module, "request_input_monitoring_permission", lambda: False)
    monkeypatch.setattr(app_module, "is_accessibility_trusted", lambda: True)
    monkeypatch.setattr(app_module, "get_input_monitoring_status", lambda: False)
    monkeypatch.setattr(app_module, "warn_missing_input_monitoring_permission", lambda: warned.append(True))
    monkeypatch.setattr(app_module, "notify_user", lambda *args: notifications.append(args))

    transcriber.transcribe(make_audio(), "ru")

    assert clipboard == ["Текст"]
    assert warned == [True]
    assert notifications


def test_transcribe_uses_typing_fallback_if_paste_fails(app_module, monkeypatch):
    """Если Cmd+V не сработал, приложение должно перейти к резервному набору текста."""
    transcriber = make_transcriber(app_module)
    typed = []

    monkeypatch.setattr(transcriber, "_run_transcription", lambda *_args: {"text": "Резерв"})
    monkeypatch.setattr(transcriber, "_copy_text_to_clipboard", lambda *_args: None)
    monkeypatch.setattr(transcriber, "_paste_text", lambda: (_ for _ in ()).throw(RuntimeError("paste failed")))
    monkeypatch.setattr(transcriber.pykeyboard, "type", typed.append)
    monkeypatch.setattr(app_module, "is_accessibility_trusted", lambda: True)
    monkeypatch.setattr(app_module, "get_input_monitoring_status", lambda: True)
    monkeypatch.setattr(app_module, "notify_user", lambda *args: None)

    transcriber.transcribe(make_audio(), "ru")

    assert typed == ["Резерв"]


def test_transcribe_notifies_when_clipboard_write_fails(app_module, monkeypatch):
    """Ошибка записи в буфер обмена должна приводить к уведомлению пользователя."""
    transcriber = make_transcriber(app_module)
    notifications = []

    monkeypatch.setattr(transcriber, "_run_transcription", lambda *_args: {"text": "Текст"})
    monkeypatch.setattr(
        transcriber,
        "_copy_text_to_clipboard",
        lambda *_args: (_ for _ in ()).throw(RuntimeError("clipboard failed")),
    )
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
