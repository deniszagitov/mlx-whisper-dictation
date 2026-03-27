"""Приложение офлайн-диктовки для macOS на базе MLX Whisper.

Точка входа приложения: парсинг аргументов командной строки,
запуск menu bar приложения и глобальных обработчиков клавиш.
"""

import argparse
import logging
import platform
import sys
from pathlib import Path

# Добавляем src/ в sys.path для импорта модулей приложения
sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

import time  # noqa: F401 — реэкспорт для тестов

import mlx_whisper  # noqa: F401 — реэкспорт для тестов
import Quartz  # noqa: F401 — реэкспорт для тестов
from Foundation import NSUserDefaults
from pynput import keyboard

from audio import Recorder, list_input_devices, microphone_menu_title  # noqa: F401 — реэкспорт для тестов
from config import (
    CGEVENT_CHUNK_DELAY,  # noqa: F401 — реэкспорт для тестов
    CGEVENT_UNICODE_CHUNK_SIZE,  # noqa: F401 — реэкспорт для тестов
    CLIPBOARD_RESTORE_DELAY,  # noqa: F401 — реэкспорт для тестов
    DEFAULT_LLM_MODEL_NAME,
    DEFAULT_MODEL_NAME,
    DEFAULTS_KEY_HISTORY,  # noqa: F401 — реэкспорт для тестов
    DEFAULTS_KEY_LANGUAGE,
    DEFAULTS_KEY_LLM_HOTKEY,
    DEFAULTS_KEY_LLM_PROMPT,  # noqa: F401 — реэкспорт для тестов
    DEFAULTS_KEY_MAX_TIME,  # noqa: F401 — реэкспорт для тестов
    DEFAULTS_KEY_MODEL,
    DEFAULTS_KEY_PASTE_AX,  # noqa: F401 — реэкспорт для тестов
    DEFAULTS_KEY_PASTE_CGEVENT,  # noqa: F401 — реэкспорт для тестов
    DEFAULTS_KEY_PASTE_CLIPBOARD,  # noqa: F401 — реэкспорт для тестов
    DEFAULTS_KEY_PERFORMANCE_MODE,  # noqa: F401 — реэкспорт для тестов
    DEFAULTS_KEY_PRIMARY_HOTKEY,
    DEFAULTS_KEY_PRIVATE_MODE,  # noqa: F401 — реэкспорт для тестов
    DEFAULTS_KEY_RECORDING_NOTIFICATION,  # noqa: F401 — реэкспорт для тестов
    DEFAULTS_KEY_SECONDARY_HOTKEY,
    DEFAULTS_KEY_TOTAL_TOKENS,  # noqa: F401 — реэкспорт для тестов
    HISTORY_DISPLAY_LENGTH,  # noqa: F401 — реэкспорт для тестов
    KEYCODE_COMMAND,  # noqa: F401 — реэкспорт для тестов
    KEYCODE_V,  # noqa: F401 — реэкспорт для тестов
    LLM_PROMPT_PRESETS,  # noqa: F401 — реэкспорт для тестов
    LOG_DIR,  # noqa: F401 — реэкспорт для тестов
    MAX_HISTORY_SIZE,  # noqa: F401 — реэкспорт для тестов
    PERFORMANCE_MODE_FAST,  # noqa: F401 — реэкспорт для тестов
    PERFORMANCE_MODE_NORMAL,  # noqa: F401 — реэкспорт для тестов
    STATUS_IDLE,  # noqa: F401 — реэкспорт для тестов
    STATUS_RECORDING,  # noqa: F401 — реэкспорт для тестов
    STATUS_TRANSCRIBING,  # noqa: F401 — реэкспорт для тестов
    _load_defaults_max_time,
    _load_defaults_str,
    format_max_time_status,  # noqa: F401 — реэкспорт для тестов
)
from diagnostics import (
    DiagnosticsStore,  # noqa: F401 — реэкспорт для тестов
    looks_like_hallucination,  # noqa: F401 — реэкспорт для тестов
    setup_logging,
)
from hotkeys import (
    MODIFIER_DISPLAY_ORDER,  # noqa: F401 — реэкспорт для тестов
    MODIFIER_FLAG_MASKS,  # noqa: F401 — реэкспорт для тестов
    MODIFIER_KEYCODES_MAP,  # noqa: F401 — реэкспорт для тестов
    DoubleCommandKeyListener,
    GlobalKeyListener,
    MultiHotkeyListener,
    _event_key_name_static,  # noqa: F401 — реэкспорт для тестов
    capture_hotkey_combination,  # noqa: F401 — реэкспорт для тестов
    format_hotkey_status,
    hotkey_name_matches,  # noqa: F401 — реэкспорт для тестов
    normalize_key_combination,
    normalize_key_name,  # noqa: F401 — реэкспорт для тестов
    parse_key,  # noqa: F401 — реэкспорт для тестов
    parse_key_combination,  # noqa: F401 — реэкспорт для тестов
)
from llm import LLMProcessor, strip_think_blocks  # noqa: F401 — реэкспорт для тестов
from permissions import (
    frontmost_application_info,  # noqa: F401 — реэкспорт для тестов
    get_accessibility_status,  # noqa: F401 — реэкспорт для тестов
    get_input_monitoring_status,  # noqa: F401 — реэкспорт для тестов
    is_accessibility_trusted,  # noqa: F401 — реэкспорт для тестов
    notify_user,  # noqa: F401 — реэкспорт для тестов
    permission_label,  # noqa: F401 — реэкспорт для тестов
    permission_preflight_status,  # noqa: F401 — реэкспорт для тестов
    request_accessibility_permission,
    request_input_monitoring_permission,
    warn_missing_accessibility_permission,
    warn_missing_input_monitoring_permission,
)
from transcriber import SpeechTranscriber
from ui import StatusBarApp, _load_microphone_profiles  # noqa: F401 — реэкспорт для тестов


def _cli_option_was_provided(*option_names):
    """Проверяет, был ли аргумент командной строки передан явно."""
    argv = sys.argv[1:]
    return any(option_name in argv for option_name in option_names)


def _load_saved_runtime_preferences(args):
    """Подставляет сохранённые настройки, если их не переопределили через CLI."""
    if not _cli_option_was_provided("-m", "--model"):
        saved_model = _load_defaults_str(DEFAULTS_KEY_MODEL, fallback=None)
        if saved_model:
            args.model = saved_model

    if not _cli_option_was_provided("-l", "--language"):
        saved_language = _load_defaults_str(DEFAULTS_KEY_LANGUAGE, fallback=None)
        if saved_language:
            args.language = saved_language

    if not _cli_option_was_provided("-t", "--max_time"):
        args.max_time = _load_defaults_max_time(args.max_time)

    if not args.k_double_cmd and not _cli_option_was_provided("-k", "--key_combination"):
        saved_primary = _load_defaults_str(DEFAULTS_KEY_PRIMARY_HOTKEY, fallback=None)
        if saved_primary:
            args.key_combination = saved_primary

    defaults = NSUserDefaults.standardUserDefaults()
    if (
        not args.k_double_cmd
        and not _cli_option_was_provided("--secondary_key_combination")
        and defaults.objectForKey_(DEFAULTS_KEY_SECONDARY_HOTKEY) is not None
    ):
        args.secondary_key_combination = _load_defaults_str(DEFAULTS_KEY_SECONDARY_HOTKEY, fallback="") or None

    if not _cli_option_was_provided("--llm_key_combination") and defaults.objectForKey_(DEFAULTS_KEY_LLM_HOTKEY) is not None:
        args.llm_key_combination = _load_defaults_str(DEFAULTS_KEY_LLM_HOTKEY, fallback="") or None


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
        default=DEFAULT_LLM_MODEL_NAME,
        help=f"Модель LLM для обработки транскрипций. По умолчанию: {DEFAULT_LLM_MODEL_NAME}.",
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


def main():
    """Запускает приложение диктовки и глобальные обработчики клавиш."""
    setup_logging()

    args = parse_args()

    accessibility_granted = request_accessibility_permission()
    input_monitoring_granted = request_input_monitoring_permission()

    logger = logging.getLogger(__name__)
    logger.info("🔓 Accessibility: %s, Input Monitoring: %s", accessibility_granted, input_monitoring_granted)

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

    print(f"Запуск с моделью: {args.model}")
    if args.k_double_cmd:
        print("Хоткей: двойное нажатие правой Command для старта и одиночное для остановки")
    else:
        print(f"Основной хоткей: {args.key_combination}")
        if args.secondary_key_combination:
            print(f"Дополнительный хоткей: {args.secondary_key_combination}")
    if args.llm_key_combination:
        print(f"LLM-хоткей: {args.llm_key_combination}")
    app.run()


if __name__ == "__main__":
    main()
