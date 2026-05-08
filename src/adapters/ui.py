"""UI menu bar приложения Dictator.

Содержит StatusBarApp — адаптер menu bar UI к DictationApp, а также
вспомогательную функцию prompt_text для простых диалогов ввода.
"""

from __future__ import annotations

import contextlib
import logging
from typing import TYPE_CHECKING, Any

import AppKit
import rumps
from PyObjCTools.AppHelper import callAfter  # type: ignore[import-untyped]

from ..domain.constants import Config
from ..domain.reader_constants import (
    RSVP_CHUNK_SIZE_OPTIONS,
    RSVP_FONT_SIZE_OPTIONS,
    RSVP_WPM_OPTIONS,
    TTS_ENGINE_LABELS,
    TTS_MAX_MINUTES_OPTIONS,
    TTS_MLX_MODEL_OPTIONS,
    TTS_RATE_MULTIPLIER_STEP,
)

if TYPE_CHECKING:
    from ..domain.ports import StatusBarControllerProtocol
    from ..domain.types import AppSnapshot, MicrophoneProfile

LOGGER = logging.getLogger(__name__)


def _call_on_main_thread(callback: Any, *args: Any) -> None:
    """Гарантирует, что обновление menu bar выполняется на главном потоке AppKit."""
    if AppKit.NSThread.isMainThread():
        callback(*args)
        return
    callAfter(callback, *args)


def prompt_text(title: str, message: str, default_text: str = "") -> str | None:
    """Открывает простое AppKit-окно ввода текста и возвращает введённое значение."""
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


class StatusBarApp(rumps.App):  # type: ignore[misc]
    """Menu bar UI-адаптер для контроллера диктовки."""

    def __init__(self, app: StatusBarControllerProtocol) -> None:
        """Создаёт menu bar приложение, привязанное к контроллеру диктовки."""
        super().__init__("whisper", "⏯")
        self.app = app
        self._history_title_to_text: dict[str, str] = {}
        self._microphone_profile_titles: dict[str, MicrophoneProfile] = {}
        self._delete_microphone_profile_titles: dict[str, MicrophoneProfile] = {}

        self.status_item = rumps.MenuItem(f"🔄 Статус: {self._state_label()}")
        self.model_item = rumps.MenuItem(f"🧠 Модель: {self.model_name}")
        for model in self.model_options:
            self.model_item.add(rumps.MenuItem(self._model_menu_title(model), callback=self.change_model))

        self.language_item = rumps.MenuItem(f"🌍 Язык: {self._format_language()}")
        if self.languages is not None and len(self.languages) > 1:
            for lang in self.languages:
                self.language_item.add(rumps.MenuItem(lang, callback=self.change_language))

        self.max_time_item = rumps.MenuItem(f"⏱ Длительность записи: {Config.format_max_time_status(self.max_time)}")
        for max_time_value in self.max_time_options:
            self.max_time_item.add(rumps.MenuItem(self._max_time_menu_title(max_time_value), callback=self.change_max_time))

        self.hotkey_item = rumps.MenuItem(f"⌨️ Основной хоткей: {self.hotkey_status}", callback=self.change_hotkey)
        self.secondary_hotkey_item = rumps.MenuItem(
            f"⌨️ Доп. хоткей: {self.secondary_hotkey_status}",
            callback=self.change_secondary_hotkey,
        )

        self.llm_hotkey_item = rumps.MenuItem(f"🤖 LLM-хоткей: {self.llm_hotkey_status}", callback=self.change_llm_hotkey)
        self.zipper_hotkey_item = rumps.MenuItem(f"🧷 Zipper: {self.zipper_hotkey_status}", callback=self.change_zipper_hotkey)
        self.rsvp_hotkey_item = rumps.MenuItem(f"📖 Reader: {self.rsvp_hotkey_status}", callback=self.change_rsvp_hotkey)
        self.tts_hotkey_item = rumps.MenuItem(f"🔈 Speaker: {self.tts_hotkey_status}", callback=self.change_tts_hotkey)
        self.llm_model_menu = rumps.MenuItem(f"🤖 LLM-модель: {self.llm_model_name}")
        for llm_model in self.llm_model_options:
            item = rumps.MenuItem(self._llm_model_menu_title(llm_model), callback=self._change_llm_model)
            item.state = int(llm_model.rsplit("/", maxsplit=1)[-1] == self.llm_model_name)
            self.llm_model_menu.add(item)
        self.llm_prompt_menu = rumps.MenuItem("🤖 Системный промпт LLM")
        for prompt_name in Config.LLM_PROMPT_PRESETS:
            item = rumps.MenuItem(prompt_name, callback=self._change_llm_prompt)
            item.state = int(prompt_name == self.llm_prompt_name)
            self.llm_prompt_menu.add(item)
        self.llm_clipboard_item = rumps.MenuItem("🤖 Буфер обмена для LLM", callback=self.toggle_llm_clipboard)
        self.llm_download_item = rumps.MenuItem(self.app.snapshot().llm_download_title, callback=self._download_llm_model)

        self.recording_notification_item = rumps.MenuItem(
            "🔔 Уведомление о старте записи",
            callback=self.toggle_recording_notification,
        )
        self.recording_indicator_menu = rumps.MenuItem("🔴 Индикация записи")
        self.recording_overlay_item = rumps.MenuItem(
            "🎯 Индикатор у курсора и время",
            callback=self.toggle_recording_overlay,
        )
        self.recording_time_in_menu_bar_item = rumps.MenuItem(
            "⏱ Отображать время записи в меню",
            callback=self.toggle_recording_time_in_menu_bar,
        )
        self.recording_indicator_menu.add(self.recording_overlay_item)
        self.recording_indicator_menu.add(self.recording_time_in_menu_bar_item)

        self.performance_menu = rumps.MenuItem(f"⚡ Режим работы: {Config.performance_mode_label(self.performance_mode)}")
        for performance_mode, title in Config.PERFORMANCE_MODE_LABELS.items():
            item = rumps.MenuItem(title, callback=self.change_performance_mode)
            item.state = int(performance_mode == self.performance_mode)
            self.performance_menu.add(item)

        self.audio_menu = rumps.MenuItem("🎙️ Аудио")
        self.audio_profile_item = rumps.MenuItem(f"Профиль: {Config.audio_profile_label(self.audio_profile_name)}")
        self.audio_profile_item.set_callback(None)
        self.high_quality_mac_builtin_item = rumps.MenuItem("Профиль MacBook HQ", callback=self.toggle_high_quality_mac_builtin)
        self.gain_normalization_item = rumps.MenuItem("Бережная нормализация", callback=self.toggle_gain_normalization)
        self.audio_artifact_cleanup_item = rumps.MenuItem(
            "Автоочистка WAV через 24 часа",
            callback=self.toggle_audio_artifact_cleanup,
        )
        self.open_recordings_directory_item = rumps.MenuItem(
            "Открыть папку WAV-записей…",
            callback=self.open_recordings_directory,
        )
        self.voice_isolation_hint_item = rumps.MenuItem("Voice Isolation включается вручную в macOS")
        self.voice_isolation_hint_item.set_callback(None)
        self.audio_menu.add(self.audio_profile_item)
        self.audio_menu.add(self.high_quality_mac_builtin_item)
        self.audio_menu.add(self.gain_normalization_item)
        self.audio_menu.add(self.audio_artifact_cleanup_item)
        self.audio_menu.add(self.open_recordings_directory_item)
        self.audio_menu.add(self.voice_isolation_hint_item)

        self.postprocessing_menu = rumps.MenuItem("✨ Постобработка текста")
        self.capitalize_first_letter_item = rumps.MenuItem(
            "Первая буква с заглавной",
            callback=self.toggle_capitalize_first_letter,
        )
        self.remove_trailing_period_for_single_sentence_item = rumps.MenuItem(
            "Убирать точку в конце одного предложения",
            callback=self.toggle_remove_trailing_period_for_single_sentence,
        )
        self.restore_trailing_period_on_next_dictation_item = rumps.MenuItem(
            ("После снятой точки связывать следующие диктовки в цепочку предложений"),
            callback=self.toggle_restore_trailing_period_on_next_dictation,
        )
        self.postprocessing_menu.add(self.capitalize_first_letter_item)
        self.postprocessing_menu.add(self.remove_trailing_period_for_single_sentence_item)
        self.postprocessing_menu.add(self.restore_trailing_period_on_next_dictation_item)

        self.recognition_menu = rumps.MenuItem("🧠 Распознавание")
        self.recognition_menu.add(self.model_item)
        self.recognition_menu.add(self.language_item)
        self.recognition_menu.add(self.max_time_item)
        self.recognition_menu.add(self.performance_menu)

        self.reader_rsvp_item = rumps.MenuItem(f"👀 Запустить RSVP    {self.rsvp_hotkey_status}", callback=self.start_rsvp)
        self.reader_tts_item = rumps.MenuItem(f"🔊 Запустить TTS    {self.tts_hotkey_status}", callback=self.start_tts)
        self.reader_preprocess_item = rumps.MenuItem("🤖 LLM-предобработка reader", callback=self.toggle_reader_preprocess)
        self.reader_rsvp_settings_menu = rumps.MenuItem("⚙️ Настройки RSVP")
        self.reader_rsvp_wpm_menu = rumps.MenuItem(f"Скорость: {self.reader_rsvp_wpm} wpm")
        for wpm in RSVP_WPM_OPTIONS:
            self.reader_rsvp_wpm_menu.add(rumps.MenuItem(f"{wpm} wpm", callback=self.change_reader_rsvp_wpm))
        self.reader_rsvp_chunk_menu = rumps.MenuItem(f"Размер chunk: {self.reader_rsvp_chunk_size}")
        for chunk_size in RSVP_CHUNK_SIZE_OPTIONS:
            self.reader_rsvp_chunk_menu.add(rumps.MenuItem(f"{chunk_size} слов", callback=self.change_reader_rsvp_chunk_size))
        self.reader_rsvp_font_menu = rumps.MenuItem(f"Размер шрифта: {self.reader_rsvp_font_size}")
        for font_size in RSVP_FONT_SIZE_OPTIONS:
            self.reader_rsvp_font_menu.add(rumps.MenuItem(f"{font_size} pt", callback=self.change_reader_rsvp_font_size))
        self.reader_rsvp_settings_menu.add(self.reader_rsvp_wpm_menu)
        self.reader_rsvp_settings_menu.add(self.reader_rsvp_chunk_menu)
        self.reader_rsvp_settings_menu.add(self.reader_rsvp_font_menu)

        self.reader_tts_settings_menu = rumps.MenuItem("⚙️ Настройки TTS")
        self.reader_tts_engine_menu = rumps.MenuItem(f"Backend: {self._format_tts_engine(self.reader_tts_engine)}")
        for title in TTS_ENGINE_LABELS.values():
            self.reader_tts_engine_menu.add(rumps.MenuItem(title, callback=self.change_reader_tts_engine))
        self.reader_tts_mlx_model_menu = rumps.MenuItem(f"MLX-модель: {self._short_model_name(self.reader_tts_mlx_model)}")
        for model_name in TTS_MLX_MODEL_OPTIONS:
            self.reader_tts_mlx_model_menu.add(
                rumps.MenuItem(self._short_model_name(model_name), callback=self.change_reader_tts_mlx_model)
            )
        self.reader_tts_mlx_model_menu.add(None)
        self.reader_tts_mlx_model_menu.add(rumps.MenuItem("Задать модель...", callback=self.prompt_reader_tts_mlx_model))
        self.reader_tts_mlx_voice_description_item = rumps.MenuItem(
            "Описание MLX-голоса...",
            callback=self.prompt_reader_tts_mlx_voice_description,
        )
        self.reader_tts_rate_menu = rumps.MenuItem(f"Скорость речи: {self._format_tts_rate(self.reader_tts_rate_multiplier)}")
        self.reader_tts_rate_down_item = rumps.MenuItem("− медленнее", callback=self.decrease_reader_tts_rate_multiplier)
        self.reader_tts_rate_value_item = rumps.MenuItem(f"Скорость: {self._format_tts_rate(self.reader_tts_rate_multiplier)}")
        self.reader_tts_rate_value_item.set_callback(None)
        self.reader_tts_rate_up_item = rumps.MenuItem("+ быстрее", callback=self.increase_reader_tts_rate_multiplier)
        self.reader_tts_rate_menu.add(self.reader_tts_rate_down_item)
        self.reader_tts_rate_menu.add(self.reader_tts_rate_value_item)
        self.reader_tts_rate_menu.add(self.reader_tts_rate_up_item)
        self.reader_tts_voice_menu = rumps.MenuItem("Голос")
        self._refresh_reader_tts_voice_menu()
        self.reader_tts_max_minutes_menu = rumps.MenuItem(f"Макс. длина аудио: {self._format_tts_max_minutes(self.reader_tts_max_minutes)}")
        for max_minutes in TTS_MAX_MINUTES_OPTIONS:
            self.reader_tts_max_minutes_menu.add(
                rumps.MenuItem(self._format_tts_max_minutes(max_minutes), callback=self.change_reader_tts_max_minutes)
            )
        self.reader_tts_settings_menu.add(self.reader_tts_engine_menu)
        self.reader_tts_settings_menu.add(self.reader_tts_mlx_model_menu)
        self.reader_tts_settings_menu.add(self.reader_tts_mlx_voice_description_item)
        self.reader_tts_settings_menu.add(self.reader_tts_rate_menu)
        self.reader_tts_settings_menu.add(self.reader_tts_voice_menu)
        self.reader_tts_settings_menu.add(self.reader_tts_max_minutes_menu)

        self.reader_menu = rumps.MenuItem("📖 Reader")
        self.reader_menu.add(self.reader_rsvp_item)
        self.reader_menu.add(self.reader_tts_item)
        self.reader_menu.add(None)
        self.reader_menu.add(self.reader_rsvp_settings_menu)
        self.reader_menu.add(self.reader_tts_settings_menu)
        self.reader_menu.add(self.reader_preprocess_item)

        self.zipper_menu = rumps.MenuItem("🧷 Zipper")
        self.zipper_toggle_item = rumps.MenuItem("Включить Zipper", callback=self.toggle_zipper_enabled)
        self.zipper_status_item = rumps.MenuItem(f"Статус: {self.zipper_status}")
        self.zipper_status_item.set_callback(None)
        self.zipper_run_item = rumps.MenuItem(f"Запустить Zipper    {self.zipper_hotkey_status}", callback=self.start_zipper)
        self.zipper_menu_hotkey_item = rumps.MenuItem(f"Хоткей: {self.zipper_hotkey_status}", callback=self.change_zipper_hotkey)
        self.zipper_config_item = rumps.MenuItem("Открыть конфиг Zipper…", callback=self.open_zipper_config)
        self.zipper_reload_config_item = rumps.MenuItem("Перезагрузить конфиг Zipper", callback=self.reload_zipper_config)
        self.zipper_debug_item = rumps.MenuItem("Debug-панель Zipper", callback=self.toggle_zipper_debug_panel)
        self.zipper_clear_context_item = rumps.MenuItem("Очистить контекст Zipper", callback=self.clear_zipper_context)
        self.zipper_clear_memory_item = rumps.MenuItem("Очистить постоянную память Zipper", callback=self.clear_zipper_memory)
        self.zipper_menu.add(self.zipper_toggle_item)
        self.zipper_menu.add(self.zipper_status_item)
        self.zipper_menu.add(self.zipper_run_item)
        self.zipper_menu.add(self.zipper_menu_hotkey_item)
        self.zipper_menu.add(None)
        self.zipper_menu.add(self.zipper_config_item)
        self.zipper_menu.add(self.zipper_reload_config_item)
        self.zipper_menu.add(self.zipper_debug_item)
        self.zipper_menu.add(None)
        self.zipper_menu.add(self.zipper_clear_context_item)
        self.zipper_menu.add(self.zipper_clear_memory_item)

        self.hotkeys_menu = rumps.MenuItem("⌨️ Хоткеи")
        self.hotkeys_menu.add(self.hotkey_item)
        self.hotkeys_menu.add(self.secondary_hotkey_item)
        self.hotkeys_menu.add(self.llm_hotkey_item)
        self.hotkeys_menu.add(self.zipper_hotkey_item)
        self.hotkeys_menu.add(self.rsvp_hotkey_item)
        self.hotkeys_menu.add(self.tts_hotkey_item)

        self.paste_method_menu = rumps.MenuItem("📝 Метод ввода")
        self.private_mode_item = rumps.MenuItem("🕶 Приватный режим", callback=self.toggle_private_mode)
        self.paste_cgevent_item = rumps.MenuItem("Прямой ввод (CGEvent)", callback=self.toggle_paste_cgevent)
        self.paste_ax_item = rumps.MenuItem("Accessibility API", callback=self.toggle_paste_ax)
        self.paste_clipboard_item = rumps.MenuItem("Буфер обмена (Cmd+V)", callback=self.toggle_paste_clipboard)
        self.paste_method_menu.add(self.paste_cgevent_item)
        self.paste_method_menu.add(self.paste_ax_item)
        self.paste_method_menu.add(self.paste_clipboard_item)

        self.behavior_menu = rumps.MenuItem("⚙️ Поведение и вид")
        self.behavior_menu.add(self.recording_notification_item)
        self.behavior_menu.add(self.recording_indicator_menu)
        self.behavior_menu.add(self.audio_menu)
        self.behavior_menu.add(self.paste_method_menu)

        self.history_menu = rumps.MenuItem("📋 История текста")
        self.token_usage_item = rumps.MenuItem(self._token_usage_title())
        self.token_usage_item.set_callback(None)

        self.llm_menu = rumps.MenuItem("🤖 LLM")
        self.llm_menu.add(self.llm_model_menu)
        self.llm_menu.add(self.llm_prompt_menu)
        self.llm_menu.add(self.llm_clipboard_item)
        self.llm_menu.add(self.llm_download_item)

        self.microphone_profiles_menu = rumps.MenuItem("🎚 Быстрые профили")
        self.input_device_menu = rumps.MenuItem(f"🎙️ Микрофон: {self._format_input_device()}")
        self.input_device_item = self.input_device_menu
        self.accessibility_item = rumps.MenuItem(self._permission_title("Accessibility", self.permission_status["accessibility"]))
        self.input_monitoring_item = rumps.MenuItem(self._permission_title("Input Monitoring", self.permission_status["input_monitoring"]))
        self.microphone_item = rumps.MenuItem(self._permission_title("Microphone", self.permission_status["microphone"]))
        self.request_accessibility_item = rumps.MenuItem("🛂 Запросить Accessibility", callback=self.request_accessibility_access)
        self.request_input_monitoring_item = rumps.MenuItem("🛂 Запросить Input Monitoring", callback=self.request_input_monitoring_access)

        self.permissions_menu = rumps.MenuItem(self._permissions_menu_title())
        self.permissions_menu.add(self.accessibility_item)
        self.permissions_menu.add(self.input_monitoring_item)
        self.permissions_menu.add(self.microphone_item)
        self.permissions_menu.add(None)
        self.permissions_menu.add(self.request_accessibility_item)
        self.permissions_menu.add(self.request_input_monitoring_item)

        menu: list[Any] = [
            "Начать запись",
            "Остановить запись",
            self.status_item,
            None,
            self.recognition_menu,
            self.postprocessing_menu,
            self.hotkeys_menu,
            self.reader_menu,
            self.zipper_menu,
            self.private_mode_item,
            self.behavior_menu,
            self.llm_menu,
            self.token_usage_item,
            self.history_menu,
            self.input_device_menu,
            self.microphone_profiles_menu,
            self.permissions_menu,
        ]

        self.menu = menu
        self.status_timer = rumps.Timer(self.on_status_tick, 1)
        self.status_timer.start()

        self._refresh_input_device_menu()
        self._refresh_microphone_profiles_menu()
        self._refresh_history_menu()
        self.app.subscribe(self._apply_snapshot_on_main_thread)

    @property
    def state(self) -> str:
        """Возвращает текущее состояние приложения."""
        return self.app.state

    @state.setter
    def state(self, value: str) -> None:
        self.app.state = value

    @property
    def started(self) -> bool:
        """Возвращает флаг активной записи."""
        return self.app.started

    @started.setter
    def started(self, value: bool) -> None:
        self.app.started = value

    @property
    def elapsed_time(self) -> int:
        """Возвращает длительность текущей записи."""
        return self.app.elapsed_time

    @property
    def model_name(self) -> str:
        """Возвращает краткое имя текущей модели."""
        return self.app.model_name

    @property
    def model_repo(self) -> str:
        """Возвращает полный идентификатор текущей модели."""
        return self.app.model_repo

    @property
    def hotkey_status(self) -> str:
        """Возвращает display-строку основного хоткея."""
        return self.app.hotkey_status

    @property
    def secondary_hotkey_status(self) -> str:
        """Возвращает display-строку дополнительного хоткея."""
        return self.app.secondary_hotkey_status

    @property
    def llm_hotkey_status(self) -> str:
        """Возвращает display-строку LLM-хоткея."""
        return self.app.llm_hotkey_status

    @property
    def zipper_hotkey_status(self) -> str:
        """Возвращает display-строку Zipper-хоткея."""
        return getattr(self.app, "zipper_hotkey_status", "не задан")

    @property
    def zipper_enabled(self) -> bool:
        """Возвращает флаг включения Zipper."""
        return bool(getattr(self.app, "zipper_enabled", False))

    @property
    def zipper_status(self) -> str:
        """Возвращает статус Zipper."""
        return str(getattr(self.app, "zipper_status", "выключен"))

    @property
    def zipper_debug_panel_enabled(self) -> bool:
        """Возвращает флаг debug-панели Zipper."""
        return bool(getattr(self.app, "zipper_debug_panel_enabled", False))

    @property
    def rsvp_hotkey_status(self) -> str:
        """Возвращает display-строку RSVP-хоткея."""
        return getattr(self.app, "rsvp_hotkey_status", "не задан")

    @property
    def tts_hotkey_status(self) -> str:
        """Возвращает display-строку TTS-хоткея."""
        return getattr(self.app, "tts_hotkey_status", "не задан")

    @property
    def llm_prompt_name(self) -> str:
        """Возвращает имя активного LLM-промпта."""
        return self.app.llm_prompt_name

    @property
    def llm_model_name(self) -> str:
        """Возвращает краткое имя текущей LLM-модели."""
        return self.app.llm_model_name

    @property
    def llm_model_options(self) -> list[str]:
        """Возвращает список доступных LLM-моделей."""
        return self.app.llm_model_options

    @property
    def reader_rsvp_wpm(self) -> int:
        """Возвращает скорость RSVP."""
        return int(getattr(self.app, "reader_rsvp_wpm", 400))

    @property
    def reader_rsvp_chunk_size(self) -> int:
        """Возвращает размер RSVP chunk-а."""
        return int(getattr(self.app, "reader_rsvp_chunk_size", 2))

    @property
    def reader_rsvp_font_size(self) -> int:
        """Возвращает размер шрифта RSVP."""
        return int(getattr(self.app, "reader_rsvp_font_size", 64))

    @property
    def reader_tts_rate_multiplier(self) -> float:
        """Возвращает множитель скорости TTS."""
        return float(getattr(self.app, "reader_tts_rate_multiplier", 1.0))

    @property
    def reader_tts_voice_id(self) -> str | None:
        """Возвращает идентификатор выбранного голоса TTS."""
        return getattr(self.app, "reader_tts_voice_id", None)

    @property
    def reader_tts_max_minutes(self) -> int:
        """Возвращает лимит длительности TTS."""
        return int(getattr(self.app, "reader_tts_max_minutes", 5))

    @property
    def reader_tts_engine(self) -> str:
        """Возвращает выбранный backend TTS."""
        return str(getattr(self.app, "reader_tts_engine", "apple"))

    @property
    def reader_tts_mlx_model(self) -> str:
        """Возвращает выбранную MLX TTS-модель."""
        return str(getattr(self.app, "reader_tts_mlx_model", "mlx-community/Qwen3-TTS-12Hz-1.7B-VoiceDesign-4bit"))

    @property
    def reader_tts_mlx_voice_description(self) -> str:
        """Возвращает описание MLX-голоса."""
        return str(getattr(self.app, "reader_tts_mlx_voice_description", ""))

    @property
    def reader_preprocess_enabled(self) -> bool:
        """Возвращает флаг LLM-предобработки reader."""
        return bool(getattr(self.app, "reader_preprocess_enabled", True))

    @property
    def performance_mode(self) -> str:
        """Возвращает текущий режим производительности."""
        return self.app.performance_mode

    @property
    def max_time(self) -> float | None:
        """Возвращает лимит записи."""
        return self.app.max_time

    @max_time.setter
    def max_time(self, value: float | None) -> None:
        self.app.max_time = value

    @property
    def max_time_options(self) -> list[float | None]:
        """Возвращает доступные лимиты записи."""
        return self.app.max_time_options

    @property
    def model_options(self) -> list[str]:
        """Возвращает список доступных моделей."""
        return self.app.model_options

    @property
    def languages(self) -> list[str] | None:
        """Возвращает список доступных языков."""
        return self.app.languages

    @property
    def current_language(self) -> str | None:
        """Возвращает текущий язык распознавания."""
        return self.app.current_language

    @property
    def input_devices(self) -> list[Any]:
        """Возвращает список доступных устройств ввода."""
        return self.app.input_devices

    @property
    def current_input_device(self) -> Any:
        """Возвращает текущее устройство ввода."""
        return self.app.current_input_device

    @property
    def audio_profile_name(self) -> str:
        """Возвращает активный аудиопрофиль."""
        return self.app.audio_profile_name

    @property
    def high_quality_mac_builtin_enabled(self) -> bool:
        """Возвращает флаг MacBook HQ-профиля."""
        return self.app.high_quality_mac_builtin_enabled

    @property
    def permission_status(self) -> dict[str, bool | None]:
        """Возвращает статусы системных разрешений."""
        return self.app.permission_status

    @property
    def microphone_profiles(self) -> list[MicrophoneProfile]:
        """Возвращает быстрые профили микрофона."""
        return self.app.microphone_profiles

    @property
    def show_recording_notification(self) -> bool:
        """Возвращает флаг уведомления о старте записи."""
        return self.app.show_recording_notification

    @show_recording_notification.setter
    def show_recording_notification(self, value: bool) -> None:
        self.app.show_recording_notification = value

    @property
    def show_recording_overlay(self) -> bool:
        """Возвращает флаг показа overlay-индикатора."""
        return self.app.show_recording_overlay

    @show_recording_overlay.setter
    def show_recording_overlay(self, value: bool) -> None:
        self.app.show_recording_overlay = value

    @property
    def show_recording_time_in_menu_bar(self) -> bool:
        """Возвращает флаг отображения времени записи в menu bar."""
        return self.app.show_recording_time_in_menu_bar

    @show_recording_time_in_menu_bar.setter
    def show_recording_time_in_menu_bar(self, value: bool) -> None:
        self.app.show_recording_time_in_menu_bar = value

    @property
    def private_mode_enabled(self) -> bool:
        """Возвращает флаг приватного режима."""
        return self.app.private_mode_enabled

    @property
    def paste_cgevent_enabled(self) -> bool:
        """Возвращает флаг метода вставки через CGEvent."""
        return self.app.paste_cgevent_enabled

    @property
    def paste_ax_enabled(self) -> bool:
        """Возвращает флаг метода вставки через AX API."""
        return self.app.paste_ax_enabled

    @property
    def paste_clipboard_enabled(self) -> bool:
        """Возвращает флаг метода вставки через буфер обмена."""
        return self.app.paste_clipboard_enabled

    @property
    def llm_clipboard_enabled(self) -> bool:
        """Возвращает флаг использования буфера обмена для LLM."""
        return self.app.llm_clipboard_enabled

    @property
    def capitalize_first_letter_enabled(self) -> bool:
        """Возвращает флаг правила заглавной буквы."""
        return self.app.capitalize_first_letter_enabled

    @property
    def remove_trailing_period_for_single_sentence_enabled(self) -> bool:
        """Возвращает флаг удаления точки в конце одного предложения."""
        return self.app.remove_trailing_period_for_single_sentence_enabled

    @property
    def restore_trailing_period_on_next_dictation_enabled(self) -> bool:
        """Возвращает флаг автоточки перед следующей диктовкой."""
        return self.app.restore_trailing_period_on_next_dictation_enabled

    @property
    def gain_normalization_enabled(self) -> bool:
        """Возвращает флаг бережной нормализации аудио."""
        return self.app.gain_normalization_enabled

    @property
    def audio_artifact_cleanup_enabled(self) -> bool:
        """Возвращает флаг автоочистки WAV-записей."""
        return self.app.audio_artifact_cleanup_enabled

    @property
    def history(self) -> list[str]:
        """Возвращает историю распознанных текстов."""
        return self.app.history

    @property
    def total_tokens(self) -> int:
        """Возвращает суммарный счётчик токенов."""
        return self.app.total_tokens

    @property
    def recording_overlay(self) -> Any:
        """Возвращает overlay-индикатор записи."""
        return self.app.recording_overlay

    @property
    def key_listener(self) -> Any:
        """Возвращает runtime-listener основных хоткеев."""
        return self.app.key_listener

    @key_listener.setter
    def key_listener(self, value: Any) -> None:
        self.app.key_listener = value

    @property
    def start_time(self) -> float | None:
        """Возвращает время старта текущей записи."""
        return self.app.start_time

    @start_time.setter
    def start_time(self, value: float | None) -> None:
        self.app.start_time = value

    @property
    def _primary_key_combination(self) -> str:
        """Возвращает основной хоткей во внутреннем формате."""
        return self.app.primary_key_combination

    @_primary_key_combination.setter
    def _primary_key_combination(self, value: str) -> None:
        self.app.primary_key_combination = value

    @property
    def _secondary_key_combination(self) -> str:
        """Возвращает дополнительный хоткей во внутреннем формате."""
        return self.app.secondary_key_combination

    @_secondary_key_combination.setter
    def _secondary_key_combination(self, value: str) -> None:
        self.app.secondary_key_combination = value

    @property
    def _llm_key_combination(self) -> str:
        """Возвращает LLM-хоткей во внутреннем формате."""
        return self.app.llm_key_combination

    @_llm_key_combination.setter
    def _llm_key_combination(self, value: str) -> None:
        self.app.llm_key_combination = value

    def _find_menu_item(self, container: Any, title: str) -> Any:
        """Рекурсивно ищет пункт меню по заголовку."""
        try:
            return container[title]
        except Exception:
            pass

        try:
            item_titles = list(container)
        except Exception:
            return None

        for item_title in item_titles:
            try:
                item = container[item_title]
            except Exception:
                continue
            if getattr(item, "title", None) == title:
                return item
            nested_item = self._find_menu_item(item, title)
            if nested_item is not None:
                return nested_item
        return None

    def _menu_item(self, title: str) -> Any:
        """Возвращает пункт меню по заголовку."""
        item = self._find_menu_item(self.menu, title)
        if item is None:
            raise KeyError(title)
        return item

    def _state_label(self) -> str:
        """Возвращает человекочитаемое имя текущего состояния."""
        labels = {
            Config.STATUS_IDLE: "ожидание",
            Config.STATUS_RECORDING: "запись",
            Config.STATUS_TRANSCRIBING: "распознавание",
            Config.STATUS_LLM_PROCESSING: "обработка LLM",
            Config.STATUS_ZIPPER_PROCESSING: "обработка Zipper",
        }
        return labels.get(self.state, "неизвестно")

    def _format_input_device(self) -> str:
        """Возвращает строку текущего микрофона для меню."""
        if self.current_input_device is None:
            return "системный по умолчанию"
        return self.app.microphone_menu_title(self.current_input_device)

    def _format_language(self) -> str:
        """Возвращает строку текущего языка для меню."""
        if self.current_language is None:
            return "автоопределение"
        return self.current_language

    def _model_menu_title(self, model_repo: str) -> str:
        """Возвращает подпись пункта меню модели."""
        return f"Модель: {model_repo.rsplit('/', maxsplit=1)[-1]}"

    def _llm_model_menu_title(self, model_repo: str) -> str:
        """Возвращает подпись пункта меню LLM-модели."""
        return f"LLM: {model_repo.rsplit('/', maxsplit=1)[-1]}"

    def _max_time_menu_title(self, max_time_value: float | None) -> str:
        """Возвращает подпись пункта меню лимита записи."""
        return f"Лимит: {Config.format_max_time_status(max_time_value)}"

    def _permission_title(self, permission_name: str, permission_status: bool | None) -> str:
        """Формирует строку статуса разрешения для меню."""
        if permission_status is True:
            status_label = Config.PERMISSION_GRANTED
        elif permission_status is False:
            status_label = Config.PERMISSION_DENIED
        else:
            status_label = Config.PERMISSION_UNKNOWN
        return f"{permission_name}: {status_label}"

    def _permissions_menu_title(self) -> str:
        """Возвращает короткий итог по состоянию системных разрешений."""
        statuses = tuple(self.permission_status.values())
        if any(status is False for status in statuses):
            return "🛂 Доступ: нужно внимание"
        if any(status is None for status in statuses):
            return "🛂 Доступ: неизвестно"
        return "🛂 Доступ: всё ок"

    def _format_total_tokens(self, token_count: int) -> str:
        """Форматирует число токенов для отображения в меню."""
        return f"{int(token_count):,}".replace(",", " ")

    def _token_usage_title(self) -> str:
        """Возвращает заголовок пункта меню со счётчиком токенов."""
        return f"🔢 Токены: {self._format_total_tokens(self.total_tokens)}"

    def _format_tts_rate(self, rate_multiplier: float) -> str:
        """Форматирует множитель скорости TTS."""
        normalized = round(float(rate_multiplier), 2)
        if normalized.is_integer():
            return f"{int(normalized)}×"
        formatted = f"{normalized:.2f}".rstrip("0").rstrip(".")
        return f"{formatted}×"

    def _format_tts_engine(self, engine: str) -> str:
        """Форматирует backend TTS для меню."""
        return TTS_ENGINE_LABELS.get(engine, TTS_ENGINE_LABELS["apple"])

    def _short_model_name(self, model_name: str) -> str:
        """Возвращает короткое имя модели для меню."""
        return model_name.rsplit("/", maxsplit=1)[-1]

    def _format_tts_max_minutes(self, max_minutes: int) -> str:
        """Форматирует лимит длительности TTS."""
        if max_minutes <= 0:
            return "без лимита"
        return f"{max_minutes} мин"

    def _refresh_token_usage_item(self) -> None:
        """Обновляет пункт меню со счётчиком токенов."""
        self.token_usage_item.title = self._token_usage_title()

    def _refresh_permission_items(self) -> None:
        """Обновляет пункты меню со статусами разрешений."""
        self.permissions_menu.title = self._permissions_menu_title()
        self.accessibility_item.title = self._permission_title("Accessibility", self.permission_status["accessibility"])
        self.input_monitoring_item.title = self._permission_title("Input Monitoring", self.permission_status["input_monitoring"])
        self.microphone_item.title = self._permission_title("Microphone", self.permission_status["microphone"])

    def _refresh_hotkey_items(self) -> None:
        """Обновляет подписи хоткеев в меню."""
        self.hotkey_item.title = f"⌨️ Основной хоткей: {self.hotkey_status}"
        self.secondary_hotkey_item.title = f"⌨️ Доп. хоткей: {self.secondary_hotkey_status}"
        self.llm_hotkey_item.title = f"🤖 LLM-хоткей: {self.llm_hotkey_status}"
        self.zipper_hotkey_item.title = f"🧷 Zipper: {self.zipper_hotkey_status}"
        self.zipper_menu_hotkey_item.title = f"Хоткей: {self.zipper_hotkey_status}"
        self.zipper_run_item.title = f"Запустить Zipper    {self.zipper_hotkey_status}"
        self.rsvp_hotkey_item.title = f"📖 Reader: {self.rsvp_hotkey_status}"
        self.tts_hotkey_item.title = f"🔈 Speaker: {self.tts_hotkey_status}"
        self.reader_rsvp_item.title = f"👀 Запустить RSVP    {self.rsvp_hotkey_status}"
        self.reader_tts_item.title = f"🔊 Запустить TTS    {self.tts_hotkey_status}"

    def _refresh_reader_tts_voice_menu(self) -> None:
        """Пересобирает подменю системных голосов TTS."""
        if getattr(self.reader_tts_voice_menu, "_menu", None) is not None:
            self.reader_tts_voice_menu.clear()

        auto_item = rumps.MenuItem("Авто: русский голос", callback=self.change_reader_tts_voice)
        auto_item.state = int(self.reader_tts_voice_id is None)
        self.reader_tts_voice_menu.add(auto_item)

        voices = self.app.reader_available_tts_voices() if hasattr(self.app, "reader_available_tts_voices") else []
        if voices:
            self.reader_tts_voice_menu.add(None)
        for voice in voices:
            item = rumps.MenuItem(voice.menu_title, callback=self.change_reader_tts_voice)
            item.state = int(voice.identifier == self.reader_tts_voice_id)
            self.reader_tts_voice_menu.add(item)

    def _refresh_reader_items(self) -> None:
        """Обновляет пункты меню reader-настроек."""
        self.reader_preprocess_item.state = int(self.reader_preprocess_enabled)
        self.reader_rsvp_wpm_menu.title = f"Скорость: {self.reader_rsvp_wpm} wpm"
        self.reader_rsvp_chunk_menu.title = f"Размер chunk: {self.reader_rsvp_chunk_size}"
        self.reader_rsvp_font_menu.title = f"Размер шрифта: {self.reader_rsvp_font_size}"
        self.reader_tts_engine_menu.title = f"Backend: {self._format_tts_engine(self.reader_tts_engine)}"
        self.reader_tts_mlx_model_menu.title = f"MLX-модель: {self._short_model_name(self.reader_tts_mlx_model)}"
        self.reader_tts_rate_menu.title = f"Скорость речи: {self._format_tts_rate(self.reader_tts_rate_multiplier)}"
        self.reader_tts_rate_value_item.title = f"Скорость: {self._format_tts_rate(self.reader_tts_rate_multiplier)}"
        self.reader_tts_max_minutes_menu.title = f"Макс. длина аудио: {self._format_tts_max_minutes(self.reader_tts_max_minutes)}"
        self._refresh_reader_tts_voice_menu()

    def _refresh_selection_states(self) -> None:
        """Обновляет отметки выбранных пунктов меню."""
        for model in self.model_options:
            self._menu_item(self._model_menu_title(model)).state = int(model == self.model_repo)

        for max_time_value in self.max_time_options:
            self._menu_item(self._max_time_menu_title(max_time_value)).state = int(max_time_value == self.max_time)

        if self.input_devices:
            for device in self.input_devices:
                title = self.app.microphone_menu_title(device)
                self._menu_item(title).state = int(device == self.current_input_device)

        if self.languages is not None and len(self.languages) > 1:
            for lang in self.languages:
                self._menu_item(lang).state = int(lang == self.current_language)

        for performance_mode, title in Config.PERFORMANCE_MODE_LABELS.items():
            self.performance_menu[title].state = int(performance_mode == self.performance_mode)

        for title, profile in self._microphone_profile_titles.items():
            self.microphone_profiles_menu[title].state = int(self.app.is_microphone_profile_active(profile))

        for prompt_name in Config.LLM_PROMPT_PRESETS:
            self.llm_prompt_menu[prompt_name].state = int(prompt_name == self.llm_prompt_name)

        for llm_model in self.llm_model_options:
            title = self._llm_model_menu_title(llm_model)
            with contextlib.suppress(KeyError):
                self._menu_item(title).state = int(llm_model.rsplit("/", maxsplit=1)[-1] == self.llm_model_name)

        for wpm in RSVP_WPM_OPTIONS:
            self.reader_rsvp_wpm_menu[f"{wpm} wpm"].state = int(wpm == self.reader_rsvp_wpm)

        for chunk_size in RSVP_CHUNK_SIZE_OPTIONS:
            self.reader_rsvp_chunk_menu[f"{chunk_size} слов"].state = int(chunk_size == self.reader_rsvp_chunk_size)

        for font_size in RSVP_FONT_SIZE_OPTIONS:
            self.reader_rsvp_font_menu[f"{font_size} pt"].state = int(font_size == self.reader_rsvp_font_size)

        for engine, title in TTS_ENGINE_LABELS.items():
            self.reader_tts_engine_menu[title].state = int(engine == self.reader_tts_engine)

        for model_name in TTS_MLX_MODEL_OPTIONS:
            title = self._short_model_name(model_name)
            self.reader_tts_mlx_model_menu[title].state = int(model_name == self.reader_tts_mlx_model)
        self.reader_tts_mlx_model_menu["Задать модель..."].state = int(self.reader_tts_mlx_model not in TTS_MLX_MODEL_OPTIONS)

        for max_minutes in TTS_MAX_MINUTES_OPTIONS:
            title = self._format_tts_max_minutes(max_minutes)
            self.reader_tts_max_minutes_menu[title].state = int(max_minutes == self.reader_tts_max_minutes)

    def _refresh_input_device_menu(self) -> None:
        """Пересобирает подменю выбора микрофона."""
        if getattr(self.input_device_menu, "_menu", None) is not None:
            self.input_device_menu.clear()

        if not self.input_devices:
            empty_item = rumps.MenuItem("(микрофоны не найдены)")
            empty_item.set_callback(None)
            self.input_device_menu.add(empty_item)
            return

        for device in self.input_devices:
            title = self.app.microphone_menu_title(device)
            item = rumps.MenuItem(title, callback=self.change_input_device)
            item.state = int(device == self.current_input_device)
            self.input_device_menu.add(item)

    def _refresh_microphone_profiles_menu(self) -> None:
        """Пересобирает подменю быстрых профилей микрофона."""
        if getattr(self.microphone_profiles_menu, "_menu", None) is not None:
            self.microphone_profiles_menu.clear()

        self._microphone_profile_titles = {}
        self._delete_microphone_profile_titles = {}

        if not self.microphone_profiles:
            empty_item = rumps.MenuItem("(пусто)")
            empty_item.set_callback(None)
            self.microphone_profiles_menu.add(empty_item)
        else:
            for profile in self.microphone_profiles:
                title = profile.name
                item = rumps.MenuItem(title, callback=self.apply_microphone_profile)
                item.state = int(self.app.is_microphone_profile_active(profile))
                self._microphone_profile_titles[title] = profile
                self.microphone_profiles_menu.add(item)

        self.microphone_profiles_menu.add(None)
        self.microphone_profiles_menu.add(rumps.MenuItem("➕ Добавить текущий профиль…", callback=self.add_current_microphone_profile))

        delete_menu = rumps.MenuItem("🗑 Удалить профиль")
        if not self.microphone_profiles:
            empty_item = rumps.MenuItem("(нет профилей)")
            empty_item.set_callback(None)
            delete_menu.add(empty_item)
        else:
            for profile in self.microphone_profiles:
                title = profile.name
                self._delete_microphone_profile_titles[title] = profile
                delete_menu.add(rumps.MenuItem(title, callback=self.delete_microphone_profile))
        self.microphone_profiles_menu.add(delete_menu)

    def _refresh_title_and_status(self) -> None:
        """Обновляет иконку и строку статуса в menu bar."""
        self.status_item.title = f"🔄 Статус: {self._state_label()}"
        self._refresh_permission_items()

        if self.state == Config.STATUS_TRANSCRIBING:
            self.title = "🧠"
            return
        if self.state == Config.STATUS_LLM_PROCESSING:
            self.title = "🤖"
            return
        if self.state == Config.STATUS_ZIPPER_PROCESSING:
            self.title = "🧷"
            return
        self.title = "⏯"

    def _format_history_title(self, text: str) -> str:
        """Форматирует текст для отображения в подменю истории."""
        single_line = text.replace("\n", " ").replace("\r", " ")
        if len(single_line) > Config.HISTORY_DISPLAY_LENGTH:
            return single_line[: Config.HISTORY_DISPLAY_LENGTH] + "…"
        return single_line

    def _refresh_history_menu(self) -> None:
        """Обновляет подменю истории текста."""
        if getattr(self.history_menu, "_menu", None) is not None:
            self.history_menu.clear()
        self._history_title_to_text = {}

        self.app.prune_expired_history()
        history = self.history
        if not history:
            empty_item = rumps.MenuItem("(пусто)")
            empty_item.set_callback(None)
            self.history_menu.add(empty_item)
            return

        for text in history:
            title = self._format_history_title(text)
            unique_title = title
            suffix_count = 0
            while unique_title in self._history_title_to_text:
                suffix_count += 1
                unique_title = f"{title} ({suffix_count})"
            self._history_title_to_text[unique_title] = text
            self.history_menu.add(rumps.MenuItem(unique_title, callback=self._copy_history_item))

    def _apply_snapshot(self, snapshot: AppSnapshot) -> None:
        """Применяет новый snapshot DictationApp к меню."""
        self.model_item.title = f"🧠 Модель: {snapshot.model_name}"
        self.language_item.title = f"🌍 Язык: {self._format_language()}"
        self.input_device_menu.title = f"🎙️ Микрофон: {self._format_input_device()}"
        self.max_time_item.title = f"⏱ Длительность записи: {Config.format_max_time_status(snapshot.max_time)}"
        self.performance_menu.title = f"⚡ Режим работы: {Config.performance_mode_label(snapshot.performance_mode)}"
        self.audio_profile_item.title = f"Профиль: {Config.audio_profile_label(snapshot.audio_profile_name)}"
        self.recording_notification_item.state = int(snapshot.show_recording_notification)
        self.recording_overlay_item.state = int(snapshot.show_recording_overlay)
        self.recording_time_in_menu_bar_item.state = int(snapshot.show_recording_time_in_menu_bar)
        self.high_quality_mac_builtin_item.state = int(snapshot.high_quality_mac_builtin_enabled)
        self.gain_normalization_item.state = int(snapshot.gain_normalization_enabled)
        self.audio_artifact_cleanup_item.state = int(snapshot.audio_artifact_cleanup_enabled)
        self.private_mode_item.state = int(snapshot.private_mode_enabled)
        self.llm_clipboard_item.state = int(snapshot.llm_clipboard_enabled)
        self.paste_cgevent_item.state = int(snapshot.paste_cgevent_enabled)
        self.paste_ax_item.state = int(snapshot.paste_ax_enabled)
        self.paste_clipboard_item.state = int(snapshot.paste_clipboard_enabled)
        self.capitalize_first_letter_item.state = int(snapshot.capitalize_first_letter_enabled)
        self.remove_trailing_period_for_single_sentence_item.state = int(snapshot.remove_trailing_period_for_single_sentence_enabled)
        self.restore_trailing_period_on_next_dictation_item.state = int(snapshot.restore_trailing_period_on_next_dictation_enabled)
        self.llm_download_item.title = snapshot.llm_download_title
        self.llm_download_item.set_callback(self._download_llm_model if snapshot.llm_download_interactive else None)
        self.llm_model_menu.title = f"🤖 LLM-модель: {snapshot.llm_model_name}"
        self.zipper_toggle_item.title = "Выключить Zipper" if snapshot.zipper_enabled else "Включить Zipper"
        self.zipper_toggle_item.state = int(snapshot.zipper_enabled)
        self.zipper_status_item.title = f"Статус: {snapshot.zipper_status}"
        self.zipper_debug_item.state = int(snapshot.zipper_debug_panel_enabled)
        self.zipper_config_item.title = f"Открыть конфиг Zipper… ({snapshot.zipper_config_path})"

        self._refresh_hotkey_items()
        self._refresh_reader_items()
        self._refresh_permission_items()
        self._refresh_token_usage_item()
        self._refresh_input_device_menu()
        self._refresh_microphone_profiles_menu()
        self._refresh_history_menu()
        self._refresh_selection_states()

        if snapshot.started:
            self._menu_item("Начать запись").set_callback(None)
            self._menu_item("Остановить запись").set_callback(self.stop_app)
        else:
            self._menu_item("Остановить запись").set_callback(None)
            self._menu_item("Начать запись").set_callback(self.start_app)

        if not snapshot.started:
            self._refresh_title_and_status()

    def _apply_snapshot_on_main_thread(self, snapshot: AppSnapshot) -> None:
        """Переводит применение snapshot на главный поток, если callback пришёл из background thread."""
        _call_on_main_thread(self._apply_snapshot, snapshot)

    def set_state(self, state: str) -> None:
        """Делегирует изменение состояния в DictationApp."""
        self.app.set_state(state)

    def set_permission_status(self, permission_name: str, status: bool | None) -> None:
        """Делегирует изменение статуса разрешения в DictationApp."""
        self.app.set_permission_status(permission_name, status)

    def change_input_device(self, sender: rumps.MenuItem) -> None:
        """Переключает текущее устройство ввода."""
        selected_device = next(
            (device for device in self.input_devices if self.app.microphone_menu_title(device) == sender.title),
            None,
        )
        if selected_device is None:
            return
        self.app.change_input_device(selected_device["index"])

    def change_language(self, sender: rumps.MenuItem) -> None:
        """Переключает текущий язык распознавания."""
        self.app.change_language(sender.title)

    def change_model(self, sender: rumps.MenuItem) -> None:
        """Переключает модель распознавания."""
        selected_model = next((model for model in self.model_options if self._model_menu_title(model) == sender.title), None)
        if selected_model is None:
            return
        self.app.change_model(selected_model)

    def change_max_time(self, sender: rumps.MenuItem) -> None:
        """Переключает лимит записи."""
        title_to_value = {self._max_time_menu_title(value): value for value in self.max_time_options}
        selected_max_time = title_to_value.get(sender.title)
        if sender.title in title_to_value:
            self.app.change_max_time(selected_max_time)

    def add_current_microphone_profile(self, _: object) -> None:
        """Открывает диалог и добавляет профиль текущего микрофона."""
        profile_name = prompt_text(
            "Добавить быстрый профиль",
            "Введите название для текущего микрофона и набора базовых настроек.",
            default_text=self.app.suggest_microphone_profile_name(),
        )
        if profile_name is None:
            return
        self.app.add_current_microphone_profile(profile_name)

    def apply_microphone_profile(self, sender: rumps.MenuItem) -> None:
        """Применяет сохранённый профиль микрофона."""
        self.app.apply_microphone_profile(sender.title)

    def delete_microphone_profile(self, sender: rumps.MenuItem) -> None:
        """Удаляет сохранённый профиль микрофона."""
        self.app.delete_microphone_profile(sender.title)

    def change_hotkey(self, _: object) -> None:
        """Изменяет основной хоткей через DictationApp."""
        self.app.change_hotkey()

    def change_secondary_hotkey(self, _: object) -> None:
        """Изменяет дополнительный хоткей через DictationApp."""
        self.app.change_secondary_hotkey()

    def change_llm_hotkey(self, _: object) -> None:
        """Изменяет LLM-хоткей через DictationApp."""
        self.app.change_llm_hotkey()

    def change_zipper_hotkey(self, _: object) -> None:
        """Изменяет Zipper-хоткей через DictationApp."""
        self.app.change_zipper_hotkey()

    def change_rsvp_hotkey(self, _: object) -> None:
        """Изменяет RSVP-хоткей через DictationApp."""
        self.app.change_rsvp_hotkey()

    def change_tts_hotkey(self, _: object) -> None:
        """Изменяет TTS-хоткей через DictationApp."""
        self.app.change_tts_hotkey()

    def request_accessibility_access(self, _: object) -> None:
        """Повторно запрашивает Accessibility."""
        self.app.request_accessibility_access()

    def request_input_monitoring_access(self, _: object) -> None:
        """Повторно запрашивает Input Monitoring."""
        self.app.request_input_monitoring_access()

    def toggle_recording_notification(self, _sender: rumps.MenuItem) -> None:
        """Переключает системное уведомление о старте записи."""
        self.app.toggle_recording_notification()

    def toggle_recording_overlay(self, _sender: rumps.MenuItem) -> None:
        """Переключает индикатор записи у курсора."""
        self.app.toggle_recording_overlay()

    def toggle_recording_time_in_menu_bar(self, _sender: rumps.MenuItem) -> None:
        """Переключает показ времени записи в строке меню."""
        self.app.toggle_recording_time_in_menu_bar()

    def toggle_high_quality_mac_builtin(self, _sender: rumps.MenuItem) -> None:
        """Переключает автоматический MacBook HQ-профиль."""
        self.app.toggle_high_quality_mac_builtin()

    def toggle_gain_normalization(self, _sender: rumps.MenuItem) -> None:
        """Переключает бережную нормализацию аудио."""
        self.app.toggle_gain_normalization()

    def toggle_audio_artifact_cleanup(self, _sender: rumps.MenuItem) -> None:
        """Переключает автоочистку диагностических WAV-записей."""
        self.app.toggle_audio_artifact_cleanup()

    def open_recordings_directory(self, _sender: rumps.MenuItem) -> None:
        """Открывает папку диагностических WAV-записей."""
        self.app.open_recordings_directory()

    def change_performance_mode(self, sender: rumps.MenuItem) -> None:
        """Переключает режим производительности."""
        selected_mode = next(
            (performance_mode for performance_mode, title in Config.PERFORMANCE_MODE_LABELS.items() if title == sender.title),
            None,
        )
        if selected_mode is not None:
            self.app.change_performance_mode(selected_mode)

    def toggle_private_mode(self, _sender: rumps.MenuItem) -> None:
        """Переключает private mode."""
        self.app.toggle_private_mode()

    def toggle_paste_cgevent(self, _sender: rumps.MenuItem) -> None:
        """Переключает метод вставки CGEvent."""
        self.app.toggle_paste_cgevent()

    def toggle_paste_ax(self, _sender: rumps.MenuItem) -> None:
        """Переключает метод вставки Accessibility API."""
        self.app.toggle_paste_ax()

    def toggle_paste_clipboard(self, _sender: rumps.MenuItem) -> None:
        """Переключает метод вставки через буфер обмена."""
        self.app.toggle_paste_clipboard()

    def toggle_llm_clipboard(self, _sender: rumps.MenuItem) -> None:
        """Переключает использование буфера обмена для LLM."""
        self.app.toggle_llm_clipboard()

    def start_rsvp(self, _sender: rumps.MenuItem) -> None:
        """Запускает RSVP из буфера обмена."""
        self.app.toggle_rsvp()

    def start_tts(self, _sender: rumps.MenuItem) -> None:
        """Запускает TTS из буфера обмена."""
        self.app.toggle_tts()

    def start_zipper(self, _sender: rumps.MenuItem) -> None:
        """Запускает Zipper из меню."""
        self.app.toggle_zipper()

    def toggle_zipper_enabled(self, _sender: rumps.MenuItem) -> None:
        """Включает или выключает Zipper."""
        self.app.toggle_zipper_enabled()

    def open_zipper_config(self, _sender: rumps.MenuItem) -> None:
        """Открывает конфиг Zipper."""
        self.app.open_zipper_config()

    def reload_zipper_config(self, _sender: rumps.MenuItem) -> None:
        """Перечитывает конфиг Zipper."""
        self.app.reload_zipper_config()

    def toggle_zipper_debug_panel(self, _sender: rumps.MenuItem) -> None:
        """Переключает debug-панель Zipper."""
        self.app.toggle_zipper_debug_panel()

    def clear_zipper_context(self, _sender: rumps.MenuItem) -> None:
        """Очищает контекст Zipper."""
        self.app.clear_zipper_context()

    def clear_zipper_memory(self, _sender: rumps.MenuItem) -> None:
        """Очищает постоянную память Zipper."""
        self.app.clear_zipper_memory()

    def change_reader_rsvp_wpm(self, sender: rumps.MenuItem) -> None:
        """Меняет скорость RSVP."""
        try:
            self.app.change_reader_rsvp_wpm(int(sender.title.split()[0]))
        except (ValueError, IndexError):
            LOGGER.warning("📖 Некорректный пункт скорости RSVP: %s", sender.title)

    def change_reader_rsvp_chunk_size(self, sender: rumps.MenuItem) -> None:
        """Меняет размер chunk-а RSVP."""
        try:
            self.app.change_reader_rsvp_chunk_size(int(sender.title.split()[0]))
        except (ValueError, IndexError):
            LOGGER.warning("📖 Некорректный пункт chunk RSVP: %s", sender.title)

    def change_reader_rsvp_font_size(self, sender: rumps.MenuItem) -> None:
        """Меняет размер шрифта RSVP."""
        try:
            self.app.change_reader_rsvp_font_size(int(sender.title.split()[0]))
        except (ValueError, IndexError):
            LOGGER.warning("📖 Некорректный пункт шрифта RSVP: %s", sender.title)

    def decrease_reader_tts_rate_multiplier(self, _sender: rumps.MenuItem) -> None:
        """Уменьшает скорость TTS на один шаг."""
        self.app.change_reader_tts_rate_multiplier(self.reader_tts_rate_multiplier - TTS_RATE_MULTIPLIER_STEP)

    def increase_reader_tts_rate_multiplier(self, _sender: rumps.MenuItem) -> None:
        """Увеличивает скорость TTS на один шаг."""
        self.app.change_reader_tts_rate_multiplier(self.reader_tts_rate_multiplier + TTS_RATE_MULTIPLIER_STEP)

    def change_reader_tts_engine(self, sender: rumps.MenuItem) -> None:
        """Меняет backend TTS."""
        selected = next((engine for engine, title in TTS_ENGINE_LABELS.items() if title == sender.title), None)
        if selected is not None:
            self.app.change_reader_tts_engine(selected)

    def change_reader_tts_mlx_model(self, sender: rumps.MenuItem) -> None:
        """Меняет MLX TTS-модель."""
        selected = next((model_name for model_name in TTS_MLX_MODEL_OPTIONS if self._short_model_name(model_name) == sender.title), None)
        if selected is not None:
            self.app.change_reader_tts_mlx_model(selected)

    def prompt_reader_tts_mlx_model(self, _sender: rumps.MenuItem) -> None:
        """Открывает диалог точного имени MLX TTS-модели."""
        model_name = prompt_text(
            "MLX TTS-модель",
            "Введите имя локальной MLX TTS-модели или repo id.",
            default_text=self.reader_tts_mlx_model,
        )
        if model_name is None:
            return
        self.app.change_reader_tts_mlx_model(model_name)

    def prompt_reader_tts_mlx_voice_description(self, _sender: rumps.MenuItem) -> None:
        """Открывает диалог описания голоса MLX VoiceDesign."""
        description = prompt_text(
            "Описание MLX-голоса",
            "Опишите голос для Qwen3-TTS VoiceDesign.",
            default_text=self.reader_tts_mlx_voice_description,
        )
        if description is None:
            return
        self.app.change_reader_tts_mlx_voice_description(description)

    def change_reader_tts_voice(self, sender: rumps.MenuItem) -> None:
        """Меняет системный голос TTS."""
        if sender.title.startswith("Авто:"):
            self.app.change_reader_tts_voice(None)
            return
        voices = self.app.reader_available_tts_voices() if hasattr(self.app, "reader_available_tts_voices") else []
        selected = next((voice for voice in voices if voice.menu_title == sender.title), None)
        if selected is not None:
            self.app.change_reader_tts_voice(selected.identifier)

    def change_reader_tts_max_minutes(self, sender: rumps.MenuItem) -> None:
        """Меняет максимальную длительность TTS."""
        if sender.title == "без лимита":
            self.app.change_reader_tts_max_minutes(0)
            return
        try:
            self.app.change_reader_tts_max_minutes(int(sender.title.split()[0]))
        except (ValueError, IndexError):
            LOGGER.warning("🔈 Некорректный пункт лимита TTS: %s", sender.title)

    def toggle_reader_preprocess(self, _sender: rumps.MenuItem) -> None:
        """Переключает LLM-предобработку reader."""
        self.app.toggle_reader_preprocess()

    def toggle_capitalize_first_letter(self, _sender: rumps.MenuItem) -> None:
        """Переключает правило заглавной буквы после распознавания."""
        self.app.toggle_capitalize_first_letter()

    def toggle_remove_trailing_period_for_single_sentence(self, _sender: rumps.MenuItem) -> None:
        """Переключает удаление точки в конце одного предложения."""
        self.app.toggle_remove_trailing_period_for_single_sentence()

    def toggle_restore_trailing_period_on_next_dictation(self, _sender: rumps.MenuItem) -> None:
        """Переключает автоточку перед следующей диктовкой."""
        self.app.toggle_restore_trailing_period_on_next_dictation()

    def _copy_history_item(self, sender: rumps.MenuItem) -> None:
        """Копирует выбранный элемент истории в буфер обмена."""
        full_text = self._history_title_to_text.get(sender.title)
        if full_text is None:
            LOGGER.warning("⚠️ Не найден текст для пункта истории: %s", sender.title)
            return
        self.app.copy_history_text(full_text)

    @rumps.clicked("Начать запись")  # type: ignore[untyped-decorator]
    def start_app(self, _: object) -> None:
        """Запускает запись."""
        self.app.start_recording()
        self.on_status_tick(None)

    @rumps.clicked("Остановить запись")  # type: ignore[untyped-decorator]
    def stop_app(self, _: object) -> None:
        """Останавливает запись."""
        self.app.stop_recording()
        self._refresh_title_and_status()

    def on_status_tick(self, _: object) -> None:
        """Обновляет индикатор времени записи в строке меню."""
        self.app.on_status_tick()
        if not self.started:
            self._refresh_title_and_status()
            return

        if self.show_recording_time_in_menu_bar:
            minutes, seconds = divmod(self.elapsed_time, 60)
            self.title = f"{minutes:02d}:{seconds:02d} 🔴"
        else:
            self.title = "🔴"
        self.status_item.title = f"🔄 Статус: {self._state_label()}"

    def toggle(self) -> None:
        """Переключает обычный сценарий записи."""
        self.app.toggle()
        if self.started:
            self.on_status_tick(None)
        else:
            self._refresh_title_and_status()

    def toggle_llm(self) -> None:
        """Переключает LLM-сценарий записи."""
        self.app.toggle_llm()
        if self.started:
            self.on_status_tick(None)
        else:
            self._refresh_title_and_status()

    def cancel_recording(self) -> None:
        """Отменяет активную запись без распознавания."""
        self.app.cancel_recording()
        self._refresh_title_and_status()

    def _download_llm_model(self, _: object) -> None:
        """Запускает загрузку LLM-модели через DictationApp."""
        self.app.download_llm_model()

    def _change_llm_prompt(self, sender: rumps.MenuItem) -> None:
        """Переключает текущий пресет системного промпта LLM."""
        self.app.change_llm_prompt(sender.title)

    def _change_llm_model(self, sender: rumps.MenuItem) -> None:
        """Переключает LLM-модель."""
        selected = next(
            (m for m in self.llm_model_options if self._llm_model_menu_title(m) == sender.title),
            None,
        )
        if selected is not None:
            self.app.change_llm_model(selected)
