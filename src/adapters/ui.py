"""UI menu bar приложения Dictator.

Содержит StatusBarApp — адаптер menu bar UI к DictationApp, а также
вспомогательную функцию prompt_text для простых диалогов ввода.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

import AppKit
import rumps
from PyObjCTools.AppHelper import callAfter  # type: ignore[import-untyped]

from ..domain.constants import Config

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
        self.hotkey_item = rumps.MenuItem(f"⌨️ Основной хоткей: {self.hotkey_status}")
        self.secondary_hotkey_item = rumps.MenuItem(f"⌨️ Доп. хоткей: {self.secondary_hotkey_status}")
        self.change_hotkey_item = rumps.MenuItem("⌨️ Изменить основной хоткей…", callback=self.change_hotkey)
        self.change_secondary_hotkey_item = rumps.MenuItem("⌨️ Изменить доп. хоткей…", callback=self.change_secondary_hotkey)

        self.llm_hotkey_item = rumps.MenuItem(f"🤖 LLM-хоткей: {self.llm_hotkey_status}")
        self.change_llm_hotkey_item = rumps.MenuItem("🤖 Изменить LLM-хоткей…", callback=self.change_llm_hotkey)
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

        self.paste_method_menu = rumps.MenuItem("📝 Метод ввода")
        self.private_mode_item = rumps.MenuItem("🕶 Приватный режим", callback=self.toggle_private_mode)
        self.paste_cgevent_item = rumps.MenuItem("Прямой ввод (CGEvent)", callback=self.toggle_paste_cgevent)
        self.paste_ax_item = rumps.MenuItem("Accessibility API", callback=self.toggle_paste_ax)
        self.paste_clipboard_item = rumps.MenuItem("Буфер обмена (Cmd+V)", callback=self.toggle_paste_clipboard)
        self.paste_method_menu.add(self.paste_cgevent_item)
        self.paste_method_menu.add(self.paste_ax_item)
        self.paste_method_menu.add(self.paste_clipboard_item)

        self.history_menu = rumps.MenuItem("📋 История текста")
        self.token_usage_item = rumps.MenuItem(self._token_usage_title())
        self.token_usage_item.set_callback(None)

        self.language_item = rumps.MenuItem(f"🌍 Язык: {self._format_language()}")
        self.input_device_item = rumps.MenuItem(f"🎙️ Микрофон: {self._format_input_device()}")
        self.microphone_profiles_menu = rumps.MenuItem("🎚 Быстрые профили")
        self.input_device_menu = rumps.MenuItem("🎙️ Выбрать микрофон")
        self.max_time_item = rumps.MenuItem(f"⏱ Длительность записи: {Config.format_max_time_status(self.max_time)}")
        self.accessibility_item = rumps.MenuItem(self._permission_title("Accessibility", self.permission_status["accessibility"]))
        self.input_monitoring_item = rumps.MenuItem(self._permission_title("Input Monitoring", self.permission_status["input_monitoring"]))
        self.microphone_item = rumps.MenuItem(self._permission_title("Microphone", self.permission_status["microphone"]))
        self.request_accessibility_item = rumps.MenuItem("🛂 Запросить Accessibility", callback=self.request_accessibility_access)
        self.request_input_monitoring_item = rumps.MenuItem("🛂 Запросить Input Monitoring", callback=self.request_input_monitoring_access)

        menu: list[Any] = [
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
            self.recording_indicator_menu,
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

        if self.languages is not None and len(self.languages) > 1:
            menu.extend(rumps.MenuItem(lang, callback=self.change_language) for lang in self.languages)
            menu.append(None)

        menu.extend(rumps.MenuItem(self._model_menu_title(model), callback=self.change_model) for model in self.model_options)
        menu.append(None)
        menu.extend(
            rumps.MenuItem(self._max_time_menu_title(max_time_value), callback=self.change_max_time)
            for max_time_value in self.max_time_options
        )
        menu.append(None)

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
    def llm_prompt_name(self) -> str:
        """Возвращает имя активного LLM-промпта."""
        return self.app.llm_prompt_name

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

    def _format_total_tokens(self, token_count: int) -> str:
        """Форматирует число токенов для отображения в меню."""
        return f"{int(token_count):,}".replace(",", " ")

    def _token_usage_title(self) -> str:
        """Возвращает заголовок пункта меню со счётчиком токенов."""
        return f"🔢 Токены: {self._format_total_tokens(self.total_tokens)}"

    def _refresh_token_usage_item(self) -> None:
        """Обновляет пункт меню со счётчиком токенов."""
        self.token_usage_item.title = self._token_usage_title()

    def _refresh_permission_items(self) -> None:
        """Обновляет пункты меню со статусами разрешений."""
        self.accessibility_item.title = self._permission_title("Accessibility", self.permission_status["accessibility"])
        self.input_monitoring_item.title = self._permission_title("Input Monitoring", self.permission_status["input_monitoring"])
        self.microphone_item.title = self._permission_title("Microphone", self.permission_status["microphone"])

    def _refresh_hotkey_items(self) -> None:
        """Обновляет подписи хоткеев в меню."""
        self.hotkey_item.title = f"⌨️ Основной хоткей: {self.hotkey_status}"
        self.secondary_hotkey_item.title = f"⌨️ Доп. хоткей: {self.secondary_hotkey_status}"
        self.llm_hotkey_item.title = f"🤖 LLM-хоткей: {self.llm_hotkey_status}"

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
        self.title = "⏯"

    def _format_history_title(self, text: str) -> str:
        """Форматирует текст для отображения в подменю истории."""
        single_line = text.replace("\n", " ").replace("\r", " ")
        if len(single_line) > Config.HISTORY_DISPLAY_LENGTH:
            return single_line[:Config.HISTORY_DISPLAY_LENGTH] + "…"
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
        self.input_device_item.title = f"🎙️ Микрофон: {self._format_input_device()}"
        self.max_time_item.title = f"⏱ Длительность записи: {Config.format_max_time_status(snapshot.max_time)}"
        self.performance_menu.title = f"⚡ Режим работы: {Config.performance_mode_label(snapshot.performance_mode)}"
        self.recording_notification_item.state = int(snapshot.show_recording_notification)
        self.recording_overlay_item.state = int(snapshot.show_recording_overlay)
        self.recording_time_in_menu_bar_item.state = int(snapshot.show_recording_time_in_menu_bar)
        self.private_mode_item.state = int(snapshot.private_mode_enabled)
        self.llm_clipboard_item.state = int(snapshot.llm_clipboard_enabled)
        self.paste_cgevent_item.state = int(snapshot.paste_cgevent_enabled)
        self.paste_ax_item.state = int(snapshot.paste_ax_enabled)
        self.paste_clipboard_item.state = int(snapshot.paste_clipboard_enabled)
        self.llm_download_item.title = snapshot.llm_download_title
        self.llm_download_item.set_callback(self._download_llm_model if snapshot.llm_download_interactive else None)

        self._refresh_hotkey_items()
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
