"""Юнит-тесты основного сценария распознавания и автовставки."""

import numpy as np

import transcriber as transcriber_module


def make_audio(seconds=1.0, amplitude=0.01):
    """Создает искусственный аудиосигнал заданной длины и амплитуды."""
    samples = int(16000 * seconds)
    return np.full(samples, amplitude, dtype=np.float32)


def make_transcriber(app_module, diagnostics_enabled=False):
    """Создает transcriber с управляемым diagnostics store для тестов."""
    diagnostics_store = app_module.DiagnosticsStore(root_dir=app_module.LOG_DIR, enabled=diagnostics_enabled)
    return app_module.SpeechTranscriber("dummy-model", diagnostics_store=diagnostics_store)


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
    monkeypatch.setattr(transcriber_module, "is_accessibility_trusted", lambda: True)
    monkeypatch.setattr(transcriber_module, "get_input_monitoring_status", lambda: True)
    monkeypatch.setattr(transcriber_module, "notify_user", lambda *args: None)

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
    monkeypatch.setattr(transcriber_module, "is_accessibility_trusted", lambda: True)
    monkeypatch.setattr(transcriber_module, "get_input_monitoring_status", lambda: True)
    monkeypatch.setattr(transcriber_module, "notify_user", lambda *args: None)

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
    monkeypatch.setattr(transcriber_module, "request_accessibility_permission", lambda: False)
    monkeypatch.setattr(transcriber_module, "get_input_monitoring_status", lambda: True)
    monkeypatch.setattr(transcriber_module, "is_accessibility_trusted", lambda: False)
    monkeypatch.setattr(transcriber_module, "warn_missing_accessibility_permission", lambda: warned.append(True))
    monkeypatch.setattr(transcriber_module, "notify_user", lambda *args: notifications.append(args))

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
    monkeypatch.setattr(transcriber_module, "request_input_monitoring_permission", lambda: False)
    monkeypatch.setattr(transcriber_module, "is_accessibility_trusted", lambda: True)
    monkeypatch.setattr(transcriber_module, "get_input_monitoring_status", lambda: False)
    monkeypatch.setattr(transcriber_module, "warn_missing_input_monitoring_permission", lambda: warned.append(True))
    monkeypatch.setattr(transcriber_module, "notify_user", lambda *args: notifications.append(args))

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
    monkeypatch.setattr(transcriber_module, "is_accessibility_trusted", lambda: True)
    monkeypatch.setattr(transcriber_module, "get_input_monitoring_status", lambda: True)
    monkeypatch.setattr(transcriber_module, "notify_user", lambda *args: notifications.append(args))

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
    monkeypatch.setattr(transcriber_module, "is_accessibility_trusted", lambda: True)
    monkeypatch.setattr(transcriber_module, "get_input_monitoring_status", lambda: True)
    monkeypatch.setattr(transcriber_module, "notify_user", lambda *args: notifications.append(args))

    transcriber.transcribe(make_audio(), "ru")

    assert notifications


def test_transcribe_notifies_on_empty_result(app_module, monkeypatch):
    """Пустой результат распознавания должен явно сообщаться пользователю."""
    transcriber = make_transcriber(app_module)
    notifications = []

    monkeypatch.setattr(transcriber, "_run_transcription", lambda *_args: {"text": ""})
    monkeypatch.setattr(transcriber_module, "notify_user", lambda *args: notifications.append(args))

    transcriber.transcribe(make_audio(), None)

    assert notifications


def test_transcribe_always_adds_to_history(app_module, monkeypatch):
    """Распознанный текст всегда должен сохраняться в историю."""
    transcriber = make_transcriber(app_module)
    history_added = []

    monkeypatch.setattr(transcriber, "_run_transcription", lambda *_args: {"text": "Текст"})
    monkeypatch.setattr(transcriber, "_add_to_history", history_added.append)
    monkeypatch.setattr(transcriber, "_type_text_via_cgevent", lambda *_args: None)
    monkeypatch.setattr(transcriber_module, "is_accessibility_trusted", lambda: True)
    monkeypatch.setattr(transcriber_module, "get_input_monitoring_status", lambda: True)
    monkeypatch.setattr(transcriber_module, "notify_user", lambda *args: None)

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
    monkeypatch.setattr(transcriber, "_add_to_history", lambda *_args: None)
    monkeypatch.setattr(transcriber, "_type_text_via_cgevent", lambda *_args: None)
    monkeypatch.setattr(transcriber_module, "_save_defaults_int", lambda *_args: None)
    monkeypatch.setattr(transcriber_module, "is_accessibility_trusted", lambda: True)
    monkeypatch.setattr(transcriber_module, "get_input_monitoring_status", lambda: True)
    monkeypatch.setattr(transcriber_module, "notify_user", lambda *args: None)

    transcriber.transcribe(make_audio(), "ru")

    assert transcriber.total_tokens == 5


def test_transcribe_for_llm_accumulates_whisper_and_llm_tokens(app_module, monkeypatch):
    """LLM-пайплайн должен суммировать токены Whisper и LLM."""
    transcriber = make_transcriber(app_module)
    transcriber.total_tokens = 0

    class LLMStub:
        def __init__(self):
            self.last_token_usage = 0

        def process_text(self, text, system_prompt, *, context=None):
            del context
            self.last_token_usage = 7
            return "Ответ"

    monkeypatch.setattr(
        transcriber,
        "_run_transcription",
        lambda *_args: {"text": "Текст", "segments": [{"tokens": [1, 2, 3]}]},
    )
    monkeypatch.setattr(transcriber, "_add_to_history", lambda *_args: None)
    monkeypatch.setattr(transcriber, "_copy_text_to_clipboard", lambda *_args: None)
    monkeypatch.setattr(transcriber_module, "_save_defaults_int", lambda *_args: None)
    monkeypatch.setattr(transcriber_module, "notify_user", lambda *args: None)

    transcriber.transcribe_for_llm(make_audio(), "ru", llm_processor=LLMStub(), system_prompt="Исправь текст")

    assert transcriber.total_tokens == 10


def test_transcribe_for_llm_passes_clipboard_as_context(app_module, monkeypatch):
    """LLM-пайплайн должен передавать содержимое буфера обмена как контекст."""
    transcriber = make_transcriber(app_module)

    captured_context = {}

    class LLMStub:
        def __init__(self):
            self.last_token_usage = 0

        def process_text(self, text, system_prompt, *, context=None):
            captured_context["text"] = text
            captured_context["context"] = context
            self.last_token_usage = 5
            return "Ответ"

    monkeypatch.setattr(
        transcriber,
        "_run_transcription",
        lambda *_args: {"text": "Переведи это", "segments": [{"tokens": [1, 2]}]},
    )
    monkeypatch.setattr(transcriber, "_read_clipboard", lambda: "Hello world")
    monkeypatch.setattr(transcriber, "_add_to_history", lambda *_args: None)
    monkeypatch.setattr(transcriber, "_copy_text_to_clipboard", lambda *_args: None)
    monkeypatch.setattr(transcriber_module, "_save_defaults_int", lambda *_args: None)
    monkeypatch.setattr(transcriber_module, "notify_user", lambda *args: None)

    transcriber.transcribe_for_llm(make_audio(), "ru", llm_processor=LLMStub(), system_prompt="Исправь текст")

    assert captured_context["text"] == "Переведи это"
    assert captured_context["context"] == "Hello world"


def test_transcribe_for_llm_passes_none_context_when_clipboard_empty(app_module, monkeypatch):
    """LLM-пайплайн должен передавать context=None при пустом буфере обмена."""
    transcriber = make_transcriber(app_module)

    captured_context = {}

    class LLMStub:
        def __init__(self):
            self.last_token_usage = 0

        def process_text(self, text, system_prompt, *, context=None):
            captured_context["context"] = context
            self.last_token_usage = 5
            return "Ответ"

    monkeypatch.setattr(
        transcriber,
        "_run_transcription",
        lambda *_args: {"text": "Что угодно", "segments": [{"tokens": [1]}]},
    )
    monkeypatch.setattr(transcriber, "_read_clipboard", lambda: None)
    monkeypatch.setattr(transcriber, "_add_to_history", lambda *_args: None)
    monkeypatch.setattr(transcriber, "_copy_text_to_clipboard", lambda *_args: None)
    monkeypatch.setattr(transcriber_module, "_save_defaults_int", lambda *_args: None)
    monkeypatch.setattr(transcriber_module, "notify_user", lambda *args: None)

    transcriber.transcribe_for_llm(make_audio(), "ru", llm_processor=LLMStub(), system_prompt="Исправь")

    assert captured_context["context"] is None


def test_transcribe_for_llm_disables_clipboard_io_when_option_off(app_module, monkeypatch):
    """При выключенном LLM-буфере контекст не читается и ответ не пишется в clipboard."""
    transcriber = make_transcriber(app_module)
    transcriber.llm_clipboard_enabled = False
    copied = []
    read_calls = []
    captured_context = {}
    notifications = []

    class LLMStub:
        def __init__(self):
            self.last_token_usage = 2

        def process_text(self, text, system_prompt, *, context=None):
            del text, system_prompt
            captured_context["context"] = context
            return "Готово 🙂"

    monkeypatch.setattr(
        transcriber,
        "_run_transcription",
        lambda *_args: {"text": "О чем этот текст?", "segments": [{"tokens": [1]}]},
    )
    monkeypatch.setattr(transcriber, "_read_clipboard", lambda: read_calls.append(True) or "Текст из буфера")
    monkeypatch.setattr(transcriber, "_add_to_history", lambda *_args: None)
    monkeypatch.setattr(transcriber, "_copy_text_to_clipboard", copied.append)
    monkeypatch.setattr(transcriber_module, "_save_defaults_int", lambda *_args: None)
    monkeypatch.setattr(transcriber_module, "notify_user", lambda *args: notifications.append(args))

    transcriber.transcribe_for_llm(make_audio(), "ru", llm_processor=LLMStub(), system_prompt="Универсальный")

    assert read_calls == []
    assert captured_context["context"] is None
    assert copied == []
    assert notifications == [("🤖 LLM", "Готово 🙂")]


def test_transcribe_for_llm_skips_clipboard_for_unrelated_request(app_module, monkeypatch):
    """Нерелевантный запрос не должен тащить в LLM содержимое буфера обмена."""
    transcriber = make_transcriber(app_module)

    captured_context = {}

    class LLMStub:
        def __init__(self):
            self.last_token_usage = 0

        def process_text(self, text, system_prompt, *, context=None):
            del text, system_prompt
            captured_context["context"] = context
            self.last_token_usage = 5
            return "Анекдот 🙂"

    monkeypatch.setattr(
        transcriber,
        "_run_transcription",
        lambda *_args: {"text": "Расскажи анекдот.", "segments": [{"tokens": [1]}]},
    )
    monkeypatch.setattr(transcriber, "_read_clipboard", lambda: "технические логи LLM")
    monkeypatch.setattr(transcriber, "_add_to_history", lambda *_args: None)
    monkeypatch.setattr(transcriber, "_copy_text_to_clipboard", lambda *_args: None)
    monkeypatch.setattr(transcriber_module, "_save_defaults_int", lambda *_args: None)
    monkeypatch.setattr(transcriber_module, "notify_user", lambda *args: None)

    transcriber.transcribe_for_llm(make_audio(), "ru", llm_processor=LLMStub(), system_prompt="Универсальный")

    assert captured_context["context"] is None


def test_transcribe_for_llm_copies_clean_answer_and_notifies(app_module, monkeypatch):
    """LLM-пайплайн должен отдавать в буфер и уведомление уже очищенный короткий ответ."""
    transcriber = make_transcriber(app_module)
    copied = []
    notifications = []

    class LLMStub:
        def __init__(self):
            self.last_token_usage = 3

        def process_text(self, text, system_prompt, *, context=None):
            del text, system_prompt, context
            return "Привет! Всё готово 🙂"

    monkeypatch.setattr(
        transcriber,
        "_run_transcription",
        lambda *_args: {"text": "Скажи красиво", "segments": [{"tokens": [1]}]},
    )
    monkeypatch.setattr(transcriber, "_read_clipboard", lambda: None)
    monkeypatch.setattr(transcriber, "_add_to_history", lambda *_args: None)
    monkeypatch.setattr(transcriber, "_copy_text_to_clipboard", copied.append)
    monkeypatch.setattr(transcriber_module, "_save_defaults_int", lambda *_args: None)
    monkeypatch.setattr(transcriber_module, "notify_user", lambda *args: notifications.append(args))

    transcriber.transcribe_for_llm(make_audio(), "ru", llm_processor=LLMStub(), system_prompt="Исправь")

    assert copied == ["Привет! Всё готово 🙂"]
    assert notifications == [("🤖 LLM", "Привет! Всё готово 🙂")]


def test_transcribe_for_llm_defers_stale_response_when_newer_request_exists(app_module, monkeypatch):
    """Устаревший ответ LLM не должен перетирать буфер обмена поверх нового запроса."""
    transcriber = make_transcriber(app_module)
    copied = []
    notifications = []
    history_added = []

    class LLMStub:
        def __init__(self):
            self.last_token_usage = 4

        def process_text(self, text, system_prompt, *, context=None):
            del text, system_prompt, context
            return "Ответ агента"

    monkeypatch.setattr(
        transcriber,
        "_run_transcription",
        lambda *_args: {"text": "Подготовь ответ", "segments": [{"tokens": [1]}]},
    )
    monkeypatch.setattr(transcriber, "_read_clipboard", lambda: None)
    monkeypatch.setattr(transcriber, "_add_to_history", history_added.append)
    monkeypatch.setattr(transcriber, "_copy_text_to_clipboard", copied.append)
    monkeypatch.setattr(transcriber_module, "_save_defaults_int", lambda *_args: None)
    monkeypatch.setattr(transcriber_module, "notify_user", lambda *args: notifications.append(args))

    transcriber.transcribe_for_llm(
        make_audio(),
        "ru",
        llm_processor=LLMStub(),
        system_prompt="Исправь",
        should_deliver_result=lambda: False,
    )

    assert copied == []
    assert history_added == ["🤖 Ответ агента"]
    assert notifications == [
        ("MLX Whisper Dictation", "Ответ LLM сохранён в историю. Новый запрос диктовки получил приоритет."),
    ]


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
    monkeypatch.setattr(transcriber_module, "is_accessibility_trusted", lambda: True)
    monkeypatch.setattr(transcriber_module, "get_input_monitoring_status", lambda: True)
    monkeypatch.setattr(transcriber_module, "notify_user", lambda *args: None)

    transcriber.transcribe(make_audio(), "ru")

    assert clipboard_calls == []
