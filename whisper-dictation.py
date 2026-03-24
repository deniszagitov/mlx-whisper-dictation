"""Приложение офлайн-диктовки для macOS на базе MLX Whisper.

Модуль содержит menu bar приложение, которое записывает звук с микрофона,
распознает речь локально через MLX Whisper и вставляет результат в активное
поле ввода.
"""

import argparse
import ctypes
import logging
import platform
import threading
import time
from typing import Any, cast

import AppKit
import mlx_whisper
import numpy as np
import pyaudio
import rumps
from pynput import keyboard

DEFAULT_MODEL_NAME = "mlx-community/whisper-large-v3-turbo"
MIN_HOTKEY_PARTS = 2
DOUBLE_COMMAND_PRESS_INTERVAL = 0.5
STATUS_IDLE = "idle"
STATUS_RECORDING = "recording"
STATUS_TRANSCRIBING = "transcribing"
PERMISSION_GRANTED = "есть"
PERMISSION_DENIED = "нет"
PERMISSION_UNKNOWN = "неизвестно"
LOGGER = logging.getLogger(__name__)


def notify_user(title, message):
    """Показывает системное уведомление macOS.

    Args:
        title: Заголовок уведомления.
        message: Основной текст уведомления.
    """
    try:
        rumps.notification(title, "", message)
    except Exception:
        LOGGER.exception("Не удалось показать системное уведомление macOS")


def is_accessibility_trusted():
    """Проверяет, выдан ли процессу доступ к Accessibility на macOS.

    Returns:
        True, если приложение может использовать глобальные события клавиатуры,
        иначе False.
    """
    if platform.system() != "Darwin":
        return True

    try:
        return permission_preflight_status("AXIsProcessTrusted") is not False
    except Exception:
        LOGGER.exception("Не удалось проверить статус Accessibility")
        return True


def permission_preflight_status(function_name):
    """Вызывает preflight-функцию из ApplicationServices, если она доступна.

    Args:
        function_name: Имя C-функции из ApplicationServices.

    Returns:
        True, False или None, если статус нельзя определить.
    """
    if platform.system() != "Darwin":
        return True

    try:
        application_services = ctypes.CDLL("/System/Library/Frameworks/ApplicationServices.framework/ApplicationServices")
        preflight_function = getattr(application_services, function_name, None)
        if preflight_function is None:
            return None
        preflight_function.restype = ctypes.c_bool
        return bool(preflight_function())
    except Exception:
        LOGGER.exception("Не удалось проверить статус разрешения %s", function_name)
        return None


def get_accessibility_status():
    """Возвращает статус доступа к Accessibility."""
    return permission_preflight_status("AXIsProcessTrusted")


def get_input_monitoring_status():
    """Возвращает статус доступа к Input Monitoring."""
    return permission_preflight_status("CGPreflightListenEventAccess")


def permission_label(status):
    """Преобразует булев статус разрешения в строку для меню.

    Args:
        status: True, False или None.

    Returns:
        Строковое значение статуса.
    """
    if status is True:
        return PERMISSION_GRANTED
    if status is False:
        return PERMISSION_DENIED
    return PERMISSION_UNKNOWN


def warn_missing_accessibility_permission():
    """Показывает пользователю предупреждение об отсутствии Accessibility-доступа."""
    message = (
        "Нет доступа к Accessibility для MLX Whisper Dictation. "
        "Без него не будут работать глобальный хоткей и вставка текста. "
        "Откройте System Settings -> Privacy & Security -> Accessibility и включите приложение заново."
    )
    LOGGER.error(message)
    notify_user("MLX Whisper Dictation", message)


def parse_key(key_name):
    """Преобразует строковое имя клавиши в объект pynput.

    Args:
        key_name: Имя клавиши, например `cmd_l`, `alt` или `space`.

    Returns:
        Объект клавиши или код символа, который понимает pynput.
    """
    return getattr(keyboard.Key, key_name, keyboard.KeyCode(char=key_name))


def parse_key_combination(key_combination):
    """Разбирает строку с комбинацией клавиш.

    Args:
        key_combination: Строка вида `cmd_l+alt` или `cmd_l+shift+space`.

    Returns:
        Кортеж объектов клавиш в том порядке, в котором они указаны.

    Raises:
        ValueError: Если в комбинации меньше двух клавиш.
    """
    parts = [part.strip() for part in key_combination.split("+") if part.strip()]
    if len(parts) < MIN_HOTKEY_PARTS:
        raise ValueError("Комбинация клавиш должна содержать как минимум две клавиши.")
    return tuple(parse_key(part) for part in parts)


def key_matches(expected_key, actual_key):
    """Проверяет, соответствует ли нажатая клавиша ожидаемой.

    Args:
        expected_key: Клавиша, описанная в настройке хоткея.
        actual_key: Фактически нажатая клавиша из pynput.

    Returns:
        True, если клавиши считаются эквивалентными.
    """
    key_variants = {
        keyboard.Key.alt: {keyboard.Key.alt, keyboard.Key.alt_l, keyboard.Key.alt_r},
        keyboard.Key.alt_l: {keyboard.Key.alt, keyboard.Key.alt_l},
        keyboard.Key.alt_r: {keyboard.Key.alt, keyboard.Key.alt_r},
        keyboard.Key.shift: {keyboard.Key.shift, keyboard.Key.shift_l, keyboard.Key.shift_r},
        keyboard.Key.shift_l: {keyboard.Key.shift, keyboard.Key.shift_l},
        keyboard.Key.shift_r: {keyboard.Key.shift, keyboard.Key.shift_r},
        keyboard.Key.ctrl: {keyboard.Key.ctrl, keyboard.Key.ctrl_l, keyboard.Key.ctrl_r},
        keyboard.Key.ctrl_l: {keyboard.Key.ctrl, keyboard.Key.ctrl_l},
        keyboard.Key.ctrl_r: {keyboard.Key.ctrl, keyboard.Key.ctrl_r},
        keyboard.Key.cmd: {keyboard.Key.cmd, keyboard.Key.cmd_l, keyboard.Key.cmd_r},
        keyboard.Key.cmd_l: {keyboard.Key.cmd, keyboard.Key.cmd_l},
        keyboard.Key.cmd_r: {keyboard.Key.cmd, keyboard.Key.cmd_r},
    }

    if expected_key == actual_key:
        return True

    return bool(key_variants.get(expected_key, {expected_key}) & key_variants.get(actual_key, {actual_key}))


def format_max_time_status(max_time):
    """Преобразует лимит длительности записи в строку для меню.

    Args:
        max_time: Максимальная длительность записи в секундах.

    Returns:
        Человекочитаемая строка ограничения.
    """
    if max_time is None:
        return "без лимита"
    if float(max_time).is_integer():
        return f"{int(max_time)} с"
    return f"{max_time} с"


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
    parts = [part.strip() for part in (key_combination or "").split("+") if part.strip()]
    return " + ".join(display_names.get(part, part.upper()) for part in parts)


class SpeechTranscriber:
    """Распознает аудио и вставляет текст в активное приложение.

    Attributes:
        pykeyboard: Контроллер клавиатуры pynput для вставки текста.
        model_name: Имя или путь к модели MLX Whisper.
    """

    def __init__(self, model_name):
        """Создает объект распознавания.

        Args:
            model_name: Имя модели Hugging Face или локальный путь к модели.
        """
        self.pykeyboard = keyboard.Controller()
        self.model_name = model_name

    def _copy_text_to_clipboard(self, text):
        """Копирует текст в системный буфер обмена.

        Args:
            text: Текст для сохранения в буфере обмена.
        """
        appkit = cast("Any", AppKit)
        pasteboard = appkit.NSPasteboard.generalPasteboard()
        pasteboard.clearContents()
        pasteboard.setString_forType_(text, appkit.NSPasteboardTypeString)

    def _paste_text(self):
        """Вставляет текущий текст из буфера обмена через Cmd+V."""
        time.sleep(0.05)

        with self.pykeyboard.pressed(keyboard.Key.cmd):
            self.pykeyboard.press("v")
            self.pykeyboard.release("v")

    def transcribe(self, audio_data, language=None):
        """Распознает аудио и вставляет результат в активное приложение.

        Args:
            audio_data: Массив с аудио в формате float32.
            language: Необязательный код языка для улучшения распознавания.
        """
        min_audio_seconds = 0.5
        if len(audio_data) < 16000 * min_audio_seconds:
            LOGGER.info("Аудио слишком короткое (%.2f с), пропускаю распознавание", len(audio_data) / 16000)
            return

        try:
            result = mlx_whisper.transcribe(
                audio_data,
                language=language,
                path_or_hf_repo=self.model_name,
                condition_on_previous_text=False,
                compression_ratio_threshold=2.4,
                no_speech_threshold=0.6,
            )
        except Exception:
            LOGGER.exception("Ошибка распознавания")
            notify_user(
                "MLX Whisper Dictation",
                "Ошибка распознавания. Смотрите stderr.log.",
            )
            return

        text = str(result.get("text", "")).strip()
        LOGGER.info("Распознавание завершено, длина текста=%s", len(text))

        if not text:
            LOGGER.info("Результат распознавания пустой")
            return

        self._copy_text_to_clipboard(text)
        LOGGER.info("Текст сохранен в буфере обмена")

        if not is_accessibility_trusted():
            notify_user(
                "MLX Whisper Dictation",
                "Текст распознан и сохранен в буфер обмена. Вставьте его вручную, потому что у приложения нет доступа к Accessibility.",
            )
            return

        try:
            self._paste_text()
            LOGGER.info("Текст вставлен через буфер обмена")
        except Exception:
            LOGGER.exception("Не удалось вставить через буфер обмена, переключаюсь на ввод клавишами")
            try:
                self.pykeyboard.type(text)
                LOGGER.info("Текст вставлен через резервный ввод клавишами")
            except Exception:
                LOGGER.exception("Резервный ввод клавишами тоже завершился ошибкой")
                notify_user(
                    "MLX Whisper Dictation",
                    "Не удалось вставить текст автоматически. Но текст сохранен в буфер обмена, его можно вставить вручную.",
                )


class Recorder:
    """Записывает звук с микрофона и передает его в распознавание.

    Attributes:
        recording: Флаг активной записи.
        transcriber: Объект распознавания, который обрабатывает аудио.
    """

    def __init__(self, transcriber):
        """Создает объект записи.

        Args:
            transcriber: Экземпляр SpeechTranscriber для обработки записанного аудио.
        """
        self.recording = False
        self.transcriber = transcriber
        self.status_callback = None
        self.permission_callback = None

    def set_status_callback(self, status_callback):
        """Регистрирует callback для обновления UI-статуса.

        Args:
            status_callback: Функция, принимающая строковый статус.
        """
        self.status_callback = status_callback

    def _set_status(self, status):
        """Передает новый статус во внешний callback.

        Args:
            status: Идентификатор состояния приложения.
        """
        if self.status_callback is not None:
            self.status_callback(status)

    def set_permission_callback(self, permission_callback):
        """Регистрирует callback для обновления статусов разрешений.

        Args:
            permission_callback: Функция, принимающая имя разрешения и его статус.
        """
        self.permission_callback = permission_callback

    def _set_permission_status(self, permission_name, status):
        """Передает обновленный статус разрешения во внешний callback.

        Args:
            permission_name: Имя разрешения.
            status: Булев статус разрешения.
        """
        if self.permission_callback is not None:
            self.permission_callback(permission_name, status)

    def start(self, language=None):
        """Запускает запись в отдельном потоке.

        Args:
            language: Необязательный код языка для последующего распознавания.
        """
        thread = threading.Thread(target=self._record_impl, args=(language,))
        thread.daemon = True
        thread.start()

    def stop(self):
        """Останавливает активную запись."""
        self.recording = False

    def _record_impl(self, language):
        """Выполняет запись, конвертацию аудио и запуск распознавания.

        Args:
            language: Необязательный код языка для последующего распознавания.
        """
        self.recording = True
        frames_per_buffer = 1024
        audio_interface = pyaudio.PyAudio()
        stream = None
        frames = []

        try:
            stream = audio_interface.open(
                format=pyaudio.paInt16,
                channels=1,
                rate=16000,
                frames_per_buffer=frames_per_buffer,
                input=True,
            )
            self._set_permission_status("microphone", True)

            while self.recording:
                data = stream.read(frames_per_buffer, exception_on_overflow=False)
                frames.append(data)
        except Exception:
            self._set_permission_status("microphone", False)
            LOGGER.exception("Ошибка записи")
            notify_user(
                "MLX Whisper Dictation",
                "Ошибка записи с микрофона. Смотрите stderr.log.",
            )
            return
        finally:
            if stream is not None:
                stream.stop_stream()
                stream.close()
            audio_interface.terminate()

        if not frames:
            LOGGER.warning("Запись остановлена без захваченных аудиофреймов")
            self._set_status(STATUS_IDLE)
            return

        audio_data = np.frombuffer(b"".join(frames), dtype=np.int16)
        audio_data_fp32 = audio_data.astype(np.float32) / 32768.0
        self._set_status(STATUS_TRANSCRIBING)
        self.transcriber.transcribe(audio_data_fp32, language)
        self._set_status(STATUS_IDLE)


class GlobalKeyListener:
    """Обрабатывает глобальную комбинацию клавиш для запуска диктовки.

    Attributes:
        app: Экземпляр StatusBarApp, которым управляет listener.
        keys: Кортеж клавиш, которые образуют хоткей.
        pressed_keys: Набор клавиш, зажатых в текущий момент.
        triggered: Флаг, защищающий от повторного срабатывания при удержании.
    """

    def __init__(self, app, key_combination):
        """Создает listener для заданной комбинации клавиш.

        Args:
            app: Экземпляр приложения, у которого будет вызван toggle.
            key_combination: Строка с комбинацией клавиш.
        """
        self.app = app
        self.key_combination = key_combination
        self.key_names = [part.strip() for part in key_combination.split("+") if part.strip()]
        self.modifier_names = {"alt", "alt_l", "alt_r", "shift", "shift_l", "shift_r", "ctrl", "ctrl_l", "ctrl_r", "cmd", "cmd_l", "cmd_r"}
        self.required_modifiers = [name for name in self.key_names if name in self.modifier_names]
        self.required_key = next((name for name in self.key_names if name not in self.modifier_names), None)
        self.pressed_modifier_names = set()
        self.triggered = False
        self.flags_monitor = None
        self.key_down_monitor = None
        self.appkit = cast("Any", AppKit)
        self.modifier_keycodes = {
            54: "cmd_r",
            55: "cmd_l",
            58: "alt_l",
            59: "ctrl_l",
            60: "shift_l",
            61: "alt_r",
            62: "ctrl_r",
        }

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
        flag_masks = {
            "alt_l": self.appkit.NSEventModifierFlagOption,
            "alt_r": self.appkit.NSEventModifierFlagOption,
            "ctrl_l": self.appkit.NSEventModifierFlagControl,
            "ctrl_r": self.appkit.NSEventModifierFlagControl,
            "shift_l": self.appkit.NSEventModifierFlagShift,
            "shift_r": self.appkit.NSEventModifierFlagShift,
            "cmd_l": self.appkit.NSEventModifierFlagCommand,
            "cmd_r": self.appkit.NSEventModifierFlagCommand,
        }
        return bool(modifier_flags & int(flag_masks.get(modifier_name, 0)))

    def _handle_flags_changed(self, event):
        """Обрабатывает глобальные изменения modifier-клавиш.

        Args:
            event: Системное NSEvent.
        """
        key_code = int(event.keyCode())
        modifier_name = self.modifier_keycodes.get(key_code)
        if modifier_name is None:
            return

        if self._event_is_modifier_pressed(event, modifier_name):
            self.pressed_modifier_names.add(modifier_name)
        else:
            self.pressed_modifier_names.discard(modifier_name)
            self.triggered = False

        if self.required_key is None and self._required_modifiers_are_pressed() and not self.triggered:
            LOGGER.info("Сработал глобальный хоткей: %s", self.key_combination)
            self.triggered = True
            self.app.toggle()

    def _event_key_name(self, event):
        """Преобразует NSEvent в строковое имя клавиши.

        Args:
            event: Системное NSEvent.

        Returns:
            Имя клавиши для сравнения с конфигурацией.
        """
        key_code = int(event.keyCode())
        named_keycodes = {
            36: "enter",
            48: "tab",
            49: "space",
            51: "backspace",
            53: "esc",
        }
        if key_code in named_keycodes:
            return named_keycodes[key_code]

        characters = str(event.charactersIgnoringModifiers() or "").lower()
        return characters[:1] if characters else ""

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
            LOGGER.info("Сработал глобальный хоткей: %s", self.key_combination)
            self.triggered = True
            self.app.toggle()
        elif event_key_name != self.required_key:
            self.triggered = False


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

    def __init__(self, recorder, model_name, hotkey_status, languages=None, max_time=None):
        """Создает menu bar приложение.

        Args:
            recorder: Объект Recorder для записи и распознавания.
            model_name: Имя модели, показываемое в меню приложения.
            hotkey_status: Строка для отображения текущего хоткея в меню.
            languages: Необязательный список доступных языков.
            max_time: Необязательный лимит длительности записи в секундах.
        """
        super().__init__("whisper", "⏯")
        self.model_name = model_name.rsplit("/", maxsplit=1)[-1]
        self.hotkey_status = hotkey_status
        self.languages = languages
        self.current_language = languages[0] if languages is not None else None
        self.state = STATUS_IDLE
        self.permission_status = {
            "accessibility": get_accessibility_status(),
            "input_monitoring": get_input_monitoring_status(),
            "microphone": None,
        }
        self.status_item = rumps.MenuItem(f"Статус: {self._state_label()}")
        self.model_item = rumps.MenuItem(f"Модель: {self.model_name}")
        self.hotkey_item = rumps.MenuItem(f"Хоткей: {self.hotkey_status}")
        self.language_item = rumps.MenuItem(f"Язык: {self._format_language()}")
        self.max_time_item = rumps.MenuItem(f"Длительность записи: {format_max_time_status(max_time)}")
        self.accessibility_item = rumps.MenuItem(self._permission_title("Accessibility", self.permission_status["accessibility"]))
        self.input_monitoring_item = rumps.MenuItem(self._permission_title("Input Monitoring", self.permission_status["input_monitoring"]))
        self.microphone_item = rumps.MenuItem(self._permission_title("Microphone", self.permission_status["microphone"]))

        menu = [
            "Начать запись",
            "Остановить запись",
            self.status_item,
            self.model_item,
            self.hotkey_item,
            self.language_item,
            self.max_time_item,
            self.accessibility_item,
            self.input_monitoring_item,
            self.microphone_item,
            None,
        ]

        if languages is not None and len(languages) > 1:
            for lang in languages:
                callback = self.change_language if lang != self.current_language else None
                menu.append(rumps.MenuItem(lang, callback=callback))
            menu.append(None)

        self.menu = menu
        self._menu_item("Остановить запись").set_callback(None)

        self.started = False
        self.key_listener = None
        self.recorder = recorder
        self.recorder.set_status_callback(self.set_state)
        self.recorder.set_permission_callback(self.set_permission_status)
        self.max_time = max_time
        self.elapsed_time = 0
        self.status_timer = rumps.Timer(self.on_status_tick, 1)
        self.status_timer.start()

    def _menu_item(self, title):
        """Возвращает пункт меню по заголовку.

        Args:
            title: Текст пункта меню.

        Returns:
            Объект пункта меню из rumps.
        """
        return cast("Any", self.menu)[title]

    def _state_label(self):
        """Возвращает человекочитаемое имя текущего состояния."""
        labels = {
            STATUS_IDLE: "ожидание",
            STATUS_RECORDING: "запись",
            STATUS_TRANSCRIBING: "распознавание",
        }
        return labels.get(self.state, "неизвестно")

    def _format_language(self):
        """Возвращает строку текущего языка для меню."""
        if self.current_language is None:
            return "автоопределение"
        return self.current_language

    def _permission_title(self, permission_name, permission_status):
        """Формирует строку статуса разрешения для меню.

        Args:
            permission_name: Имя разрешения.
            permission_status: Булев статус разрешения или None.

        Returns:
            Строка для пункта меню.
        """
        return f"{permission_name}: {permission_label(permission_status)}"

    def _refresh_permission_items(self):
        """Обновляет пункты меню со статусами разрешений."""
        self.permission_status["accessibility"] = get_accessibility_status()
        self.permission_status["input_monitoring"] = get_input_monitoring_status()
        self.accessibility_item.title = self._permission_title("Accessibility", self.permission_status["accessibility"])
        self.input_monitoring_item.title = self._permission_title("Input Monitoring", self.permission_status["input_monitoring"])
        self.microphone_item.title = self._permission_title("Microphone", self.permission_status["microphone"])

    def _refresh_title_and_status(self):
        """Обновляет иконку и строку статуса в меню."""
        self.status_item.title = f"Статус: {self._state_label()}"
        self._refresh_permission_items()

        if self.state == STATUS_TRANSCRIBING:
            self.title = "🧠"
            return

        if self.state == STATUS_IDLE:
            self.title = "⏯"

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

    def change_language(self, sender):
        """Переключает текущий язык распознавания.

        Args:
            sender: Пункт меню, выбранный пользователем.
        """
        if self.languages is None:
            return

        self.current_language = sender.title
        self.language_item.title = f"Язык: {self._format_language()}"
        for lang in self.languages:
            self._menu_item(lang).set_callback(self.change_language if lang != self.current_language else None)

    @rumps.clicked("Начать запись")
    def start_app(self, _):
        """Запускает запись и обновляет состояние интерфейса.

        Args:
            _: Аргумент callback от rumps, который здесь не используется.
        """
        print("Слушаю...")
        LOGGER.info("Запись началась")
        self.state = STATUS_RECORDING
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

        print("Распознаю...")
        LOGGER.info("Запись остановлена, запускаю распознавание")
        self.started = False
        self.state = STATUS_TRANSCRIBING
        self._refresh_title_and_status()
        self._menu_item("Остановить запись").set_callback(None)
        self._menu_item("Начать запись").set_callback(self.start_app)
        self.recorder.stop()
        print("Готово.\n")

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
        self.title = f"({minutes:02d}:{seconds:02d}) 🔴"
        self.status_item.title = f"Статус: {self._state_label()}"

        if self.max_time is not None and self.elapsed_time >= self.max_time:
            self.stop_app(None)

    def toggle(self):
        """Переключает приложение между состояниями записи и ожидания."""
        if self.started:
            self.stop_app(None)
        else:
            self.start_app(None)


def parse_args():
    """Разбирает аргументы командной строки.

    Returns:
        Пространство имен argparse с настройками запуска приложения.

    Raises:
        SystemExit: Если передана некорректная комбинация клавиш.
        ValueError: Если выбран несовместимый язык для модели с суффиксом `.en`.
    """
    parser = argparse.ArgumentParser(
        description=("Приложение диктовки на базе MLX Whisper. По умолчанию комбинация cmd+option запускает и останавливает диктовку.")
    )
    parser.add_argument(
        "-m",
        "--model",
        type=str,
        default=DEFAULT_MODEL_NAME,
        help="Локальный путь к модели MLX или Hugging Face repo для распознавания.",
    )
    parser.add_argument(
        "-k",
        "--key_combination",
        type=str,
        default="cmd_l+alt" if platform.system() == "Darwin" else "ctrl+alt",
        help=(
            "Комбинация клавиш для запуска и остановки приложения. "
            "Примеры: cmd_l+alt, cmd_l+shift+space, ctrl+alt. "
            "По умолчанию: cmd_l+alt на macOS и ctrl+alt на остальных платформах."
        ),
    )
    parser.add_argument(
        "--k_double_cmd",
        action="store_true",
        help=(
            "Если флаг включен, приложение использует двойное нажатие правой Command "
            "для старта записи и одиночное нажатие для остановки. "
            "Параметр --key_combination при этом игнорируется."
        ),
    )
    parser.add_argument(
        "-l",
        "--language",
        type=str,
        default="ru",
        help=(
            'Двухбуквенный код языка, например "en" или "ru", который помогает '
            "улучшить точность распознавания. Это особенно полезно для более компактных моделей. "
            "Без явного указания языка Whisper пытается определить его автоматически, "
            "но на коротких фразах может ошибаться и галлюцинировать. "
            "По умолчанию: ru. "
            "Полный список языков есть в официальном списке Whisper: "
            "https://github.com/openai/whisper/blob/main/whisper/tokenizer.py."
        ),
    )
    parser.add_argument(
        "-t",
        "--max_time",
        type=float,
        default=30,
        help=(
            "Максимальная длительность записи в секундах. "
            "После этого времени приложение автоматически остановит запись. "
            "По умолчанию: 30 секунд."
        ),
    )

    args = parser.parse_args()

    if not args.k_double_cmd:
        try:
            parse_key_combination(args.key_combination)
        except ValueError as error:
            parser.error(str(error))

    if args.language is not None:
        args.language = args.language.split(",")

    if args.model.endswith(".en") and args.language is not None and any(lang != "en" for lang in args.language):
        raise ValueError("Для модели с суффиксом .en нельзя указывать язык, отличный от английского.")

    return args


def main():
    """Запускает приложение диктовки и глобальные обработчики клавиш."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    args = parse_args()

    if not is_accessibility_trusted():
        warn_missing_accessibility_permission()

    transcriber = SpeechTranscriber(args.model)
    recorder = Recorder(transcriber)

    app = StatusBarApp(
        recorder,
        args.model,
        format_hotkey_status(args.key_combination, use_double_cmd=args.k_double_cmd),
        args.language,
        args.max_time,
    )
    if args.k_double_cmd:
        key_listener = DoubleCommandKeyListener(app)
        listener = keyboard.Listener(
            on_press=key_listener.on_key_press,
            on_release=key_listener.on_key_release,
        )
        listener.start()
        app.key_listener = listener
    else:
        key_listener = GlobalKeyListener(app, args.key_combination)
        key_listener.start()
        app.key_listener = key_listener

    print(f"Запуск с моделью: {args.model}")
    if args.k_double_cmd:
        print("Хоткей: двойное нажатие правой Command для старта и одиночное для остановки")
    else:
        print(f"Хоткей: {args.key_combination}")
    app.run()


if __name__ == "__main__":
    main()
