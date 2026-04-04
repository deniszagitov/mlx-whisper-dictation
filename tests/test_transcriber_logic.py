"""Юнит-тесты основного сценария распознавания и автовставки."""

from dataclasses import dataclass

import numpy as np
from src.domain.constants import Config

AppInfo = dict[str, str | int]


@dataclass(frozen=True, slots=True)
class DictationScenarioStep:
    """Описывает один шаг сценария последовательных диктовок."""

    transcribed_text: str
    keyboard_activity_after: bool = False
    application_change_after: AppInfo | None = None


@dataclass(frozen=True, slots=True)
class DictationScenario:
    """Описывает сценарий серии вызовов `transcribe`."""

    steps: tuple[DictationScenarioStep, ...]
    expected_inserted: tuple[str, ...]
    expected_history: tuple[str, ...] | None = None
    restore_trailing_period_on_next_dictation_enabled: bool = False
    initial_frontmost_application: AppInfo | None = None


@dataclass(frozen=True, slots=True)
class TranscribeToTextScenario:
    """Описывает сценарий для `transcribe_to_text`."""

    transcription_result: dict[str, object]
    expected_text: str | None


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


# Сценарии

NOTES_APP_INFO: AppInfo = {"name": "Notes", "bundle_id": "com.apple.Notes", "pid": 100}
SAFARI_APP_INFO: AppInfo = {"name": "Safari", "bundle_id": "com.apple.Safari", "pid": 200}

RESTORES_PERIOD_BEFORE_NEXT_DICTATION_SCENARIO = DictationScenario(
    steps=(
        DictationScenarioStep("привет."),
        DictationScenarioStep("как дела"),
    ),
    expected_inserted=("Привет", ". Как дела."),
    restore_trailing_period_on_next_dictation_enabled=True,
)

DOES_NOT_RESTORE_PERIOD_WHEN_FEATURE_DISABLED_SCENARIO = DictationScenario(
    steps=(
        DictationScenarioStep("привет."),
        DictationScenarioStep("как дела"),
    ),
    expected_inserted=("Привет", "Как дела"),
    restore_trailing_period_on_next_dictation_enabled=False,
)

KEYBOARD_ACTIVITY_CLEARS_PENDING_PERIOD_PREFIX_SCENARIO = DictationScenario(
    steps=(
        DictationScenarioStep("привет.", keyboard_activity_after=True),
        DictationScenarioStep("как дела"),
    ),
    expected_inserted=("Привет", "Как дела"),
    restore_trailing_period_on_next_dictation_enabled=True,
)

APPLICATION_CHANGE_CLEARS_PENDING_PERIOD_PREFIX_SCENARIO = DictationScenario(
    steps=(
        DictationScenarioStep("привет.", application_change_after=SAFARI_APP_INFO),
        DictationScenarioStep("как дела"),
    ),
    expected_inserted=("Привет", "Как дела"),
    restore_trailing_period_on_next_dictation_enabled=True,
    initial_frontmost_application=NOTES_APP_INFO,
)

KEEPS_RESTORING_PERIOD_ACROSS_MULTIPLE_DICTATIONS_SCENARIO = DictationScenario(
    steps=(
        DictationScenarioStep("первое после нажатия."),
        DictationScenarioStep("второе"),
        DictationScenarioStep("третье"),
        DictationScenarioStep("четвертое"),
    ),
    expected_inserted=(
        "Первое после нажатия",
        ". Второе.",
        " Третье.",
        " Четвертое.",
    ),
    restore_trailing_period_on_next_dictation_enabled=True,
)

KEEPS_EXISTING_TERMINAL_PUNCTUATION_INSIDE_CHAIN_SCENARIO = DictationScenario(
    steps=(
        DictationScenarioStep("первое после нажатия."),
        DictationScenarioStep("второе!"),
        DictationScenarioStep("третье"),
    ),
    expected_inserted=(
        "Первое после нажатия",
        ". Второе!",
        " Третье.",
    ),
    restore_trailing_period_on_next_dictation_enabled=True,
)

KEYBOARD_ACTIVITY_STARTS_NEW_CHAIN_AFTER_EXISTING_ONE_SCENARIO = DictationScenario(
    steps=(
        DictationScenarioStep("первое после нажатия."),
        DictationScenarioStep("второе", keyboard_activity_after=True),
        DictationScenarioStep("было нажатие."),
        DictationScenarioStep("теперь второе"),
    ),
    expected_inserted=(
        "Первое после нажатия",
        ". Второе.",
        "Было нажатие",
        ". Теперь второе.",
    ),
    restore_trailing_period_on_next_dictation_enabled=True,
)

TRANSCRIBE_TO_TEXT_POSTPROCESSING_SCENARIO = TranscribeToTextScenario(
    transcription_result={"text": "привет.", "segments": [{"tokens": [1]}]},
    expected_text="Привет",
)


# Общий код выполнения сценариев

def run_dictation_scenario(app_module, monkeypatch, scenario: DictationScenario):
    """Прогоняет сценарий серии диктовок и возвращает наблюдаемые эффекты."""
    transcriber = make_transcriber(app_module)
    transcriber.restore_trailing_period_on_next_dictation_enabled = (
        scenario.restore_trailing_period_on_next_dictation_enabled
    )
    inserted: list[str] = []
    history_added: list[str] = []
    transcription_results = iter([{"text": step.transcribed_text} for step in scenario.steps])

    monkeypatch.setattr(transcriber, "_run_transcription", lambda *_args: next(transcription_results))
    monkeypatch.setattr(transcriber, "_type_text_via_cgevent", inserted.append)
    monkeypatch.setattr(transcriber, "add_to_history", history_added.append)

    if scenario.initial_frontmost_application is not None:
        transcriber._frontmost_application_info_reader = lambda: scenario.initial_frontmost_application

    for step in scenario.steps:
        transcriber.transcribe(make_audio(), "ru")
        if step.keyboard_activity_after:
            transcriber.handle_keyboard_activity()
        if step.application_change_after is not None:
            transcriber.handle_frontmost_application_change(step.application_change_after)

    return inserted, history_added


def assert_dictation_scenario(app_module, monkeypatch, scenario: DictationScenario) -> None:
    """Проверяет сценарий серии диктовок через общий runner."""
    inserted, history_added = run_dictation_scenario(app_module, monkeypatch, scenario)
    expected_history = scenario.expected_history or scenario.expected_inserted

    assert inserted == list(scenario.expected_inserted)
    assert history_added == list(expected_history)


def run_transcribe_to_text_scenario(app_module, monkeypatch, scenario: TranscribeToTextScenario):
    """Прогоняет сценарий `transcribe_to_text` через общую настройку transcriber-а."""
    transcriber = make_transcriber(app_module)

    monkeypatch.setattr(transcriber, "_run_transcription", lambda *_args: scenario.transcription_result)
    monkeypatch.setattr(transcriber.settings_store, "save_int", lambda *_args: None)
    monkeypatch.setattr(transcriber, "_notify_user", lambda *args: None)

    return transcriber.transcribe_to_text(make_audio(), "ru")


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


def test_transcribe_applies_postprocessing_rules_in_order(app_module, monkeypatch):
    """После ASR текст должен пройти через включённую цепочку постобработки."""
    transcriber = make_transcriber(app_module)
    inserted: list[str] = []
    history_added: list[str] = []

    monkeypatch.setattr(transcriber, "_run_transcription", lambda *_args: {"text": "привет."})
    monkeypatch.setattr(transcriber, "_type_text_via_cgevent", inserted.append)
    monkeypatch.setattr(transcriber, "add_to_history", history_added.append)

    transcriber.transcribe(make_audio(), "ru")

    assert inserted == ["Привет"]
    assert history_added == ["Привет"]


def test_transcribe_can_disable_capitalization_rule(app_module, monkeypatch):
    """Правило заглавной буквы должно отключаться отдельно."""
    transcriber = make_transcriber(app_module)
    transcriber.capitalize_first_letter_enabled = False
    inserted: list[str] = []

    monkeypatch.setattr(transcriber, "_run_transcription", lambda *_args: {"text": "привет."})
    monkeypatch.setattr(transcriber, "_type_text_via_cgevent", inserted.append)
    monkeypatch.setattr(transcriber, "add_to_history", lambda *_args: None)

    transcriber.transcribe(make_audio(), "ru")

    assert inserted == ["привет"]


def test_transcribe_can_disable_trailing_period_rule(app_module, monkeypatch):
    """Правило удаления точки должно отключаться отдельно."""
    transcriber = make_transcriber(app_module)
    transcriber.remove_trailing_period_for_single_sentence_enabled = False
    inserted: list[str] = []

    monkeypatch.setattr(transcriber, "_run_transcription", lambda *_args: {"text": "привет."})
    monkeypatch.setattr(transcriber, "_type_text_via_cgevent", inserted.append)
    monkeypatch.setattr(transcriber, "add_to_history", lambda *_args: None)

    transcriber.transcribe(make_audio(), "ru")

    assert inserted == ["Привет."]


def test_transcribe_keeps_final_period_for_multiple_sentences(app_module, monkeypatch):
    """Финальная точка не должна убираться, если предложений больше одного."""
    transcriber = make_transcriber(app_module)
    inserted: list[str] = []

    monkeypatch.setattr(transcriber, "_run_transcription", lambda *_args: {"text": "привет. как дела."})
    monkeypatch.setattr(transcriber, "_type_text_via_cgevent", inserted.append)
    monkeypatch.setattr(transcriber, "add_to_history", lambda *_args: None)

    transcriber.transcribe(make_audio(), "ru")

    assert inserted == ["Привет. как дела."]


def test_transcribe_restores_period_before_next_dictation_when_enabled(app_module, monkeypatch):
    """Второй фрагмент цепочки должен получить '. ' в начале и точку в конце."""
    assert_dictation_scenario(app_module, monkeypatch, RESTORES_PERIOD_BEFORE_NEXT_DICTATION_SCENARIO)


def test_transcribe_does_not_restore_period_when_feature_disabled(app_module, monkeypatch):
    """При выключенной автоточке следующая диктовка не должна получать префикс."""
    assert_dictation_scenario(
        app_module,
        monkeypatch,
        DOES_NOT_RESTORE_PERIOD_WHEN_FEATURE_DISABLED_SCENARIO,
    )


def test_keyboard_activity_clears_pending_period_prefix(app_module, monkeypatch):
    """Любой ручной ввод с клавиатуры должен отменять автоточку на следующую диктовку."""
    assert_dictation_scenario(
        app_module,
        monkeypatch,
        KEYBOARD_ACTIVITY_CLEARS_PENDING_PERIOD_PREFIX_SCENARIO,
    )


def test_application_change_clears_pending_period_prefix(app_module, monkeypatch):
    """Смена активного приложения должна отменять автоточку на следующую диктовку."""
    assert_dictation_scenario(
        app_module,
        monkeypatch,
        APPLICATION_CHANGE_CLEARS_PENDING_PERIOD_PREFIX_SCENARIO,
    )


def test_transcribe_keeps_restoring_period_across_multiple_dictations(app_module, monkeypatch):
    """Без ручного ввода цепочка должна оформляться как последовательность предложений."""
    assert_dictation_scenario(
        app_module,
        monkeypatch,
        KEEPS_RESTORING_PERIOD_ACROSS_MULTIPLE_DICTATIONS_SCENARIO,
    )


def test_transcribe_keeps_existing_terminal_punctuation_inside_chain(app_module, monkeypatch):
    """Внутри цепочки существующий знак конца предложения не должен заменяться точкой."""
    assert_dictation_scenario(
        app_module,
        monkeypatch,
        KEEPS_EXISTING_TERMINAL_PUNCTUATION_INSIDE_CHAIN_SCENARIO,
    )


def test_keyboard_activity_starts_new_chain_after_existing_one(app_module, monkeypatch):
    """После ручного ввода следующая диктовка должна начинать новую цепочку заново."""
    assert_dictation_scenario(
        app_module,
        monkeypatch,
        KEYBOARD_ACTIVITY_STARTS_NEW_CHAIN_AFTER_EXISTING_ONE_SCENARIO,
    )


def test_transcribe_to_text_applies_postprocessing_rules(app_module, monkeypatch):
    """transcribe_to_text тоже должен возвращать уже постобработанный текст."""
    result = run_transcribe_to_text_scenario(
        app_module,
        monkeypatch,
        TRANSCRIBE_TO_TEXT_POSTPROCESSING_SCENARIO,
    )

    assert result == TRANSCRIBE_TO_TEXT_POSTPROCESSING_SCENARIO.expected_text
