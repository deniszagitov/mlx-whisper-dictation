"""Приложение офлайн-диктовки для macOS на базе MLX Whisper.

Точка входа приложения: парсинг аргументов командной строки,
запуск menu bar приложения и глобальных обработчиков клавиш.
"""

import argparse
import logging
import platform
import sys
import time
from pathlib import Path

import mlx_whisper
import Quartz
from Foundation import NSUserDefaults
from pynput import keyboard
from src.audio import Recorder, list_input_devices, microphone_menu_title
from src.config import Config, Defaults
from src.diagnostics import (
    DiagnosticsStore,
    looks_like_hallucination,
    setup_logging,
)
from src.hotkeys import (
    _CARBON_AVAILABLE,
    _KEYCODE_ESCAPE,
    MODIFIER_DISPLAY_ORDER,
    MODIFIER_FLAG_MASKS,
    MODIFIER_KEYCODES_MAP,
    DoubleCommandKeyListener,
    GlobalKeyListener,
    MultiHotkeyListener,
    _event_key_name_static,
    _keycode_to_char,
    capture_hotkey_combination,
    format_hotkey_status,
    hotkey_name_matches,
    normalize_key_combination,
    normalize_key_name,
    parse_key,
    parse_key_combination,
)
from src.llm import LLMProcessor, strip_think_blocks
from src.permissions import (
    frontmost_application_info,
    get_accessibility_status,
    get_input_monitoring_status,
    is_accessibility_trusted,
    notify_user,
    permission_label,
    permission_preflight_status,
    request_accessibility_permission,
    request_input_monitoring_permission,
    warn_missing_accessibility_permission,
    warn_missing_input_monitoring_permission,
)
from src.transcriber import SpeechTranscriber
from src.ui import RecordingOverlay, StatusBarApp, _load_microphone_profiles

defaults = Defaults()

LOGGER = logging.getLogger(__name__)


def _cli_option_was_provided(*option_names):
    """Проверяет, был ли аргумент командной строки передан явно."""
    argv = sys.argv[1:]
    return any(option_name in argv for option_name in option_names)


def _load_saved_runtime_preferences(args):
    """Подставляет сохранённые настройки, если их не переопределили через CLI."""
    if not _cli_option_was_provided("-m", "--model"):
        saved_model = defaults.load_str(Config.DEFAULTS_KEY_MODEL, fallback=None)
        if saved_model:
            args.model = saved_model

    if not _cli_option_was_provided("-l", "--language"):
        saved_language = defaults.load_str(Config.DEFAULTS_KEY_LANGUAGE, fallback=None)
        if saved_language:
            args.language = saved_language

    if not _cli_option_was_provided("-t", "--max_time"):
        args.max_time = defaults.load_max_time(args.max_time)

    if not args.k_double_cmd and not _cli_option_was_provided("-k", "--key_combination"):
        saved_primary = defaults.load_str(Config.DEFAULTS_KEY_PRIMARY_HOTKEY, fallback=None)
        if saved_primary:
            args.key_combination = saved_primary

    ns_defaults = NSUserDefaults.standardUserDefaults()
    if (
        not args.k_double_cmd
        and not _cli_option_was_provided("--secondary_key_combination")
        and ns_defaults.objectForKey_(Config.DEFAULTS_KEY_SECONDARY_HOTKEY) is not None
    ):
        args.secondary_key_combination = defaults.load_str(Config.DEFAULTS_KEY_SECONDARY_HOTKEY, fallback="") or None

    if not _cli_option_was_provided("--llm_key_combination") and ns_defaults.objectForKey_(Config.DEFAULTS_KEY_LLM_HOTKEY) is not None:
        args.llm_key_combination = defaults.load_str(Config.DEFAULTS_KEY_LLM_HOTKEY, fallback="") or None


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
        default=Config.DEFAULT_MODEL_NAME,
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
    parser.add_argument(
        "--llm_key_combination",
        type=str,
        default="ctrl+shift+alt+l",
        help=(
            "Комбинация клавиш для запуска LLM-пайплайна: "
            "голос → Whisper → LLM → результат в буфер обмена и уведомление. "
            "По умолчанию: ctrl+shift+alt+l. Укажите пустую строку, чтобы отключить."
        ),
    )
    parser.add_argument(
        "--llm_model",
        type=str,
        default=Config.DEFAULT_LLM_MODEL_NAME,
        help=f"Модель LLM для обработки транскрипций. По умолчанию: {Config.DEFAULT_LLM_MODEL_NAME}.",
    )

    args = parser.parse_args()

    _load_saved_runtime_preferences(args)

    if args.secondary_key_combination is not None and not args.secondary_key_combination.strip():
        args.secondary_key_combination = None

    if args.llm_key_combination is not None and not args.llm_key_combination.strip():
        args.llm_key_combination = None

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
            if args.llm_key_combination:
                args.llm_key_combination = normalize_key_combination(args.llm_key_combination)
        except ValueError as error:
            parser.error(str(error))

    if args.language is not None:
        args.language = args.language.split(",")

    if args.model.endswith(".en") and args.language is not None and any(lang != "en" for lang in args.language):
        raise ValueError("Для модели с суффиксом .en нельзя указывать язык, отличный от английского.")

    return args


def _log_startup_configuration(args):
    """Пишет в лог итоговую конфигурацию запуска приложения."""
    LOGGER.info("Запуск с моделью: %s", args.model)
    if args.k_double_cmd:
        LOGGER.info("Хоткей: двойное нажатие правой Command для старта и одиночное для остановки")
    else:
        LOGGER.info("Основной хоткей: %s", args.key_combination)
        if args.secondary_key_combination:
            LOGGER.info("Дополнительный хоткей: %s", args.secondary_key_combination)
    if args.llm_key_combination:
        LOGGER.info("LLM-хоткей: %s", args.llm_key_combination)


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
    recorder.llm_processor = LLMProcessor(args.llm_model)

    app = StatusBarApp(
        recorder,
        args.model,
        format_hotkey_status(args.key_combination, use_double_cmd=args.k_double_cmd),
        args.language,
        args.max_time,
        key_combination=args.key_combination if not args.k_double_cmd else None,
        secondary_hotkey_status=format_hotkey_status(args.secondary_key_combination) if args.secondary_key_combination else "не задан",
        secondary_key_combination=args.secondary_key_combination,
        llm_hotkey_status=format_hotkey_status(args.llm_key_combination) if args.llm_key_combination else "не задан",
        llm_key_combination=args.llm_key_combination,
        use_double_command_hotkey=args.k_double_cmd,
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
        key_listener = MultiHotkeyListener(app, app._active_key_combinations())
        key_listener.start()
        app.key_listener = key_listener

    if app._llm_key_combination:
        llm_listener = GlobalKeyListener(app, app._llm_key_combination, callback=app.toggle_llm)
        llm_listener.start()
        app.llm_key_listener = llm_listener

    _log_startup_configuration(args)
    app.run()


if __name__ == "__main__":
    main()
