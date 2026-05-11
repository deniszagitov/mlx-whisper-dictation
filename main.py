"""Приложение офлайн-диктовки для macOS на базе MLX Whisper.

Точка входа приложения: парсинг аргументов командной строки,
запуск menu bar приложения и глобальных обработчиков клавиш.
"""

import argparse
import logging
import platform
import sys
from typing import Any, cast

import Quartz  # noqa: F401
from src.adapters.hotkey_dialog import capture_hotkey_combination
from src.adapters.overlay import RecordingOverlay
from src.adapters.rsvp_overlay import RSVPOverlay
from src.adapters.ui import StatusBarApp
from src.app import (  # noqa: F401
    AppSnapshot,
    ClipboardService,
    DictationApp,
    DisplaySleepPreventionService,
    HotkeyCaptureService,
    HotkeyListenerFactoryService,
    InputDeviceCatalogService,
    MicrophoneProfilesService,
    ObsidianService,
    SystemDiagnosticsService,
    SystemIntegrationService,
)
from src.domain.audio import microphone_menu_title  # noqa: F401
from src.domain.constants import Config
from src.domain.hotkeys import (  # noqa: F401
    MODIFIER_DISPLAY_ORDER,
    format_hotkey_status,
    hotkey_name_matches,
    is_modifier_only_combination,
    normalize_key_combination,
    normalize_key_name,
)
from src.domain.types import (  # noqa: F401
    AppPreferences,
    LaunchConfig,
    PreprocessedAudio,
    RecordedAudio,
    TranscriberPreferences,
)
from src.infrastructure.asr_runtime import run_asr_transcription
from src.infrastructure.audio_preprocessing import preprocess_recorded_audio, resample_to_16k  # noqa: F401
from src.infrastructure.audio_runtime import Recorder, list_input_devices
from src.infrastructure.clipboard_reader import PasteboardReader
from src.infrastructure.hotkeys import (
    MODIFIER_FLAG_MASKS,  # noqa: F401
    MODIFIER_KEYCODES_MAP,  # noqa: F401
    GlobalKeyListener,  # noqa: F401
    HotkeyDispatcher,
    MultiHotkeyListener,  # noqa: F401
    _event_key_name_static,  # noqa: F401
    parse_key_combination,  # noqa: F401
)
from src.infrastructure.llm_runtime import (
    LlmGateway as LLMProcessor,
)
from src.infrastructure.llm_runtime import (
    cleanup_llm_runtime_memory,
    ensure_llm_model_downloaded,
    generate_llm_text,
    generate_vlm_text,
    is_llm_model_cached,
    load_llm_runtime_objects,
    load_vlm_runtime_objects,
)
from src.infrastructure.obsidian import (
    get_default_vault_path,
    search_obsidian_notes,
    write_obsidian_note,
)
from src.infrastructure.permissions import (
    frontmost_application_info,
    get_accessibility_status,
    get_input_monitoring_status,
    is_accessibility_trusted,
    notify_user,
    open_path,
    permission_label,  # noqa: F401
    permission_preflight_status,  # noqa: F401
    register_application_activation_observer,
    register_system_event_observer,
    request_accessibility_permission,
    request_input_monitoring_permission,
    warn_missing_accessibility_permission,
    warn_missing_input_monitoring_permission,
)
from src.infrastructure.persistence.defaults import Defaults
from src.infrastructure.persistence.diagnostics import DiagnosticsStore, setup_logging
from src.infrastructure.persistence.history import load_history_items, save_history_records
from src.infrastructure.persistence.journal_db import JournalDb
from src.infrastructure.persistence.microphone_profiles import _load_microphone_profiles, _save_microphone_profiles
from src.infrastructure.power import MacOSDisplaySleepAssertion
from src.infrastructure.system_diagnostics import capture_system_diagnostics
from src.infrastructure.text_input import (
    copy_to_clipboard,
    insert_text_via_ax,
    read_clipboard,
    send_cmd_v,
    type_text_via_cgevent,
)
from src.infrastructure.tts_macos import MacOSTTSController
from src.infrastructure.tts_mlx import MlxStreamingTTSController
from src.infrastructure.tts_router import ReaderTTSRouter
from src.use_cases.transcription import TranscriptionUseCases as SpeechTranscriber

defaults = Defaults()

LOGGER = logging.getLogger(__name__)


def _cli_option_was_provided(*option_names: str) -> bool:
    """Проверяет, был ли аргумент командной строки передан явно."""
    argv = sys.argv[1:]
    return any(option_name in argv for option_name in option_names)


def _create_hotkey_dispatcher(app: Any) -> HotkeyDispatcher:
    """Создаёт единый runtime-dispatcher горячих клавиш."""
    return HotkeyDispatcher(app)


def parse_args() -> LaunchConfig:
    """Разбирает аргументы командной строки.

    Returns:
        Нормализованная конфигурация запуска приложения.

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
    cli_overrides = {
        option_name
        for option_names in (
            ("-m", "--model"),
            ("-k", "--key_combination"),
            ("--secondary_key_combination",),
            ("-l", "--language"),
            ("-t", "--max_time"),
            ("--llm_key_combination",),
            ("--llm_model",),
        )
        if _cli_option_was_provided(*option_names)
        for option_name in option_names
    }

    try:
        return LaunchConfig.from_sources(
            model=args.model,
            language=args.language,
            max_time=args.max_time,
            llm_model=args.llm_model,
            key_combination=args.key_combination,
            secondary_key_combination=args.secondary_key_combination,
            llm_key_combination=args.llm_key_combination,
            settings_store=defaults,
            cli_overrides=cli_overrides,
        )
    except ValueError as error:
        parser.error(str(error))
        raise AssertionError("parser.error() должен завершить выполнение") from error


def _log_startup_configuration(args: LaunchConfig) -> None:
    """Пишет в лог итоговую конфигурацию запуска приложения."""
    LOGGER.info("Запуск с моделью: %s", args.model)
    LOGGER.info("Основной хоткей: %s", args.key_combination)
    if args.secondary_key_combination:
        LOGGER.info("Дополнительный хоткей: %s", args.secondary_key_combination)
    if args.llm_key_combination:
        LOGGER.info("LLM-хоткей: %s", args.llm_key_combination)
    LOGGER.info("Reader RSVP/TTS хоткеи читаются из NSUserDefaults с безопасными дефолтами")


def main() -> None:
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

    app_preferences = AppPreferences.from_store(defaults)
    transcriber_preferences = TranscriberPreferences.from_store(defaults)

    journal_db = JournalDb()

    transcriber = SpeechTranscriber(
        args.model,
        settings_store=defaults,
        preferences=transcriber_preferences,
        diagnostics_store=DiagnosticsStore(
            recording_artifact_cleanup_enabled=transcriber_preferences.audio_artifact_cleanup_enabled,
        ),
        audio_preprocessor=preprocess_recorded_audio,
        transcription_runner=run_asr_transcription,
        type_text_via_cgevent=lambda text: type_text_via_cgevent(text, frontmost_app_info=frontmost_application_info),
        insert_text_via_ax=insert_text_via_ax,
        send_cmd_v=lambda: send_cmd_v(frontmost_app_info=frontmost_application_info),
        clipboard_reader=read_clipboard,
        clipboard_writer=copy_to_clipboard,
        history_item_loader=load_history_items,
        history_record_saver=save_history_records,
        notify_user=notify_user,
        is_accessibility_trusted=is_accessibility_trusted,
        get_input_monitoring_status=get_input_monitoring_status,
        request_accessibility_permission=request_accessibility_permission,
        request_input_monitoring_permission=request_input_monitoring_permission,
        warn_missing_accessibility_permission=warn_missing_accessibility_permission,
        warn_missing_input_monitoring_permission=warn_missing_input_monitoring_permission,
        frontmost_application_info=frontmost_application_info,
        journal_writer=journal_db.record_event,
    )
    recorder = Recorder()
    llm_processor = LLMProcessor(
        args.llm_model,
        runtime_loader=load_llm_runtime_objects,
        generation_runner=generate_llm_text,
        model_cache_checker=is_llm_model_cached,
        model_downloader=ensure_llm_model_downloaded,
        memory_cleanup=cleanup_llm_runtime_memory,
        vlm_runtime_loader=load_vlm_runtime_objects,
        vlm_generation_runner=generate_vlm_text,
    )

    obsidian_vault_path = defaults.load_str(Config.DEFAULTS_KEY_OBSIDIAN_VAULT, fallback=None) or str(get_default_vault_path())
    obsidian_service = ObsidianService(
        write_note=lambda content: write_obsidian_note(obsidian_vault_path, content),
        search_notes=lambda query: search_obsidian_notes(obsidian_vault_path, query),
    )
    clipboard_service = ClipboardService(
        read_text=read_clipboard,
        write_text=copy_to_clipboard,
    )
    microphone_profiles_service = MicrophoneProfilesService(
        load_profiles=_load_microphone_profiles,
        save_profiles=_save_microphone_profiles,
    )
    system_integration_service = SystemIntegrationService(
        notify=notify_user,
        get_accessibility_status=get_accessibility_status,
        get_input_monitoring_status=get_input_monitoring_status,
        request_accessibility_permission=request_accessibility_permission,
        request_input_monitoring_permission=request_input_monitoring_permission,
        warn_missing_accessibility_permission=warn_missing_accessibility_permission,
        warn_missing_input_monitoring_permission=warn_missing_input_monitoring_permission,
        open_path=open_path,
    )
    display_sleep_assertion = MacOSDisplaySleepAssertion()
    display_sleep_prevention_service = DisplaySleepPreventionService(
        acquire=display_sleep_assertion.acquire,
        release=display_sleep_assertion.release,
    )
    system_diagnostics_service = SystemDiagnosticsService(capture=capture_system_diagnostics)
    input_device_catalog = InputDeviceCatalogService(list_input_devices=list_input_devices)
    hotkey_capture_service = HotkeyCaptureService(capture_combination=capture_hotkey_combination)
    hotkey_listener_factory = HotkeyListenerFactoryService(
        create_listener=_create_hotkey_dispatcher,
    )
    recording_overlay = RecordingOverlay()
    reader_clipboard = PasteboardReader()
    rsvp_display = RSVPOverlay()
    tts_speaker = ReaderTTSRouter(
        apple_speaker=MacOSTTSController(),
        mlx_speaker=MlxStreamingTTSController(),
    )

    app_controller = DictationApp(
        recorder,
        transcriber,
        llm_processor,
        args,
        app_preferences,
        clipboard_service=clipboard_service,
        microphone_profiles_service=microphone_profiles_service,
        obsidian_service=obsidian_service,
        system_integration_service=system_integration_service,
        display_sleep_prevention_service=display_sleep_prevention_service,
        system_diagnostics_service=system_diagnostics_service,
        input_device_catalog=input_device_catalog,
        hotkey_capture_service=hotkey_capture_service,
        hotkey_listener_factory=hotkey_listener_factory,
        recording_overlay=recording_overlay,
        reader_clipboard=reader_clipboard,
        rsvp_display=rsvp_display,
        tts_speaker=tts_speaker,
        settings_store=defaults,
    )
    app = StatusBarApp(cast("Any", app_controller))
    key_listener = hotkey_listener_factory.create_listener(app_controller)
    key_listener.start()
    app_controller.key_listener = key_listener
    app_controller.system_event_observer = register_system_event_observer(app_controller.handle_system_power_event)
    app_controller.wake_observer = app_controller.system_event_observer
    app_controller.application_activation_observer = register_application_activation_observer(
        transcriber.handle_frontmost_application_change
    )

    _log_startup_configuration(args)
    app.run()


if __name__ == "__main__":
    main()
