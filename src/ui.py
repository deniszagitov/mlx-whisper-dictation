"""UI menu bar приложения Dictator.

Содержит StatusBarApp — основной класс меню, а также вспомогательные
функции для работы с профилями микрофона и диалоговыми окнами.
"""

import json
import logging
import threading
import time
from typing import Any, cast

import rumps

from audio import list_input_devices, microphone_menu_title
from config import (
    DEFAULT_LLM_PROMPT_NAME,
    DEFAULT_MODEL_NAME,
    DEFAULT_PERFORMANCE_MODE,
    DEFAULTS_KEY_LANGUAGE,
    DEFAULTS_KEY_LLM_CLIPBOARD,
    DEFAULTS_KEY_LLM_HOTKEY,
    DEFAULTS_KEY_LLM_PROMPT,
    DEFAULTS_KEY_MICROPHONE_PROFILES,
    DEFAULTS_KEY_MODEL,
    DEFAULTS_KEY_PASTE_AX,
    DEFAULTS_KEY_PASTE_CGEVENT,
    DEFAULTS_KEY_PASTE_CLIPBOARD,
    DEFAULTS_KEY_PERFORMANCE_MODE,
    DEFAULTS_KEY_PRIMARY_HOTKEY,
    DEFAULTS_KEY_PRIVATE_MODE,
    DEFAULTS_KEY_RECORDING_NOTIFICATION,
    DEFAULTS_KEY_SECONDARY_HOTKEY,
    DOWNLOAD_COMPLETE_PCT,
    HISTORY_DISPLAY_LENGTH,
    LLM_PROMPT_PRESETS,
    MAX_MICROPHONE_PROFILES,
    MAX_TIME_PRESETS,
    MODEL_PRESETS,
    PERFORMANCE_MODE_LABELS,
    STATUS_IDLE,
    STATUS_LLM_PROCESSING,
    STATUS_RECORDING,
    STATUS_TRANSCRIBING,
    _load_defaults_bool,
    _load_defaults_input_device_index,
    _load_defaults_str,
    _normalize_performance_mode,
    _performance_mode_label,
    _remove_defaults_key,
    _save_defaults_bool,
    _save_defaults_input_device_index,
    _save_defaults_max_time,
    _save_defaults_str,
    format_max_time_status,
)
from hotkeys import (
    GlobalKeyListener,
    capture_hotkey_combination,
    format_hotkey_status,
    normalize_key_combination,
)
from permissions import (
    get_accessibility_status,
    get_input_monitoring_status,
    notify_user,
    permission_label,
    request_accessibility_permission,
    request_input_monitoring_permission,
    warn_missing_accessibility_permission,
    warn_missing_input_monitoring_permission,
)

LOGGER = logging.getLogger(__name__)


def prompt_text(title, message, default_text=""):
    """Открывает простое окно ввода текста и возвращает введённое значение."""
    response = rumps.Window(
        title=title,
        message=message,
        default_text=default_text,
        ok="Сохранить",
        cancel=True,
        dimensions=(320, 120),
    ).run()
    if not getattr(response, "clicked", False):
        return None
    return str(getattr(response, "text", "")).strip()


def _normalize_microphone_profile(raw_profile):
    """Нормализует сохранённый профиль микрофона."""
    if not isinstance(raw_profile, dict):
        return None

    name = str(raw_profile.get("name") or "").strip()
    input_device_index = raw_profile.get("input_device_index")
    if not name or input_device_index is None:
        return None

    try:
        normalized_index = int(input_device_index)
    except (TypeError, ValueError):
        return None

    max_time = raw_profile.get("max_time")
    if max_time is not None:
        try:
            parsed_max_time = float(max_time)
        except (TypeError, ValueError):
            max_time = None
        else:
            max_time = int(parsed_max_time) if parsed_max_time.is_integer() else parsed_max_time

    language = raw_profile.get("language")
    if language is not None:
        language = str(language)

    model_repo = str(raw_profile.get("model_repo") or DEFAULT_MODEL_NAME)
    performance_mode = _normalize_performance_mode(raw_profile.get("performance_mode"))

    return {
        "name": name,
        "input_device_index": normalized_index,
        "input_device_name": str(raw_profile.get("input_device_name") or ""),
        "model_repo": model_repo,
        "language": language,
        "max_time": max_time,
        "performance_mode": performance_mode,
        "private_mode": bool(raw_profile.get("private_mode", False)),
        "paste_cgevent": bool(raw_profile.get("paste_cgevent", True)),
        "paste_ax": bool(raw_profile.get("paste_ax", False)),
        "paste_clipboard": bool(raw_profile.get("paste_clipboard", False)),
        "llm_clipboard": bool(raw_profile.get("llm_clipboard", True)),
    }


def _load_microphone_profiles():
    """Читает быстрые профили микрофона из NSUserDefaults."""
    raw_value = _load_defaults_str(DEFAULTS_KEY_MICROPHONE_PROFILES, fallback="")
    if not raw_value:
        return []

    try:
        payload = json.loads(raw_value)
    except Exception:
        LOGGER.exception("⚠️ Не удалось прочитать сохранённые профили микрофона")
        return []

    if not isinstance(payload, list):
        return []

    profiles = []
    for raw_profile in payload[:MAX_MICROPHONE_PROFILES]:
        normalized_profile = _normalize_microphone_profile(raw_profile)
        if normalized_profile is not None:
            profiles.append(normalized_profile)
    return profiles


def _save_microphone_profiles(profiles):
    """Сохраняет быстрые профили микрофона в NSUserDefaults."""
    serialized_profiles = []
    for profile in profiles[:MAX_MICROPHONE_PROFILES]:
        normalized_profile = _normalize_microphone_profile(profile)
        if normalized_profile is not None:
            serialized_profiles.append(normalized_profile)
    _save_defaults_str(
        DEFAULTS_KEY_MICROPHONE_PROFILES,
        json.dumps(serialized_profiles, ensure_ascii=False),
    )


class StatusBarApp(rumps.App):
    """Menu bar приложение для управления записью и распознаванием.

    Attributes:
        languages: Доступные языки распознавания или None.
        current_language: Текущий выбранный язык или None.
        started: Флаг активной записи.
        recorder: Объект записи аудио.
        max_time: Максимальная длительность записи в секундах.
        elapsed_time: Количество секунд с начала текущей записи.
        status_timer: Таймер обновления индикатора в строке меню.
    """

    def __init__(
        self,
        recorder,
        model_name,
        hotkey_status,
        languages=None,
        max_time=None,
        key_combination=None,
        secondary_hotkey_status=None,
        secondary_key_combination=None,
        llm_hotkey_status=None,
        llm_key_combination=None,
        use_double_command_hotkey=False,
    ):
        """Создает menu bar приложение.

        Args:
            recorder: Объект Recorder для записи и распознавания.
            model_name: Имя модели, показываемое в меню приложения.
            hotkey_status: Строка для отображения текущего хоткея в меню.
            languages: Необязательный список доступных языков.
            max_time: Необязательный лимит длительности записи в секундах.
            key_combination: Нормализованная строка комбинации клавиш.
            secondary_hotkey_status: Строка для отображения дополнительного хоткея.
            secondary_key_combination: Нормализованная строка дополнительной комбинации.
            llm_hotkey_status: Строка для отображения LLM-хоткея.
            llm_key_combination: Нормализованная строка комбинации для LLM.
            use_double_command_hotkey: Включён ли режим запуска по двойному нажатию Command.
        """
        super().__init__("whisper", "⏯")
        self.recorder = recorder
        self.model_repo = model_name
        self.model_name = model_name.rsplit("/", maxsplit=1)[-1]
        self.hotkey_status = hotkey_status
        self.secondary_hotkey_status = secondary_hotkey_status or "не задан"
        self._primary_key_combination = "" if use_double_command_hotkey else (key_combination or "")
        self._secondary_key_combination = "" if use_double_command_hotkey else (secondary_key_combination or "")
        self._llm_key_combination = llm_key_combination or ""
        self.llm_hotkey_status = llm_hotkey_status or "не задан"
        self.llm_prompt_name = _load_defaults_str(DEFAULTS_KEY_LLM_PROMPT, DEFAULT_LLM_PROMPT_NAME)
        if self.llm_prompt_name not in LLM_PROMPT_PRESETS:
            self.llm_prompt_name = DEFAULT_LLM_PROMPT_NAME
        self.performance_mode = _normalize_performance_mode(
            _load_defaults_str(DEFAULTS_KEY_PERFORMANCE_MODE, DEFAULT_PERFORMANCE_MODE),
        )
        self.max_time_options = list(MAX_TIME_PRESETS)
        if max_time not in self.max_time_options:
            self.max_time_options.insert(0, max_time)
        self.model_options = list(MODEL_PRESETS)
        if self.model_repo not in self.model_options:
            self.model_options.insert(0, self.model_repo)
        self.languages = languages
        self.input_devices = list_input_devices()
        saved_language = _load_defaults_str(DEFAULTS_KEY_LANGUAGE, fallback=None)
        self.current_language = languages[0] if languages is not None else None
        if languages is not None and saved_language in languages:
            self.current_language = saved_language
        self.current_input_device = next((device for device in self.input_devices if device["is_default"]), None)
        saved_input_device_index = _load_defaults_input_device_index()
        if saved_input_device_index is not None:
            saved_input_device = next(
                (device for device in self.input_devices if device["index"] == saved_input_device_index),
                None,
            )
            if saved_input_device is not None:
                self.current_input_device = saved_input_device
        if self.current_input_device is None and self.input_devices:
            self.current_input_device = self.input_devices[0]
        self.state = STATUS_IDLE
        self.permission_status = {
            "accessibility": get_accessibility_status(),
            "input_monitoring": get_input_monitoring_status(),
            "microphone": None,
        }
        self.max_time = max_time
        self.microphone_profiles = _load_microphone_profiles()
        self.status_item = rumps.MenuItem(f"🔄 Статус: {self._state_label()}")
        self.model_item = rumps.MenuItem(f"🧠 Модель: {self.model_name}")
        self.hotkey_item = rumps.MenuItem(f"⌨️ Основной хоткей: {self.hotkey_status}")
        self.secondary_hotkey_item = rumps.MenuItem(f"⌨️ Доп. хоткей: {self.secondary_hotkey_status}")
        self.change_hotkey_item = rumps.MenuItem("⌨️ Изменить основной хоткей…", callback=self.change_hotkey)
        self.change_secondary_hotkey_item = rumps.MenuItem("⌨️ Изменить доп. хоткей…", callback=self.change_secondary_hotkey)

        # LLM-хоткей и промпты
        self.llm_hotkey_item = rumps.MenuItem(f"🤖 LLM-хоткей: {self.llm_hotkey_status}")
        self.change_llm_hotkey_item = rumps.MenuItem("🤖 Изменить LLM-хоткей…", callback=self.change_llm_hotkey)
        self.llm_prompt_menu = rumps.MenuItem("🤖 Системный промпт LLM")
        for prompt_name in LLM_PROMPT_PRESETS:
            item = rumps.MenuItem(prompt_name, callback=self._change_llm_prompt)
            item.state = int(prompt_name == self.llm_prompt_name)
            self.llm_prompt_menu.add(item)
        self.llm_clipboard_item = rumps.MenuItem("🤖 Буфер обмена для LLM", callback=self.toggle_llm_clipboard)
        self._llm_downloading = False
        llm_processor = self.recorder.llm_processor if hasattr(self.recorder, "llm_processor") else None
        llm_cached = llm_processor.is_model_cached() if llm_processor is not None else False
        self.llm_download_item = rumps.MenuItem(
            "✅ LLM-модель загружена" if llm_cached else "📥 Скачать LLM-модель…",
            callback=None if llm_cached else self._download_llm_model,
        )

        self.show_recording_notification = _load_defaults_bool(DEFAULTS_KEY_RECORDING_NOTIFICATION, fallback=True)
        self.recording_notification_item = rumps.MenuItem(
            "🔔 Уведомление о старте записи",
            callback=self.toggle_recording_notification,
        )
        self.recording_notification_item.state = int(self.show_recording_notification)
        self.performance_menu = rumps.MenuItem(f"⚡ Режим работы: {_performance_mode_label(self.performance_mode)}")
        for performance_mode, title in PERFORMANCE_MODE_LABELS.items():
            item = rumps.MenuItem(title, callback=self.change_performance_mode)
            item.state = int(performance_mode == self.performance_mode)
            self.performance_menu.add(item)

        # Подменю «Метод ввода»
        self.paste_method_menu = rumps.MenuItem("📝 Метод ввода")
        transcriber = self.recorder.transcriber if hasattr(self.recorder, "transcriber") else None
        self.private_mode_item = rumps.MenuItem("🕶 Приватный режим", callback=self.toggle_private_mode)
        if transcriber is not None:
            self.private_mode_item.state = int(transcriber.private_mode_enabled)
            self.llm_clipboard_item.state = int(getattr(transcriber, "llm_clipboard_enabled", True))
        else:
            self.llm_clipboard_item.state = int(_load_defaults_bool(DEFAULTS_KEY_LLM_CLIPBOARD, fallback=True))
        self.paste_cgevent_item = rumps.MenuItem("Прямой ввод (CGEvent)", callback=self.toggle_paste_cgevent)
        self.paste_ax_item = rumps.MenuItem("Accessibility API", callback=self.toggle_paste_ax)
        self.paste_clipboard_item = rumps.MenuItem("Буфер обмена (Cmd+V)", callback=self.toggle_paste_clipboard)
        if transcriber is not None:
            self.paste_cgevent_item.state = int(transcriber.paste_cgevent_enabled)
            self.paste_ax_item.state = int(transcriber.paste_ax_enabled)
            self.paste_clipboard_item.state = int(transcriber.paste_clipboard_enabled)
        else:
            self.paste_cgevent_item.state = 1
        self.paste_method_menu.add(self.paste_cgevent_item)
        self.paste_method_menu.add(self.paste_ax_item)
        self.paste_method_menu.add(self.paste_clipboard_item)

        # Подменю «История текста»
        self.history_menu = rumps.MenuItem("📋 История текста")
        self._history_title_to_text = {}
        self._refresh_history_menu()
        if transcriber is not None:
            transcriber.history_callback = self._refresh_history_menu

        self.token_usage_item = rumps.MenuItem(self._token_usage_title())
        self.token_usage_item.set_callback(None)
        if transcriber is not None:
            transcriber.token_usage_callback = self._refresh_token_usage_item

        self.language_item = rumps.MenuItem(f"🌍 Язык: {self._format_language()}")
        self.input_device_item = rumps.MenuItem(f"🎙️ Микрофон: {self._format_input_device()}")
        self.microphone_profiles_menu = rumps.MenuItem("🎚 Быстрые профили")
        self.input_device_menu = rumps.MenuItem("🎙️ Выбрать микрофон")
        self._microphone_profile_titles = {}
        self._delete_microphone_profile_titles = {}
        self._refresh_microphone_profiles_menu()
        self._refresh_input_device_menu()
        self.max_time_item = rumps.MenuItem(f"⏱ Длительность записи: {format_max_time_status(max_time)}")
        self.accessibility_item = rumps.MenuItem(self._permission_title("Accessibility", self.permission_status["accessibility"]))
        self.input_monitoring_item = rumps.MenuItem(self._permission_title("Input Monitoring", self.permission_status["input_monitoring"]))
        self.microphone_item = rumps.MenuItem(self._permission_title("Microphone", self.permission_status["microphone"]))
        self.request_accessibility_item = rumps.MenuItem("🛂 Запросить Accessibility", callback=self.request_accessibility_access)
        self.request_input_monitoring_item = rumps.MenuItem("🛂 Запросить Input Monitoring", callback=self.request_input_monitoring_access)

        menu = [
            "Начать запись",
            "Остановить запись",
            self.status_item,
            self.model_item,
            self.hotkey_item,
            self.secondary_hotkey_item,
            self.llm_hotkey_item,
            self.change_hotkey_item,
            self.change_secondary_hotkey_item,
            self.change_llm_hotkey_item,
            self.recording_notification_item,
            self.performance_menu,
            self.private_mode_item,
            self.paste_method_menu,
            self.llm_prompt_menu,
            self.llm_clipboard_item,
            self.llm_download_item,
            self.history_menu,
            self.token_usage_item,
            self.language_item,
            self.input_device_item,
            self.microphone_profiles_menu,
            self.input_device_menu,
            self.max_time_item,
            "🧠 Выбрать модель",
            "⏱ Выбрать лимит записи",
            self.accessibility_item,
            self.input_monitoring_item,
            self.microphone_item,
            self.request_accessibility_item,
            self.request_input_monitoring_item,
            None,
        ]

        if languages is not None and len(languages) > 1:
            for lang in languages:
                callback = self.change_language
                menu.append(rumps.MenuItem(lang, callback=callback))
            menu.append(None)

        menu.extend(rumps.MenuItem(self._model_menu_title(model), callback=self.change_model) for model in self.model_options)
        menu.append(None)

        menu.extend(
            rumps.MenuItem(self._max_time_menu_title(max_time_value), callback=self.change_max_time)
            for max_time_value in self.max_time_options
        )
        menu.append(None)

        self.menu = menu
        self._menu_item("Остановить запись").set_callback(None)

        self.started = False
        self.key_listener = cast("Any", None)
        self.recorder.set_input_device(self.current_input_device)
        if hasattr(self.recorder, "set_performance_mode"):
            self.recorder.set_performance_mode(self.performance_mode)
        self.recorder.llm_prompt_name = self.llm_prompt_name
        self.recorder.llm_system_prompt = LLM_PROMPT_PRESETS.get(
            self.llm_prompt_name,
            LLM_PROMPT_PRESETS[DEFAULT_LLM_PROMPT_NAME],
        )
        self.recorder.set_status_callback(self.set_state)
        self.recorder.set_permission_callback(self.set_permission_status)
        self.elapsed_time = 0
        self.status_timer = rumps.Timer(self.on_status_tick, 1)
        self.status_timer.start()
        self._refresh_selection_states()

    def _find_menu_item(self, container, title):
        """Рекурсивно ищет пункт меню по заголовку."""
        try:
            return cast("Any", container)[title]
        except Exception:
            pass

        try:
            item_titles = list(container)
        except Exception:
            return None

        for item_title in item_titles:
            try:
                item = cast("Any", container)[item_title]
            except Exception:
                continue
            if getattr(item, "title", None) == title:
                return item
            nested_item = self._find_menu_item(item, title)
            if nested_item is not None:
                return nested_item
        return None

    def _menu_item(self, title):
        """Возвращает пункт меню по заголовку.

        Args:
            title: Текст пункта меню.

        Returns:
            Объект пункта меню из rumps.
        """
        item = self._find_menu_item(self.menu, title)
        if item is None:
            raise KeyError(title)
        return item

    def _state_label(self):
        """Возвращает человекочитаемое имя текущего состояния."""
        labels = {
            STATUS_IDLE: "ожидание",
            STATUS_RECORDING: "запись",
            STATUS_TRANSCRIBING: "распознавание",
            STATUS_LLM_PROCESSING: "обработка LLM",
        }
        return labels.get(self.state, "неизвестно")

    def _format_input_device(self):
        """Возвращает строку текущего микрофона для меню."""
        if self.current_input_device is None:
            return "системный по умолчанию"
        return microphone_menu_title(self.current_input_device)

    def _format_language(self):
        """Возвращает строку текущего языка для меню."""
        if self.current_language is None:
            return "автоопределение"
        return self.current_language

    def _model_menu_title(self, model_repo):
        """Возвращает подпись пункта меню модели."""
        return f"Модель: {model_repo.rsplit('/', maxsplit=1)[-1]}"

    def _max_time_menu_title(self, max_time_value):
        """Возвращает подпись пункта меню лимита записи."""
        return f"Лимит: {format_max_time_status(max_time_value)}"

    def _permission_title(self, permission_name, permission_status):
        """Формирует строку статуса разрешения для меню.

        Args:
            permission_name: Имя разрешения.
            permission_status: Булев статус разрешения или None.

        Returns:
            Строка для пункта меню.
        """
        return f"{permission_name}: {permission_label(permission_status)}"

    def _format_total_tokens(self, token_count):
        """Форматирует число токенов для отображения в меню."""
        return f"{int(token_count):,}".replace(",", " ")

    def _token_usage_title(self):
        """Возвращает заголовок пункта меню со счётчиком токенов."""
        transcriber = self.recorder.transcriber if hasattr(self.recorder, "transcriber") else None
        total_tokens = transcriber.total_tokens if transcriber is not None else 0
        return f"🔢 Токены: {self._format_total_tokens(total_tokens)}"

    def _refresh_token_usage_item(self):
        """Обновляет пункт меню с общим числом потраченных токенов."""
        self.token_usage_item.title = self._token_usage_title()

    def _refresh_permission_items(self):
        """Обновляет пункты меню со статусами разрешений."""
        self.permission_status["accessibility"] = get_accessibility_status()
        self.permission_status["input_monitoring"] = get_input_monitoring_status()
        self.accessibility_item.title = self._permission_title("Accessibility", self.permission_status["accessibility"])
        self.input_monitoring_item.title = self._permission_title("Input Monitoring", self.permission_status["input_monitoring"])
        self.microphone_item.title = self._permission_title("Microphone", self.permission_status["microphone"])

    def _refresh_selection_states(self):
        """Обновляет отметки выбранных пунктов в списках меню."""
        for model in self.model_options:
            self._menu_item(self._model_menu_title(model)).state = int(model == self.model_repo)

        for max_time_value in self.max_time_options:
            self._menu_item(self._max_time_menu_title(max_time_value)).state = int(max_time_value == self.max_time)

        if self.input_devices:
            for device in self.input_devices:
                title = microphone_menu_title(device)
                self._menu_item(title).state = int(device == self.current_input_device)

        if self.languages is not None and len(self.languages) > 1:
            for lang in self.languages:
                self._menu_item(lang).state = int(lang == self.current_language)

        for performance_mode, title in PERFORMANCE_MODE_LABELS.items():
            self.performance_menu[title].state = int(performance_mode == self.performance_mode)

        for title, profile in self._microphone_profile_titles.items():
            self.microphone_profiles_menu[title].state = int(self._is_microphone_profile_active(profile))

    def _persist_microphone_profiles(self):
        """Сохраняет быстрые профили микрофона."""
        _save_microphone_profiles(self.microphone_profiles)

    def _active_input_device_index(self):
        """Возвращает индекс активного микрофона или None."""
        if self.current_input_device is None:
            return None
        return int(self.current_input_device["index"])

    def _suggest_microphone_profile_name(self):
        """Возвращает имя профиля по умолчанию для текущего микрофона."""
        if self.current_input_device is None:
            return "Новый профиль"
        return str(self.current_input_device.get("name") or "Новый профиль")

    def _unique_microphone_profile_name(self, base_name):
        """Делает имя профиля уникальным в пределах сохранённого списка."""
        normalized_name = " ".join(base_name.split()) or "Новый профиль"
        existing_names = {profile["name"] for profile in self.microphone_profiles}
        if normalized_name not in existing_names:
            return normalized_name

        suffix = 2
        while f"{normalized_name} {suffix}" in existing_names:
            suffix += 1
        return f"{normalized_name} {suffix}"

    def _current_microphone_profile(self, profile_name):
        """Собирает профиль из текущих настроек приложения."""
        transcriber = self.recorder.transcriber if hasattr(self.recorder, "transcriber") else None
        return {
            "name": profile_name,
            "input_device_index": self._active_input_device_index(),
            "input_device_name": "" if self.current_input_device is None else str(self.current_input_device.get("name") or ""),
            "model_repo": self.model_repo,
            "language": self.current_language,
            "max_time": self.max_time,
            "performance_mode": self.performance_mode,
            "private_mode": bool(getattr(transcriber, "private_mode_enabled", False)),
            "paste_cgevent": bool(getattr(transcriber, "paste_cgevent_enabled", True)),
            "paste_ax": bool(getattr(transcriber, "paste_ax_enabled", False)),
            "paste_clipboard": bool(getattr(transcriber, "paste_clipboard_enabled", False)),
            "llm_clipboard": bool(getattr(transcriber, "llm_clipboard_enabled", True)),
        }

    def _is_microphone_profile_active(self, profile):
        """Проверяет, соответствует ли профиль текущим настройкам."""
        if profile.get("input_device_index") != self._active_input_device_index():
            return False
        if profile.get("model_repo") != self.model_repo:
            return False
        if profile.get("language") != self.current_language:
            return False
        if profile.get("max_time") != self.max_time:
            return False
        if profile.get("performance_mode") != self.performance_mode:
            return False

        transcriber = self.recorder.transcriber if hasattr(self.recorder, "transcriber") else None
        if transcriber is None:
            return True

        return (
            bool(profile.get("private_mode", False)) == bool(getattr(transcriber, "private_mode_enabled", False))
            and bool(profile.get("paste_cgevent", True)) == bool(getattr(transcriber, "paste_cgevent_enabled", True))
            and bool(profile.get("paste_ax", False)) == bool(getattr(transcriber, "paste_ax_enabled", False))
            and bool(profile.get("paste_clipboard", False)) == bool(getattr(transcriber, "paste_clipboard_enabled", False))
            and bool(profile.get("llm_clipboard", True)) == bool(getattr(transcriber, "llm_clipboard_enabled", True))
        )

    def _refresh_input_device_menu(self):
        """Пересобирает подменю выбора микрофона."""
        if getattr(self.input_device_menu, "_menu", None) is not None:
            self.input_device_menu.clear()

        if not self.input_devices:
            empty_item = rumps.MenuItem("(микрофоны не найдены)")
            empty_item.set_callback(None)
            self.input_device_menu.add(empty_item)
            return

        for device in self.input_devices:
            title = microphone_menu_title(device)
            item = rumps.MenuItem(title, callback=self.change_input_device)
            item.state = int(device == self.current_input_device)
            self.input_device_menu.add(item)

    def _refresh_microphone_profiles_menu(self):
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
                title = profile["name"]
                item = rumps.MenuItem(title, callback=self.apply_microphone_profile)
                item.state = int(self._is_microphone_profile_active(profile))
                self._microphone_profile_titles[title] = profile
                self.microphone_profiles_menu.add(item)

        self.microphone_profiles_menu.add(None)
        self.microphone_profiles_menu.add(
            rumps.MenuItem("➕ Добавить текущий профиль…", callback=self.add_current_microphone_profile),
        )

        delete_menu = rumps.MenuItem("🗑 Удалить профиль")
        if not self.microphone_profiles:
            empty_item = rumps.MenuItem("(нет профилей)")
            empty_item.set_callback(None)
            delete_menu.add(empty_item)
        else:
            for profile in self.microphone_profiles:
                title = profile["name"]
                self._delete_microphone_profile_titles[title] = profile
                delete_menu.add(rumps.MenuItem(title, callback=self.delete_microphone_profile))
        self.microphone_profiles_menu.add(delete_menu)

    def _persist_hotkey_settings(self):
        """Сохраняет активные хоткеи в NSUserDefaults."""
        _save_defaults_str(DEFAULTS_KEY_PRIMARY_HOTKEY, self._primary_key_combination)
        _save_defaults_str(DEFAULTS_KEY_SECONDARY_HOTKEY, self._secondary_key_combination)

    def _refresh_title_and_status(self):
        """Обновляет иконку и строку статуса в меню."""
        self.status_item.title = f"🔄 Статус: {self._state_label()}"
        self._refresh_permission_items()

        if self.state == STATUS_TRANSCRIBING:
            self.title = "🧠"
            return

        if self.state == STATUS_LLM_PROCESSING:
            self.title = "🤖"
            return

        if self.state == STATUS_IDLE:
            self.title = "⏯"

    def _active_key_combinations(self):
        """Возвращает список всех включенных комбинаций клавиш."""
        return [key_combination for key_combination in (self._primary_key_combination, self._secondary_key_combination) if key_combination]

    def _refresh_hotkey_items(self):
        """Обновляет подписи пунктов меню с основным и дополнительным хоткеями."""
        if self._primary_key_combination:
            self.hotkey_status = format_hotkey_status(self._primary_key_combination)
        if self._secondary_key_combination:
            self.secondary_hotkey_status = format_hotkey_status(self._secondary_key_combination)
        else:
            self.secondary_hotkey_status = "не задан"

        self.hotkey_item.title = f"⌨️ Основной хоткей: {self.hotkey_status}"
        self.secondary_hotkey_item.title = f"⌨️ Доп. хоткей: {self.secondary_hotkey_status}"
        if self._llm_key_combination:
            self.llm_hotkey_status = format_hotkey_status(self._llm_key_combination)
        else:
            self.llm_hotkey_status = "не задан"
        self.llm_hotkey_item.title = f"🤖 LLM-хоткей: {self.llm_hotkey_status}"

    def _can_update_hotkeys_runtime(self):
        """Проверяет, поддерживает ли текущий listener горячее обновление хоткеев."""
        return hasattr(self.key_listener, "update_key_combinations")

    def _apply_hotkey_changes(self):
        """Применяет обновленные комбинации к меню и активному listener-у."""
        self._refresh_hotkey_items()
        self._persist_hotkey_settings()
        if self._can_update_hotkeys_runtime():
            listener = cast("Any", self.key_listener)
            listener.update_key_combinations(self._active_key_combinations())
            return True
        return False

    def _update_hotkey_value(self, *, is_secondary, new_combination):
        """Обновляет основную или дополнительную комбинацию с проверкой на дубликаты."""
        if is_secondary:
            if new_combination and new_combination == self._primary_key_combination:
                raise ValueError("Дополнительный хоткей должен отличаться от основного.")
            self._secondary_key_combination = new_combination
            return

        if new_combination == self._secondary_key_combination:
            raise ValueError("Основной хоткей должен отличаться от дополнительного.")
        self._primary_key_combination = new_combination

    def set_state(self, state):
        """Сохраняет новое состояние приложения.

        Args:
            state: Новый идентификатор состояния.
        """
        self.state = state

    def set_permission_status(self, permission_name, status):
        """Сохраняет новый статус разрешения.

        Args:
            permission_name: Имя разрешения.
            status: Булев статус разрешения.
        """
        self.permission_status[permission_name] = status

    def change_input_device(self, sender):
        """Переключает текущее устройство ввода."""
        selected_device = next(
            (device for device in self.input_devices if microphone_menu_title(device) == sender.title),
            None,
        )
        if selected_device is None:
            return

        if selected_device == self.current_input_device:
            return

        self.current_input_device = selected_device
        self.recorder.set_input_device(selected_device)
        _save_defaults_input_device_index(selected_device["index"])
        self.input_device_item.title = f"🎙️ Микрофон: {self._format_input_device()}"
        LOGGER.info(
            "🎙️ Выбран микрофон: index=%s, name=%s",
            selected_device["index"],
            selected_device["name"],
        )
        self._refresh_selection_states()

    def change_language(self, sender):
        """Переключает текущий язык распознавания.

        Args:
            sender: Пункт меню, выбранный пользователем.
        """
        if self.languages is None:
            return

        if sender.title == self.current_language:
            return

        self.current_language = sender.title
        _save_defaults_str(DEFAULTS_KEY_LANGUAGE, self.current_language)
        self.language_item.title = f"🌍 Язык: {self._format_language()}"
        self._refresh_selection_states()

    def change_model(self, sender):
        """Переключает модель распознавания из списка доступных."""
        selected_model = next((model for model in self.model_options if self._model_menu_title(model) == sender.title), None)
        if selected_model is None or selected_model == self.model_repo:
            return

        self.model_repo = selected_model
        self.model_name = selected_model.rsplit("/", maxsplit=1)[-1]
        self.recorder.transcriber.model_name = selected_model
        _save_defaults_str(DEFAULTS_KEY_MODEL, selected_model)
        self.model_item.title = f"🧠 Модель: {self.model_name}"
        self._refresh_selection_states()
        LOGGER.info("🧠 Выбрана модель: %s", selected_model)
        notify_user("MLX Whisper Dictation", f"Модель переключена: {self.model_name}")

    def change_max_time(self, sender):
        """Переключает лимит длительности записи из списка."""
        title_to_value = {self._max_time_menu_title(value): value for value in self.max_time_options}
        if sender.title not in title_to_value:
            return
        selected_max_time = title_to_value[sender.title]
        if selected_max_time == self.max_time:
            return

        self.max_time = selected_max_time
        _save_defaults_max_time(self.max_time)
        self.max_time_item.title = f"⏱ Длительность записи: {format_max_time_status(self.max_time)}"
        self._refresh_selection_states()
        LOGGER.info("⏱ Обновлен лимит записи: %s", format_max_time_status(self.max_time))

    def add_current_microphone_profile(self, _):
        """Сохраняет текущие настройки как быстрый профиль микрофона."""
        if self.current_input_device is None:
            notify_user("MLX Whisper Dictation", "Нельзя сохранить профиль без выбранного микрофона.")
            return

        if len(self.microphone_profiles) >= MAX_MICROPHONE_PROFILES:
            notify_user(
                "MLX Whisper Dictation",
                f"Можно сохранить не больше {MAX_MICROPHONE_PROFILES} быстрых профилей.",
            )
            return

        profile_name = prompt_text(
            "Добавить быстрый профиль",
            "Введите название для текущего микрофона и набора базовых настроек.",
            default_text=self._suggest_microphone_profile_name(),
        )
        if profile_name is None:
            return

        unique_name = self._unique_microphone_profile_name(profile_name)
        self.microphone_profiles.append(self._current_microphone_profile(unique_name))
        self._persist_microphone_profiles()
        self._refresh_microphone_profiles_menu()
        self._refresh_selection_states()
        LOGGER.info("🎚 Добавлен быстрый профиль микрофона: %s", unique_name)
        notify_user("MLX Whisper Dictation", f"Профиль сохранён: {unique_name}")

    def apply_microphone_profile(self, sender):
        """Применяет сохранённый быстрый профиль микрофона."""
        profile = self._microphone_profile_titles.get(sender.title)
        if profile is None:
            return

        selected_device = next(
            (device for device in self.input_devices if device["index"] == profile["input_device_index"]),
            None,
        )
        if selected_device is None:
            notify_user(
                "MLX Whisper Dictation",
                f"Микрофон для профиля «{profile['name']}» сейчас недоступен.",
            )
            return

        self.current_input_device = selected_device
        self.recorder.set_input_device(selected_device)
        _save_defaults_input_device_index(selected_device["index"])
        self.input_device_item.title = f"🎙️ Микрофон: {self._format_input_device()}"

        self.model_repo = profile["model_repo"]
        self.model_name = self.model_repo.rsplit("/", maxsplit=1)[-1]
        self.model_item.title = f"🧠 Модель: {self.model_name}"
        if hasattr(self.recorder, "transcriber") and self.recorder.transcriber is not None:
            self.recorder.transcriber.model_name = self.model_repo
        _save_defaults_str(DEFAULTS_KEY_MODEL, self.model_repo)

        profile_language = profile.get("language")
        if self.languages is None:
            self.current_language = None
        elif profile_language in self.languages or profile_language is None:
            self.current_language = profile_language
        self.language_item.title = f"🌍 Язык: {self._format_language()}"
        if self.current_language is None:
            _remove_defaults_key(DEFAULTS_KEY_LANGUAGE)
        else:
            _save_defaults_str(DEFAULTS_KEY_LANGUAGE, self.current_language)

        self.max_time = profile.get("max_time")
        self.max_time_item.title = f"⏱ Длительность записи: {format_max_time_status(self.max_time)}"
        _save_defaults_max_time(self.max_time)

        self.performance_mode = _normalize_performance_mode(profile.get("performance_mode"))
        if hasattr(self.recorder, "set_performance_mode"):
            self.recorder.set_performance_mode(self.performance_mode)
        self.performance_menu.title = f"⚡ Режим работы: {_performance_mode_label(self.performance_mode)}"
        _save_defaults_str(DEFAULTS_KEY_PERFORMANCE_MODE, self.performance_mode)

        transcriber = self.recorder.transcriber if hasattr(self.recorder, "transcriber") else None
        if transcriber is not None:
            private_mode = bool(profile.get("private_mode", False))
            if hasattr(transcriber, "set_private_mode"):
                transcriber.set_private_mode(private_mode)
            else:
                transcriber.private_mode_enabled = private_mode
                _save_defaults_bool(DEFAULTS_KEY_PRIVATE_MODE, private_mode)
            self.private_mode_item.state = int(getattr(transcriber, "private_mode_enabled", False))

            transcriber.paste_cgevent_enabled = bool(profile.get("paste_cgevent", True))
            transcriber.paste_ax_enabled = bool(profile.get("paste_ax", False))
            transcriber.paste_clipboard_enabled = bool(profile.get("paste_clipboard", False))
            transcriber.llm_clipboard_enabled = bool(profile.get("llm_clipboard", True))
            self.paste_cgevent_item.state = int(transcriber.paste_cgevent_enabled)
            self.paste_ax_item.state = int(transcriber.paste_ax_enabled)
            self.paste_clipboard_item.state = int(transcriber.paste_clipboard_enabled)
            self.llm_clipboard_item.state = int(transcriber.llm_clipboard_enabled)
            _save_defaults_bool(DEFAULTS_KEY_PASTE_CGEVENT, transcriber.paste_cgevent_enabled)
            _save_defaults_bool(DEFAULTS_KEY_PASTE_AX, transcriber.paste_ax_enabled)
            _save_defaults_bool(DEFAULTS_KEY_PASTE_CLIPBOARD, transcriber.paste_clipboard_enabled)
            _save_defaults_bool(DEFAULTS_KEY_LLM_CLIPBOARD, transcriber.llm_clipboard_enabled)

        self._refresh_selection_states()
        LOGGER.info("🎚 Применён быстрый профиль микрофона: %s", profile["name"])
        notify_user("MLX Whisper Dictation", f"Профиль применён: {profile['name']}")

    def delete_microphone_profile(self, sender):
        """Удаляет сохранённый быстрый профиль микрофона."""
        profile = self._delete_microphone_profile_titles.get(sender.title)
        if profile is None:
            return

        self.microphone_profiles = [item for item in self.microphone_profiles if item["name"] != profile["name"]]
        self._persist_microphone_profiles()
        self._refresh_microphone_profiles_menu()
        self._refresh_selection_states()
        LOGGER.info("🗑 Удалён быстрый профиль микрофона: %s", profile["name"])
        notify_user("MLX Whisper Dictation", f"Профиль удалён: {profile['name']}")

    def change_hotkey(self, _):
        """Открывает диалог для смены комбинации клавиш через захват нажатия."""
        if not self._can_update_hotkeys_runtime():
            notify_user("MLX Whisper Dictation", "Смена хоткея недоступна в режиме двойного нажатия Command.")
            return

        result = capture_hotkey_combination(
            "Изменить основной хоткей",
            "Нажмите нужную комбинацию клавиш.\nНапример: зажмите Ctrl+Shift+Alt и нажмите T.",
            current_combination=self._primary_key_combination,
        )
        if result is None:
            return

        try:
            normalized = normalize_key_combination(result)
            self._update_hotkey_value(is_secondary=False, new_combination=normalized)
        except ValueError as error:
            notify_user("MLX Whisper Dictation", f"Ошибка: {error}")
            return

        self._apply_hotkey_changes()
        LOGGER.info("⌨️ Основной хоткей изменён на: %s", normalized)
        notify_user("MLX Whisper Dictation", f"Основной хоткей изменён: {self.hotkey_status}")

    def change_secondary_hotkey(self, _):
        """Открывает диалог для смены дополнительной комбинации клавиш через захват."""
        if not self._can_update_hotkeys_runtime():
            notify_user("MLX Whisper Dictation", "Смена хоткея недоступна в режиме двойного нажатия Command.")
            return

        result = capture_hotkey_combination(
            "Изменить доп. хоткей",
            "Нажмите нужную комбинацию клавиш.\nОставьте пустым и нажмите Применить, чтобы отключить.",
            current_combination=self._secondary_key_combination,
        )
        if result is None:
            return

        try:
            normalized = normalize_key_combination(result) if result else ""
            self._update_hotkey_value(is_secondary=True, new_combination=normalized)
        except ValueError as error:
            notify_user("MLX Whisper Dictation", f"Ошибка: {error}")
            return

        self._apply_hotkey_changes()
        if normalized:
            LOGGER.info("⌨️ Дополнительный хоткей изменён на: %s", normalized)
            notify_user("MLX Whisper Dictation", f"Доп. хоткей изменён: {self.secondary_hotkey_status}")
            return

        LOGGER.info("⌨️ Дополнительный хоткей отключён")
        notify_user("MLX Whisper Dictation", "Доп. хоткей отключён.")

    def change_llm_hotkey(self, _):
        """Открывает диалог для смены LLM-хоткея через захват нажатия."""
        result = capture_hotkey_combination(
            "Изменить LLM-хоткей",
            "Нажмите нужную комбинацию клавиш.\nОставьте пустым и нажмите Применить, чтобы отключить.",
            current_combination=self._llm_key_combination,
        )
        if result is None:
            return

        try:
            normalized = normalize_key_combination(result) if result else ""
        except ValueError as error:
            notify_user("MLX Whisper Dictation", f"Ошибка: {error}")
            return

        old_combination = self._llm_key_combination
        self._llm_key_combination = normalized
        _save_defaults_str(DEFAULTS_KEY_LLM_HOTKEY, self._llm_key_combination)
        self._refresh_hotkey_items()

        llm_listener = getattr(self, "llm_key_listener", None)
        if llm_listener is not None:
            llm_listener.stop()

        if normalized:
            new_listener = GlobalKeyListener(self, normalized, callback=self.toggle_llm)
            new_listener.start()
            self.llm_key_listener = new_listener
            LOGGER.info("🤖 LLM-хоткей изменён на: %s", normalized)
            notify_user("MLX Whisper Dictation", f"LLM-хоткей изменён: {self.llm_hotkey_status}")
        else:
            self.llm_key_listener = None
            LOGGER.info("🤖 LLM-хоткей отключён (был: %s)", old_combination)
            notify_user("MLX Whisper Dictation", "LLM-хоткей отключён.")

    def request_accessibility_access(self, _):
        """Повторно запрашивает у macOS доступ к Accessibility."""
        granted = request_accessibility_permission()
        self.permission_status["accessibility"] = get_accessibility_status()
        self._refresh_permission_items()
        if granted or self.permission_status["accessibility"] is True:
            notify_user("MLX Whisper Dictation", "Доступ к Accessibility подтвержден.")
            return

        warn_missing_accessibility_permission()

    def request_input_monitoring_access(self, _):
        """Повторно запрашивает у macOS доступ к Input Monitoring."""
        granted = request_input_monitoring_permission()
        self.permission_status["input_monitoring"] = get_input_monitoring_status()
        self._refresh_permission_items()
        if granted or self.permission_status["input_monitoring"] is True:
            notify_user("MLX Whisper Dictation", "Доступ к Input Monitoring подтвержден.")
            return

        warn_missing_input_monitoring_permission()

    def toggle_recording_notification(self, sender):
        """Переключает системное уведомление о старте записи."""
        self.show_recording_notification = not self.show_recording_notification
        sender.state = int(self.show_recording_notification)
        _save_defaults_bool(DEFAULTS_KEY_RECORDING_NOTIFICATION, self.show_recording_notification)
        LOGGER.info("🔔 Уведомление о старте записи: %s", "включено" if self.show_recording_notification else "выключено")

    def change_performance_mode(self, sender):
        """Переключает баланс между задержкой и потреблением ресурсов."""
        selected_mode = next(
            (performance_mode for performance_mode, title in PERFORMANCE_MODE_LABELS.items() if title == sender.title),
            None,
        )
        if selected_mode is None or selected_mode == self.performance_mode:
            return

        self.performance_mode = selected_mode
        _save_defaults_str(DEFAULTS_KEY_PERFORMANCE_MODE, self.performance_mode)
        if hasattr(self.recorder, "set_performance_mode"):
            self.recorder.set_performance_mode(self.performance_mode)
        self.performance_menu.title = f"⚡ Режим работы: {_performance_mode_label(self.performance_mode)}"
        self._refresh_selection_states()
        LOGGER.info("⚡ Режим работы переключён: %s", _performance_mode_label(self.performance_mode))

    def toggle_private_mode(self, sender):
        """Переключает private mode для истории текста."""
        transcriber = self.recorder.transcriber
        new_state = not transcriber.private_mode_enabled
        transcriber.set_private_mode(new_state)
        sender.state = int(transcriber.private_mode_enabled)
        self._refresh_selection_states()
        LOGGER.info("🕶 Приватный режим: %s", "включён" if transcriber.private_mode_enabled else "выключен")

    def toggle_paste_cgevent(self, sender):
        """Переключает метод вставки через CGEvent Unicode."""
        transcriber = self.recorder.transcriber
        transcriber.paste_cgevent_enabled = not transcriber.paste_cgevent_enabled
        sender.state = int(transcriber.paste_cgevent_enabled)
        _save_defaults_bool(DEFAULTS_KEY_PASTE_CGEVENT, transcriber.paste_cgevent_enabled)
        self._refresh_selection_states()
        LOGGER.info("📝 Прямой ввод (CGEvent): %s", "включён" if transcriber.paste_cgevent_enabled else "выключен")

    def toggle_paste_ax(self, sender):
        """Переключает метод вставки через Accessibility API."""
        transcriber = self.recorder.transcriber
        transcriber.paste_ax_enabled = not transcriber.paste_ax_enabled
        sender.state = int(transcriber.paste_ax_enabled)
        _save_defaults_bool(DEFAULTS_KEY_PASTE_AX, transcriber.paste_ax_enabled)
        self._refresh_selection_states()
        LOGGER.info("📝 Accessibility API: %s", "включён" if transcriber.paste_ax_enabled else "выключен")

    def toggle_paste_clipboard(self, sender):
        """Переключает метод вставки через буфер обмена (Cmd+V)."""
        transcriber = self.recorder.transcriber
        transcriber.paste_clipboard_enabled = not transcriber.paste_clipboard_enabled
        sender.state = int(transcriber.paste_clipboard_enabled)
        _save_defaults_bool(DEFAULTS_KEY_PASTE_CLIPBOARD, transcriber.paste_clipboard_enabled)
        self._refresh_selection_states()
        LOGGER.info("📝 Буфер обмена (Cmd+V): %s", "включён" if transcriber.paste_clipboard_enabled else "выключен")

    def toggle_llm_clipboard(self, sender):
        """Переключает использование буфера обмена для LLM-контекста и ответа."""
        transcriber = self.recorder.transcriber
        transcriber.llm_clipboard_enabled = not getattr(transcriber, "llm_clipboard_enabled", True)
        sender.state = int(transcriber.llm_clipboard_enabled)
        _save_defaults_bool(DEFAULTS_KEY_LLM_CLIPBOARD, transcriber.llm_clipboard_enabled)
        self._refresh_selection_states()
        LOGGER.info("🤖 Буфер обмена для LLM: %s", "включён" if transcriber.llm_clipboard_enabled else "выключен")

    def _format_history_title(self, text):
        """Форматирует текст для отображения в подменю истории.

        Заменяет переносы строк пробелами и обрезает до HISTORY_DISPLAY_LENGTH символов.

        Args:
            text: Полный текст записи.

        Returns:
            Сокращённая строка для пункта меню.
        """
        single_line = text.replace("\n", " ").replace("\r", " ")
        if len(single_line) > HISTORY_DISPLAY_LENGTH:
            return single_line[:HISTORY_DISPLAY_LENGTH] + "…"
        return single_line

    def _refresh_history_menu(self):
        """Обновляет подменю «История текста» из данных transcriber.

        Вызывается при каждом добавлении текста в историю.
        """
        if getattr(self.history_menu, "_menu", None) is not None:
            self.history_menu.clear()
        self._history_title_to_text = {}

        transcriber = self.recorder.transcriber if hasattr(self.recorder, "transcriber") else None
        if transcriber is not None and hasattr(transcriber, "prune_expired_history"):
            transcriber.prune_expired_history()
        history = transcriber.history if transcriber is not None else []

        if not history:
            empty_item = rumps.MenuItem("(пусто)")
            empty_item.set_callback(None)
            self.history_menu.add(empty_item)
            return

        for _idx, text in enumerate(history):
            title = self._format_history_title(text)
            # Гарантируем уникальность заголовков добавлением невидимого суффикса
            unique_title = title
            suffix_count = 0
            while unique_title in self._history_title_to_text:
                suffix_count += 1
                unique_title = f"{title} ({suffix_count})"
            self._history_title_to_text[unique_title] = text
            item = rumps.MenuItem(unique_title, callback=self._copy_history_item)
            self.history_menu.add(item)

    def _copy_history_item(self, sender):
        """Копирует выбранный элемент истории в буфер обмена.

        Args:
            sender: Пункт меню, по которому кликнули.
        """
        full_text = self._history_title_to_text.get(sender.title)
        if full_text is None:
            LOGGER.warning("⚠️ Не найден текст для пункта истории: %s", sender.title)
            return
        transcriber = self.recorder.transcriber
        transcriber._copy_text_to_clipboard(full_text)
        LOGGER.info("📋 Текст из истории скопирован в буфер обмена: %r", full_text[:80])
        notify_user(
            "MLX Whisper Dictation",
            "Текст скопирован в буфер обмена.",
        )

    @rumps.clicked("Начать запись")
    def start_app(self, _):
        """Запускает запись и обновляет состояние интерфейса.

        Args:
            _: Аргумент callback от rumps, который здесь не используется.
        """
        LOGGER.info("🎙️ Запись началась")
        self.state = STATUS_RECORDING
        if self.show_recording_notification:
            notify_user(
                "MLX Whisper Dictation",
                "Запись началась. Говорите, пока в строке меню горит красный индикатор.",
            )
        self.started = True
        self._menu_item("Начать запись").set_callback(None)
        self._menu_item("Остановить запись").set_callback(self.stop_app)
        self.recorder.start(self.current_language)

        self.start_time = time.time()
        self.on_status_tick(None)

    @rumps.clicked("Остановить запись")
    def stop_app(self, _):
        """Останавливает запись и запускает этап распознавания.

        Args:
            _: Аргумент callback от rumps, который здесь не используется.
        """
        if not self.started:
            return

        LOGGER.info("⏹ Запись остановлена, запускаю распознавание")
        self.started = False
        self.state = STATUS_TRANSCRIBING
        self._refresh_title_and_status()
        self._menu_item("Остановить запись").set_callback(None)
        self._menu_item("Начать запись").set_callback(self.start_app)
        self.recorder.stop()

    def on_status_tick(self, _):
        """Обновляет индикатор времени записи в строке меню.

        Args:
            _: Аргумент timer callback, который здесь не используется.
        """
        if not self.started:
            self._refresh_title_and_status()
            return

        self.elapsed_time = int(time.time() - self.start_time)
        minutes, seconds = divmod(self.elapsed_time, 60)
        self.title = f"{minutes:02d}:{seconds:02d} 🔴"
        self.status_item.title = f"🔄 Статус: {self._state_label()}"

        if self.max_time is not None and self.elapsed_time >= self.max_time:
            self.stop_app(None)

    def toggle(self):
        """Переключает приложение между состояниями записи и ожидания."""
        if self.started:
            self.stop_app(None)
        else:
            self.start_app(None)

    def toggle_llm(self):
        """Переключает запись для LLM-пайплайна."""
        if self.started:
            self.stop_app(None)
            return

        llm_proc = getattr(self.recorder, "llm_processor", None)
        if llm_proc is not None and not llm_proc.is_model_cached():
            notify_user("MLX Whisper Dictation", "LLM-модель ещё не скачана. Запускаю загрузку…")
            self._download_llm_model(None)
            return

        LOGGER.info("🤖 Запуск LLM-пайплайна, промпт=%r", self.llm_prompt_name)
        self.state = STATUS_RECORDING
        if self.show_recording_notification:
            notify_user("MLX Whisper Dictation", "Запись для LLM. Говорите.")
        self.started = True
        self._menu_item("Начать запись").set_callback(None)
        self._menu_item("Остановить запись").set_callback(self.stop_app)
        self.recorder.llm_prompt_name = self.llm_prompt_name
        self.recorder.llm_system_prompt = LLM_PROMPT_PRESETS.get(self.llm_prompt_name, LLM_PROMPT_PRESETS[DEFAULT_LLM_PROMPT_NAME])
        self.recorder.start_llm(self.current_language)
        self.start_time = time.time()
        self.on_status_tick(None)

    def _download_llm_model(self, _):
        """Запускает загрузку LLM-модели в фоновом потоке с индикатором прогресса."""
        llm_proc = getattr(self.recorder, "llm_processor", None)
        if llm_proc is None:
            return
        if self._llm_downloading:
            notify_user("MLX Whisper Dictation", "Загрузка уже выполняется…")
            return

        self._llm_downloading = True
        self.llm_download_item.set_callback(None)
        self.llm_download_item.title = "📥 Загрузка LLM: 0%"

        def _on_progress(desc, pct, total_bytes):
            if total_bytes > 0:
                size_mb = total_bytes / (1024 * 1024)
                self.llm_download_item.title = f"📥 Загрузка LLM: {pct:.0f}% ({size_mb:.0f} МБ)"
            elif pct >= DOWNLOAD_COMPLETE_PCT:
                self.llm_download_item.title = "✅ LLM-модель загружена"
            else:
                self.llm_download_item.title = f"📥 Загрузка LLM: {desc}"

        def _download_thread():
            try:
                llm_proc.download_progress_callback = _on_progress
                llm_proc.ensure_model_downloaded()
                self.llm_download_item.title = "✅ LLM-модель загружена"
                self.llm_download_item.set_callback(None)
                notify_user("MLX Whisper Dictation", "LLM-модель успешно загружена.")
            except Exception:
                LOGGER.exception("❌ Ошибка загрузки LLM-модели")
                self.llm_download_item.title = "❌ Ошибка загрузки LLM"
                self.llm_download_item.set_callback(self._download_llm_model)
                notify_user("MLX Whisper Dictation", "Не удалось скачать LLM-модель. Попробуйте снова.")
            finally:
                llm_proc.download_progress_callback = None
                self._llm_downloading = False

        thread = threading.Thread(target=_download_thread, daemon=True)
        thread.start()

    def _change_llm_prompt(self, sender):
        """Переключает текущий пресет системного промпта для LLM.

        Args:
            sender: Пункт меню с именем пресета.
        """
        self.llm_prompt_name = sender.title
        _save_defaults_str(DEFAULTS_KEY_LLM_PROMPT, self.llm_prompt_name)
        self.recorder.llm_prompt_name = self.llm_prompt_name
        self.recorder.llm_system_prompt = LLM_PROMPT_PRESETS.get(
            self.llm_prompt_name,
            LLM_PROMPT_PRESETS[DEFAULT_LLM_PROMPT_NAME],
        )
        for item_title in self.llm_prompt_menu:
            self.llm_prompt_menu[item_title].state = int(item_title == self.llm_prompt_name)
        LOGGER.info("🤖 Выбран промпт LLM: %s", self.llm_prompt_name)
