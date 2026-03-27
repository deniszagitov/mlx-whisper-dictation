"""Горячие клавиши и слушатели клавиатуры приложения Dictator.

Парсинг комбинаций клавиш, глобальные мониторы нажатий через AppKit,
режим двойного нажатия Command и модальный захват хоткея.
"""

import logging
import time
from typing import Any, cast

import AppKit
from pynput import keyboard

from config import DOUBLE_COMMAND_PRESS_INTERVAL, MIN_HOTKEY_PARTS

LOGGER = logging.getLogger(__name__)

KEY_NAME_ALIASES = {
    "ctrl": "ctrl",
    "control": "ctrl",
    "alt": "alt",
    "option": "alt",
    "opt": "alt",
    "shift": "shift",
    "cmd": "cmd",
    "command": "cmd",
    "meta": "cmd",
    "super": "cmd",
}

MODIFIER_KEYCODES_MAP = {
    54: "cmd_r",
    55: "cmd_l",
    56: "shift_l",
    58: "alt_l",
    59: "ctrl_l",
    60: "shift_r",
    61: "alt_r",
    62: "ctrl_r",
}

MODIFIER_FLAG_MASKS = {
    "alt_l": 0x00080000,
    "alt_r": 0x00080000,
    "ctrl_l": 0x00040000,
    "ctrl_r": 0x00040000,
    "shift_l": 0x00020000,
    "shift_r": 0x00020000,
    "cmd_l": 0x00100000,
    "cmd_r": 0x00100000,
}

NAMED_KEYCODES_MAP = {
    36: "enter",
    48: "tab",
    49: "space",
    51: "backspace",
    53: "esc",
}

MODIFIER_DISPLAY_ORDER = ["ctrl", "ctrl_l", "ctrl_r", "alt", "alt_l", "alt_r", "shift", "shift_l", "shift_r", "cmd", "cmd_l", "cmd_r"]


def normalize_key_name(raw_name):
    """Нормализует имя клавиши к каноническому виду.

    Поддерживает человекочитаемые алиасы (Ctrl, Control, Option, Command)
    и приводит регистр к нижнему.

    Args:
        raw_name: Строковое имя клавиши, например `Ctrl`, `cmd_l` или `T`.

    Returns:
        Нормализованное имя клавиши.
    """
    lowered = raw_name.strip().lower()
    alias = KEY_NAME_ALIASES.get(lowered)
    return alias if alias is not None else lowered


def parse_key(key_name):
    """Преобразует строковое имя клавиши в объект pynput.

    Args:
        key_name: Имя клавиши, например `cmd_l`, `alt` или `space`.

    Returns:
        Объект клавиши или код символа, который понимает pynput.
    """
    return getattr(keyboard.Key, key_name, keyboard.KeyCode(char=key_name))


def normalize_key_combination(key_combination):
    """Нормализует строку комбинации клавиш к внутреннему формату.

    Args:
        key_combination: Строка вида `cmd_l+alt` или `Command+Option+space`.

    Returns:
        Нормализованная строка комбинации клавиш.

    Raises:
        ValueError: Если в комбинации меньше двух клавиш.
    """
    parts = [normalize_key_name(part) for part in key_combination.split("+") if part.strip()]
    if len(parts) < MIN_HOTKEY_PARTS:
        raise ValueError("Комбинация клавиш должна содержать как минимум две клавиши.")
    return "+".join(parts)


def parse_key_combination(key_combination):
    """Разбирает строку с комбинацией клавиш.

    Args:
        key_combination: Строка вида `cmd_l+alt`, `ctrl+shift+alt+t`
            или `Ctrl+Shift+Alt+T`.

    Returns:
        Кортеж объектов клавиш в том порядке, в котором они указаны.

    Raises:
        ValueError: Если в комбинации меньше двух клавиш.
    """
    parts = normalize_key_combination(key_combination).split("+")
    return tuple(parse_key(part) for part in parts)


def hotkey_name_matches(expected_name, actual_name):
    """Проверяет, считаются ли два строковых имени клавиш эквивалентными.

    Args:
        expected_name: Имя клавиши из конфигурации хоткея.
        actual_name: Имя клавиши, полученное из системного события.

    Returns:
        True, если клавиши эквивалентны.
    """
    equivalent_names = {
        "alt": {"alt", "alt_l", "alt_r"},
        "alt_l": {"alt", "alt_l"},
        "alt_r": {"alt", "alt_r"},
        "shift": {"shift", "shift_l", "shift_r"},
        "shift_l": {"shift", "shift_l"},
        "shift_r": {"shift", "shift_r"},
        "ctrl": {"ctrl", "ctrl_l", "ctrl_r"},
        "ctrl_l": {"ctrl", "ctrl_l"},
        "ctrl_r": {"ctrl", "ctrl_r"},
        "cmd": {"cmd", "cmd_l", "cmd_r"},
        "cmd_l": {"cmd", "cmd_l"},
        "cmd_r": {"cmd", "cmd_r"},
    }
    return bool(equivalent_names.get(expected_name, {expected_name}) & equivalent_names.get(actual_name, {actual_name}))


def format_hotkey_status(key_combination=None, *, use_double_cmd=False):
    """Преобразует настройку хоткея в строку для меню.

    Args:
        key_combination: Строка комбинации клавиш.
        use_double_cmd: Флаг режима двойного нажатия правой Command.

    Returns:
        Человекочитаемая строка хоткея.
    """
    if use_double_cmd:
        return "двойное нажатие правой ⌘"

    display_names = {
        "cmd": "⌘",
        "cmd_l": "левая ⌘",
        "cmd_r": "правая ⌘",
        "alt": "⌥",
        "alt_l": "левая ⌥",
        "alt_r": "правая ⌥",
        "shift": "⇧",
        "shift_l": "левая ⇧",
        "shift_r": "правая ⇧",
        "ctrl": "⌃",
        "ctrl_l": "левая ⌃",
        "ctrl_r": "правая ⌃",
        "space": "Space",
    }
    parts = [normalize_key_name(part) for part in (key_combination or "").split("+") if part.strip()]
    return " + ".join(display_names[part] if part in display_names else part.upper() for part in parts)


def _event_key_name_static(event):
    """Извлекает имя обычной клавиши из NSEvent."""
    key_code = int(event.keyCode())
    if key_code in NAMED_KEYCODES_MAP:
        return NAMED_KEYCODES_MAP[key_code]
    characters = str(event.charactersIgnoringModifiers() or "").lower()
    return characters[:1] if characters else ""


def capture_hotkey_combination(title, message, current_combination=""):
    """Открывает модальное окно для захвата комбинации клавиш по нажатию.

    Показывает NSAlert с текстовым полем, которое отображает текущую
    комбинацию по мере нажатия клавиш. Пользователь нажимает модификаторы
    и обычную клавишу, комбинация фиксируется и показывается в поле.

    Args:
        title: Заголовок диалогового окна.
        message: Подсказка для пользователя.
        current_combination: Текущая комбинация для отображения по умолчанию.

    Returns:
        Нормализованную строку комбинации клавиш или None, если отменено.
    """
    appkit = cast("Any", AppKit)

    captured_parts = []
    pressed_modifiers = set()
    confirmed_combination = [None]

    alert = appkit.NSAlert.alloc().init()
    alert.setMessageText_(title)
    alert.setInformativeText_(message)
    alert.addButtonWithTitle_("Применить")
    alert.addButtonWithTitle_("Отмена")

    input_field = appkit.NSTextField.alloc().initWithFrame_(((0, 0), (280, 24)))
    input_field.setStringValue_(format_hotkey_status(current_combination) if current_combination else "")
    input_field.setEditable_(False)
    input_field.setSelectable_(False)
    input_field.setAlignment_(appkit.NSTextAlignmentCenter)
    font = appkit.NSFont.systemFontOfSize_(14)
    input_field.setFont_(font)
    alert.setAccessoryView_(input_field)

    def _update_display():
        """Обновляет текстовое поле с текущей комбинацией."""
        if captured_parts:
            combo = "+".join(captured_parts)
            input_field.setStringValue_(format_hotkey_status(combo))
        elif pressed_modifiers:
            sorted_mods = sorted(pressed_modifiers, key=lambda m: MODIFIER_DISPLAY_ORDER.index(m) if m in MODIFIER_DISPLAY_ORDER else 99)
            combo = "+".join(sorted_mods)
            input_field.setStringValue_(format_hotkey_status(combo) + " + …")

    def _handle_flags(event):
        """Обрабатывает нажатия модификаторов внутри диалога."""
        key_code = int(event.keyCode())
        modifier_name = MODIFIER_KEYCODES_MAP.get(key_code)
        if modifier_name is None:
            return event

        modifier_flags = int(event.modifierFlags())
        mask = MODIFIER_FLAG_MASKS.get(modifier_name, 0)
        if modifier_flags & mask:
            pressed_modifiers.add(modifier_name)
        else:
            pressed_modifiers.discard(modifier_name)

        if not captured_parts:
            _update_display()
        return event

    def _handle_key_down(event):
        """Фиксирует обычную клавишу при зажатых модификаторах."""
        if not pressed_modifiers:
            return event

        key_name = _event_key_name_static(event)
        if not key_name:
            return event

        all_modifier_names = {"alt", "alt_l", "alt_r", "shift", "shift_l", "shift_r", "ctrl", "ctrl_l", "ctrl_r", "cmd", "cmd_l", "cmd_r"}
        if key_name in all_modifier_names:
            return event

        sorted_mods = sorted(pressed_modifiers, key=lambda m: MODIFIER_DISPLAY_ORDER.index(m) if m in MODIFIER_DISPLAY_ORDER else 99)
        captured_parts.clear()
        captured_parts.extend(sorted_mods)
        captured_parts.append(key_name)
        _update_display()
        return None

    flags_mask = appkit.NSEventMaskFlagsChanged
    key_down_mask = appkit.NSEventMaskKeyDown

    local_flags_monitor = appkit.NSEvent.addLocalMonitorForEventsMatchingMask_handler_(flags_mask, _handle_flags)
    local_key_monitor = appkit.NSEvent.addLocalMonitorForEventsMatchingMask_handler_(key_down_mask, _handle_key_down)
    global_flags_monitor = appkit.NSEvent.addGlobalMonitorForEventsMatchingMask_handler_(flags_mask, _handle_flags)
    global_key_monitor = appkit.NSEvent.addGlobalMonitorForEventsMatchingMask_handler_(key_down_mask, _handle_key_down)

    try:
        response = alert.runModal()
    finally:
        appkit.NSEvent.removeMonitor_(local_flags_monitor)
        appkit.NSEvent.removeMonitor_(local_key_monitor)
        appkit.NSEvent.removeMonitor_(global_flags_monitor)
        appkit.NSEvent.removeMonitor_(global_key_monitor)

    _nsalert_first_button = 1000
    if response != _nsalert_first_button:
        return None

    if captured_parts:
        confirmed_combination[0] = "+".join(captured_parts)
    elif pressed_modifiers and len(pressed_modifiers) >= MIN_HOTKEY_PARTS:
        sorted_mods = sorted(pressed_modifiers, key=lambda m: MODIFIER_DISPLAY_ORDER.index(m) if m in MODIFIER_DISPLAY_ORDER else 99)
        confirmed_combination[0] = "+".join(sorted_mods)

    return confirmed_combination[0]


class GlobalKeyListener:
    """Обрабатывает глобальную комбинацию клавиш для запуска диктовки.

    Attributes:
        app: Экземпляр StatusBarApp, которым управляет listener.
        keys: Кортеж клавиш, которые образуют хоткей.
        pressed_keys: Набор клавиш, зажатых в текущий момент.
        triggered: Флаг, защищающий от повторного срабатывания при удержании.
    """

    def __init__(self, app, key_combination, callback=None):
        """Создает listener для заданной комбинации клавиш.

        Args:
            app: Экземпляр приложения, у которого будет вызван toggle.
            key_combination: Строка с комбинацией клавиш.
            callback: Функция, вызываемая при срабатывании. По умолчанию app.toggle.
        """
        self.app = app
        self.callback = callback or app.toggle
        self.key_combination = normalize_key_combination(key_combination)
        self.key_names = self.key_combination.split("+")
        self.modifier_names = {"alt", "alt_l", "alt_r", "shift", "shift_l", "shift_r", "ctrl", "ctrl_l", "ctrl_r", "cmd", "cmd_l", "cmd_r"}
        self.required_modifiers = [name for name in self.key_names if name in self.modifier_names]
        self.required_key = next((name for name in self.key_names if name not in self.modifier_names), None)
        self.pressed_modifier_names = set()
        self.triggered = False
        self.flags_monitor = None
        self.key_down_monitor = None
        self.appkit = cast("Any", AppKit)

    def stop(self):
        """Удаляет глобальные мониторы событий клавиатуры."""
        if self.flags_monitor is not None:
            self.appkit.NSEvent.removeMonitor_(self.flags_monitor)
            self.flags_monitor = None
        if self.key_down_monitor is not None:
            self.appkit.NSEvent.removeMonitor_(self.key_down_monitor)
            self.key_down_monitor = None

    def update_key_combination(self, key_combination):
        """Обновляет комбинацию клавиш без пересоздания listener."""
        self.key_combination = normalize_key_combination(key_combination)
        self.key_names = self.key_combination.split("+")
        self.required_modifiers = [name for name in self.key_names if name in self.modifier_names]
        self.required_key = next((name for name in self.key_names if name not in self.modifier_names), None)
        self.pressed_modifier_names.clear()
        self.triggered = False

    def start(self):
        """Запускает глобальный монитор событий клавиатуры через AppKit."""
        flags_mask = self.appkit.NSEventMaskFlagsChanged
        key_down_mask = self.appkit.NSEventMaskKeyDown
        self.flags_monitor = self.appkit.NSEvent.addGlobalMonitorForEventsMatchingMask_handler_(
            flags_mask,
            self._handle_flags_changed,
        )
        self.key_down_monitor = self.appkit.NSEvent.addGlobalMonitorForEventsMatchingMask_handler_(
            key_down_mask,
            self._handle_key_down,
        )

    def _required_modifiers_are_pressed(self):
        """Проверяет, зажаты ли нужные modifier-клавиши."""
        return all(
            any(hotkey_name_matches(expected_name, pressed_name) for pressed_name in self.pressed_modifier_names)
            for expected_name in self.required_modifiers
        )

    def _event_is_modifier_pressed(self, event, modifier_name):
        """Определяет, находится ли modifier в нажатом состоянии для flagsChanged-события.

        Args:
            event: Системное NSEvent.
            modifier_name: Имя modifier-клавиши.

        Returns:
            True, если соответствующий modifier сейчас зажат.
        """
        modifier_flags = int(event.modifierFlags())
        mask = MODIFIER_FLAG_MASKS.get(modifier_name, 0)
        return bool(modifier_flags & mask)

    def _handle_flags_changed(self, event):
        """Обрабатывает глобальные изменения modifier-клавиш.

        Args:
            event: Системное NSEvent.
        """
        key_code = int(event.keyCode())
        modifier_name = MODIFIER_KEYCODES_MAP.get(key_code)
        if modifier_name is None:
            return

        if self._event_is_modifier_pressed(event, modifier_name):
            self.pressed_modifier_names.add(modifier_name)
        else:
            self.pressed_modifier_names.discard(modifier_name)
            self.triggered = False

        if self.required_key is None and self._required_modifiers_are_pressed() and not self.triggered:
            LOGGER.info("⌨️ Сработал глобальный хоткей: %s", self.key_combination)
            self.triggered = True
            self.callback()

    def _event_key_name(self, event):
        """Преобразует NSEvent в строковое имя клавиши."""
        return _event_key_name_static(event)

    def _handle_key_down(self, event):
        """Обрабатывает глобальные события обычных клавиш.

        Args:
            event: Системное NSEvent.
        """
        if self.required_key is None:
            if not self._required_modifiers_are_pressed():
                self.triggered = False
            return

        event_key_name = self._event_key_name(event)
        if self._required_modifiers_are_pressed() and hotkey_name_matches(self.required_key, event_key_name) and not self.triggered:
            LOGGER.info("⌨️ Сработал глобальный хоткей: %s", self.key_combination)
            self.triggered = True
            self.callback()
        elif event_key_name != self.required_key:
            self.triggered = False


class MultiHotkeyListener:
    """Управляет несколькими глобальными хоткеями одновременно."""

    def __init__(self, app, key_combinations):
        """Создает набор listener-ов для списка комбинаций клавиш."""
        self.app = app
        self.key_combinations = []
        self.listeners = []
        self._build_listeners(key_combinations)

    def start(self):
        """Запускает все глобальные listener-ы."""
        for listener in self.listeners:
            listener.start()

    def stop(self):
        """Останавливает все глобальные listener-ы."""
        for listener in self.listeners:
            listener.stop()

    def _build_listeners(self, key_combinations):
        """Нормализует комбинации и создаёт listener-ы без запуска."""
        normalized = []
        for key_combination in key_combinations:
            if not key_combination:
                continue
            normalized.append(normalize_key_combination(key_combination))

        if not normalized:
            raise ValueError("Нужно указать хотя бы один хоткей.")

        self.key_combinations = normalized
        self.listeners = [GlobalKeyListener(self.app, key_combination) for key_combination in self.key_combinations]

    def update_key_combinations(self, key_combinations):
        """Пересоздает listener-ы для нового списка комбинаций и запускает их."""
        self.stop()
        self._build_listeners(key_combinations)
        self.start()


class DoubleCommandKeyListener:
    """Обрабатывает режим управления через правую клавишу Command.

    Attributes:
        app: Экземпляр приложения, у которого будет вызван toggle.
        key: Клавиша, используемая для переключения записи.
        last_press_time: Время предыдущего нажатия для определения двойного клика.
    """

    def __init__(self, app):
        """Создает listener для режима двойного нажатия Command.

        Args:
            app: Экземпляр приложения, у которого будет вызван toggle.
        """
        self.app = app
        self.key = keyboard.Key.cmd_r
        self.last_press_time = 0.0

    def on_key_press(self, key):
        """Обрабатывает нажатие правой клавиши Command.

        Args:
            key: Объект клавиши из pynput.
        """
        is_listening = self.app.started
        if key == self.key:
            current_time = time.time()
            if is_listening or current_time - self.last_press_time < DOUBLE_COMMAND_PRESS_INTERVAL:
                self.app.toggle()
            self.last_press_time = current_time

    def on_key_release(self, key):
        """Игнорирует отпускание клавиши в этом режиме.

        Args:
            key: Объект клавиши из pynput.
        """
        del key
