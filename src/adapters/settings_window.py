"""Нативное окно настроек Dictator для macOS.

Окно открывается из menu bar и остаётся адаптером поверх того же
контроллера, что и `StatusBarApp`: состояние читается из AppSnapshot,
команды делегируются в DictationApp.
"""

from __future__ import annotations

import contextlib
import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, cast

import AppKit
import objc
from PyObjCTools.AppHelper import callAfter  # type: ignore[import-untyped]

from ..domain.constants import Config
from ..domain.reader_constants import (
    RSVP_CHUNK_SIZE_OPTIONS,
    RSVP_FONT_SIZE_OPTIONS,
    RSVP_WPM_OPTIONS,
    TTS_ENGINE_LABELS,
    TTS_MAX_MINUTES_OPTIONS,
    TTS_MLX_MODEL_OPTIONS,
    TTS_RATE_MULTIPLIER_MAX,
    TTS_RATE_MULTIPLIER_MIN,
    TTS_RATE_MULTIPLIER_STEP,
)
from ..domain.types import DownloadableModelStatus

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence

    from ..domain.ports import StatusBarControllerProtocol
    from ..domain.reader_types import TTSVoice
    from ..domain.types import AppSnapshot

LOGGER = logging.getLogger(__name__)

WINDOW_WIDTH = 980.0
WINDOW_HEIGHT = 680.0
TOOLBAR_HEIGHT = 126.0
TOOLBAR_ITEM_WIDTH = 76.0
CONTENT_MIN_WIDTH = 640.0
CONTENT_MARGIN = 76.0
ROW_HEIGHT = 58.0
SECTION_GAP = 24.0
HISTORY_PREVIEW_LENGTH = 90

NAVIGATION_ITEMS: tuple[NavigationItem, ...]


@dataclass(frozen=True, slots=True)
class NavigationItem:
    """Один пункт навигации окна настроек."""

    identifier: str
    title: str
    icon: str
    group: int


@dataclass(frozen=True, slots=True)
class SettingsOption:
    """Значение для select/segmented control."""

    value: object
    title: str


@dataclass(frozen=True, slots=True)
class SettingsRowSpec:
    """Один ряд настроек в секции."""

    title: str
    subtitle: str | None = None
    control: str = "none"
    value: object = None
    action: str | None = None
    options: tuple[SettingsOption, ...] = ()
    button_title: str = ""
    secondary_action: str | None = None
    secondary_button_title: str = ""
    tone: str = "neutral"
    enabled: bool = True


@dataclass(frozen=True, slots=True)
class SettingsSectionSpec:
    """Группа рядов настроек."""

    title: str | None
    rows: tuple[SettingsRowSpec, ...]
    footer: str | None = None


@dataclass(frozen=True, slots=True)
class SettingsScreenSpec:
    """Описание одного экрана настроек."""

    identifier: str
    title: str
    sections: tuple[SettingsSectionSpec, ...]
    description: str = ""


@dataclass(frozen=True, slots=True)
class _ControlPayload:
    """Данные, привязанные к AppKit control через numeric tag."""

    action: str
    value: object = None
    options: tuple[SettingsOption, ...] = ()


NAVIGATION_ITEMS = (
    NavigationItem("home", "Главная", "⌂", 0),
    NavigationItem("recognition", "STT", "🎙", 1),
    NavigationItem("llm", "LLM", "🤖", 1),
    NavigationItem("tts", "TTS", "🔈", 1),
    NavigationItem("rsvp", "RSVP", "👀", 1),
    NavigationItem("input", "Ввод текста", "⌨", 2),
    NavigationItem("hotkeys", "Хоткеи", "⌘", 2),
    NavigationItem("audio", "Аудио", "〰", 2),
    NavigationItem("history", "История", "📋", 3),
    NavigationItem("permissions", "Доступы", "🛂", 3),
    NavigationItem("about", "О приложении", "ⓘ", 3),
)


def _call_on_main_thread(callback: Callable[..., None], *args: object) -> None:
    """Гарантирует, что AppKit-обновление выполняется на главном потоке."""
    if AppKit.NSThread.isMainThread():
        callback(*args)
        return
    callAfter(callback, *args)


def _short_name(value: object) -> str:
    """Возвращает короткое имя модели или устройства для компактного UI."""
    return str(value or "").rsplit("/", maxsplit=1)[-1]


def _fallback_model_status(model_id: str) -> DownloadableModelStatus:
    """Возвращает нейтральный статус модели, если snapshot ещё не знает о ней."""
    return DownloadableModelStatus(
        model_id=model_id,
        title=_short_name(model_id),
        state="missing",
        status_text="Статус неизвестен",
        progress_percent=None,
        can_download=False,
        can_delete=False,
    )


def _model_status(snapshot: AppSnapshot, model_id: str) -> DownloadableModelStatus:
    """Возвращает статус модели из snapshot."""
    return snapshot.downloadable_models.get(model_id, _fallback_model_status(model_id))


def _model_option_title(snapshot: AppSnapshot, model_id: str) -> str:
    """Формирует подпись модели с маркером локального cache."""
    status = _model_status(snapshot, model_id)
    if status.state == "downloaded":
        marker = "загружено"
    elif status.state == "downloading":
        marker = f"загрузка {(status.progress_percent or 0):.0f}%"
    elif status.state == "error":
        marker = "ошибка"
    elif status.state == "missing":
        marker = "не загружено"
    else:
        marker = status.status_text.lower()
    return f"{_short_name(model_id)} · {marker}"


def _format_max_time(value: float | None) -> str:
    """Форматирует лимит записи для окна настроек."""
    return "∞" if value is None else Config.format_max_time_status(value)


def _format_tts_rate(value: float) -> str:
    """Форматирует множитель скорости TTS."""
    normalized = round(float(value), 2)
    if normalized.is_integer():
        return f"{int(normalized)}×"
    return f"{normalized:.2f}".rstrip("0").rstrip(".") + "×"


def _format_tts_max_minutes(value: int) -> str:
    """Форматирует лимит длительности TTS."""
    return "∞" if value <= 0 else f"{value} мин"


def _permission_tone(value: bool | None) -> str:
    """Возвращает визуальный тон статуса разрешения."""
    if value is True:
        return "ok"
    if value is False:
        return "warn"
    return "neutral"


def _permission_label(value: bool | None) -> str:
    """Возвращает русскую подпись статуса разрешения."""
    if value is True:
        return "Предоставлено"
    if value is False:
        return "Не предоставлено"
    return "Неизвестно"


def _language_options(snapshot: AppSnapshot) -> tuple[SettingsOption, ...]:
    """Возвращает варианты языка распознавания."""
    if not snapshot.languages:
        return (SettingsOption(None, "Автоопределение"),)
    return tuple(SettingsOption(language, language) for language in snapshot.languages)


def _max_time_options(snapshot: AppSnapshot) -> tuple[SettingsOption, ...]:
    """Возвращает варианты лимита записи."""
    return tuple(SettingsOption(value, _format_max_time(value)) for value in snapshot.max_time_options)


def _input_device_options(snapshot: AppSnapshot) -> tuple[SettingsOption, ...]:
    """Возвращает варианты микрофона для окна настроек."""
    options = [SettingsOption(None, "Системный по умолчанию")]
    options.extend(
        SettingsOption(device["index"], f"[{device['index']}] {device['name']}") for device in snapshot.input_devices
    )
    return tuple(options)


def _tts_voice_options(snapshot: AppSnapshot, voices: Sequence[TTSVoice]) -> tuple[SettingsOption, ...]:
    """Возвращает варианты системного голоса TTS."""
    options = [SettingsOption(None, "Авто: русский голос")]
    options.extend(SettingsOption(voice.identifier, voice.menu_title) for voice in voices)
    selected = snapshot.reader_tts_voice_id
    if selected is not None and all(option.value != selected for option in options):
        options.append(SettingsOption(selected, selected))
    return tuple(options)


def build_settings_screens(snapshot: AppSnapshot, *, tts_voices: Sequence[TTSVoice] = ()) -> tuple[SettingsScreenSpec, ...]:
    """Строит чистое описание экранов настроек из snapshot."""
    current_input_value = None if snapshot.current_input_device is None else snapshot.current_input_device["index"]
    tts_model_options = tuple(SettingsOption(model, _model_option_title(snapshot, model)) for model in TTS_MLX_MODEL_OPTIONS)
    if snapshot.reader_tts_mlx_model not in {option.value for option in tts_model_options}:
        tts_model_options += (
            SettingsOption(snapshot.reader_tts_mlx_model, _model_option_title(snapshot, snapshot.reader_tts_mlx_model)),
        )

    status_text = {
        Config.STATUS_IDLE: "Готов слушать",
        Config.STATUS_RECORDING: f"Запись: {snapshot.elapsed_time} с",
        Config.STATUS_TRANSCRIBING: "Распознавание…",
        Config.STATUS_LLM_PROCESSING: "Обработка LLM…",
    }.get(snapshot.state, "Состояние неизвестно")
    record_action = "stop_recording" if snapshot.started else "start_recording"
    record_title = "Остановить" if snapshot.started else "Начать запись"

    screens = {
        "home": SettingsScreenSpec(
            "home",
            "Главная",
            (
                SettingsSectionSpec(
                    None,
                    (
                        SettingsRowSpec(
                            "Статус",
                            "Основной сценарий записи доступен из этого окна и из menu bar.",
                            "status",
                            status_text,
                            tone="warn" if snapshot.started else "ok",
                        ),
                        SettingsRowSpec(
                            "Диктовка",
                            f"Модель: {_short_name(snapshot.model_repo)} · язык: {snapshot.current_language or 'авто'}",
                            "button",
                            action=record_action,
                            button_title=record_title,
                        ),
                    ),
                ),
                SettingsSectionSpec(
                    "Быстрые действия",
                    (
                        SettingsRowSpec(
                            "Запустить RSVP",
                            "Читает текст из системного буфера обмена, не изменяя его.",
                            "button",
                            action="toggle_rsvp",
                            button_title="Запустить",
                        ),
                        SettingsRowSpec(
                            "Запустить TTS",
                            "Озвучивает текст из системного буфера обмена локально.",
                            "button",
                            action="toggle_tts",
                            button_title="Запустить",
                        ),
                        SettingsRowSpec("LLM-пайплайн", "Голос → Whisper → LLM → буфер.", "label", snapshot.llm_hotkey_status),
                    ),
                ),
                SettingsSectionSpec(
                    "Сводка",
                    (
                        SettingsRowSpec("Whisper-модель", control="label", value=_short_name(snapshot.model_repo)),
                        SettingsRowSpec("Основной хоткей", control="label", value=snapshot.hotkey_status),
                        SettingsRowSpec("Лимит записи", control="label", value=_format_max_time(snapshot.max_time)),
                        SettingsRowSpec("Токены LLM", control="label", value=f"{snapshot.total_tokens:,}".replace(",", " ")),
                    ),
                ),
            ),
            "Быстрый обзор состояния Dictator: запись, reader-сценарии и ключевые параметры, которые чаще всего нужны во время работы.",
        ),
        "recognition": SettingsScreenSpec(
            "recognition",
            "STT",
            (
                SettingsSectionSpec(
                    "Модель",
                    (
                        SettingsRowSpec(
                            "Whisper-модель",
                            "Модели работают локально через MLX.",
                            "select",
                            snapshot.model_repo,
                            "change_model",
                            tuple(SettingsOption(model, _model_option_title(snapshot, model)) for model in snapshot.model_options),
                        ),
                        SettingsRowSpec(
                            "Состояние Whisper-модели",
                            "Если модель не загружена, выбор запустит скачивание в локальный cache.",
                            "model_status",
                            _model_status(snapshot, snapshot.model_repo),
                            "download_model",
                            secondary_action="delete_downloaded_model",
                        ),
                        SettingsRowSpec(
                            "Язык распознавания",
                            "Подсказка для коротких фраз и компактных моделей.",
                            "select",
                            snapshot.current_language,
                            "change_language",
                            _language_options(snapshot),
                        ),
                        SettingsRowSpec(
                            "Длительность записи",
                            "После лимита запись остановится автоматически.",
                            "segmented",
                            snapshot.max_time,
                            "change_max_time",
                            _max_time_options(snapshot),
                        ),
                    ),
                    "Распознавание выполняется локально, без облачных сервисов.",
                ),
                SettingsSectionSpec(
                    "Производительность",
                    (
                        SettingsRowSpec(
                            "Режим работы",
                            "Баланс между скоростью ответа и нагрузкой на Apple Silicon.",
                            "segmented",
                            snapshot.performance_mode,
                            "change_performance_mode",
                            tuple(
                                SettingsOption(mode, title) for mode, title in Config.PERFORMANCE_MODE_LABELS.items()
                            ),
                        ),
                    ),
                ),
                SettingsSectionSpec(
                    "Постобработка текста",
                    (
                        SettingsRowSpec(
                            "Первая буква с заглавной",
                            control="toggle",
                            value=snapshot.capitalize_first_letter_enabled,
                            action="toggle_capitalize_first_letter",
                        ),
                        SettingsRowSpec(
                            "Убирать точку в конце одного предложения",
                            "Если диктовка состоит из одной фразы.",
                            "toggle",
                            snapshot.remove_trailing_period_for_single_sentence_enabled,
                            "toggle_remove_trailing_period_for_single_sentence",
                        ),
                        SettingsRowSpec(
                            "Связывать диктовки в цепочку",
                            "Восстанавливать точку, если следом идёт ещё одна диктовка.",
                            "toggle",
                            snapshot.restore_trailing_period_on_next_dictation_enabled,
                            "toggle_restore_trailing_period_on_next_dictation",
                        ),
                    ),
                    "Правила применяются перед вставкой распознанного текста.",
                ),
            ),
            "STT означает Speech-to-Text: приложение записывает голос, распознаёт речь локальной MLX ASR-моделью "
            "и передаёт текст в сценарий вставки или LLM.",
        ),
        "tts": SettingsScreenSpec(
            "tts",
            "TTS",
            (
                SettingsSectionSpec(
                    "TTS — озвучивание",
                    (
                        SettingsRowSpec(
                            "Запустить TTS",
                            f"Текущий хоткей: {snapshot.tts_hotkey_status}.",
                            "button",
                            action="toggle_tts",
                            button_title="Запустить",
                        ),
                        SettingsRowSpec(
                            "LLM-предобработка",
                            "Чистит и нормализует текст перед чтением.",
                            "toggle",
                            snapshot.reader_preprocess_enabled,
                            "toggle_reader_preprocess",
                        ),
                    ),
                    "TTS читает только системный буфер обмена и не изменяет его.",
                ),
                SettingsSectionSpec(
                    "Голос",
                    (
                        SettingsRowSpec(
                            "Backend",
                            control="segmented",
                            value=snapshot.reader_tts_engine,
                            action="change_reader_tts_engine",
                            options=tuple(SettingsOption(engine, title) for engine, title in TTS_ENGINE_LABELS.items()),
                        ),
                        SettingsRowSpec(
                            "MLX-модель",
                            "Локальная модель синтеза для MLX backend.",
                            "select",
                            snapshot.reader_tts_mlx_model,
                            "change_reader_tts_mlx_model",
                            tts_model_options,
                        ),
                        SettingsRowSpec(
                            "Состояние MLX TTS-модели",
                            "Для Apple AVSpeech скачивание не нужно; для MLX backend модель хранится локально.",
                            "model_status",
                            _model_status(snapshot, snapshot.reader_tts_mlx_model),
                            "download_model",
                            secondary_action="delete_downloaded_model",
                        ),
                        SettingsRowSpec(
                            "Задать MLX-модель",
                            "Точное имя локальной модели или repo id.",
                            "button",
                            action="prompt_reader_tts_mlx_model",
                            button_title="Изменить…",
                        ),
                        SettingsRowSpec(
                            "Описание MLX-голоса",
                            "Промпт для VoiceDesign.",
                            "button",
                            action="prompt_reader_tts_mlx_voice_description",
                            button_title="Изменить…",
                        ),
                        SettingsRowSpec(
                            "Голос",
                            control="select",
                            value=snapshot.reader_tts_voice_id,
                            action="change_reader_tts_voice",
                            options=_tts_voice_options(snapshot, tts_voices),
                        ),
                        SettingsRowSpec(
                            "Скорость речи",
                            control="stepper",
                            value=_format_tts_rate(snapshot.reader_tts_rate_multiplier),
                            action="decrease_reader_tts_rate_multiplier",
                            secondary_action="increase_reader_tts_rate_multiplier",
                        ),
                    ),
                ),
                SettingsSectionSpec(
                    "Лимиты",
                    (
                        SettingsRowSpec(
                            "Максимальная длительность",
                            "Принудительно остановить длинное озвучивание.",
                            "segmented",
                            snapshot.reader_tts_max_minutes,
                            "change_reader_tts_max_minutes",
                            tuple(SettingsOption(value, _format_tts_max_minutes(value)) for value in TTS_MAX_MINUTES_OPTIONS),
                        ),
                    ),
                ),
            ),
            "TTS означает Text-to-Speech: Reader берёт текст из системного буфера обмена и озвучивает его локально "
            "через Apple AVSpeech или MLX Qwen3-TTS.",
        ),
        "rsvp": SettingsScreenSpec(
            "rsvp",
            "RSVP",
            (
                SettingsSectionSpec(
                    "RSVP — пословное чтение",
                    (
                        SettingsRowSpec(
                            "Запустить RSVP",
                            f"Текущий хоткей: {snapshot.rsvp_hotkey_status}.",
                            "button",
                            action="toggle_rsvp",
                            button_title="Запустить",
                        ),
                        SettingsRowSpec(
                            "LLM-предобработка",
                            "Очищает разметку и сноски перед показом.",
                            "toggle",
                            snapshot.reader_preprocess_enabled,
                            "toggle_reader_preprocess",
                        ),
                    ),
                    "Текст берётся из системного буфера обмена, содержимое буфера не меняется.",
                ),
                SettingsSectionSpec(
                    "Параметры чтения",
                    (
                        SettingsRowSpec(
                            "Скорость чтения",
                            "Слов в минуту.",
                            "stepper",
                            f"{snapshot.reader_rsvp_wpm} wpm",
                            "decrease_reader_rsvp_wpm",
                            secondary_action="increase_reader_rsvp_wpm",
                        ),
                        SettingsRowSpec(
                            "Размер chunk-а",
                            "Сколько слов показывать одновременно.",
                            "segmented",
                            snapshot.reader_rsvp_chunk_size,
                            "change_reader_rsvp_chunk_size",
                            tuple(SettingsOption(value, str(value)) for value in RSVP_CHUNK_SIZE_OPTIONS),
                        ),
                        SettingsRowSpec(
                            "Размер шрифта",
                            control="segmented",
                            value=snapshot.reader_rsvp_font_size,
                            action="change_reader_rsvp_font_size",
                            options=tuple(SettingsOption(value, str(value)) for value in RSVP_FONT_SIZE_OPTIONS),
                        ),
                    ),
                ),
            ),
            "RSVP означает Rapid Serial Visual Presentation: текст из буфера показывается короткими кадрами, "
            "чтобы читать быстрее без прокрутки документа.",
        ),
        "input": SettingsScreenSpec(
            "input",
            "Ввод текста",
            (
                SettingsSectionSpec(
                    "Метод вставки",
                    (
                        SettingsRowSpec(
                            "Прямой ввод",
                            "CGEvent печатает текст в активное поле.",
                            "toggle",
                            snapshot.paste_cgevent_enabled,
                            "toggle_paste_cgevent",
                        ),
                        SettingsRowSpec(
                            "Accessibility API",
                            "Самый надёжный способ автовставки.",
                            "toggle",
                            snapshot.paste_ax_enabled,
                            "toggle_paste_ax",
                        ),
                        SettingsRowSpec(
                            "Буфер обмена + ⌘V",
                            "Резервный способ, результат не теряется.",
                            "toggle",
                            snapshot.paste_clipboard_enabled,
                            "toggle_paste_clipboard",
                        ),
                    ),
                    "Если автовставка не сработает, текст останется доступен в истории и fallback-буфере.",
                ),
                SettingsSectionSpec(
                    "Приватность",
                    (
                        SettingsRowSpec(
                            "Приватный режим",
                            "Не сохранять новые распознанные тексты в историю.",
                            "toggle",
                            snapshot.private_mode_enabled,
                            "toggle_private_mode",
                        ),
                    ),
                ),
                SettingsSectionSpec(
                    "Индикация записи",
                    (
                        SettingsRowSpec(
                            "Уведомление о старте записи",
                            control="toggle",
                            value=snapshot.show_recording_notification,
                            action="toggle_recording_notification",
                        ),
                        SettingsRowSpec(
                            "Индикатор у курсора",
                            "Маленькая точка рядом с текущей точкой ввода.",
                            "toggle",
                            snapshot.show_recording_overlay,
                            "toggle_recording_overlay",
                        ),
                        SettingsRowSpec(
                            "Время записи в menu bar",
                            control="toggle",
                            value=snapshot.show_recording_time_in_menu_bar,
                            action="toggle_recording_time_in_menu_bar",
                        ),
                    ),
                ),
            ),
            "Здесь задаётся, как распознанный текст попадает в активное поле ввода и какие резервные сценарии "
            "сохраняют результат, если автовставка недоступна.",
        ),
        "hotkeys": SettingsScreenSpec(
            "hotkeys",
            "Хоткеи",
            (
                SettingsSectionSpec(
                    "Глобальные хоткеи",
                    (
                        SettingsRowSpec(
                            "Основная запись",
                            snapshot.hotkey_status,
                            "button",
                            action="change_hotkey",
                            button_title="Изменить…",
                        ),
                        SettingsRowSpec(
                            "Дополнительная запись",
                            snapshot.secondary_hotkey_status,
                            "button",
                            action="change_secondary_hotkey",
                            button_title="Изменить…",
                        ),
                        SettingsRowSpec(
                            "LLM-пайплайн",
                            snapshot.llm_hotkey_status,
                            "button",
                            action="change_llm_hotkey",
                            button_title="Изменить…",
                        ),
                        SettingsRowSpec(
                            "RSVP",
                            snapshot.rsvp_hotkey_status,
                            "button",
                            action="change_rsvp_hotkey",
                            button_title="Изменить…",
                        ),
                        SettingsRowSpec(
                            "TTS",
                            snapshot.tts_hotkey_status,
                            "button",
                            action="change_tts_hotkey",
                            button_title="Изменить…",
                        ),
                    ),
                    "Хоткеи требуют Accessibility и Input Monitoring. Запись из menu bar работает отдельно от хоткея.",
                ),
            ),
            "Глобальные хоткеи запускают запись, LLM-пайплайн и Reader без открытия окна. Даже при проблемах "
            "с хоткеями запись остаётся доступной из menu bar.",
        ),
        "audio": SettingsScreenSpec(
            "audio",
            "Аудио",
            (
                SettingsSectionSpec(
                    "Микрофон",
                    (
                        SettingsRowSpec(
                            "Устройство ввода",
                            control="select",
                            value=current_input_value,
                            action="change_input_device",
                            options=_input_device_options(snapshot),
                        ),
                        SettingsRowSpec(
                            "Текущий профиль",
                            control="label",
                            value=Config.audio_profile_label(snapshot.audio_profile_name),
                        ),
                    ),
                ),
                SettingsSectionSpec(
                    "Уровни",
                    (
                        SettingsRowSpec(
                            "Профиль MacBook HQ",
                            "Автоматически улучшает встроенный микрофон MacBook.",
                            "toggle",
                            snapshot.high_quality_mac_builtin_enabled,
                            "toggle_high_quality_mac_builtin",
                        ),
                        SettingsRowSpec(
                            "Бережная нормализация",
                            "Подтягивает тихую речь, не ломая громкую.",
                            "toggle",
                            snapshot.gain_normalization_enabled,
                            "toggle_gain_normalization",
                        ),
                        SettingsRowSpec("Voice Isolation", control="label", value="Включается вручную в Control Center macOS"),
                    ),
                ),
                SettingsSectionSpec(
                    "Файлы записей",
                    (
                        SettingsRowSpec(
                            "Автоочистка WAV через 24 часа",
                            control="toggle",
                            value=snapshot.audio_artifact_cleanup_enabled,
                            action="toggle_audio_artifact_cleanup",
                        ),
                        SettingsRowSpec(
                            "Папка WAV-записей",
                            control="button",
                            action="open_recordings_directory",
                            button_title="Открыть в Finder",
                        ),
                    ),
                ),
                SettingsSectionSpec(
                    "Быстрые профили",
                    (
                        *(
                            SettingsRowSpec(
                                profile.name,
                                "Сохранённый набор микрофона и базовых настроек.",
                                "button_pair",
                                profile.name,
                                "apply_microphone_profile",
                                button_title="Применить",
                                secondary_action="delete_microphone_profile",
                                secondary_button_title="Удалить",
                            )
                            for profile in snapshot.microphone_profiles
                        ),
                        SettingsRowSpec(
                            "Добавить текущий профиль",
                            control="button",
                            action="add_current_microphone_profile",
                            button_title="Добавить…",
                        ),
                    ),
                    "Профиль сохраняет текущий микрофон и связанные настройки.",
                ),
            ),
            "Аудио-раздел управляет микрофоном, профилем записи, бережной нормализацией и диагностическими "
            "WAV-файлами для локальной отладки.",
        ),
        "llm": SettingsScreenSpec(
            "llm",
            "LLM",
            (
                SettingsSectionSpec(
                    "Модель LLM",
                    (
                        SettingsRowSpec(
                            "Активная модель",
                            "Используется для диктовки и Reader-предобработки.",
                            "select",
                            snapshot.llm_model_repo,
                            "change_llm_model",
                            tuple(SettingsOption(model, _model_option_title(snapshot, model)) for model in snapshot.llm_model_options),
                        ),
                        SettingsRowSpec(
                            "Состояние LLM-модели",
                            "Если модель не загружена, выбор запустит скачивание перед локальной генерацией.",
                            "model_status",
                            _model_status(snapshot, snapshot.llm_model_repo),
                            "download_model",
                            secondary_action="delete_downloaded_model",
                        ),
                        SettingsRowSpec(
                            "Системный промпт",
                            control="select",
                            value=snapshot.llm_prompt_name,
                            action="change_llm_prompt",
                            options=tuple(SettingsOption(name, name) for name in Config.LLM_PROMPT_PRESETS),
                        ),
                        SettingsRowSpec(
                            "Использовать буфер обмена",
                            "Передавать LLM содержимое буфера как контекст.",
                            "toggle",
                            snapshot.llm_clipboard_enabled,
                            "toggle_llm_clipboard",
                        ),
                    ),
                    "Все LLM-функции используют локальную модель.",
                ),
                SettingsSectionSpec(
                    "Загрузка",
                    (
                        SettingsRowSpec(
                            "Статус модели",
                            control="button" if snapshot.llm_download_interactive else "label",
                            value=snapshot.llm_download_title,
                            action="download_llm_model" if snapshot.llm_download_interactive else None,
                            button_title=snapshot.llm_download_title,
                        ),
                    ),
                ),
                SettingsSectionSpec(
                    "Расход токенов",
                    (SettingsRowSpec("Всего обработано локально", control="label", value=f"{snapshot.total_tokens:,}".replace(",", " ")),),
                ),
            ),
            "LLM означает Large Language Model: локальная языковая модель исправляет, переводит, резюмирует "
            "или подготавливает текст без облачного API.",
        ),
        "history": SettingsScreenSpec(
            "history",
            "История",
            (
                SettingsSectionSpec(
                    "Obsidian-архив",
                    (
                        SettingsRowSpec(
                            "Спросить историю",
                            "Локальная LLM ищет ответ по дневным markdown-файлам Obsidian.",
                            "button",
                            "search",
                            "search_obsidian_history",
                            button_title="Спросить…",
                        ),
                        SettingsRowSpec(
                            "Obsidian vault",
                            control="label",
                            value=snapshot.obsidian_vault_path or "не настроен",
                        ),
                        SettingsRowSpec(
                            "Папка архива",
                            control="label",
                            value=snapshot.obsidian_history_directory or "не настроена",
                        ),
                        SettingsRowSpec(
                            "Открыть архив в Finder",
                            "Записи лежат в Daily Notes/Dictator, а темы создают Obsidian graph по смысловым узлам.",
                            "button",
                            snapshot.obsidian_history_directory,
                            "open_obsidian_history_directory",
                            button_title="Открыть…",
                        ),
                    ),
                    "Поиск работает по дневным заметкам Obsidian, а локальная LLM добавляет короткие темы для graph view.",
                ),
                SettingsSectionSpec(
                    "Темы за сегодня",
                    tuple(
                        SettingsRowSpec(topic, control="label", value=f"{mentions}×")
                        for topic, mentions in snapshot.obsidian_today_topics
                    )
                    or (
                        SettingsRowSpec(
                            "Тем пока нет",
                            "После первых записей Dictator покажет здесь узлы дневного graph.",
                        ),
                    ),
                    "Это сводка по сегодняшней заметке Dictator. Те же узлы пишутся в папку Темы и видны в Obsidian graph.",
                ),
                SettingsSectionSpec(
                    "Последние распознанные тексты",
                    tuple(
                        SettingsRowSpec(
                            text.replace("\n", " ")[:HISTORY_PREVIEW_LENGTH]
                            + ("…" if len(text) > HISTORY_PREVIEW_LENGTH else ""),
                            "Нажмите, чтобы вернуть полный текст в буфер обмена.",
                            "button",
                            text,
                            "copy_history_text",
                            button_title="Скопировать",
                        )
                        for text in snapshot.history
                    )
                    or (SettingsRowSpec("История пуста", "Новые диктовки появятся здесь, если приватный режим выключен."),),
                    "Последние элементы берутся из локального Obsidian-архива. В приватном режиме новые записи туда не попадают.",
                ),
            ),
            "История работает как дневник диктовок: новые записи складываются в Obsidian, а локальная LLM умеет "
            "искать по ним прошлые мысли, запросы и ответы.",
        ),
        "permissions": SettingsScreenSpec(
            "permissions",
            "Доступы",
            (
                SettingsSectionSpec(
                    "Разрешения macOS",
                    (
                        SettingsRowSpec(
                            "Accessibility",
                            "Нужен для автовставки и части сценариев хоткеев.",
                            "status_button",
                            _permission_label(snapshot.permission_status.get("accessibility")),
                            "request_accessibility_access",
                            button_title="Запросить…",
                            tone=_permission_tone(snapshot.permission_status.get("accessibility")),
                        ),
                        SettingsRowSpec(
                            "Input Monitoring",
                            "Позволяет отслеживать глобальные сочетания клавиш.",
                            "status_button",
                            _permission_label(snapshot.permission_status.get("input_monitoring")),
                            "request_input_monitoring_access",
                            button_title="Запросить…",
                            tone=_permission_tone(snapshot.permission_status.get("input_monitoring")),
                        ),
                        SettingsRowSpec(
                            "Microphone",
                            "Без доступа к микрофону диктовка не начнётся.",
                            "status",
                            _permission_label(snapshot.permission_status.get("microphone")),
                            tone=_permission_tone(snapshot.permission_status.get("microphone")),
                        ),
                    ),
                    "После обновления .app через перетаскивание macOS может потребовать выдать права заново.",
                ),
            ),
            "Доступы macOS показывают, хватает ли приложению прав на микрофон, глобальные хоткеи и автовставку "
            "текста в активное приложение.",
        ),
        "about": SettingsScreenSpec(
            "about",
            "О приложении",
            (
                SettingsSectionSpec(
                    "Диктатор",
                    (
                        SettingsRowSpec(
                            "Локальное распознавание",
                            "MLX Whisper без облачных сервисов.",
                            "status",
                            "Офлайн",
                            tone="ok",
                        ),
                        SettingsRowSpec("Платформа", control="label", value="macOS · Apple Silicon"),
                        SettingsRowSpec(
                            "Логи",
                            "~/Library/Logs/whisper-dictation/",
                            "button",
                            action="open_recordings_directory",
                            button_title="Открыть…",
                        ),
                    ),
                ),
            ),
            "Сведения о приложении и локальных файлах диагностики. Dictator остаётся menu bar-приложением "
            "и не создаёт основное окно при запуске.",
        ),
    }

    return tuple(screens[item.identifier] for item in NAVIGATION_ITEMS)


def _prompt_text(title: str, message: str, default_text: str = "") -> str | None:
    """Открывает нативный диалог ввода текста."""
    AppKit.NSApplication.sharedApplication().activateIgnoringOtherApps_(True)
    input_field = AppKit.NSTextField.alloc().initWithFrame_(AppKit.NSMakeRect(0, 0, 420, 24))
    input_field.setStringValue_(default_text)
    input_field.setEditable_(True)
    input_field.setSelectable_(True)
    input_field.setBezeled_(True)
    input_field.setDrawsBackground_(True)

    alert = AppKit.NSAlert.alloc().init()
    alert.setMessageText_(title)
    alert.setInformativeText_(message)
    alert.addButtonWithTitle_("Сохранить")
    alert.addButtonWithTitle_("Отмена")
    alert.setAccessoryView_(input_field)
    alert.window().setInitialFirstResponder_(input_field)
    input_field.selectText_(None)

    if alert.runModal() != AppKit.NSAlertFirstButtonReturn:
        return None
    return str(input_field.stringValue()).strip()


def _show_text_result(title: str, message: str) -> None:
    """Показывает результат операции в простом нативном диалоге."""
    AppKit.NSApplication.sharedApplication().activateIgnoringOtherApps_(True)
    alert = AppKit.NSAlert.alloc().init()
    alert.setMessageText_(title)
    alert.setInformativeText_(message)
    alert.addButtonWithTitle_("ОК")
    alert.runModal()


class SettingsWindowController(AppKit.NSObject):  # type: ignore[misc]
    """Управляет нативным окном настроек Dictator."""

    app: StatusBarControllerProtocol
    _snapshot: AppSnapshot | None
    _window: Any | None
    _root_view: Any | None
    _toolbar_view: Any | None
    _scroll_view: Any | None
    _selected_screen: str
    _next_control_tag: int
    _control_payloads: dict[int, _ControlPayload]

    def initWithApp_(self, app: StatusBarControllerProtocol) -> SettingsWindowController | None:  # noqa: N802
        """Инициализирует контроллер без создания окна до первого открытия."""
        initialized_self = objc.super(SettingsWindowController, self).init()
        if initialized_self is None:
            return None
        controller = cast("SettingsWindowController", initialized_self)
        controller.app = app
        controller._snapshot = None
        controller._window = None
        controller._root_view = None
        controller._toolbar_view = None
        controller._scroll_view = None
        controller._selected_screen = "home"
        controller._next_control_tag = 1000
        controller._control_payloads = {}
        controller.app.subscribe(controller._apply_snapshot_from_subscription)
        return controller

    def show(self) -> None:
        """Показывает окно настроек и переводит приложение в фокус."""
        _call_on_main_thread(self._show_on_main_thread)

    def _show_on_main_thread(self) -> None:
        """Создаёт окно при первом открытии и показывает его."""
        if self._window is None:
            self._build_window()
        self._snapshot = self.app.snapshot()
        self._rebuild_toolbar()
        self._rebuild_content()
        window = self._window
        if window is None:
            return
        AppKit.NSApplication.sharedApplication().activateIgnoringOtherApps_(True)
        window.makeKeyAndOrderFront_(None)

    def selectSection_(self, sender: Any) -> None:  # noqa: N802
        """Переключает раздел окна настроек."""
        payload = self._payload_for_sender(sender)
        if payload is None:
            return
        self._selected_screen = str(payload.value)
        self._rebuild_toolbar()
        self._rebuild_content()

    def performButtonAction_(self, sender: Any) -> None:  # noqa: N802
        """Обрабатывает нажатие кнопки в окне настроек."""
        payload = self._payload_for_sender(sender)
        if payload is not None:
            self._perform_action(payload.action, payload.value)

    def performToggleAction_(self, sender: Any) -> None:  # noqa: N802
        """Обрабатывает переключатель в окне настроек."""
        payload = self._payload_for_sender(sender)
        if payload is not None:
            self._perform_action(payload.action, payload.value)

    def performSelectAction_(self, sender: Any) -> None:  # noqa: N802
        """Обрабатывает выпадающий список."""
        payload = self._payload_for_sender(sender)
        if payload is None:
            return
        index = int(sender.indexOfSelectedItem())
        if 0 <= index < len(payload.options):
            self._perform_action(payload.action, payload.options[index].value)

    def performSegmentedAction_(self, sender: Any) -> None:  # noqa: N802
        """Обрабатывает segmented control."""
        payload = self._payload_for_sender(sender)
        if payload is None:
            return
        index = int(sender.selectedSegment())
        if 0 <= index < len(payload.options):
            self._perform_action(payload.action, payload.options[index].value)

    def _apply_snapshot_from_subscription(self, snapshot: AppSnapshot) -> None:
        """Получает snapshot из контроллера и переносит обновление на главный поток."""
        _call_on_main_thread(self._apply_snapshot, snapshot)

    def _apply_snapshot(self, snapshot: AppSnapshot) -> None:
        """Применяет snapshot к открытому окну."""
        self._snapshot = snapshot
        if self._window is not None and self._window.isVisible():
            self._rebuild_toolbar()
            self._rebuild_content()

    def _current_snapshot(self) -> AppSnapshot:
        """Возвращает последний snapshot или синхронно читает новый."""
        if self._snapshot is None:
            self._snapshot = self.app.snapshot()
        return self._snapshot

    def _build_window(self) -> None:
        """Создаёт нативное окно и базовый layout."""
        style = (
            AppKit.NSWindowStyleMaskTitled
            | AppKit.NSWindowStyleMaskClosable
            | AppKit.NSWindowStyleMaskMiniaturizable
            | AppKit.NSWindowStyleMaskResizable
        )
        rect = AppKit.NSMakeRect(0, 0, WINDOW_WIDTH, WINDOW_HEIGHT)
        self._window = AppKit.NSWindow.alloc().initWithContentRect_styleMask_backing_defer_(
            rect,
            style,
            AppKit.NSBackingStoreBuffered,
            False,
        )
        self._window.setTitle_("Диктатор")
        self._window.setReleasedWhenClosed_(False)
        self._window.setMinSize_(AppKit.NSMakeSize(820, 560))
        self._window.center()

        self._root_view = AppKit.NSView.alloc().initWithFrame_(rect)
        self._window.setContentView_(self._root_view)

        self._toolbar_view = AppKit.NSVisualEffectView.alloc().initWithFrame_(
            AppKit.NSMakeRect(0, WINDOW_HEIGHT - TOOLBAR_HEIGHT, WINDOW_WIDTH, TOOLBAR_HEIGHT)
        )
        self._toolbar_view.setAutoresizingMask_(AppKit.NSViewWidthSizable | AppKit.NSViewMinYMargin)
        with contextlib.suppress(Exception):
            self._toolbar_view.setMaterial_(AppKit.NSVisualEffectMaterialHeaderView)
            self._toolbar_view.setBlendingMode_(AppKit.NSVisualEffectBlendingModeBehindWindow)
            self._toolbar_view.setState_(AppKit.NSVisualEffectStateActive)
        self._root_view.addSubview_(self._toolbar_view)

        self._scroll_view = AppKit.NSScrollView.alloc().initWithFrame_(
            AppKit.NSMakeRect(0, 0, WINDOW_WIDTH, WINDOW_HEIGHT - TOOLBAR_HEIGHT)
        )
        self._scroll_view.setAutoresizingMask_(AppKit.NSViewWidthSizable | AppKit.NSViewHeightSizable)
        self._scroll_view.setHasVerticalScroller_(True)
        self._scroll_view.setBorderType_(AppKit.NSNoBorder)
        self._root_view.addSubview_(self._scroll_view)

    def _rebuild_toolbar(self) -> None:
        """Перерисовывает верхнюю toolbar-навигацию."""
        if self._toolbar_view is None:
            return
        self._clear_subviews(self._toolbar_view)
        width = float(self._toolbar_view.bounds().size.width) or WINDOW_WIDTH
        height = float(self._toolbar_view.bounds().size.height) or TOOLBAR_HEIGHT
        self._add_label(
            self._toolbar_view,
            "Диктатор",
            AppKit.NSMakeRect(0, height - 30, width, 22),
            size=15,
            weight=_font_weight("semibold"),
            color=AppKit.NSColor.secondaryLabelColor(),
            alignment=AppKit.NSTextAlignmentCenter,
        )

        available_width = max(width - 32, 1)
        item_width = min(TOOLBAR_ITEM_WIDTH, max(58.0, available_width / len(NAVIGATION_ITEMS)))
        total_width = item_width * len(NAVIGATION_ITEMS)
        x = max(16.0, (width - total_width) / 2)
        y = 12.0
        for item in NAVIGATION_ITEMS:
            button = AppKit.NSButton.buttonWithTitle_target_action_(
                f"{item.icon}\n{item.title}",
                self,
                "selectSection:",
            )
            button.setFrame_(AppKit.NSMakeRect(x, y, item_width, 72))
            button.setBordered_(item.identifier == self._selected_screen)
            button.setBezelStyle_(AppKit.NSBezelStyleRounded)
            button.setAlignment_(AppKit.NSTextAlignmentCenter)
            if item.identifier == self._selected_screen:
                with contextlib.suppress(Exception):
                    button.setContentTintColor_(AppKit.NSColor.systemBlueColor())
            self._register_control(button, _ControlPayload("select_section", item.identifier))
            self._toolbar_view.addSubview_(button)
            x += item_width

    def _rebuild_content(self) -> None:
        """Перерисовывает правую часть окна."""
        if self._scroll_view is None:
            return
        snapshot = self._current_snapshot()
        voices = self._available_tts_voices()
        screens = {screen.identifier: screen for screen in build_settings_screens(snapshot, tts_voices=voices)}
        screen = screens.get(self._selected_screen, screens["home"])
        visible_width = max(CONTENT_MIN_WIDTH, float(self._scroll_view.contentSize().width))
        card_width = max(560.0, visible_width - CONTENT_MARGIN * 2)
        document_height = max(float(self._scroll_view.contentSize().height), self._content_height(screen))
        document = AppKit.NSView.alloc().initWithFrame_(AppKit.NSMakeRect(0, 0, visible_width, document_height))

        top = document_height - 28
        self._add_label(
            document,
            screen.title,
            AppKit.NSMakeRect(CONTENT_MARGIN, top - 28, card_width, 28),
            size=22,
            weight=_font_weight("semibold"),
        )
        top -= 38
        if screen.description:
            self._add_label(
                document,
                screen.description,
                AppKit.NSMakeRect(CONTENT_MARGIN, top - 42, card_width, 42),
                size=12,
                color=AppKit.NSColor.secondaryLabelColor(),
                wrap=True,
            )
            top -= 60
        else:
            top -= 20

        for section in screen.sections:
            top = self._add_section(document, section, CONTENT_MARGIN, top, card_width)

        self._scroll_view.setDocumentView_(document)

    def _add_section(self, parent: Any, section: SettingsSectionSpec, x: float, top: float, width: float) -> float:
        """Добавляет секцию настроек в document view."""
        if section.title:
            self._add_label(
                parent,
                section.title.upper(),
                AppKit.NSMakeRect(x + 4, top - 18, width, 18),
                size=11,
                color=AppKit.NSColor.secondaryLabelColor(),
                weight=_font_weight("semibold"),
            )
            top -= 28

        row_count = max(1, len(section.rows))
        card_height = row_count * ROW_HEIGHT
        card_bottom = top - card_height
        card = self._make_card(AppKit.NSMakeRect(x, card_bottom, width, card_height))
        parent.addSubview_(card)

        for index, row in enumerate(section.rows):
            self._add_row(card, row, index, row_count, width)

        top = card_bottom - 8
        if section.footer:
            self._add_label(
                parent,
                section.footer,
                AppKit.NSMakeRect(x + 4, top - 36, width - 8, 36),
                size=11,
                color=AppKit.NSColor.secondaryLabelColor(),
            )
            top -= 44
        return top - SECTION_GAP

    def _add_row(self, card: Any, row: SettingsRowSpec, index: int, row_count: int, width: float) -> None:
        """Добавляет один ряд в карточку секции."""
        row_bottom = (row_count - index - 1) * ROW_HEIGHT
        if index > 0:
            self._add_separator(card, AppKit.NSMakeRect(14, row_bottom + ROW_HEIGHT - 1, width - 28, 1))

        control_width = self._control_width(row.control)
        text_width = width - control_width - 50
        if row.subtitle:
            self._add_label(
                card,
                row.title,
                AppKit.NSMakeRect(16, row_bottom + 31, text_width, 18),
                size=13,
                weight=_font_weight("medium"),
            )
            self._add_label(
                card,
                row.subtitle,
                AppKit.NSMakeRect(16, row_bottom + 11, text_width, 20),
                size=11,
                color=AppKit.NSColor.secondaryLabelColor(),
            )
        else:
            self._add_label(
                card,
                row.title,
                AppKit.NSMakeRect(16, row_bottom + 20, text_width, 20),
                size=13,
                weight=_font_weight("medium"),
            )

        control_frame = AppKit.NSMakeRect(width - control_width - 16, row_bottom + 15, control_width, 28)
        self._add_control(card, row, control_frame)

    def _add_control(self, parent: Any, row: SettingsRowSpec, frame: Any) -> None:
        """Создаёт AppKit-control по описанию ряда."""
        if row.control in {"none", ""}:
            return
        if row.control == "label":
            self._add_label(
                parent,
                str(row.value or ""),
                frame,
                size=12,
                color=AppKit.NSColor.secondaryLabelColor(),
                alignment=AppKit.NSTextAlignmentRight,
            )
            return
        if row.control == "status":
            self._add_status_label(parent, str(row.value or ""), row.tone, frame)
            return
        if row.control == "status_button":
            status_frame = AppKit.NSMakeRect(frame.origin.x - 104, frame.origin.y, 100, frame.size.height)
            self._add_status_label(parent, str(row.value or ""), row.tone, status_frame)
            self._add_button(parent, row.button_title, row.action, row.value, frame)
            return
        if row.control == "button":
            self._add_button(parent, row.button_title or str(row.value or "Открыть"), row.action, row.value, frame)
            return
        if row.control == "button_pair":
            half = (frame.size.width - 8) / 2
            first = AppKit.NSMakeRect(frame.origin.x, frame.origin.y, half, frame.size.height)
            second = AppKit.NSMakeRect(frame.origin.x + half + 8, frame.origin.y, half, frame.size.height)
            self._add_button(parent, row.button_title, row.action, row.value, first)
            self._add_button(parent, row.secondary_button_title, row.secondary_action, row.value, second)
            return
        if row.control == "toggle":
            toggle = AppKit.NSButton.alloc().initWithFrame_(frame)
            toggle.setButtonType_(getattr(AppKit, "NSSwitchButton", 3))
            toggle.setTitle_("")
            toggle.setState_(getattr(AppKit, "NSControlStateValueOn", 1) if bool(row.value) else 0)
            toggle.setEnabled_(row.enabled)
            toggle.setTarget_(self)
            toggle.setAction_("performToggleAction:")
            self._register_control(toggle, _ControlPayload(str(row.action), row.value))
            parent.addSubview_(toggle)
            return
        if row.control == "select":
            popup = AppKit.NSPopUpButton.alloc().initWithFrame_pullsDown_(frame, False)
            popup.addItemsWithTitles_([option.title for option in row.options])
            selected_index = self._selected_option_index(row.options, row.value)
            popup.selectItemAtIndex_(selected_index)
            popup.setTarget_(self)
            popup.setAction_("performSelectAction:")
            self._register_control(popup, _ControlPayload(str(row.action), row.value, row.options))
            parent.addSubview_(popup)
            return
        if row.control == "segmented":
            segmented = AppKit.NSSegmentedControl.alloc().initWithFrame_(frame)
            segmented.setSegmentCount_(len(row.options))
            for index, option in enumerate(row.options):
                segmented.setLabel_forSegment_(option.title, index)
            segmented.setTrackingMode_(getattr(AppKit, "NSSegmentSwitchTrackingSelectOne", 0))
            segmented.setSelectedSegment_(self._selected_option_index(row.options, row.value))
            segmented.setTarget_(self)
            segmented.setAction_("performSegmentedAction:")
            self._register_control(segmented, _ControlPayload(str(row.action), row.value, row.options))
            parent.addSubview_(segmented)
            return
        if row.control == "model_status":
            self._add_model_status_control(parent, row, frame)
            return
        if row.control == "stepper":
            self._add_stepper(parent, row, frame)

    def _add_model_status_control(self, parent: Any, row: SettingsRowSpec, frame: Any) -> None:
        """Добавляет статус скачиваемой модели: загрузка, скачивание или удаление."""
        status = row.value if isinstance(row.value, DownloadableModelStatus) else _fallback_model_status(str(row.value or ""))
        if status.state == "downloading":
            indicator_frame = AppKit.NSMakeRect(frame.origin.x, frame.origin.y + 5, 18, 18)
            indicator = AppKit.NSProgressIndicator.alloc().initWithFrame_(indicator_frame)
            indicator.setIndeterminate_(True)
            with contextlib.suppress(Exception):
                indicator.setStyle_(AppKit.NSProgressIndicatorSpinningStyle)
                indicator.setControlSize_(AppKit.NSControlSizeSmall)
            indicator.startAnimation_(None)
            parent.addSubview_(indicator)
            label_frame = AppKit.NSMakeRect(frame.origin.x + 24, frame.origin.y + 2, frame.size.width - 24, frame.size.height)
            self._add_label(parent, status.status_text, label_frame, size=12, color=AppKit.NSColor.secondaryLabelColor())
            return

        if status.can_delete:
            status_frame = AppKit.NSMakeRect(frame.origin.x, frame.origin.y + 2, 92, frame.size.height)
            button_frame = AppKit.NSMakeRect(frame.origin.x + frame.size.width - 82, frame.origin.y, 82, frame.size.height)
            self._add_status_label(parent, status.status_text, "ok", status_frame)
            self._add_button(parent, "Удалить", row.secondary_action, status.model_id, button_frame)
            return

        if status.can_download:
            button_title = "Повторить" if status.state == "error" else "Скачать"
            button_frame = AppKit.NSMakeRect(frame.origin.x + frame.size.width - 96, frame.origin.y, 96, frame.size.height)
            label_frame = AppKit.NSMakeRect(frame.origin.x, frame.origin.y + 2, frame.size.width - 104, frame.size.height)
            tone = "err" if status.state == "error" else "warn"
            self._add_status_label(parent, status.status_text, tone, label_frame)
            self._add_button(parent, button_title, row.action, status.model_id, button_frame)
            return

        self._add_status_label(parent, status.status_text, "neutral", frame)

    def _add_stepper(self, parent: Any, row: SettingsRowSpec, frame: Any) -> None:
        """Добавляет пару кнопок −/+ с текущим значением."""
        button_width = 28.0
        minus_frame = AppKit.NSMakeRect(frame.origin.x, frame.origin.y, button_width, frame.size.height)
        label_frame = AppKit.NSMakeRect(
            frame.origin.x + button_width,
            frame.origin.y,
            frame.size.width - button_width * 2,
            frame.size.height,
        )
        plus_frame = AppKit.NSMakeRect(
            frame.origin.x + frame.size.width - button_width,
            frame.origin.y,
            button_width,
            frame.size.height,
        )
        self._add_button(parent, "−", row.action, row.value, minus_frame)
        self._add_label(parent, str(row.value or ""), label_frame, size=12, alignment=AppKit.NSTextAlignmentCenter)
        self._add_button(parent, "+", row.secondary_action, row.value, plus_frame)

    def _add_button(self, parent: Any, title: str, action: str | None, value: object, frame: Any) -> None:
        """Добавляет кнопку и регистрирует действие."""
        button = AppKit.NSButton.buttonWithTitle_target_action_(title or "Открыть", self, "performButtonAction:")
        button.setFrame_(frame)
        button.setBezelStyle_(AppKit.NSBezelStyleRounded)
        button.setEnabled_(action is not None)
        if action is not None:
            self._register_control(button, _ControlPayload(action, value))
        parent.addSubview_(button)

    def _add_status_label(self, parent: Any, title: str, tone: str, frame: Any) -> None:
        """Добавляет компактный статус."""
        color = {
            "ok": AppKit.NSColor.systemGreenColor(),
            "warn": AppKit.NSColor.systemOrangeColor(),
            "err": AppKit.NSColor.systemRedColor(),
        }.get(tone, AppKit.NSColor.secondaryLabelColor())
        self._add_label(parent, title, frame, size=12, color=color, alignment=AppKit.NSTextAlignmentRight)

    def _add_label(
        self,
        parent: Any,
        text: str,
        frame: Any,
        *,
        size: float,
        weight: float | None = None,
        color: Any | None = None,
        alignment: int | None = None,
        wrap: bool = False,
    ) -> Any:
        """Добавляет read-only NSTextField."""
        label = AppKit.NSTextField.labelWithString_(text)
        label.setFrame_(frame)
        label.setFont_(AppKit.NSFont.systemFontOfSize_weight_(size, AppKit.NSFontWeightRegular if weight is None else weight))
        label.setTextColor_(color or AppKit.NSColor.labelColor())
        label.setLineBreakMode_(
            getattr(AppKit, "NSLineBreakByWordWrapping", 0) if wrap else getattr(AppKit, "NSLineBreakByTruncatingTail", 4)
        )
        if wrap:
            with contextlib.suppress(Exception):
                label.setMaximumNumberOfLines_(0)
        if alignment is not None:
            label.setAlignment_(alignment)
        parent.addSubview_(label)
        return label

    def _make_card(self, frame: Any) -> Any:
        """Создаёт карточку секции."""
        card = AppKit.NSBox.alloc().initWithFrame_(frame)
        card.setTitlePosition_(getattr(AppKit, "NSNoTitle", 0))
        card.setBoxType_(getattr(AppKit, "NSBoxCustom", 4))
        card.setBorderType_(getattr(AppKit, "NSLineBorder", 1))
        card.setBorderWidth_(0.5)
        card.setCornerRadius_(8.0)
        card.setFillColor_(AppKit.NSColor.controlBackgroundColor())
        card.setBorderColor_(AppKit.NSColor.separatorColor())
        return card

    def _add_separator(self, parent: Any, frame: Any) -> None:
        """Добавляет тонкий разделитель."""
        separator = AppKit.NSBox.alloc().initWithFrame_(frame)
        separator.setBoxType_(getattr(AppKit, "NSBoxCustom", 4))
        separator.setBorderWidth_(0)
        separator.setFillColor_(AppKit.NSColor.separatorColor())
        parent.addSubview_(separator)

    def _content_height(self, screen: SettingsScreenSpec) -> float:
        """Оценивает высоту document view для текущего экрана."""
        height = 150.0 if screen.description else 110.0
        for section in screen.sections:
            if section.title:
                height += 28.0
            height += max(1, len(section.rows)) * ROW_HEIGHT
            if section.footer:
                height += 44.0
            height += SECTION_GAP
        return max(WINDOW_HEIGHT, height)

    def _control_width(self, control: str) -> float:
        """Возвращает ширину правого control."""
        return {
            "label": 210.0,
            "status": 150.0,
            "status_button": 112.0,
            "button": 132.0,
            "button_pair": 184.0,
            "toggle": 56.0,
            "select": 230.0,
            "segmented": 250.0,
            "stepper": 126.0,
            "model_status": 260.0,
        }.get(control, 120.0)

    def _selected_option_index(self, options: Sequence[SettingsOption], value: object) -> int:
        """Возвращает индекс текущего значения в options."""
        for index, option in enumerate(options):
            if option.value == value:
                return index
        return 0

    def _register_control(self, control: Any, payload: _ControlPayload) -> None:
        """Привязывает payload к AppKit control."""
        tag = self._next_control_tag
        self._next_control_tag += 1
        control.setTag_(tag)
        self._control_payloads[tag] = payload

    def _payload_for_sender(self, sender: Any) -> _ControlPayload | None:
        """Возвращает payload для sender."""
        return self._control_payloads.get(int(sender.tag()))

    def _clear_subviews(self, view: Any) -> None:
        """Удаляет все subview перед полной перерисовкой."""
        for subview in list(view.subviews()):
            subview.removeFromSuperview()

    def _available_tts_voices(self) -> list[TTSVoice]:
        """Безопасно читает список системных голосов TTS."""
        with contextlib.suppress(Exception):
            return self.app.reader_available_tts_voices()
        return []

    def _perform_action(self, action: str, value: object = None) -> None:
        """Делегирует команду окна настроек в контроллер приложения."""
        LOGGER.debug("Окно настроек: действие %s, значение=%r", action, value)
        if action == "select_section":
            self._selected_screen = str(value)
            return
        try:
            self._dispatch_action(action, value)
        except Exception:
            LOGGER.exception("⚠️ Не удалось выполнить действие окна настроек: %s", action)

    def _dispatch_action(self, action: str, value: object = None) -> None:
        """Выполняет конкретную команду окна настроек."""
        snapshot = self._current_snapshot()
        if action == "start_recording":
            self.app.start_recording()
        elif action == "stop_recording":
            self.app.stop_recording()
        elif action == "toggle_rsvp":
            self.app.toggle_rsvp()
        elif action == "toggle_tts":
            self.app.toggle_tts()
        elif action == "change_model":
            self.app.change_model(str(value))
        elif action == "change_language":
            self.app.change_language(None if value is None else str(value))
        elif action == "change_max_time":
            self.app.change_max_time(None if value is None else _to_float(value))
        elif action == "change_performance_mode":
            self.app.change_performance_mode(value)
        elif action == "toggle_capitalize_first_letter":
            self.app.toggle_capitalize_first_letter()
        elif action == "toggle_remove_trailing_period_for_single_sentence":
            self.app.toggle_remove_trailing_period_for_single_sentence()
        elif action == "toggle_restore_trailing_period_on_next_dictation":
            self.app.toggle_restore_trailing_period_on_next_dictation()
        elif action == "toggle_reader_preprocess":
            self.app.toggle_reader_preprocess()
        elif action == "change_reader_tts_engine":
            self.app.change_reader_tts_engine(str(value))
        elif action == "change_reader_tts_mlx_model":
            self.app.change_reader_tts_mlx_model(str(value))
        elif action == "change_reader_tts_voice":
            self.app.change_reader_tts_voice(None if value is None else str(value))
        elif action == "change_reader_tts_max_minutes":
            self.app.change_reader_tts_max_minutes(_to_int(value))
        elif action == "decrease_reader_tts_rate_multiplier":
            next_rate = max(
                TTS_RATE_MULTIPLIER_MIN,
                snapshot.reader_tts_rate_multiplier - TTS_RATE_MULTIPLIER_STEP,
            )
            self.app.change_reader_tts_rate_multiplier(next_rate)
        elif action == "increase_reader_tts_rate_multiplier":
            next_rate = min(
                TTS_RATE_MULTIPLIER_MAX,
                snapshot.reader_tts_rate_multiplier + TTS_RATE_MULTIPLIER_STEP,
            )
            self.app.change_reader_tts_rate_multiplier(next_rate)
        elif action == "decrease_reader_rsvp_wpm":
            self.app.change_reader_rsvp_wpm(_neighbor_value(RSVP_WPM_OPTIONS, snapshot.reader_rsvp_wpm, -1))
        elif action == "increase_reader_rsvp_wpm":
            self.app.change_reader_rsvp_wpm(_neighbor_value(RSVP_WPM_OPTIONS, snapshot.reader_rsvp_wpm, 1))
        elif action == "change_reader_rsvp_chunk_size":
            self.app.change_reader_rsvp_chunk_size(_to_int(value))
        elif action == "change_reader_rsvp_font_size":
            self.app.change_reader_rsvp_font_size(_to_int(value))
        elif action == "toggle_paste_cgevent":
            self.app.toggle_paste_cgevent()
        elif action == "toggle_paste_ax":
            self.app.toggle_paste_ax()
        elif action == "toggle_paste_clipboard":
            self.app.toggle_paste_clipboard()
        elif action == "toggle_private_mode":
            self.app.toggle_private_mode()
        elif action == "toggle_recording_notification":
            self.app.toggle_recording_notification()
        elif action == "toggle_recording_overlay":
            self.app.toggle_recording_overlay()
        elif action == "toggle_recording_time_in_menu_bar":
            self.app.toggle_recording_time_in_menu_bar()
        elif action == "change_input_device":
            self.app.change_input_device(None if value is None else _to_int(value))
        elif action == "toggle_high_quality_mac_builtin":
            self.app.toggle_high_quality_mac_builtin()
        elif action == "toggle_gain_normalization":
            self.app.toggle_gain_normalization()
        elif action == "toggle_audio_artifact_cleanup":
            self.app.toggle_audio_artifact_cleanup()
        elif action == "open_recordings_directory":
            self.app.open_recordings_directory()
        elif action == "apply_microphone_profile":
            self.app.apply_microphone_profile(str(value))
        elif action == "delete_microphone_profile":
            self.app.delete_microphone_profile(str(value))
        elif action == "add_current_microphone_profile":
            self._prompt_and_add_microphone_profile()
        elif action == "change_hotkey":
            self.app.change_hotkey()
        elif action == "change_secondary_hotkey":
            self.app.change_secondary_hotkey()
        elif action == "change_llm_hotkey":
            self.app.change_llm_hotkey()
        elif action == "change_rsvp_hotkey":
            self.app.change_rsvp_hotkey()
        elif action == "change_tts_hotkey":
            self.app.change_tts_hotkey()
        elif action == "change_llm_model":
            self.app.change_llm_model(str(value))
        elif action == "change_llm_prompt":
            self.app.change_llm_prompt(str(value))
        elif action == "toggle_llm_clipboard":
            self.app.toggle_llm_clipboard()
        elif action == "download_llm_model":
            self.app.download_llm_model()
        elif action == "download_model":
            self.app.download_model(str(value))
        elif action == "delete_downloaded_model":
            self.app.delete_downloaded_model(str(value))
        elif action == "copy_history_text":
            self.app.copy_history_text(str(value))
        elif action == "search_obsidian_history":
            self._prompt_and_search_obsidian_history()
        elif action == "open_obsidian_history_directory":
            self.app.open_obsidian_history_directory()
        elif action == "request_accessibility_access":
            self.app.request_accessibility_access()
        elif action == "request_input_monitoring_access":
            self.app.request_input_monitoring_access()
        elif action == "prompt_reader_tts_mlx_model":
            self._prompt_reader_tts_mlx_model(snapshot)
        elif action == "prompt_reader_tts_mlx_voice_description":
            self._prompt_reader_tts_mlx_voice_description(snapshot)

    def _prompt_reader_tts_mlx_model(self, snapshot: AppSnapshot) -> None:
        """Запрашивает точное имя MLX TTS-модели."""
        model_name = _prompt_text(
            "MLX TTS-модель",
            "Введите имя локальной MLX TTS-модели или repo id.",
            snapshot.reader_tts_mlx_model,
        )
        if model_name is not None:
            self.app.change_reader_tts_mlx_model(model_name)

    def _prompt_reader_tts_mlx_voice_description(self, snapshot: AppSnapshot) -> None:
        """Запрашивает описание голоса MLX VoiceDesign."""
        description = _prompt_text(
            "Описание MLX-голоса",
            "Опишите голос для Qwen3-TTS VoiceDesign.",
            snapshot.reader_tts_mlx_voice_description,
        )
        if description is not None:
            self.app.change_reader_tts_mlx_voice_description(description)

    def _prompt_and_add_microphone_profile(self) -> None:
        """Запрашивает имя и сохраняет текущий быстрый профиль микрофона."""
        profile_name = _prompt_text(
            "Добавить быстрый профиль",
            "Введите название для текущего микрофона и набора базовых настроек.",
            self.app.suggest_microphone_profile_name(),
        )
        if profile_name is not None:
            self.app.add_current_microphone_profile(profile_name)

    def _prompt_and_search_obsidian_history(self) -> None:
        """Запрашивает вопрос к архиву диктовок и показывает ответ."""
        query = _prompt_text(
            "Поиск по истории",
            "Введите вопрос к вашему архиву диктовок и заметок в Obsidian.",
        )
        if query is None:
            return
        answer = self.app.search_obsidian_history(query)
        if answer is not None:
            _show_text_result("Ответ по истории", answer)


def _font_weight(name: str) -> float:
    """Возвращает вес системного шрифта с fallback для старых PyObjC."""
    mapping = {
        "regular": getattr(AppKit, "NSFontWeightRegular", 0.0),
        "medium": getattr(AppKit, "NSFontWeightMedium", 0.23),
        "semibold": getattr(AppKit, "NSFontWeightSemibold", 0.3),
    }
    return float(mapping.get(name, mapping["regular"]))


def _to_int(value: object) -> int:
    """Безопасно приводит значение control к int."""
    if isinstance(value, (int, float, str)):
        return int(value)
    raise ValueError(f"Ожидалось числовое значение, получено: {value!r}")


def _to_float(value: object) -> float:
    """Безопасно приводит значение control к float."""
    if isinstance(value, (int, float, str)):
        return float(value)
    raise ValueError(f"Ожидалось числовое значение, получено: {value!r}")


def _neighbor_value(options: Sequence[int], current: int, direction: int) -> int:
    """Возвращает соседнее значение из ordered options."""
    values = list(options)
    if current not in values:
        return values[0]
    index = values.index(current)
    next_index = min(max(index + direction, 0), len(values) - 1)
    return values[next_index]
