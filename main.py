"""Приложение офлайн-диктовки для macOS на базе MLX Whisper.

Точка входа приложения: парсинг аргументов командной строки,
запуск menu bar приложения и глобальных обработчиков клавиш.
"""

import argparse
import logging
import os
import platform
import signal
import sys
import threading
from typing import Any, cast

import Quartz  # noqa: F401
import rumps
from src.adapters.hotkey_dialog import capture_hotkey_combination
from src.adapters.overlay import RecordingOverlay
from src.adapters.rsvp_overlay import RSVPOverlay
from src.adapters.ui import StatusBarApp
from src.adapters.zipper_windows import ZipperTextOutput, ZipperVoiceOutput
from src.app import (  # noqa: F401
    AppSnapshot,
    ClipboardService,
    DictationApp,
    DisplaySleepPreventionService,
    HotkeyCaptureService,
    HotkeyListenerFactoryService,
    InputDeviceCatalogService,
    MicrophoneProfilesService,
    ModelDownloadService,
    ObsidianService,
    SystemDiagnosticsService,
    SystemIntegrationService,
    ZipperAgentService,
    ZipperConfigProviderService,
    ZipperMemoryStoreService,
    ZipperTextOutputService,
    ZipperVoiceOutputService,
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
from src.domain.reader_types import TTSConfig
from src.domain.types import (  # noqa: F401
    AppPreferences,
    LaunchConfig,
    PreprocessedAudio,
    RecordedAudio,
    TranscriberPreferences,
)
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
    generate_llm_text,
    generate_vlm_text,
)
from src.infrastructure.model_manager import ModelManager
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
from src.infrastructure.zipper_config import ZipperConfigProvider
from src.infrastructure.zipper_runtime import (
    FileZipperMemoryStore,
    LangChainZipperAgent,
)
from src.use_cases.transcription import TranscriptionUseCases as SpeechTranscriber

defaults = Defaults()

LOGGER = logging.getLogger(__name__)
CLI_FORCE_EXIT_DELAY_SECONDS = 2.0


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
        "--zipper_key_combination",
        type=str,
        default="ctrl+shift+alt+z",
        help=(
            "Комбинация клавиш для голосового агента Zipper: "
            "голос → Whisper → локальный агентский runtime. "
            "По умолчанию: ctrl+shift+alt+z. Укажите пустую строку, чтобы отключить."
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
            ("--zipper_key_combination",),
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
            zipper_key_combination=args.zipper_key_combination,
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
    if args.zipper_key_combination:
        LOGGER.info("Zipper-хоткей: %s", args.zipper_key_combination)
    LOGGER.info("Reader RSVP/TTS хоткеи читаются из NSUserDefaults с безопасными дефолтами")


def _safe_shutdown_call(label: str, callback: Any) -> None:
    """Выполняет шаг остановки приложения, не срывая общий shutdown."""
    if not callable(callback):
        return
    try:
        callback()
    except Exception:
        LOGGER.exception("⚠️ Ошибка при завершении: %s", label)


def _stop_runtime_for_cli_shutdown(
    *,
    app_controller: DictationApp,
    key_listener: Any,
    tts_speaker: Any,
    rsvp_display: Any,
    display_sleep_prevention_service: DisplaySleepPreventionService,
) -> None:
    """Останавливает runtime-ресурсы перед выходом из CLI."""
    _safe_shutdown_call("отмена активной записи", app_controller.cancel_recording)
    _safe_shutdown_call("остановка hotkey-listener", getattr(key_listener, "stop", None))
    _safe_shutdown_call("остановка TTS", getattr(tts_speaker, "stop", None))
    _safe_shutdown_call("закрытие RSVP", getattr(rsvp_display, "close", None))
    _safe_shutdown_call("скрытие overlay записи", getattr(app_controller.recording_overlay, "hide", None))
    _safe_shutdown_call("отпускание защиты дисплея", display_sleep_prevention_service.release)


def _install_cli_signal_wait_thread(
    handler: Any,
    *,
    signals: tuple[int, ...] = (signal.SIGINT, signal.SIGTERM),
    pthread_sigmask: Any = signal.pthread_sigmask,
    sigwait: Any = signal.sigwait,
    stdin_isatty: Any = None,
) -> Any | None:
    """Обрабатывает CLI-сигналы из отдельного потока, не полагаясь на Cocoa run loop."""
    isatty = stdin_isatty or sys.stdin.isatty
    if not isatty():
        return None

    watched_signals = tuple(int(signum) for signum in signals)
    try:
        previous_mask = pthread_sigmask(signal.SIG_BLOCK, watched_signals)
    except (AttributeError, OSError, ValueError):
        LOGGER.exception("⚠️ Не удалось включить sigwait для CLI-сигналов")
        return None

    active = True

    def wait_for_signals() -> None:
        while active:
            try:
                signum = int(sigwait(watched_signals))
            except OSError:
                break
            if signum in watched_signals:
                handler(signum, None)

    thread = threading.Thread(target=wait_for_signals, name="cli-signal-wait", daemon=True)
    thread.start()

    def cleanup() -> None:
        nonlocal active
        active = False
        try:
            pthread_sigmask(signal.SIG_SETMASK, previous_mask)
        except (OSError, ValueError):
            LOGGER.exception("⚠️ Не удалось восстановить mask CLI-сигналов")

    return cleanup


def _build_cli_shutdown_handler(
    *,
    app_controller: DictationApp,
    key_listener: Any,
    tts_speaker: Any,
    rsvp_display: Any,
    display_sleep_prevention_service: DisplaySleepPreventionService,
    quit_application: Any = None,
    force_exit: Any = os._exit,
    timer_factory: Any = threading.Timer,
) -> Any:
    """Создаёт обработчик SIGINT/SIGTERM для запуска из терминала."""
    shutdown_requested = False
    quit_app = quit_application or rumps.quit_application

    def handler(signum: int, _frame: Any = None) -> None:
        nonlocal shutdown_requested
        exit_code = 128 + int(signum)
        if shutdown_requested:
            LOGGER.warning("🛑 Получен повторный сигнал завершения, выхожу принудительно: signal=%s", signum)
            force_exit(exit_code)
            return

        shutdown_requested = True
        LOGGER.info("🛑 Получен сигнал завершения из CLI: signal=%s", signum)
        timer = timer_factory(CLI_FORCE_EXIT_DELAY_SECONDS, lambda: force_exit(exit_code))
        timer.daemon = True
        timer.start()

        _stop_runtime_for_cli_shutdown(
            app_controller=app_controller,
            key_listener=key_listener,
            tts_speaker=tts_speaker,
            rsvp_display=rsvp_display,
            display_sleep_prevention_service=display_sleep_prevention_service,
        )
        _safe_shutdown_call("остановка menu bar приложения", lambda: quit_app(None))

    return handler


def _install_cli_shutdown_handlers(
    *,
    app_controller: DictationApp,
    key_listener: Any,
    tts_speaker: Any,
    rsvp_display: Any,
    display_sleep_prevention_service: DisplaySleepPreventionService,
) -> None:
    """Регистрирует Ctrl-C/Ctrl-Term shutdown для запуска приложения из CLI."""
    handler = _build_cli_shutdown_handler(
        app_controller=app_controller,
        key_listener=key_listener,
        tts_speaker=tts_speaker,
        rsvp_display=rsvp_display,
        display_sleep_prevention_service=display_sleep_prevention_service,
    )
    signal_wait_cleanup = _install_cli_signal_wait_thread(handler)
    standard_handler = (lambda _signum, _frame: None) if signal_wait_cleanup is not None else handler
    signal.signal(signal.SIGINT, standard_handler)
    signal.signal(signal.SIGTERM, standard_handler)

    def install_mach_signal_handlers() -> None:
        try:
            from PyObjCTools import MachSignals  # type: ignore[import-untyped]  # noqa: PLC0415

            def shutdown_mach_handler(signum: int) -> None:
                handler(signum, None)

            MachSignals.signal(signal.SIGINT, shutdown_mach_handler)
            MachSignals.signal(signal.SIGTERM, shutdown_mach_handler)
        except Exception:
            LOGGER.exception("⚠️ Не удалось зарегистрировать Mach signal handlers для CLI")

    def cleanup_before_quit(*_args: Any, **_kwargs: Any) -> None:
        _stop_runtime_for_cli_shutdown(
            app_controller=app_controller,
            key_listener=key_listener,
            tts_speaker=tts_speaker,
            rsvp_display=rsvp_display,
            display_sleep_prevention_service=display_sleep_prevention_service,
        )
        if callable(signal_wait_cleanup):
            signal_wait_cleanup()

    rumps.events.before_start.register(install_mach_signal_handlers)
    rumps.events.before_quit.register(cleanup_before_quit)


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
    model_manager = ModelManager()

    transcriber = SpeechTranscriber(
        args.model,
        settings_store=defaults,
        preferences=transcriber_preferences,
        diagnostics_store=DiagnosticsStore(
            recording_artifact_cleanup_enabled=transcriber_preferences.audio_artifact_cleanup_enabled,
        ),
        audio_preprocessor=preprocess_recorded_audio,
        transcription_runner=model_manager.run_asr_transcription,
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
    )
    recorder = Recorder()

    def make_llm_processor() -> LLMProcessor:
        """Создаёт независимый MLX LLM runtime поверх общего менеджера моделей."""
        return LLMProcessor(
            args.llm_model,
            runtime_loader=model_manager.load_llm_runtime_objects,
            generation_runner=generate_llm_text,
            model_cache_checker=model_manager.is_model_cached,
            model_downloader=lambda model_name, progress_callback, label="LLM-модель": model_manager.ensure_model_downloaded(
                model_name,
                label=label,
                progress_callback=progress_callback,
            ),
            memory_cleanup=cleanup_llm_runtime_memory,
            vlm_runtime_loader=model_manager.load_vlm_runtime_objects,
            vlm_generation_runner=generate_vlm_text,
        )

    llm_processor = make_llm_processor()
    zipper_llm_processor = make_llm_processor()

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
    model_download_service = ModelDownloadService(
        ensure_downloaded=lambda model_name, label: model_manager.ensure_model_downloaded(model_name, label=label),
    )
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
        mlx_speaker=MlxStreamingTTSController(model_loader=model_manager.load_tts_model),
    )
    zipper_config_provider = ZipperConfigProvider(open_path=open_path)
    zipper_memory_store = FileZipperMemoryStore()
    zipper_text_output_adapter = ZipperTextOutput()
    app_controller_holder: dict[str, Any] = {}

    def _zipper_tts_config() -> TTSConfig:
        controller = cast("DictationApp", app_controller_holder["controller"])
        return controller.reader_preferences.tts_config

    zipper_voice_output_adapter = ZipperVoiceOutput(
        tts_speaker,
        config_factory=_zipper_tts_config,
    )
    zipper_agent_runtime = LangChainZipperAgent(
        zipper_llm_processor,
        clipboard_service=clipboard_service,
        text_output=zipper_text_output_adapter,
        voice_output=zipper_voice_output_adapter,
    )

    app_controller = DictationApp(
        recorder,
        transcriber,
        llm_processor,
        args,
        zipper_llm_processor=zipper_llm_processor,
        app_preferences=app_preferences,
        clipboard_service=clipboard_service,
        microphone_profiles_service=microphone_profiles_service,
        obsidian_service=obsidian_service,
        system_integration_service=system_integration_service,
        display_sleep_prevention_service=display_sleep_prevention_service,
        system_diagnostics_service=system_diagnostics_service,
        model_download_service=model_download_service,
        input_device_catalog=input_device_catalog,
        hotkey_capture_service=hotkey_capture_service,
        hotkey_listener_factory=hotkey_listener_factory,
        recording_overlay=recording_overlay,
        reader_clipboard=reader_clipboard,
        rsvp_display=rsvp_display,
        tts_speaker=tts_speaker,
        settings_store=defaults,
        zipper_config_provider=ZipperConfigProviderService(
            load_config=zipper_config_provider.load_config,
            config_path=zipper_config_provider.config_path,
            open_config=zipper_config_provider.open_config,
        ),
        zipper_memory_store=ZipperMemoryStoreService(
            load=zipper_memory_store.load,
            save=zipper_memory_store.save,
        ),
        zipper_agent_service=ZipperAgentService(
            invoke=zipper_agent_runtime.invoke,
            summarize_memory=zipper_agent_runtime.summarize_memory,
        ),
        zipper_text_output=ZipperTextOutputService(
            show_text=zipper_text_output_adapter.show_text,
            confirm=zipper_text_output_adapter.confirm,
            set_debug_visible=zipper_text_output_adapter.set_debug_visible,
            append_debug_event=zipper_text_output_adapter.append_debug_event,
            debug_events=zipper_text_output_adapter.debug_events,
        ),
        zipper_voice_output=ZipperVoiceOutputService(speak=zipper_voice_output_adapter.speak),
    )
    model_manager.set_progress_callback(app_controller.handle_model_download_progress)
    app_controller_holder["controller"] = app_controller
    app = StatusBarApp(cast("Any", app_controller))
    key_listener = hotkey_listener_factory.create_listener(app_controller)
    app_controller.key_listener = key_listener
    _install_cli_shutdown_handlers(
        app_controller=app_controller,
        key_listener=key_listener,
        tts_speaker=tts_speaker,
        rsvp_display=rsvp_display,
        display_sleep_prevention_service=display_sleep_prevention_service,
    )
    key_listener.start()
    app_controller.system_event_observer = register_system_event_observer(app_controller.handle_system_power_event)
    app_controller.wake_observer = app_controller.system_event_observer
    app_controller.application_activation_observer = register_application_activation_observer(
        transcriber.handle_frontmost_application_change
    )

    _log_startup_configuration(args)
    app.run()


if __name__ == "__main__":
    main()
