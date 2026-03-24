"""Приложение офлайн-диктовки для macOS на базе MLX Whisper.

Модуль содержит menu bar приложение, которое записывает звук с микрофона,
распознает речь локально через MLX Whisper и вставляет результат в активное
поле ввода.
"""

import argparse
import ctypes
import json
import logging
import logging.handlers
import platform
import sys
import threading
import time
import wave
from pathlib import Path
from typing import Any, cast

import AppKit
import mlx_whisper
import numpy as np
import objc
import pyaudio
import Quartz
import rumps
from Foundation import NSURL, NSDictionary
from pynput import keyboard

DEFAULT_MODEL_NAME = "mlx-community/whisper-large-v3-turbo"
MODEL_PRESETS = [
    "mlx-community/whisper-large-v3-turbo",
    "mlx-community/whisper-large-v3-mlx",
    "mlx-community/whisper-turbo",
]
MAX_TIME_PRESETS = [15, 30, 45, 60, 90, None]
MIN_HOTKEY_PARTS = 2
DOUBLE_COMMAND_PRESS_INTERVAL = 0.5
STATUS_IDLE = "idle"
STATUS_RECORDING = "recording"
STATUS_TRANSCRIBING = "transcribing"
PERMISSION_GRANTED = "есть"
PERMISSION_DENIED = "нет"
PERMISSION_UNKNOWN = "неизвестно"
SILENCE_RMS_THRESHOLD = 0.0005
HALLUCINATION_RMS_THRESHOLD = 0.002
SHORT_AUDIO_WARNING_SECONDS = 0.3
MAX_DEBUG_ARTIFACTS = 10
LOG_DIR = Path.home() / "Library/Logs/whisper-dictation"
ACCESSIBILITY_SETTINGS_URL = "x-apple.systempreferences:com.apple.preference.security?Privacy_Accessibility"
INPUT_MONITORING_SETTINGS_URL = "x-apple.systempreferences:com.apple.preference.security?Privacy_ListenEvent"
KEYCODE_COMMAND = 0x37
KEYCODE_V = 0x09
KNOWN_HALLUCINATIONS = {
    "thank you",
    "thank you.",
    "продолжение следует",
    "продолжение следует...",
    "спасибо за внимание",
    "спасибо за просмотр",
}
LOGGER = logging.getLogger(__name__)


class MaxLevelFilter(logging.Filter):
    """Пропускает записи не выше заданного уровня логирования."""

    def __init__(self, level):
        """Сохраняет максимальный уровень логов для фильтрации."""
        super().__init__()
        self.level = level

    def filter(self, record):
        """Возвращает True, если запись не превышает допустимый уровень."""
        return record.levelno < self.level


def setup_logging():
    """Настраивает консольное и файловое логирование приложения."""
    LOG_DIR.mkdir(parents=True, exist_ok=True)

    formatter = logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)
    root_logger.handlers.clear()

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(formatter)

    stdout_handler = logging.handlers.RotatingFileHandler(
        LOG_DIR / "stdout.log",
        maxBytes=5_000_000,
        backupCount=3,
        encoding="utf-8",
    )
    stdout_handler.setLevel(logging.INFO)
    stdout_handler.addFilter(MaxLevelFilter(logging.ERROR))
    stdout_handler.setFormatter(formatter)

    stderr_handler = logging.handlers.RotatingFileHandler(
        LOG_DIR / "stderr.log",
        maxBytes=5_000_000,
        backupCount=3,
        encoding="utf-8",
    )
    stderr_handler.setLevel(logging.ERROR)
    stderr_handler.setFormatter(formatter)

    root_logger.addHandler(console_handler)
    root_logger.addHandler(stdout_handler)
    root_logger.addHandler(stderr_handler)


def looks_like_hallucination(text):
    """Проверяет, похож ли результат на типичную галлюцинацию Whisper."""
    return text.strip().lower() in KNOWN_HALLUCINATIONS


class DiagnosticsStore:
    """Изолирует сохранение диагностических артефактов от основного runtime-кода."""

    def __init__(self, root_dir=LOG_DIR, enabled=True, max_artifacts=MAX_DEBUG_ARTIFACTS):
        """Создает хранилище диагностических файлов.

        Args:
            root_dir: Корневая директория логов и артефактов.
            enabled: Нужно ли сохранять диагностические файлы.
            max_artifacts: Сколько последних наборов артефактов хранить.
        """
        self.root_dir = Path(root_dir)
        self.enabled = enabled
        self.max_artifacts = max_artifacts

    @property
    def recordings_dir(self):
        """Возвращает путь к папке с диагностическими аудиозаписями."""
        return self.root_dir / "recordings"

    @property
    def transcriptions_dir(self):
        """Возвращает путь к папке с диагностическими транскрипциями."""
        return self.root_dir / "transcriptions"

    def artifact_stem(self):
        """Возвращает уникальное имя группы диагностических файлов."""
        timestamp = time.strftime("%Y%m%d-%H%M%S")
        milliseconds = int((time.time() % 1) * 1000)
        return f"{timestamp}-{milliseconds:03d}"

    def _cleanup_directory(self, directory):
        """Оставляет только последние диагностические файлы в указанной директории."""
        stems_to_mtime = {}
        for path in directory.iterdir():
            if path.is_file():
                stems_to_mtime[path.stem] = max(stems_to_mtime.get(path.stem, 0.0), path.stat().st_mtime)

        sorted_stems = sorted(stems_to_mtime.items(), key=lambda item: item[1], reverse=True)
        stems_to_keep = {stem for stem, _mtime in sorted_stems[: self.max_artifacts]}

        for old_file in directory.iterdir():
            if old_file.is_file() and old_file.stem not in stems_to_keep:
                old_file.unlink(missing_ok=True)

    def build_audio_diagnostics(self, audio_data, language):
        """Собирает компактную диагностику входного аудиосигнала."""
        audio_duration_seconds = len(audio_data) / 16000
        rms_energy = float(np.sqrt(np.mean(audio_data**2)))
        peak_amplitude = float(np.max(np.abs(audio_data))) if len(audio_data) else 0.0
        return {
            "language": language,
            "duration_seconds": audio_duration_seconds,
            "rms_energy": rms_energy,
            "peak_amplitude": peak_amplitude,
            "silence_threshold": SILENCE_RMS_THRESHOLD,
            "hallucination_threshold": HALLUCINATION_RMS_THRESHOLD,
            "sample_rate": 16000,
            "samples": len(audio_data),
            "first_samples": audio_data[:16].tolist(),
        }

    def save_audio_recording(self, stem, audio_data, diagnostics):
        """Сохраняет аудиозапись и метаданные, если диагностика включена."""
        if not self.enabled:
            return None

        self.recordings_dir.mkdir(parents=True, exist_ok=True)
        wav_path = self.recordings_dir / f"{stem}.wav"
        with wave.open(str(wav_path), "wb") as wav_file:
            wav_file.setnchannels(1)
            wav_file.setsampwidth(2)
            wav_file.setframerate(16000)
            pcm_data = np.clip(audio_data * 32768.0, -32768, 32767).astype(np.int16)
            wav_file.writeframes(pcm_data.tobytes())

        metadata_path = self.recordings_dir / f"{stem}.json"
        metadata_path.write_text(json.dumps(diagnostics, ensure_ascii=False, indent=2), encoding="utf-8")
        self._cleanup_directory(self.recordings_dir)
        return wav_path

    def save_transcription_artifacts(self, stem, diagnostics, result=None, text="", error_message=None):
        """Сохраняет результат распознавания и метаданные, если диагностика включена."""
        if not self.enabled:
            return None

        self.transcriptions_dir.mkdir(parents=True, exist_ok=True)
        payload = {"diagnostics": diagnostics, "text": text, "error": error_message, "result": result}
        json_path = self.transcriptions_dir / f"{stem}.json"
        json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8")

        text_path = self.transcriptions_dir / f"{stem}.txt"
        text_path.write_text(text, encoding="utf-8")

        self._cleanup_directory(self.transcriptions_dir)
        return json_path


def notify_user(title, message):
    """Показывает системное уведомление macOS.

    Args:
        title: Заголовок уведомления.
        message: Основной текст уведомления.
    """
    try:
        rumps.notification(title, "", message)
    except Exception:
        LOGGER.exception("❌ Не удалось показать системное уведомление macOS")


def open_system_settings(url):
    """Открывает нужный раздел System Settings по специальной ссылке macOS."""
    if platform.system() != "Darwin":
        return False

    try:
        settings_url = NSURL.URLWithString_(url)
        return bool(AppKit.NSWorkspace.sharedWorkspace().openURL_(settings_url))
    except Exception:
        LOGGER.exception("❌ Не удалось открыть System Settings: %s", url)
        return False


def frontmost_application_info():
    """Возвращает краткую информацию о текущем активном приложении."""
    try:
        workspace = AppKit.NSWorkspace.sharedWorkspace()
        application = workspace.frontmostApplication()
        if application is None:
            return None

        return {
            "name": str(application.localizedName() or ""),
            "bundle_id": str(application.bundleIdentifier() or ""),
            "pid": int(application.processIdentifier()),
        }
    except Exception:
        LOGGER.exception("❌ Не удалось определить активное приложение")
        return None


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
        LOGGER.exception("❌ Не удалось проверить статус Accessibility")
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
        LOGGER.exception("❌ Не удалось проверить статус разрешения %s", function_name)
        return None


def get_accessibility_status():
    """Возвращает статус доступа к Accessibility."""
    return permission_preflight_status("AXIsProcessTrusted")


def get_input_monitoring_status():
    """Возвращает статус доступа к Input Monitoring."""
    return permission_preflight_status("CGPreflightListenEventAccess")


def request_accessibility_permission():
    """Запрашивает Accessibility через системный диалог macOS.

    Вызывает AXIsProcessTrustedWithOptions с kAXTrustedCheckOptionPrompt=True,
    чтобы macOS показала пользователю диалог с предложением открыть настройки.

    Returns:
        True, если разрешение уже выдано, False если нужно выдать вручную.
    """
    if platform.system() != "Darwin":
        return True

    try:
        application_services = ctypes.CDLL("/System/Library/Frameworks/ApplicationServices.framework/ApplicationServices")
        options = NSDictionary.dictionaryWithObject_forKey_(True, "AXTrustedCheckOptionPrompt")
        request_function = getattr(application_services, "AXIsProcessTrustedWithOptions", None)
        if request_function is None:
            LOGGER.warning("⚠️ AXIsProcessTrustedWithOptions не найдена")
            return False

        request_function.restype = ctypes.c_bool
        request_function.argtypes = [ctypes.c_void_p]
        result = bool(request_function(objc.pyobjc_id(options)))
    except Exception:
        LOGGER.exception("❌ Не удалось запросить Accessibility")
        return False
    else:
        return result


def request_input_monitoring_permission():
    """Запрашивает Input Monitoring через системный диалог macOS.

    Вызывает CGRequestListenEventAccess, чтобы macOS показала пользователю
    диалог с предложением открыть настройки Input Monitoring.

    Returns:
        True, если разрешение уже выдано, False если нужно выдать вручную.
    """
    if platform.system() != "Darwin":
        return True

    try:
        request_function = getattr(Quartz, "CGRequestListenEventAccess", None)
        if request_function is None:
            LOGGER.warning("⚠️ CGRequestListenEventAccess не найдена")
            return False
        return bool(request_function())
    except Exception:
        LOGGER.exception("❌ Не удалось запросить Input Monitoring")
        return False


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
    LOGGER.error("🔐 %s", message)
    open_system_settings(ACCESSIBILITY_SETTINGS_URL)
    notify_user("MLX Whisper Dictation", message)


def warn_missing_input_monitoring_permission():
    """Показывает пользователю предупреждение об отсутствии Input Monitoring."""
    message = (
        "Нет доступа к Input Monitoring для MLX Whisper Dictation. "
        "Без него macOS может блокировать глобальный хоткей или синтетический ввод. "
        "Откройте System Settings -> Privacy & Security -> Input Monitoring и включите приложение заново."
    )
    LOGGER.error("🔐 %s", message)
    open_system_settings(INPUT_MONITORING_SETTINGS_URL)
    notify_user("MLX Whisper Dictation", message)


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


def microphone_menu_title(device_info):
    """Формирует подпись микрофона для меню приложения."""
    name = str(device_info.get("name", "Неизвестное устройство"))
    return f"[{device_info['index']}] {name}"


def list_input_devices():
    """Возвращает список доступных устройств ввода из PyAudio."""
    audio_interface = pyaudio.PyAudio()
    devices = []
    try:
        default_input = None
        try:
            default_info = audio_interface.get_default_input_device_info()
        except Exception:
            default_info = None
        if default_info is not None:
            default_input = int(default_info.get("index", -1))

        for device_index in range(audio_interface.get_device_count()):
            info = audio_interface.get_device_info_by_index(device_index)
            if int(info.get("maxInputChannels", 0)) <= 0:
                continue
            normalized = {
                "index": int(info.get("index", device_index)),
                "name": str(info.get("name", f"Input {device_index}")),
                "max_input_channels": int(info.get("maxInputChannels", 0)),
                "default_sample_rate": float(info.get("defaultSampleRate", 16000.0)),
                "is_default": int(info.get("index", device_index)) == default_input,
            }
            devices.append(normalized)
    finally:
        audio_interface.terminate()

    devices.sort(key=lambda item: (not item["is_default"], item["index"]))
    return devices


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


class SpeechTranscriber:
    """Распознает аудио и вставляет текст в активное приложение.

    Attributes:
        pykeyboard: Контроллер клавиатуры pynput для вставки текста.
        diagnostics_store: Изолированное хранилище диагностических артефактов.
        model_name: Имя или путь к модели MLX Whisper.
    """

    def __init__(self, model_name, diagnostics_store=None):
        """Создает объект распознавания.

        Args:
            model_name: Имя модели Hugging Face или локальный путь к модели.
            diagnostics_store: Необязательное хранилище диагностических файлов.
        """
        self.pykeyboard = keyboard.Controller()
        self.diagnostics_store = diagnostics_store or DiagnosticsStore()
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
        active_app = frontmost_application_info()
        if active_app is not None:
            LOGGER.info(
                "🎤 Пытаюсь вставить в активное приложение: name=%s, bundle_id=%s, pid=%s",
                active_app["name"],
                active_app["bundle_id"],
                active_app["pid"],
            )

        event_source = Quartz.CGEventSourceCreate(Quartz.kCGEventSourceStateHIDSystemState)
        if event_source is None:
            raise RuntimeError("Не удалось создать источник системных keyboard events")

        command_down = Quartz.CGEventCreateKeyboardEvent(event_source, KEYCODE_COMMAND, True)
        paste_down = Quartz.CGEventCreateKeyboardEvent(event_source, KEYCODE_V, True)
        paste_up = Quartz.CGEventCreateKeyboardEvent(event_source, KEYCODE_V, False)
        command_up = Quartz.CGEventCreateKeyboardEvent(event_source, KEYCODE_COMMAND, False)

        if not all((command_down, paste_down, paste_up, command_up)):
            raise RuntimeError("Не удалось создать keyboard events для Cmd+V")

        Quartz.CGEventSetFlags(command_down, Quartz.kCGEventFlagMaskCommand)
        Quartz.CGEventSetFlags(paste_down, Quartz.kCGEventFlagMaskCommand)
        Quartz.CGEventSetFlags(paste_up, Quartz.kCGEventFlagMaskCommand)

        Quartz.CGEventPost(Quartz.kCGHIDEventTap, command_down)
        Quartz.CGEventPost(Quartz.kCGHIDEventTap, paste_down)
        Quartz.CGEventPost(Quartz.kCGHIDEventTap, paste_up)
        Quartz.CGEventPost(Quartz.kCGHIDEventTap, command_up)

    def _run_transcription(self, audio_data, language):
        """Запускает один проход распознавания с заданными параметрами языка."""
        return mlx_whisper.transcribe(
            audio_data,
            language=language,
            path_or_hf_repo=self.model_name,
            condition_on_previous_text=False,
            hallucination_silence_threshold=2.0,
        )

    def transcribe(self, audio_data, language=None):
        """Распознает аудио и вставляет результат в активное приложение.

        Args:
            audio_data: Массив с аудио в формате float32.
            language: Необязательный код языка для улучшения распознавания.
        """
        stem = self.diagnostics_store.artifact_stem()
        diagnostics = self.diagnostics_store.build_audio_diagnostics(audio_data, language)
        audio_duration_seconds = diagnostics["duration_seconds"]
        rms_energy = diagnostics["rms_energy"]
        peak_amplitude = diagnostics["peak_amplitude"]
        wav_path = self.diagnostics_store.save_audio_recording(stem, audio_data, diagnostics)
        if wav_path is None:
            LOGGER.info(
                "🔍 Диагностика аудио: длительность=%.2f с, RMS=%.6f, peak=%.6f, language=%s",
                audio_duration_seconds,
                rms_energy,
                peak_amplitude,
                language,
            )
        else:
            LOGGER.info(
                "🔍 Диагностика аудио: длительность=%.2f с, RMS=%.6f, peak=%.6f, language=%s, wav=%s",
                audio_duration_seconds,
                rms_energy,
                peak_amplitude,
                language,
                wav_path,
            )
        if audio_duration_seconds < SHORT_AUDIO_WARNING_SECONDS:
            LOGGER.warning("⚠️ Аудио короткое (%.2f с), но распознавание всё равно будет запущено", audio_duration_seconds)
        if rms_energy < SILENCE_RMS_THRESHOLD:
            LOGGER.warning(
                "🔇 Аудио очень тихое (RMS=%.6f < %.4f), но распознавание всё равно будет запущено",
                rms_energy,
                SILENCE_RMS_THRESHOLD,
            )

        try:
            result = self._run_transcription(audio_data, language)
        except Exception:
            LOGGER.exception("❌ Ошибка распознавания")
            self.diagnostics_store.save_transcription_artifacts(stem, diagnostics, error_message="Ошибка распознавания")
            notify_user(
                "MLX Whisper Dictation",
                "Ошибка распознавания. Смотрите stderr.log.",
            )
            return

        text = str(result.get("text", "")).strip()
        LOGGER.info("🧠 Первый проход распознавания завершен, длина текста=%s, текст=%r", len(text), text[:120])

        if not text and language is not None:
            LOGGER.info("🔄 Первый проход вернул пустой результат, повторяю распознавание без фиксированного языка")
            try:
                result = self._run_transcription(audio_data, None)
            except Exception:
                LOGGER.exception("❌ Ошибка повторного распознавания без языка")
            else:
                text = str(result.get("text", "")).strip()
                LOGGER.info("🧠 Повторный проход завершен, длина текста=%s, текст=%r", len(text), text[:120])

        self.diagnostics_store.save_transcription_artifacts(stem, diagnostics, result=result, text=text)

        if not text:
            LOGGER.warning("⚠️ Результат распознавания пустой")
            notify_user(
                "MLX Whisper Dictation",
                "Речь не распознана. Проверьте микрофон, уровень сигнала и попробуйте еще раз.",
            )
            return

        if looks_like_hallucination(text) and rms_energy < HALLUCINATION_RMS_THRESHOLD:
            LOGGER.warning("👻 Отброшен вероятный галлюцинаторный результат: %r", text)

        try:
            self._copy_text_to_clipboard(text)
        except Exception:
            LOGGER.exception("❌ Не удалось сохранить текст в буфер обмена")
            notify_user(
                "MLX Whisper Dictation",
                "Не удалось сохранить распознанный текст в буфер обмена. Смотрите stderr.log.",
            )
            return
        else:
            LOGGER.info("📋 Текст сохранен в буфере обмена")

        if not is_accessibility_trusted():
            LOGGER.warning("🔐 Перед вставкой нет доступа к Accessibility, повторно запрашиваю разрешение")
            request_accessibility_permission()
            time.sleep(0.2)

        if get_input_monitoring_status() is not True:
            LOGGER.warning("🔐 Перед вставкой нет доступа к Input Monitoring, повторно запрашиваю разрешение")
            request_input_monitoring_permission()
            time.sleep(0.2)

        if not is_accessibility_trusted():
            warn_missing_accessibility_permission()
            notify_user(
                "MLX Whisper Dictation",
                "Текст распознан и сохранен в буфер обмена. Вставьте его вручную, потому что у приложения нет доступа к Accessibility.",
            )
            return

        if get_input_monitoring_status() is False:
            warn_missing_input_monitoring_permission()
            notify_user(
                "MLX Whisper Dictation",
                "Текст распознан и сохранен в буфер обмена. Вставьте его вручную, потому что macOS не дала доступ к Input Monitoring.",
            )
            return

        try:
            self._paste_text()
            LOGGER.info("📌 Текст вставлен через буфер обмена")
        except Exception:
            LOGGER.exception("⚠️ Не удалось вставить через буфер обмена, переключаюсь на ввод клавишами")
            try:
                self.pykeyboard.type(text)
                LOGGER.info("⌨️ Текст вставлен через резервный ввод клавишами")
            except Exception:
                LOGGER.exception("❌ Резервный ввод клавишами тоже завершился ошибкой")
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
        self.input_device_index = None
        self.input_device_name = "системный по умолчанию"

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

    def set_input_device(self, device_info=None):
        """Сохраняет выбранное устройство ввода для последующей записи."""
        if device_info is None:
            self.input_device_index = None
            self.input_device_name = "системный по умолчанию"
            return

        self.input_device_index = int(device_info["index"])
        self.input_device_name = str(device_info["name"])

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
            LOGGER.info(
                "🎙️ Открываю поток записи: input_device_index=%s, input_device_name=%s",
                self.input_device_index,
                self.input_device_name,
            )
            stream = audio_interface.open(
                format=pyaudio.paInt16,
                channels=1,
                rate=16000,
                frames_per_buffer=frames_per_buffer,
                input=True,
                input_device_index=self.input_device_index,
            )
            self._set_permission_status("microphone", True)

            while self.recording:
                data = stream.read(frames_per_buffer, exception_on_overflow=False)
                frames.append(data)
        except Exception:
            self._set_permission_status("microphone", False)
            LOGGER.exception("❌ Ошибка записи")
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
            LOGGER.warning("⚠️ Запись остановлена без захваченных аудиофреймов")
            self._set_status(STATUS_IDLE)
            return

        audio_data = np.frombuffer(b"".join(frames), dtype=np.int16)
        audio_data_fp32 = audio_data.astype(np.float32) / 32768.0
        LOGGER.info(
            "✅ Запись завершена: фреймов=%s, сэмплов=%s, длительность=%.2f с",
            len(frames),
            len(audio_data_fp32),
            len(audio_data_fp32) / 16000,
        )
        self._set_status(STATUS_TRANSCRIBING)
        self.transcriber.transcribe(audio_data_fp32, language)
        self._set_status(STATUS_IDLE)


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

    def __init__(self, app, key_combination):
        """Создает listener для заданной комбинации клавиш.

        Args:
            app: Экземпляр приложения, у которого будет вызван toggle.
            key_combination: Строка с комбинацией клавиш.
        """
        self.app = app
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
            self.app.toggle()

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
            self.app.toggle()
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
        """
        super().__init__("whisper", "⏯")
        self.model_repo = model_name
        self.model_name = model_name.rsplit("/", maxsplit=1)[-1]
        self.hotkey_status = hotkey_status
        self.secondary_hotkey_status = secondary_hotkey_status or "не задан"
        self._primary_key_combination = key_combination or ""
        self._secondary_key_combination = secondary_key_combination or ""
        self.max_time_options = list(MAX_TIME_PRESETS)
        if max_time not in self.max_time_options:
            self.max_time_options.insert(0, max_time)
        self.model_options = list(MODEL_PRESETS)
        if self.model_repo not in self.model_options:
            self.model_options.insert(0, self.model_repo)
        self.languages = languages
        self.input_devices = list_input_devices()
        self.current_language = languages[0] if languages is not None else None
        self.current_input_device = next((device for device in self.input_devices if device["is_default"]), None)
        if self.current_input_device is None and self.input_devices:
            self.current_input_device = self.input_devices[0]
        self.state = STATUS_IDLE
        self.permission_status = {
            "accessibility": get_accessibility_status(),
            "input_monitoring": get_input_monitoring_status(),
            "microphone": None,
        }
        self.status_item = rumps.MenuItem(f"🔄 Статус: {self._state_label()}")
        self.model_item = rumps.MenuItem(f"🧠 Модель: {self.model_name}")
        self.hotkey_item = rumps.MenuItem(f"⌨️ Основной хоткей: {self.hotkey_status}")
        self.secondary_hotkey_item = rumps.MenuItem(f"⌨️ Доп. хоткей: {self.secondary_hotkey_status}")
        self.change_hotkey_item = rumps.MenuItem("⌨️ Изменить основной хоткей…", callback=self.change_hotkey)
        self.change_secondary_hotkey_item = rumps.MenuItem("⌨️ Изменить доп. хоткей…", callback=self.change_secondary_hotkey)
        self.show_recording_notification = True
        self.recording_notification_item = rumps.MenuItem(
            "🔔 Уведомление о старте записи",
            callback=self.toggle_recording_notification,
        )
        self.recording_notification_item.state = int(self.show_recording_notification)
        self.language_item = rumps.MenuItem(f"🌍 Язык: {self._format_language()}")
        self.input_device_item = rumps.MenuItem(f"🎙️ Микрофон: {self._format_input_device()}")
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
            self.change_hotkey_item,
            self.change_secondary_hotkey_item,
            self.recording_notification_item,
            self.language_item,
            self.input_device_item,
            self.max_time_item,
            "🧠 Выбрать модель",
            "🎙️ Выбрать микрофон",
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

        if self.input_devices:
            for device in self.input_devices:
                title = microphone_menu_title(device)
                callback = self.change_input_device
                menu.append(rumps.MenuItem(title, callback=callback))
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
        self.recorder = recorder
        self.recorder.set_input_device(self.current_input_device)
        self.recorder.set_status_callback(self.set_state)
        self.recorder.set_permission_callback(self.set_permission_status)
        self.max_time = max_time
        self.elapsed_time = 0
        self.status_timer = rumps.Timer(self.on_status_tick, 1)
        self.status_timer.start()
        self._refresh_selection_states()

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

    def _refresh_title_and_status(self):
        """Обновляет иконку и строку статуса в меню."""
        self.status_item.title = f"🔄 Статус: {self._state_label()}"
        self._refresh_permission_items()

        if self.state == STATUS_TRANSCRIBING:
            self.title = "🧠"
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

    def _can_update_hotkeys_runtime(self):
        """Проверяет, поддерживает ли текущий listener горячее обновление хоткеев."""
        return hasattr(self.key_listener, "update_key_combinations")

    def _apply_hotkey_changes(self):
        """Применяет обновленные комбинации к меню и активному listener-у."""
        self._refresh_hotkey_items()
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
        self.max_time_item.title = f"⏱ Длительность записи: {format_max_time_status(self.max_time)}"
        self._refresh_selection_states()
        LOGGER.info("⏱ Обновлен лимит записи: %s", format_max_time_status(self.max_time))

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
        LOGGER.info("🔔 Уведомление о старте записи: %s", "включено" if self.show_recording_notification else "выключено")

    @rumps.clicked("Начать запись")
    def start_app(self, _):
        """Запускает запись и обновляет состояние интерфейса.

        Args:
            _: Аргумент callback от rumps, который здесь не используется.
        """
        print("Слушаю...")
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

        print("Распознаю...")
        LOGGER.info("⏹ Запись остановлена, запускаю распознавание")
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
            "Поддерживаются несколько модификаторов одновременно. "
            "Примеры: cmd_l+alt, cmd_l+shift+space, ctrl+shift+alt+t. "
            "Регистр не важен, можно писать Ctrl+Shift+Alt+T. "
            "Допустимые алиасы: Control=ctrl, Option=alt, Command=cmd. "
            "По умолчанию: cmd_l+alt на macOS и ctrl+alt на остальных платформах."
        ),
    )
    parser.add_argument(
        "--secondary_key_combination",
        type=str,
        default="ctrl+shift+alt+t",
        help=(
            "Дополнительная комбинация клавиш для тех же действий запуска и остановки записи. "
            "По умолчанию: ctrl+shift+alt+t. Укажите пустую строку, чтобы отключить."
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

    if args.secondary_key_combination is not None and not args.secondary_key_combination.strip():
        args.secondary_key_combination = None

    if args.k_double_cmd and args.secondary_key_combination:
        if "--secondary_key_combination" in sys.argv:
            parser.error("Параметр --secondary_key_combination нельзя использовать вместе с --k_double_cmd.")
        args.secondary_key_combination = None

    if not args.k_double_cmd:
        try:
            args.key_combination = normalize_key_combination(args.key_combination)
            if args.secondary_key_combination:
                args.secondary_key_combination = normalize_key_combination(args.secondary_key_combination)
                if args.secondary_key_combination == args.key_combination:
                    parser.error("Дополнительный хоткей должен отличаться от основного.")
        except ValueError as error:
            parser.error(str(error))

    if args.language is not None:
        args.language = args.language.split(",")

    if args.model.endswith(".en") and args.language is not None and any(lang != "en" for lang in args.language):
        raise ValueError("Для модели с суффиксом .en нельзя указывать язык, отличный от английского.")

    return args


def main():
    """Запускает приложение диктовки и глобальные обработчики клавиш."""
    setup_logging()

    args = parse_args()

    accessibility_granted = request_accessibility_permission()
    input_monitoring_granted = request_input_monitoring_permission()
    LOGGER.info("🔓 Accessibility: %s, Input Monitoring: %s", accessibility_granted, input_monitoring_granted)

    if not accessibility_granted:
        warn_missing_accessibility_permission()
    if input_monitoring_granted is False:
        warn_missing_input_monitoring_permission()

    transcriber = SpeechTranscriber(args.model)
    recorder = Recorder(transcriber)

    app = StatusBarApp(
        recorder,
        args.model,
        format_hotkey_status(args.key_combination, use_double_cmd=args.k_double_cmd),
        args.language,
        args.max_time,
        key_combination=args.key_combination if not args.k_double_cmd else None,
        secondary_hotkey_status=format_hotkey_status(args.secondary_key_combination) if args.secondary_key_combination else "не задан",
        secondary_key_combination=args.secondary_key_combination,
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
        key_listener = MultiHotkeyListener(app, [args.key_combination, args.secondary_key_combination])
        key_listener.start()
        app.key_listener = key_listener

    print(f"Запуск с моделью: {args.model}")
    if args.k_double_cmd:
        print("Хоткей: двойное нажатие правой Command для старта и одиночное для остановки")
    else:
        print(f"Основной хоткей: {args.key_combination}")
        if args.secondary_key_combination:
            print(f"Дополнительный хоткей: {args.secondary_key_combination}")
    app.run()


if __name__ == "__main__":
    main()
