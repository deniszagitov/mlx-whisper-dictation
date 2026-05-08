"""Orchestration-слой приложения Dictator.

Содержит DictationApp — объект приложения без UI-меню. Он хранит
runtime-state, управляет записью и LLM-сценарием, синхронизирует
настройки и уведомляет подписчиков о смене состояния через snapshot.
"""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from .domain.audio import (
    audio_profile_for_input_device,
    input_device_name_matches,
    normalize_input_device_name,
    resolve_input_device,
)
from .domain.audio import (
    microphone_menu_title as format_microphone_menu_title,
)
from .domain.constants import Config
from .domain.model_downloads import ModelDownloadProgress, ModelRequiredError, format_model_download_title
from .domain.reader_constants import DEFAULT_TTS_ENGINE, DEFAULT_TTS_RATE_MULTIPLIER
from .domain.reader_types import (
    ClipboardContent,
    ReaderClipboardPort,
    ReaderPreferences,
    RSVPConfig,
    RSVPDisplayPort,
    RSVPFrame,
    TTSConfig,
    TTSPort,
    TTSVoice,
)
from .domain.types import AppPreferences, AppSnapshot, LaunchConfig, MicrophoneProfile
from .domain.zipper import ZipperAgentResult, ZipperConfig, ZipperMemorySnapshot
from .use_cases.hotkey_management import HotkeyManagementUseCases
from .use_cases.llm_pipeline import LlmPipelineUseCases
from .use_cases.microphone_profiles import MicrophoneProfilesUseCases
from .use_cases.play_rsvp import PlayRSVPUseCase
from .use_cases.play_tts import PlayTTSUseCase
from .use_cases.preprocess_text import PreprocessTextUseCase
from .use_cases.recording import RecordingUseCases
from .use_cases.settings import SettingsUseCases
from .use_cases.zipper import ZipperUseCases

if TYPE_CHECKING:
    from collections.abc import Callable

    from .domain.ports import LlmGatewayProtocol, RecorderProtocol, SettingsStoreProtocol
    from .domain.types import AudioDeviceInfo
    from .use_cases.transcription import TranscriptionUseCases

LOGGER = logging.getLogger(__name__)
READER_SHUTDOWN_JOIN_TIMEOUT_SECONDS = 3.0


@dataclass(frozen=True, slots=True)
class ClipboardService:
    """Concrete bundle для чтения и записи системного буфера обмена."""

    read_text: Callable[[], str | None]
    write_text: Callable[[str], None]


@dataclass(frozen=True, slots=True)
class MicrophoneProfilesService:
    """Concrete bundle для persistence быстрых профилей микрофона."""

    load_profiles: Callable[[], list[MicrophoneProfile]]
    save_profiles: Callable[[list[MicrophoneProfile]], None]


@dataclass(frozen=True, slots=True)
class ObsidianService:
    """Concrete bundle для чтения и записи заметок в Obsidian vault."""

    write_note: Callable[[str], Any]
    search_notes: Callable[[str], str]


@dataclass(frozen=True, slots=True)
class SystemIntegrationService:
    """Concrete bundle для уведомлений и статусов системных разрешений."""

    notify: Callable[[str, str], None]
    get_accessibility_status: Callable[[], bool | None]
    get_input_monitoring_status: Callable[[], bool | None]
    request_accessibility_permission: Callable[[], bool]
    request_input_monitoring_permission: Callable[[], bool | None]
    warn_missing_accessibility_permission: Callable[[], None]
    warn_missing_input_monitoring_permission: Callable[[], None]
    open_path: Callable[[str], bool]


@dataclass(frozen=True, slots=True)
class DisplaySleepPreventionService:
    """Concrete bundle для временного запрета сна дисплея."""

    acquire: Callable[[], bool]
    release: Callable[[], None]


@dataclass(frozen=True, slots=True)
class SystemDiagnosticsService:
    """Concrete bundle для расширенной диагностики macOS runtime."""

    capture: Callable[[str], None]


@dataclass(frozen=True, slots=True)
class ModelDownloadService:
    """Concrete bundle единой загрузки локальных моделей."""

    ensure_downloaded: Callable[[str, str], None]


@dataclass(frozen=True, slots=True)
class ModelRuntimeControlService:
    """Concrete bundle управления загруженными runtime-моделями."""

    release_model: Callable[[str], None]
    preload_asr_model: Callable[[str], None]
    preload_llm_model: Callable[[str], None]
    preload_tts_model: Callable[[str], None]
    shutdown: Callable[[], None]


@dataclass(frozen=True, slots=True)
class InputDeviceCatalogService:
    """Concrete bundle для перечисления доступных устройств ввода."""

    list_input_devices: Callable[[], list[AudioDeviceInfo]]


@dataclass(frozen=True, slots=True)
class HotkeyCaptureService:
    """Concrete bundle для UI-захвата новой комбинации клавиш."""

    capture_combination: Callable[[str, str, str], str | None]


@dataclass(frozen=True, slots=True)
class HotkeyListenerFactoryService:
    """Concrete bundle для создания runtime-dispatcher'а хоткеев."""

    create_listener: Callable[[Any], Any]


@dataclass(frozen=True, slots=True)
class ZipperConfigProviderService:
    """Concrete bundle для чтения и открытия конфига Zipper."""

    load_config: Callable[[], ZipperConfig]
    config_path: Callable[[], str]
    open_config: Callable[[], bool]


@dataclass(frozen=True, slots=True)
class ZipperMemoryStoreService:
    """Concrete bundle persistence контекста и памяти Zipper."""

    load: Callable[[], ZipperMemorySnapshot]
    save: Callable[[ZipperMemorySnapshot], None]


@dataclass(frozen=True, slots=True)
class ZipperAgentService:
    """Concrete bundle агентского runtime Zipper."""

    invoke: Callable[..., ZipperAgentResult]
    summarize_memory: Callable[..., str]


@dataclass(frozen=True, slots=True)
class ZipperTextOutputService:
    """Concrete bundle текстового вывода и debug-панели Zipper."""

    show_text: Callable[[str, str], None]
    confirm: Callable[[str, str], bool]
    set_debug_visible: Callable[[bool], None]
    append_debug_event: Callable[[Any], None]
    debug_events: Callable[[], list[Any]]


@dataclass(frozen=True, slots=True)
class ZipperVoiceOutputService:
    """Concrete bundle голосового вывода Zipper."""

    speak: Callable[[str], None]


class _NullRecordingOverlay:
    """Null-object для сценариев без подключённого overlay-адаптера."""

    def show(self) -> None:
        """Игнорирует показ overlay."""
        return None

    def hide(self) -> None:
        """Игнорирует скрытие overlay."""
        return None

    def update_time(self, _elapsed_seconds: int) -> None:
        """Игнорирует обновление таймера overlay."""
        return None


def _null_system_notify(_title: str, _message: str) -> None:
    """Игнорирует системные уведомления в сценариях без integration-сервиса."""
    return None


def _null_bool_permission_request() -> bool:
    """Возвращает отрицательный результат для request-функций по умолчанию."""
    return False


def _null_optional_permission_request() -> bool | None:
    """Возвращает unknown-результат для request-функций по умолчанию."""
    return None


def _null_permission_status() -> bool | None:
    """Возвращает неизвестный статус системного разрешения."""
    return None


def _null_permission_warning() -> None:
    """Игнорирует предупреждение о недостающих разрешениях."""
    return None


def _null_open_path(_path: str) -> bool:
    """Возвращает отрицательный результат открытия пути без integration-сервиса."""
    return False


def _null_display_sleep_prevention_acquire() -> bool:
    """Не создаёт power assertion в сценариях без macOS integration-сервиса."""
    return False


def _null_display_sleep_prevention_release() -> None:
    """Игнорирует отпускание power assertion в headless-сценариях."""
    return None


def _null_system_diagnostics_capture(_label: str) -> None:
    """Игнорирует сбор системной диагностики в headless-сценариях."""
    return None


def _null_model_download(_model_name: str, _label: str) -> None:
    """Игнорирует загрузку модели в headless-сценариях."""
    return None


def _null_release_runtime_model(_model_name: str) -> None:
    """Игнорирует выгрузку runtime-модели в headless-сценариях."""
    return None


def _null_preload_runtime_model(_model_name: str) -> None:
    """Игнорирует прогрев runtime-модели в headless-сценариях."""
    return None


def _null_shutdown_runtime_models() -> None:
    """Игнорирует очистку runtime-cache моделей в headless-сценариях."""
    return None


def _empty_input_devices() -> list[AudioDeviceInfo]:
    """Возвращает пустой список устройств ввода по умолчанию."""
    return []


def _create_null_hotkey_listener(_app: Any) -> _NullHotkeyListener:
    """Создаёт no-op dispatcher горячих клавиш по умолчанию."""
    return _NullHotkeyListener()


def _noop_capture_combination(_title: str, _message: str, _current_combination: str = "") -> str | None:
    """Возвращает отсутствие новой комбинации клавиш по умолчанию."""
    return None


def _null_zipper_config() -> ZipperConfig:
    """Возвращает выключенный конфиг Zipper по умолчанию."""
    return ZipperConfig(enabled=False)


def _null_config_path() -> str:
    """Возвращает пустой путь конфига Zipper для headless-сценариев."""
    return ""


def _null_open_config() -> bool:
    """Не открывает конфиг Zipper в headless-сценариях."""
    return False


def _null_load_zipper_memory() -> ZipperMemorySnapshot:
    """Возвращает пустую память Zipper."""
    return ZipperMemorySnapshot(memory="", events=())


def _null_save_zipper_memory(_snapshot: ZipperMemorySnapshot) -> None:
    """Игнорирует сохранение памяти Zipper."""
    return None


def _null_zipper_agent_invoke(*_args: Any, **_kwargs: Any) -> ZipperAgentResult:
    """Возвращает ответ для отключённого агентского runtime Zipper."""
    return ZipperAgentResult(text="Zipper не настроен.", output_mode="window")


def _null_zipper_memory_summary(*_args: Any, **_kwargs: Any) -> str:
    """Возвращает пустую суммаризацию Zipper без агентского runtime."""
    return ""


def _null_show_zipper_text(_title: str, _text: str) -> None:
    """Игнорирует текстовый вывод Zipper."""
    return None


def _null_confirm_zipper(_title: str, _message: str) -> bool:
    """Отклоняет подтверждение Zipper по умолчанию."""
    return False


def _null_zipper_debug_visible(_visible: bool) -> None:
    """Игнорирует debug-панель Zipper."""
    return None


def _null_zipper_event(_event: Any) -> None:
    """Игнорирует событие Zipper."""
    return None


def _null_zipper_debug_events() -> list[Any]:
    """Возвращает пустой поток debug-событий."""
    return []


def _null_zipper_speak(_text: str) -> None:
    """Игнорирует голосовой вывод Zipper."""
    return None


class _NullHotkeyListener:
    """Null-object для runtime-dispatcher'а горячих клавиш."""

    def start(self) -> None:
        """Игнорирует запуск listener'а."""
        return None

    def stop(self) -> None:
        """Игнорирует остановку listener'а."""
        return None

    def update_hotkeys(self, _primary: str, _secondary: str, _llm: str, _rsvp: str = "", _tts: str = "", _zipper: str = "") -> None:
        """Игнорирует обновление набора горячих клавиш."""
        return None


class _NullReaderClipboard:
    """Null-object read-only буфера обмена для reader-сценариев."""

    def read_content(self) -> ClipboardContent:
        """Возвращает отсутствие текстового содержимого."""
        return ClipboardContent(text=None, has_text_type=False)


class _NullRSVPDisplay:
    """Null-object RSVP overlay для headless-сценариев."""

    def show_frames(self, _frames: list[RSVPFrame], _config: RSVPConfig) -> None:
        """Игнорирует показ RSVP."""
        return None

    def close(self) -> None:
        """Игнорирует закрытие RSVP."""
        return None

    def is_running(self) -> bool:
        """Сообщает, что RSVP overlay не активен."""
        return False

    def handle_key(self, _key_name: str) -> bool:
        """Не обрабатывает клавиатуру."""
        return False


class _NullTTS:
    """Null-object TTS speaker для headless-сценариев."""

    def speak(self, _text: str, _config: TTSConfig) -> None:
        """Игнорирует запуск озвучивания."""
        return None

    def stop(self) -> None:
        """Игнорирует остановку озвучивания."""
        return None

    def is_speaking(self) -> bool:
        """Сообщает, что TTS не воспроизводится."""
        return False

    def available_voices(self) -> list[TTSVoice]:
        """Возвращает пустой список голосов."""
        return []

    def set_keep_model_loaded(self, _enabled: bool) -> None:
        """Игнорирует режим удержания MLX TTS-модели."""
        return None


class _InMemorySettingsStore:
    """Простейшее in-memory хранилище настроек для headless и тестовых сценариев."""

    def __init__(self) -> None:
        self._values: dict[str, object] = {}

    def load_bool(self, key: str, fallback: bool) -> bool:
        """Читает bool-значение или fallback."""
        value = self._values.get(key, fallback)
        return bool(value)

    def contains_key(self, key: str) -> bool:
        """Проверяет наличие ключа в in-memory хранилище."""
        return key in self._values

    def save_bool(self, key: str, value: bool) -> None:
        """Сохраняет bool-значение."""
        self._values[key] = bool(value)

    def load_list(self, key: str) -> list[str]:
        """Читает список строк."""
        value = self._values.get(key, [])
        return list(value) if isinstance(value, list) else []

    def save_list(self, key: str, value: list[str]) -> None:
        """Сохраняет список строк."""
        self._values[key] = list(value)

    def load_int(self, key: str, fallback: int) -> int:
        """Читает целое число или fallback."""
        value = self._values.get(key, fallback)
        return value if isinstance(value, int) else fallback

    def save_int(self, key: str, value: int) -> None:
        """Сохраняет целое число."""
        self._values[key] = int(value)

    def load_str(self, key: str, fallback: str | None = None) -> str | None:
        """Читает строковое значение или fallback."""
        value = self._values.get(key, fallback)
        if value is None:
            return None
        return str(value)

    def save_str(self, key: str, value: object) -> None:
        """Сохраняет строковое значение."""
        self._values[key] = value

    def load_max_time(self, fallback: int | float | None) -> int | float | None:
        """Читает лимит записи или fallback."""
        return self._values.get(Config.DEFAULTS_KEY_MAX_TIME, fallback)  # type: ignore[return-value]

    def save_max_time(self, value: int | float | None) -> None:
        """Сохраняет лимит записи."""
        self._values[Config.DEFAULTS_KEY_MAX_TIME] = value

    def load_input_device_index(self) -> int | None:
        """Читает индекс микрофона."""
        value = self._values.get(Config.DEFAULTS_KEY_INPUT_DEVICE_INDEX)
        return value if isinstance(value, int) else None

    def load_input_device_name(self) -> str | None:
        """Читает имя микрофона."""
        value = self._values.get(Config.DEFAULTS_KEY_INPUT_DEVICE_NAME)
        if value is None:
            return None
        normalized = str(value).strip()
        return normalized or None

    def save_input_device_index(self, value: int | None) -> None:
        """Сохраняет индекс микрофона."""
        self._values[Config.DEFAULTS_KEY_INPUT_DEVICE_INDEX] = value

    def save_input_device_name(self, value: str | None) -> None:
        """Сохраняет имя микрофона."""
        if value is None:
            self._values.pop(Config.DEFAULTS_KEY_INPUT_DEVICE_NAME, None)
            return
        normalized = str(value).strip()
        if not normalized:
            self._values.pop(Config.DEFAULTS_KEY_INPUT_DEVICE_NAME, None)
            return
        self._values[Config.DEFAULTS_KEY_INPUT_DEVICE_NAME] = normalized

    def remove_key(self, key: str) -> None:
        """Удаляет ключ из хранилища."""
        self._values.pop(key, None)


class DictationApp:
    """Основной orchestration-объект приложения диктовки."""

    def __init__(
        self,
        recorder: RecorderProtocol,
        transcriber: TranscriptionUseCases,
        llm_processor: LlmGatewayProtocol | None,
        launch_config: LaunchConfig,
        zipper_llm_processor: LlmGatewayProtocol | None = None,
        app_preferences: AppPreferences | None = None,
        clipboard_service: ClipboardService | None = None,
        microphone_profiles_service: MicrophoneProfilesService | None = None,
        obsidian_service: ObsidianService | None = None,
        system_integration_service: SystemIntegrationService | None = None,
        display_sleep_prevention_service: DisplaySleepPreventionService | None = None,
        system_diagnostics_service: SystemDiagnosticsService | None = None,
        model_download_service: ModelDownloadService | None = None,
        model_runtime_service: ModelRuntimeControlService | None = None,
        input_device_catalog: InputDeviceCatalogService | None = None,
        hotkey_capture_service: HotkeyCaptureService | None = None,
        hotkey_listener_factory: HotkeyListenerFactoryService | None = None,
        recording_overlay: Any | None = None,
        reader_clipboard: ReaderClipboardPort | None = None,
        rsvp_display: RSVPDisplayPort | None = None,
        tts_speaker: TTSPort | None = None,
        settings_store: SettingsStoreProtocol | None = None,
        zipper_config_provider: ZipperConfigProviderService | None = None,
        zipper_memory_store: ZipperMemoryStoreService | None = None,
        zipper_agent_service: ZipperAgentService | None = None,
        zipper_text_output: ZipperTextOutputService | None = None,
        zipper_voice_output: ZipperVoiceOutputService | None = None,
    ) -> None:
        self.settings_store = settings_store or _InMemorySettingsStore()
        self.recorder = recorder
        self.transcriber = transcriber
        self.llm_processor = llm_processor
        self.zipper_llm_processor = zipper_llm_processor or llm_processor
        self.launch_config = launch_config
        self.app_preferences = app_preferences or AppPreferences.from_store(self.settings_store)
        self._migrate_reader_tts_rate_default()
        self._migrate_reader_tts_engine_default()
        self.reader_preferences = ReaderPreferences.from_store(self.settings_store, llm_model=self.launch_config.llm_model)
        self.hotkey_status = self.launch_config.hotkeys.hotkey_status
        self.secondary_hotkey_status = self.launch_config.hotkeys.secondary_hotkey_status
        self.llm_hotkey_status = self.launch_config.hotkeys.llm_hotkey_status
        self.rsvp_hotkey_status = self.reader_preferences.rsvp_hotkey_status
        self.tts_hotkey_status = self.reader_preferences.tts_hotkey_status
        self.zipper_hotkey_status = self.launch_config.hotkeys.zipper_hotkey_status
        self.clipboard_service = clipboard_service or ClipboardService(read_text=lambda: None, write_text=lambda _text: None)
        self.microphone_profiles_service = microphone_profiles_service or MicrophoneProfilesService(
            load_profiles=lambda: [],
            save_profiles=lambda _profiles: None,
        )
        self.obsidian_service = obsidian_service
        self.system_integration_service = system_integration_service or SystemIntegrationService(
            notify=_null_system_notify,
            get_accessibility_status=_null_permission_status,
            get_input_monitoring_status=_null_permission_status,
            request_accessibility_permission=_null_bool_permission_request,
            request_input_monitoring_permission=_null_optional_permission_request,
            warn_missing_accessibility_permission=_null_permission_warning,
            warn_missing_input_monitoring_permission=_null_permission_warning,
            open_path=_null_open_path,
        )
        self.display_sleep_prevention_service = display_sleep_prevention_service or DisplaySleepPreventionService(
            acquire=_null_display_sleep_prevention_acquire,
            release=_null_display_sleep_prevention_release,
        )
        self.system_diagnostics_service = system_diagnostics_service or SystemDiagnosticsService(
            capture=_null_system_diagnostics_capture,
        )
        self.model_download_service = model_download_service or ModelDownloadService(ensure_downloaded=_null_model_download)
        self.model_runtime_service = model_runtime_service or ModelRuntimeControlService(
            release_model=_null_release_runtime_model,
            preload_asr_model=_null_preload_runtime_model,
            preload_llm_model=_null_preload_runtime_model,
            preload_tts_model=_null_preload_runtime_model,
            shutdown=_null_shutdown_runtime_models,
        )
        self.input_device_catalog = input_device_catalog or InputDeviceCatalogService(list_input_devices=_empty_input_devices)
        self.hotkey_capture_service = hotkey_capture_service or HotkeyCaptureService(capture_combination=_noop_capture_combination)
        self.hotkey_listener_factory = hotkey_listener_factory or HotkeyListenerFactoryService(
            create_listener=_create_null_hotkey_listener,
        )
        self.recording_overlay = recording_overlay or _NullRecordingOverlay()
        self.reader_clipboard = reader_clipboard or _NullReaderClipboard()
        self.rsvp_display = rsvp_display or _NullRSVPDisplay()
        self.tts_speaker = tts_speaker or _NullTTS()
        self.zipper_config_provider = zipper_config_provider or ZipperConfigProviderService(
            load_config=_null_zipper_config,
            config_path=_null_config_path,
            open_config=_null_open_config,
        )
        self.zipper_memory_store = zipper_memory_store or ZipperMemoryStoreService(
            load=_null_load_zipper_memory,
            save=_null_save_zipper_memory,
        )
        self.zipper_agent_service = zipper_agent_service or ZipperAgentService(
            invoke=_null_zipper_agent_invoke,
            summarize_memory=_null_zipper_memory_summary,
        )
        self.zipper_text_output = zipper_text_output or ZipperTextOutputService(
            show_text=_null_show_zipper_text,
            confirm=_null_confirm_zipper,
            set_debug_visible=_null_zipper_debug_visible,
            append_debug_event=_null_zipper_event,
            debug_events=_null_zipper_debug_events,
        )
        self.zipper_voice_output = zipper_voice_output or ZipperVoiceOutputService(speak=_null_zipper_speak)

        self.model_options = list(Config.MODEL_PRESETS)
        if self.launch_config.model not in self.model_options:
            self.model_options.insert(0, self.launch_config.model)
        self.llm_model_options = list(Config.LLM_MODEL_PRESETS)
        if self.launch_config.llm_model not in self.llm_model_options:
            self.llm_model_options.insert(0, self.launch_config.llm_model)
        self.llm_model_name = self.launch_config.llm_model.rsplit("/", maxsplit=1)[-1]
        self.max_time_options: list[float | None] = list(Config.MAX_TIME_PRESETS)
        if self.launch_config.max_time not in self.max_time_options:
            self.max_time_options.insert(0, self.launch_config.max_time)

        self.model_name = self.launch_config.model.rsplit("/", maxsplit=1)[-1]
        self.input_devices: list[AudioDeviceInfo] = []
        initial_language = self.languages[0] if self.languages is not None else None
        if self.languages is not None and self.app_preferences.selected_language in self.languages:
            initial_language = self.app_preferences.selected_language
        self.current_language = initial_language
        self.current_input_device: AudioDeviceInfo | None = None
        self.refresh_input_devices(publish_snapshot=False)

        self.state = Config.STATUS_IDLE
        self.permission_status = {
            "accessibility": self.system_integration_service.get_accessibility_status(),
            "input_monitoring": self.system_integration_service.get_input_monitoring_status(),
            "microphone": None,
        }
        self.max_time = self.launch_config.max_time
        self.microphone_profiles = self.microphone_profiles_service.load_profiles()
        self.llm_prompt_name = self.app_preferences.llm_prompt_name
        self.performance_mode = self.app_preferences.performance_mode
        self.high_quality_mac_builtin_enabled = self.app_preferences.high_quality_mac_builtin_enabled
        self.tts_speaker.set_keep_model_loaded(self.performance_mode == Config.PERFORMANCE_MODE_FAST)
        self.show_recording_notification = self.app_preferences.show_recording_notification
        self.show_recording_overlay = self.app_preferences.show_recording_overlay
        self.show_recording_time_in_menu_bar = self.app_preferences.show_recording_time_in_menu_bar
        self.started = False
        self.zipper_recording_active = False
        self.zipper_enabled = False
        self.zipper_debug_panel_enabled = False
        self.start_time = 0.0
        self.elapsed_time = 0
        self.key_listener: Any = None
        self.wake_observer: Any = None
        self.system_event_observer: Any = None
        self.application_activation_observer: Any = None
        self._llm_downloading = False
        self._model_download_active = False
        self._model_download_title = "📦 Загрузка моделей: нет"
        self._model_memory_loading_count = 0
        self._state_before_model_memory_loading: str | None = None
        self._preferred_input_device_unavailable = False
        self._preferred_input_device_notified = False
        self._display_sleep_prevention_active = False
        self._display_sleep_release_timer: threading.Timer | None = None
        self.display_sleep_release_delay_seconds = Config.DISPLAY_SLEEP_RELEASE_GRACE_SECONDS
        self._reader_worker: threading.Thread | None = None
        self._model_download_worker: threading.Thread | None = None

        llm_cached = self.llm_processor.is_model_cached() if self.llm_processor is not None else False
        self._llm_download_title = "✅ LLM-модель загружена" if llm_cached else "📥 Скачать LLM-модель…"

        self._subscribers: list[Callable[[AppSnapshot], None]] = []
        self.recording_use_cases = RecordingUseCases(
            runtime=self,
            recorder=self.recorder,
            transcriber=self.transcriber,
            system_integration_service=self.system_integration_service,
            recording_overlay=self.recording_overlay,
            publish_snapshot=self._notify_subscribers,
        )
        self.settings_use_cases = SettingsUseCases(
            runtime=self,
            settings_store=self.settings_store,
            recorder=self.recorder,
            transcriber=self.transcriber,
            llm_processor=self.llm_processor,
            zipper_llm_processor=self.zipper_llm_processor,
            system_integration_service=self.system_integration_service,
            publish_snapshot=self._notify_subscribers,
        )
        self.microphone_profiles_use_cases = MicrophoneProfilesUseCases(
            runtime=self,
            settings_store=self.settings_store,
            recorder=self.recorder,
            transcriber=self.transcriber,
            microphone_profiles_service=self.microphone_profiles_service,
            system_integration_service=self.system_integration_service,
            change_performance_mode=self.settings_use_cases.change_performance_mode,
            publish_snapshot=self._notify_subscribers,
        )
        self.llm_pipeline_use_cases = LlmPipelineUseCases(
            runtime=self,
            recorder=self.recorder,
            transcriber=self.transcriber,
            llm_processor=self.llm_processor,
            clipboard_service=self.clipboard_service,
            system_integration_service=self.system_integration_service,
            recording_overlay=self.recording_overlay,
            stop_recording=self.stop_recording,
            publish_snapshot=self._notify_subscribers,
            obsidian_service=self.obsidian_service,
        )
        self.reader_preprocess_use_case = PreprocessTextUseCase(self.llm_processor)
        self.play_rsvp_use_case = PlayRSVPUseCase(
            clipboard=self.reader_clipboard,
            preprocessor=self.reader_preprocess_use_case,
            display=self.rsvp_display,
            notify=self.system_integration_service.notify,
        )
        self.play_tts_use_case = PlayTTSUseCase(
            clipboard=self.reader_clipboard,
            preprocessor=self.reader_preprocess_use_case,
            speaker=self.tts_speaker,
            notify=self.system_integration_service.notify,
        )
        self.zipper_use_cases = ZipperUseCases(
            runtime=self,
            recorder=self.recorder,
            transcriber=self.transcriber,
            llm_processor=self.zipper_llm_processor,
            config_provider=self.zipper_config_provider,
            memory_store=self.zipper_memory_store,
            agent_service=self.zipper_agent_service,
            text_output=self.zipper_text_output,
            voice_output=self.zipper_voice_output,
            system_integration_service=self.system_integration_service,
            recording_overlay=self.recording_overlay,
            publish_snapshot=self._notify_subscribers,
        )
        self.zipper_enabled = self.zipper_use_cases.config.enabled
        self.zipper_debug_panel_enabled = self.zipper_use_cases.config.debug.enabled
        self.zipper_text_output.set_debug_visible(self.zipper_debug_panel_enabled)
        LOGGER.info(
            "🧷 Runtime Zipper инициализирован: enabled=%s, debug_panel=%s, status=%s, config_path=%s",
            self.zipper_enabled,
            self.zipper_debug_panel_enabled,
            self.zipper_status,
            self.zipper_config_path,
        )
        self.hotkey_management_use_cases = HotkeyManagementUseCases(
            runtime=self,
            settings_store=self.settings_store,
            system_integration_service=self.system_integration_service,
            capture_hotkey_combination=self.hotkey_capture_service.capture_combination,
            publish_snapshot=self._notify_subscribers,
        )

        if hasattr(self.recorder, "set_performance_mode"):
            self.recorder.set_performance_mode(self.performance_mode)
        if hasattr(self.recorder, "set_high_quality_mac_builtin"):
            self.recorder.set_high_quality_mac_builtin(self.high_quality_mac_builtin_enabled)
        if hasattr(self.recorder, "set_error_callback"):
            self.recorder.set_error_callback(self.system_integration_service.notify)
        if hasattr(self.recorder, "set_runtime_error_callback"):
            self.recorder.set_runtime_error_callback(self.handle_recording_runtime_error)
        if self.llm_processor is not None:
            self.llm_processor.set_performance_mode(self.performance_mode)
            set_memory_loading_callback = getattr(self.llm_processor, "set_model_memory_loading_callback", None)
            if callable(set_memory_loading_callback):
                set_memory_loading_callback(self.handle_model_memory_loading)
        if self.zipper_llm_processor is not None and self.zipper_llm_processor is not self.llm_processor:
            set_memory_loading_callback = getattr(self.zipper_llm_processor, "set_model_memory_loading_callback", None)
            if callable(set_memory_loading_callback):
                set_memory_loading_callback(self.handle_model_memory_loading)
        self.recorder.set_status_callback(self.set_state)
        self.recorder.set_permission_callback(self.set_permission_status)
        self.transcriber.history_callback = self._notify_subscribers
        self.transcriber.token_usage_callback = self._notify_subscribers
        self._refresh_hotkey_statuses()

    def _migrate_reader_tts_rate_default(self) -> None:
        """Одноразово сбрасывает старый дефолт скорости TTS на 1×."""
        if self.settings_store.contains_key(Config.DEFAULTS_KEY_READER_TTS_RATE_DEFAULT_V2):
            return
        self.settings_store.save_str(Config.DEFAULTS_KEY_READER_TTS_RATE_MULTIPLIER, DEFAULT_TTS_RATE_MULTIPLIER)
        self.settings_store.save_bool(Config.DEFAULTS_KEY_READER_TTS_RATE_DEFAULT_V2, True)

    def _migrate_reader_tts_engine_default(self) -> None:
        """Одноразово сбрасывает дефолтный backend TTS на Apple AVSpeech."""
        if self.settings_store.contains_key(Config.DEFAULTS_KEY_READER_TTS_ENGINE_DEFAULT_V2):
            return
        self.settings_store.save_str(Config.DEFAULTS_KEY_READER_TTS_ENGINE, DEFAULT_TTS_ENGINE)
        self.settings_store.save_bool(Config.DEFAULTS_KEY_READER_TTS_ENGINE_DEFAULT_V2, True)

    def _save_input_device_name_preference(self, device_name: str | None) -> None:
        """Сохраняет предпочитаемое имя микрофона в настройках."""
        normalized_name = normalize_input_device_name(device_name)
        if normalized_name is None:
            self.settings_store.remove_key(Config.DEFAULTS_KEY_INPUT_DEVICE_NAME)
            return
        self.settings_store.save_str(Config.DEFAULTS_KEY_INPUT_DEVICE_NAME, normalized_name)

    def _persist_selected_input_device_preference(self, device: AudioDeviceInfo | None) -> None:
        """Сохраняет пользовательское предпочтение по микрофону."""
        preferred_index = None if device is None else int(device["index"])
        preferred_name = None if device is None else str(device.get("name") or "")
        self.app_preferences = self.app_preferences.with_selected_input_device(preferred_index, preferred_name)
        self.settings_store.save_input_device_index(preferred_index)
        self._save_input_device_name_preference(preferred_name)

    def _same_input_device(self, left: AudioDeviceInfo | None, right: AudioDeviceInfo | None) -> bool:
        """Сравнивает устройства по индексу и имени, учитывая переиндексацию после sleep."""
        if left is right:
            return True
        if left is None or right is None:
            return False
        if input_device_name_matches(left.get("name"), right.get("name")):
            return True
        return int(left["index"]) == int(right["index"])

    def _select_runtime_input_device(self, device: AudioDeviceInfo | None) -> None:
        """Применяет текущее активное устройство ввода без смены пользовательского предпочтения."""
        self.current_input_device = device
        self.recorder.set_input_device(device)

    def _resolve_input_device(
        self,
        *,
        preferred_index: int | None = None,
        preferred_name: str | None = None,
        fallback_to_default: bool = True,
        fallback_to_first: bool = True,
    ) -> tuple[AudioDeviceInfo | None, str]:
        """Подбирает устройство на основании текущего каталога и заданных предпочтений."""
        return resolve_input_device(
            self.input_devices,
            preferred_index=preferred_index,
            preferred_name=preferred_name,
            fallback_to_default=fallback_to_default,
            fallback_to_first=fallback_to_first,
        )

    def refresh_input_devices(self, *, publish_snapshot: bool = True, notify: bool = False) -> bool:
        """Обновляет каталог микрофонов и восстанавливает лучший доступный input device."""
        previous_device = self.current_input_device
        try:
            devices = list(self.input_device_catalog.list_input_devices())
        except Exception:
            LOGGER.exception("❌ Не удалось обновить список устройств ввода")
            devices = list(self.input_devices)

        preferred_index = self.app_preferences.selected_input_device_index
        preferred_name = self.app_preferences.selected_input_device_name
        if preferred_index is None and preferred_name is None and previous_device is not None:
            preferred_index = int(previous_device["index"])
            preferred_name = str(previous_device.get("name") or "")

        self.input_devices = devices
        resolved_device, resolution = self._resolve_input_device(
            preferred_index=preferred_index,
            preferred_name=preferred_name,
        )
        self._select_runtime_input_device(resolved_device)

        has_saved_preference = (
            self.app_preferences.selected_input_device_index is not None or self.app_preferences.selected_input_device_name is not None
        )
        self._preferred_input_device_unavailable = bool(has_saved_preference and resolution in {"default", "first", "none"})
        if not self._preferred_input_device_unavailable:
            self._preferred_input_device_notified = False

        if (
            resolved_device is not None
            and has_saved_preference
            and resolution in {"exact", "index", "name"}
            and (
                self.app_preferences.selected_input_device_index != int(resolved_device["index"])
                or not input_device_name_matches(
                    self.app_preferences.selected_input_device_name,
                    resolved_device.get("name"),
                )
            )
        ):
            self._persist_selected_input_device_preference(resolved_device)

        device_changed = not self._same_input_device(previous_device, resolved_device)
        LOGGER.info(
            "🎙️ Обновлен список микрофонов: count=%s, resolution=%s, preferred_index=%s, preferred_name=%s, active_index=%s, active_name=%s",
            len(devices),
            resolution,
            self.app_preferences.selected_input_device_index,
            self.app_preferences.selected_input_device_name,
            None if resolved_device is None else resolved_device["index"],
            None if resolved_device is None else resolved_device.get("name"),
        )

        if notify:
            if resolved_device is None:
                self.system_integration_service.notify(
                    "MLX Whisper Dictation",
                    "После пробуждения не найден ни один доступный микрофон. Проверьте подключение устройства и доступ к Microphone.",
                )
            elif device_changed and has_saved_preference and resolution in {"default", "first"}:
                self.system_integration_service.notify(
                    "MLX Whisper Dictation",
                    f"Выбранный микрофон временно недоступен. Переключаюсь на: {resolved_device['name']}",
                )
                self._preferred_input_device_notified = True

        if publish_snapshot and hasattr(self, "_subscribers"):
            self._notify_subscribers()
        return device_changed

    def prepare_recording(self) -> bool:
        """Проверяет и обновляет аудиоустройства перед стартом новой записи."""
        self.refresh_input_devices(publish_snapshot=False, notify=True)
        if self.current_input_device is not None and self._preferred_input_device_unavailable and not self._preferred_input_device_notified:
            self.system_integration_service.notify(
                "MLX Whisper Dictation",
                f"Выбранный микрофон временно недоступен. Переключаюсь на: {self.current_input_device['name']}",
            )
            self._preferred_input_device_notified = True
        if self.current_input_device is not None:
            return True

        LOGGER.error("🎙️ Невозможно начать запись: нет доступного микрофона")
        self.started = False
        self.state = Config.STATUS_IDLE
        self.recording_overlay.hide()
        self.system_integration_service.notify(
            "MLX Whisper Dictation",
            "Не найден доступный микрофон. Проверьте устройство, разрешение Microphone и при необходимости переподключите аудио-интерфейс.",
        )
        self._notify_subscribers()
        return False

    def handle_recording_runtime_error(self, _title: str, _message: str) -> None:
        """Сбрасывает runtime-состояние после ошибки открытия или чтения микрофона."""
        LOGGER.warning("🎙️ Сбрасываю состояние приложения после ошибки записи")
        self.started = False
        self.state = Config.STATUS_IDLE
        self.recording_overlay.hide()
        self.release_display_sleep_for_active_session(immediate=True, reason="recording_runtime_error")
        self.refresh_input_devices(publish_snapshot=False)
        self._notify_subscribers()

    def handle_system_wake(self) -> None:
        """Восстанавливает аудио и хоткеи после выхода macOS из sleep."""
        LOGGER.info("💤 macOS вышла из сна, обновляю аудио- и hotkey-runtime")
        self.capture_system_diagnostics("system_wake")
        was_recording = self.started
        if self.started:
            LOGGER.warning("🎙️ Активная запись прервана после sleep/wake, отменяю текущую сессию")
            self.recorder.cancel()
            self.started = False
            self.state = Config.STATUS_IDLE
            self.recording_overlay.hide()
        if was_recording:
            self.release_display_sleep_for_active_session(immediate=True, reason="system_wake_active_recording")
        elif self._display_sleep_prevention_active:
            LOGGER.warning(
                "💤 Wake пришёл во время post-dictation grace-паузы; оставляю защиту дисплея активной: state=%s",
                self.state,
            )
            self.release_display_sleep_for_active_session(reason="system_wake_grace")

        self.permission_status["accessibility"] = self.system_integration_service.get_accessibility_status()
        self.permission_status["input_monitoring"] = self.system_integration_service.get_input_monitoring_status()
        self.refresh_input_devices(publish_snapshot=False, notify=True)

        listener = self.key_listener
        if hasattr(listener, "on_system_wake"):
            try:
                listener.on_system_wake()
            except Exception:
                LOGGER.exception("⌨️ Не удалось восстановить hotkey-listener после wake")
        elif hasattr(listener, "stop") and hasattr(listener, "start"):
            try:
                listener.stop()
                listener.start()
            except Exception:
                LOGGER.exception("⌨️ Не удалось перезапустить hotkey-listener после wake")

        self._notify_subscribers()

    def handle_system_power_event(self, event_name: str) -> None:
        """Логирует системные события экранов, сна и пользовательской сессии."""
        LOGGER.info(
            "🖥️ Системное событие macOS: event=%s, state=%s, started=%s, display_assertion_active=%s",
            event_name,
            self.state,
            self.started,
            self._display_sleep_prevention_active,
        )
        if event_name == "did_wake":
            self.handle_system_wake()
            return
        self.capture_system_diagnostics(f"system_event_{event_name}")

    def capture_system_diagnostics(self, label: str) -> None:
        """Запускает расширенный снимок состояния macOS для расследования мерцаний/lock."""
        LOGGER.info(
            "🧪 System diagnostics requested: label=%s, state=%s, started=%s, active_display_assertion=%s, input_device=%s",
            label,
            self.state,
            self.started,
            self._display_sleep_prevention_active,
            None if self.current_input_device is None else self.current_input_device.get("name"),
        )
        try:
            self.system_diagnostics_service.capture(label)
        except Exception:
            LOGGER.exception("🧪 Не удалось запустить расширенную системную диагностику: label=%s", label)

    @property
    def paste_cgevent_enabled(self) -> bool:
        """Возвращает флаг метода вставки через CGEvent."""
        return bool(getattr(self.transcriber, "paste_cgevent_enabled", True))

    @property
    def paste_ax_enabled(self) -> bool:
        """Возвращает флаг метода вставки через Accessibility API."""
        return bool(getattr(self.transcriber, "paste_ax_enabled", False))

    @property
    def paste_clipboard_enabled(self) -> bool:
        """Возвращает флаг метода вставки через буфер обмена."""
        return bool(getattr(self.transcriber, "paste_clipboard_enabled", False))

    @property
    def capitalize_first_letter_enabled(self) -> bool:
        """Возвращает флаг правила заглавной буквы после распознавания."""
        return bool(getattr(self.transcriber, "capitalize_first_letter_enabled", True))

    @property
    def remove_trailing_period_for_single_sentence_enabled(self) -> bool:
        """Возвращает флаг удаления точки в конце одного предложения."""
        return bool(getattr(self.transcriber, "remove_trailing_period_for_single_sentence_enabled", True))

    @property
    def restore_trailing_period_on_next_dictation_enabled(self) -> bool:
        """Возвращает флаг автоточки перед следующей диктовкой."""
        return bool(getattr(self.transcriber, "restore_trailing_period_on_next_dictation_enabled", False))

    @property
    def gain_normalization_enabled(self) -> bool:
        """Возвращает флаг бережной нормализации аудио."""
        return bool(getattr(self.transcriber, "gain_normalization_enabled", True))

    @property
    def audio_artifact_cleanup_enabled(self) -> bool:
        """Возвращает флаг автоочистки WAV-артефактов."""
        return bool(getattr(self.transcriber, "audio_artifact_cleanup_enabled", False))

    @property
    def llm_clipboard_enabled(self) -> bool:
        """Возвращает флаг использования буфера обмена для LLM."""
        return bool(getattr(self.transcriber, "llm_clipboard_enabled", True))

    @property
    def private_mode_enabled(self) -> bool:
        """Возвращает флаг приватного режима."""
        return bool(getattr(self.transcriber, "private_mode_enabled", False))

    @property
    def history(self) -> list[str]:
        """Возвращает историю транскрипций."""
        return list(getattr(self.transcriber, "history", []))

    @property
    def total_tokens(self) -> int:
        """Возвращает суммарное количество использованных токенов."""
        return int(getattr(self.transcriber, "total_tokens", 0))

    @property
    def model_repo(self) -> str:
        """Возвращает полный идентификатор модели распознавания."""
        return self.launch_config.model

    @model_repo.setter
    def model_repo(self, value: str) -> None:
        self.launch_config = self.launch_config.with_model(value)
        self.model_name = self.launch_config.model.rsplit("/", maxsplit=1)[-1]
        if self.launch_config.model not in self.model_options:
            self.model_options.insert(0, self.launch_config.model)

    @property
    def languages(self) -> list[str] | None:
        """Возвращает список доступных языков."""
        return self.launch_config.language

    @property
    def max_time(self) -> float | None:
        """Возвращает лимит записи."""
        return self.launch_config.max_time

    @max_time.setter
    def max_time(self, value: float | None) -> None:
        self.launch_config = self.launch_config.with_max_time(value)
        if self.launch_config.max_time not in self.max_time_options:
            self.max_time_options.insert(0, self.launch_config.max_time)

    @property
    def current_language(self) -> str | None:
        """Возвращает текущий язык распознавания."""
        return self.app_preferences.selected_language

    @current_language.setter
    def current_language(self, value: str | None) -> None:
        self.app_preferences = self.app_preferences.with_selected_language(value)

    @property
    def llm_prompt_name(self) -> str:
        """Возвращает имя активного LLM-промпта."""
        return self.app_preferences.llm_prompt_name

    @llm_prompt_name.setter
    def llm_prompt_name(self, value: str) -> None:
        self.app_preferences = self.app_preferences.with_llm_prompt_name(value)

    @property
    def performance_mode(self) -> str:
        """Возвращает текущий режим производительности."""
        return self.app_preferences.performance_mode

    @performance_mode.setter
    def performance_mode(self, value: str) -> None:
        self.app_preferences = self.app_preferences.with_performance_mode(value)

    @property
    def audio_profile_name(self) -> str:
        """Возвращает активный аудиопрофиль для текущего микрофона."""
        return audio_profile_for_input_device(
            self.current_input_device,
            high_quality_mac_builtin_enabled=self.high_quality_mac_builtin_enabled,
        )

    @property
    def high_quality_mac_builtin_enabled(self) -> bool:
        """Возвращает флаг автоматического MacBook HQ-профиля."""
        return self.app_preferences.high_quality_mac_builtin_enabled

    @high_quality_mac_builtin_enabled.setter
    def high_quality_mac_builtin_enabled(self, value: bool) -> None:
        self.app_preferences = self.app_preferences.with_high_quality_mac_builtin(value)

    @property
    def show_recording_notification(self) -> bool:
        """Возвращает флаг уведомления о старте записи."""
        return self.app_preferences.show_recording_notification

    @show_recording_notification.setter
    def show_recording_notification(self, value: bool) -> None:
        self.app_preferences = self.app_preferences.with_recording_notification(value)

    @property
    def show_recording_overlay(self) -> bool:
        """Возвращает флаг показа overlay записи."""
        return self.app_preferences.show_recording_overlay

    @show_recording_overlay.setter
    def show_recording_overlay(self, value: bool) -> None:
        self.app_preferences = self.app_preferences.with_recording_overlay(value)

    @property
    def show_recording_time_in_menu_bar(self) -> bool:
        """Возвращает флаг показа таймера записи в строке меню."""
        return self.app_preferences.show_recording_time_in_menu_bar

    @show_recording_time_in_menu_bar.setter
    def show_recording_time_in_menu_bar(self, value: bool) -> None:
        self.app_preferences = self.app_preferences.with_recording_time_in_menu_bar(value)

    @property
    def primary_key_combination(self) -> str:
        """Возвращает основной хоткей во внутреннем формате."""
        return self.launch_config.key_combination or ""

    @primary_key_combination.setter
    def primary_key_combination(self, value: str) -> None:
        self.launch_config = self.launch_config.with_hotkeys(self.launch_config.hotkeys.with_primary(value))

    @property
    def secondary_key_combination(self) -> str:
        """Возвращает дополнительный хоткей во внутреннем формате."""
        return self.launch_config.secondary_key_combination or ""

    @secondary_key_combination.setter
    def secondary_key_combination(self, value: str) -> None:
        self.launch_config = self.launch_config.with_hotkeys(self.launch_config.hotkeys.with_secondary(value))

    @property
    def llm_key_combination(self) -> str:
        """Возвращает LLM-хоткей во внутреннем формате."""
        return self.launch_config.llm_key_combination or ""

    @llm_key_combination.setter
    def llm_key_combination(self, value: str) -> None:
        self.launch_config = self.launch_config.with_hotkeys(self.launch_config.hotkeys.with_llm(value))

    @property
    def zipper_key_combination(self) -> str:
        """Возвращает Zipper-хоткей во внутреннем формате."""
        return self.launch_config.zipper_key_combination or ""

    @zipper_key_combination.setter
    def zipper_key_combination(self, value: str) -> None:
        self.launch_config = self.launch_config.with_hotkeys(self.launch_config.hotkeys.with_zipper(value))

    @property
    def rsvp_key_combination(self) -> str:
        """Возвращает RSVP-хоткей во внутреннем формате."""
        return self.reader_preferences.rsvp_hotkey

    @rsvp_key_combination.setter
    def rsvp_key_combination(self, value: str) -> None:
        self.reader_preferences = self.reader_preferences.with_rsvp_hotkey(value)

    @property
    def tts_key_combination(self) -> str:
        """Возвращает TTS-хоткей во внутреннем формате."""
        return self.reader_preferences.tts_hotkey

    @tts_key_combination.setter
    def tts_key_combination(self, value: str) -> None:
        self.reader_preferences = self.reader_preferences.with_tts_hotkey(value)

    @property
    def reader_rsvp_wpm(self) -> int:
        """Возвращает скорость RSVP в словах в минуту."""
        return self.reader_preferences.rsvp_config.wpm

    @property
    def reader_rsvp_chunk_size(self) -> int:
        """Возвращает размер RSVP chunk-а."""
        return self.reader_preferences.rsvp_config.chunk_size

    @property
    def reader_rsvp_font_size(self) -> int:
        """Возвращает размер шрифта RSVP."""
        return self.reader_preferences.rsvp_config.font_size

    @property
    def reader_tts_rate_multiplier(self) -> float:
        """Возвращает множитель скорости TTS."""
        return self.reader_preferences.tts_config.rate_multiplier

    @property
    def reader_tts_voice_id(self) -> str | None:
        """Возвращает идентификатор выбранного TTS-голоса."""
        return self.reader_preferences.tts_config.voice_id

    @property
    def reader_tts_max_minutes(self) -> int:
        """Возвращает лимит длительности TTS в минутах; 0 означает без лимита."""
        return self.reader_preferences.tts_config.max_minutes

    @property
    def reader_tts_engine(self) -> str:
        """Возвращает выбранный backend TTS."""
        return self.reader_preferences.tts_config.engine

    @property
    def reader_tts_mlx_model(self) -> str:
        """Возвращает выбранную MLX TTS-модель."""
        return self.reader_preferences.tts_config.mlx_model

    @property
    def reader_tts_mlx_voice_description(self) -> str:
        """Возвращает описание голоса для MLX VoiceDesign."""
        return self.reader_preferences.tts_config.mlx_voice_description

    @property
    def reader_tts_tone_instruction(self) -> str:
        """Возвращает свободную инструкцию по интонации TTS."""
        return self.reader_preferences.tts_config.tone_instruction

    @property
    def reader_preprocess_enabled(self) -> bool:
        """Возвращает флаг LLM-предобработки reader."""
        return self.reader_preferences.preprocess_enabled

    @property
    def zipper_status(self) -> str:
        """Возвращает статус Zipper для меню."""
        if not self.zipper_enabled:
            return "выключен"
        if self.zipper_recording_active:
            return "запись"
        if self.state == Config.STATUS_MODEL_LOADING:
            return "загрузка модели"
        if self.state == Config.STATUS_ZIPPER_PROCESSING:
            return "обработка"
        return "ожидание"

    @property
    def zipper_config_path(self) -> str:
        """Возвращает путь пользовательского конфига Zipper."""
        return self.zipper_config_provider.config_path()

    @property
    def llm_downloading(self) -> bool:
        """Возвращает флаг активной загрузки LLM-модели."""
        return self._llm_downloading

    @llm_downloading.setter
    def llm_downloading(self, value: bool) -> None:
        self._llm_downloading = value

    @property
    def llm_download_title(self) -> str:
        """Возвращает строку статуса загрузки LLM-модели."""
        return self._llm_download_title

    @llm_download_title.setter
    def llm_download_title(self, value: str) -> None:
        self._llm_download_title = value

    @property
    def model_download_title(self) -> str:
        """Возвращает строку общего прогресса загрузки моделей."""
        return self._model_download_title

    @property
    def model_download_active(self) -> bool:
        """Сообщает, идёт ли сейчас загрузка модели."""
        return self._model_download_active

    def handle_model_download_progress(self, progress: ModelDownloadProgress) -> None:
        """Обновляет общий статус загрузки моделей для menu bar."""
        self._model_download_active = not (progress.complete or progress.failed)
        self._model_download_title = format_model_download_title(progress)
        self._notify_subscribers()

    def handle_model_memory_loading(self, active: bool, model_name: str, label: str) -> None:
        """Показывает в menu bar синхронную загрузку MLX-модели в память."""
        if active:
            if self._model_memory_loading_count == 0:
                self._state_before_model_memory_loading = self.state
            self._model_memory_loading_count += 1
            short_name = model_name.rsplit("/", maxsplit=1)[-1]
            LOGGER.info("🧠 %s загружается в память: %s", label, model_name)
            self.state = Config.STATUS_MODEL_LOADING
            self._model_download_title = f"🧠 {label}: загрузка в память ({short_name})"
            self._notify_subscribers()
            return

        if self._model_memory_loading_count > 0:
            self._model_memory_loading_count -= 1
        if self._model_memory_loading_count > 0:
            return

        previous_state = self._state_before_model_memory_loading or Config.STATUS_IDLE
        self._state_before_model_memory_loading = None
        if self.state == Config.STATUS_MODEL_LOADING:
            self.state = previous_state if previous_state != Config.STATUS_MODEL_LOADING else Config.STATUS_IDLE
        LOGGER.info("🧠 Загрузка модели в память завершена: label=%s, model=%s", label, model_name)
        self._model_download_title = "📦 Загрузка моделей: нет" if not self._model_download_active else self._model_download_title
        self._notify_subscribers()

    def download_required_model(self, requirement: ModelRequiredError) -> None:
        """Запускает общую загрузку модели по сигналу runtime-слоя."""
        self.download_model(requirement.model_name, label=requirement.label)

    def release_runtime_model(self, model_name: str) -> None:
        """Освобождает загруженный runtime-экземпляр модели."""
        try:
            self.model_runtime_service.release_model(model_name)
        except Exception:
            LOGGER.exception("⚠️ Не удалось освободить runtime-модель: %s", model_name)

    def preload_asr_model(self, model_name: str) -> None:
        """Запускает фоновый прогрев ASR-модели."""
        try:
            self.model_runtime_service.preload_asr_model(model_name)
        except Exception:
            LOGGER.exception("⚠️ Не удалось запустить прогрев ASR-модели: %s", model_name)

    def preload_llm_model(self, model_name: str) -> None:
        """Запускает фоновый прогрев LLM/VLM-модели."""
        try:
            self.model_runtime_service.preload_llm_model(model_name)
        except Exception:
            LOGGER.exception("⚠️ Не удалось запустить прогрев LLM/VLM-модели: %s", model_name)

    def preload_tts_model(self, model_name: str) -> None:
        """Запускает фоновый прогрев MLX TTS-модели."""
        try:
            self.model_runtime_service.preload_tts_model(model_name)
        except Exception:
            LOGGER.exception("⚠️ Не удалось запустить прогрев MLX TTS-модели: %s", model_name)

    def shutdown_model_runtime(self) -> None:
        """Очищает единый runtime-cache моделей при завершении приложения."""
        try:
            self.model_runtime_service.shutdown()
        except Exception:
            LOGGER.exception("⚠️ Не удалось очистить runtime-cache моделей")

    def download_model(self, model_name: str, *, label: str) -> None:
        """Запускает фоновую загрузку модели через единый downloader приложения."""
        if self._model_download_worker is not None and self._model_download_worker.is_alive():
            self.system_integration_service.notify("MLX Whisper Dictation", "Загрузка модели уже выполняется.")
            return

        LOGGER.info("📥 Запускаю общую загрузку модели: label=%s, model=%s", label, model_name)
        self._model_download_active = True
        self._model_download_title = f"📥 {label}: подготовка"
        self.system_integration_service.notify(
            "MLX Whisper Dictation",
            f"{label} {model_name} не найдена локально. Загружаю из Hugging Face…",
        )
        self._notify_subscribers()

        def run() -> None:
            try:
                self.model_download_service.ensure_downloaded(model_name, label)
            except Exception:
                LOGGER.exception("❌ Ошибка общей загрузки модели: label=%s, model=%s", label, model_name)
                self._model_download_active = False
                self._model_download_title = f"❌ {label}: ошибка загрузки"
                self.system_integration_service.notify(
                    "MLX Whisper Dictation",
                    f"Не удалось скачать модель: {label}. Попробуйте снова.",
                )
            else:
                self._model_download_active = False
                self._model_download_title = f"✅ {label}: загружена"
                self.system_integration_service.notify(
                    "MLX Whisper Dictation",
                    f"{label} загружена. Повторите действие.",
                )
            finally:
                self._notify_subscribers()

        thread = threading.Thread(target=run, daemon=True)
        self._model_download_worker = thread
        thread.start()

    def subscribe(self, callback: Callable[[AppSnapshot], None]) -> None:
        """Подписывает UI или тесты на обновления snapshot."""
        self._subscribers.append(callback)
        callback(self.snapshot())

    def snapshot(self) -> AppSnapshot:
        """Возвращает текущий snapshot состояния для UI."""
        return AppSnapshot(
            state=self.state,
            started=self.started,
            elapsed_time=self.elapsed_time,
            model_repo=self.model_repo,
            model_name=self.model_name,
            hotkey_status=self.hotkey_status,
            secondary_hotkey_status=self.secondary_hotkey_status,
            llm_hotkey_status=self.llm_hotkey_status,
            zipper_hotkey_status=self.zipper_hotkey_status,
            primary_key_combination=self.primary_key_combination,
            secondary_key_combination=self.secondary_key_combination,
            llm_key_combination=self.llm_key_combination,
            zipper_key_combination=self.zipper_key_combination,
            llm_prompt_name=self.llm_prompt_name,
            performance_mode=self.performance_mode,
            max_time=self.max_time,
            max_time_options=list(self.max_time_options),
            model_options=list(self.model_options),
            languages=None if self.languages is None else list(self.languages),
            current_language=self.current_language,
            input_devices=list(self.input_devices),
            current_input_device=self.current_input_device,
            audio_profile_name=self.audio_profile_name,
            high_quality_mac_builtin_enabled=self.high_quality_mac_builtin_enabled,
            permission_status=dict(self.permission_status),
            microphone_profiles=list(self.microphone_profiles),
            show_recording_notification=self.show_recording_notification,
            show_recording_overlay=self.show_recording_overlay,
            show_recording_time_in_menu_bar=self.show_recording_time_in_menu_bar,
            private_mode_enabled=bool(getattr(self.transcriber, "private_mode_enabled", False)),
            paste_cgevent_enabled=bool(getattr(self.transcriber, "paste_cgevent_enabled", True)),
            paste_ax_enabled=bool(getattr(self.transcriber, "paste_ax_enabled", False)),
            paste_clipboard_enabled=bool(getattr(self.transcriber, "paste_clipboard_enabled", False)),
            capitalize_first_letter_enabled=bool(getattr(self.transcriber, "capitalize_first_letter_enabled", True)),
            remove_trailing_period_for_single_sentence_enabled=bool(
                getattr(self.transcriber, "remove_trailing_period_for_single_sentence_enabled", True)
            ),
            restore_trailing_period_on_next_dictation_enabled=bool(
                getattr(self.transcriber, "restore_trailing_period_on_next_dictation_enabled", False)
            ),
            gain_normalization_enabled=bool(getattr(self.transcriber, "gain_normalization_enabled", True)),
            audio_artifact_cleanup_enabled=self.audio_artifact_cleanup_enabled,
            llm_clipboard_enabled=bool(getattr(self.transcriber, "llm_clipboard_enabled", True)),
            history=list(getattr(self.transcriber, "history", [])),
            total_tokens=int(getattr(self.transcriber, "total_tokens", 0)),
            model_download_title=self._model_download_title,
            model_download_active=self._model_download_active,
            llm_download_title=self._llm_download_title,
            llm_download_interactive=not self._llm_downloading and not self._is_llm_model_cached(),
            llm_model_name=self.llm_model_name,
            llm_model_options=list(self.llm_model_options),
            zipper_enabled=self.zipper_enabled,
            zipper_status=self.zipper_status,
            zipper_debug_panel_enabled=self.zipper_debug_panel_enabled,
            zipper_config_path=self.zipper_config_path,
        )

    def _notify_subscribers(self) -> None:
        """Рассылает новый snapshot всем подписчикам."""
        snapshot = self.snapshot()
        for callback in list(self._subscribers):
            try:
                callback(snapshot)
            except Exception:
                LOGGER.exception("⚠️ Ошибка в callback подписчика приложения")

    def microphone_menu_title(self, device_info: AudioDeviceInfo) -> str:
        """Возвращает подпись микрофона для меню UI."""
        return format_microphone_menu_title(device_info)

    def is_microphone_profile_active(self, profile: MicrophoneProfile) -> bool:
        """Проверяет, соответствует ли профиль текущим runtime-настройкам."""
        return self.microphone_profiles_use_cases.is_microphone_profile_active(profile)

    def set_state(self, state: str) -> None:
        """Сохраняет новое состояние приложения и уведомляет подписчиков."""
        self.state = state
        if state == Config.STATUS_IDLE and not self.started:
            self.release_display_sleep_for_active_session(reason="idle")
        self._notify_subscribers()

    def _cancel_pending_display_sleep_release(self) -> None:
        """Отменяет отложенное отпускание power assertion, если оно было запланировано."""
        timer = self._display_sleep_release_timer
        self._display_sleep_release_timer = None
        if timer is not None and timer.is_alive() and threading.current_thread() is not timer:
            timer.cancel()

    def _release_display_sleep_after_grace(self) -> None:
        """Отпускает display assertion после короткой паузы после успешной диктовки."""
        self._display_sleep_release_timer = None
        if self.started or self.state != Config.STATUS_IDLE:
            LOGGER.info(
                "💡 Не отпускаю защиту дисплея после grace-паузы: state=%s, started=%s",
                self.state,
                self.started,
            )
            return
        self.release_display_sleep_for_active_session(immediate=True, reason="grace_elapsed")

    def prevent_display_sleep_for_active_session(self) -> None:
        """Удерживает дисплей от сна до завершения текущей диктовки."""
        self._cancel_pending_display_sleep_release()
        if self._display_sleep_prevention_active:
            return
        try:
            acquired = self.display_sleep_prevention_service.acquire()
        except Exception:
            LOGGER.exception("💡 Не удалось включить защиту дисплея от сна")
            return
        self._display_sleep_prevention_active = bool(acquired)

    def release_display_sleep_for_active_session(self, *, immediate: bool = False, reason: str = "unknown") -> None:
        """Отпускает удержание дисплея после завершения диктовки."""
        if not self._display_sleep_prevention_active:
            return
        delay = float(self.display_sleep_release_delay_seconds)
        if not immediate and delay > 0:
            if self._display_sleep_release_timer is None:
                LOGGER.info(
                    "💡 Дисплей останется активным ещё %.0f с после диктовки: reason=%s",
                    delay,
                    reason,
                )
                timer = threading.Timer(delay, self._release_display_sleep_after_grace)
                timer.daemon = True
                self._display_sleep_release_timer = timer
                timer.start()
            return

        self._cancel_pending_display_sleep_release()
        try:
            LOGGER.info("💡 Отпускаю защиту дисплея: reason=%s", reason)
            self.display_sleep_prevention_service.release()
        except Exception:
            LOGGER.exception("💡 Не удалось выключить защиту дисплея от сна")
        finally:
            self._display_sleep_prevention_active = False

    def set_permission_status(self, permission_name: str, status: bool | None) -> None:
        """Сохраняет новый статус разрешения и уведомляет подписчиков."""
        self.permission_status[permission_name] = status
        self._notify_subscribers()

    def _refresh_hotkey_statuses(self) -> None:
        """Синхронизирует display-строки хоткеев с текущими комбинациями."""
        self.hotkey_management_use_cases.refresh_hotkey_statuses()

    def _persist_hotkey_settings(self) -> None:
        """Сохраняет текущие хоткеи в NSUserDefaults."""
        self.settings_store.save_str(Config.DEFAULTS_KEY_PRIMARY_HOTKEY, self.launch_config.hotkeys.primary_store_value)
        self.settings_store.save_str(Config.DEFAULTS_KEY_SECONDARY_HOTKEY, self.launch_config.hotkeys.secondary_store_value)
        self.settings_store.save_str(Config.DEFAULTS_KEY_ZIPPER_HOTKEY, self.launch_config.hotkeys.zipper_store_value)
        self.settings_store.save_str(Config.DEFAULTS_KEY_READER_RSVP_HOTKEY, self.reader_preferences.rsvp_hotkey)
        self.settings_store.save_str(Config.DEFAULTS_KEY_READER_TTS_HOTKEY, self.reader_preferences.tts_hotkey)

    def _active_key_combinations(self) -> list[str]:
        """Возвращает все включённые комбинации для основного listener-а."""
        return self.hotkey_management_use_cases.active_key_combinations()

    def _can_update_hotkeys_runtime(self) -> bool:
        """Проверяет, умеет ли текущий listener обновляться без перезапуска."""
        return hasattr(self.key_listener, "update_hotkeys")

    def _apply_hotkey_changes(self) -> bool:
        """Применяет новый набор основных хоткеев к текущему listener-у."""
        self._refresh_hotkey_statuses()
        self._persist_hotkey_settings()
        self._notify_subscribers()
        if self._can_update_hotkeys_runtime():
            listener = self.key_listener
            try:
                listener.update_hotkeys(
                    self.primary_key_combination,
                    self.secondary_key_combination,
                    self.llm_key_combination,
                    self.rsvp_key_combination,
                    self.tts_key_combination,
                    self.zipper_key_combination,
                )
            except TypeError:
                try:
                    listener.update_hotkeys(
                        self.primary_key_combination,
                        self.secondary_key_combination,
                        self.llm_key_combination,
                        self.rsvp_key_combination,
                        self.tts_key_combination,
                    )
                except TypeError:
                    listener.update_hotkeys(
                        self.primary_key_combination,
                        self.secondary_key_combination,
                        self.llm_key_combination,
                    )
            return True
        return False

    def _update_hotkey_value(self, *, is_secondary: bool, new_combination: str) -> None:
        """Проверяет и сохраняет новую комбинацию клавиш."""
        if is_secondary:
            self.secondary_key_combination = new_combination
            return

        self.primary_key_combination = new_combination

    def change_input_device(self, device_index: int | None) -> None:
        """Переключает активное устройство ввода по индексу."""
        self.settings_use_cases.change_input_device(device_index)

    def change_language(self, language: str | None) -> None:
        """Переключает язык распознавания."""
        self.settings_use_cases.change_language(language)

    def change_model(self, model_repo: str) -> None:
        """Переключает модель распознавания."""
        self.settings_use_cases.change_model(model_repo)

    def change_max_time(self, max_time: float | None) -> None:
        """Переключает лимит записи."""
        self.settings_use_cases.change_max_time(max_time)

    def _persist_microphone_profiles(self) -> None:
        """Сохраняет быстрые профили микрофона."""
        self.microphone_profiles_service.save_profiles(self.microphone_profiles)

    def _active_input_device_index(self) -> int | None:
        """Возвращает индекс текущего микрофона."""
        if self.current_input_device is None:
            return None
        return int(self.current_input_device["index"])

    def suggest_microphone_profile_name(self) -> str:
        """Предлагает имя для нового быстрого профиля."""
        return self.microphone_profiles_use_cases.suggest_microphone_profile_name()

    def _unique_microphone_profile_name(self, base_name: str) -> str:
        """Нормализует и делает имя профиля уникальным."""
        normalized_name = " ".join(base_name.split()) or "Новый профиль"
        existing_names = {profile.name for profile in self.microphone_profiles}
        if normalized_name not in existing_names:
            return normalized_name

        suffix = 2
        while f"{normalized_name} {suffix}" in existing_names:
            suffix += 1
        return f"{normalized_name} {suffix}"

    def _current_microphone_profile(self, profile_name: str) -> MicrophoneProfile:
        """Собирает профиль из текущих runtime-настроек."""
        return MicrophoneProfile.from_runtime(
            profile_name,
            input_device_index=self._active_input_device_index(),
            input_device_name="" if self.current_input_device is None else str(self.current_input_device.get("name") or ""),
            model_repo=self.model_repo,
            language=self.current_language,
            max_time=self.max_time,
            performance_mode=self.performance_mode,
            private_mode=bool(getattr(self.transcriber, "private_mode_enabled", False)),
            paste_cgevent=bool(getattr(self.transcriber, "paste_cgevent_enabled", True)),
            paste_ax=bool(getattr(self.transcriber, "paste_ax_enabled", False)),
            paste_clipboard=bool(getattr(self.transcriber, "paste_clipboard_enabled", False)),
            capitalize_first_letter=bool(getattr(self.transcriber, "capitalize_first_letter_enabled", True)),
            remove_trailing_period_for_single_sentence=bool(
                getattr(self.transcriber, "remove_trailing_period_for_single_sentence_enabled", True)
            ),
            restore_trailing_period_on_next_dictation=bool(
                getattr(self.transcriber, "restore_trailing_period_on_next_dictation_enabled", False)
            ),
            llm_clipboard=bool(getattr(self.transcriber, "llm_clipboard_enabled", True)),
        )

    def add_current_microphone_profile(self, profile_name: str) -> None:
        """Сохраняет текущий runtime как новый быстрый профиль."""
        self.microphone_profiles_use_cases.add_current_microphone_profile(profile_name)

    def apply_microphone_profile(self, profile_name: str) -> None:
        """Применяет быстрый профиль по его имени."""
        self.microphone_profiles_use_cases.apply_microphone_profile(profile_name)

    def delete_microphone_profile(self, profile_name: str) -> None:
        """Удаляет быстрый профиль по имени."""
        self.microphone_profiles_use_cases.delete_microphone_profile(profile_name)

    def change_hotkey(self) -> None:
        """Открывает диалог и меняет основной хоткей."""
        self.hotkey_management_use_cases.change_hotkey()

    def change_secondary_hotkey(self) -> None:
        """Открывает диалог и меняет дополнительный хоткей."""
        self.hotkey_management_use_cases.change_secondary_hotkey()

    def change_llm_hotkey(self) -> None:
        """Открывает диалог и меняет LLM-хоткей."""
        self.hotkey_management_use_cases.change_llm_hotkey()

    def change_zipper_hotkey(self) -> None:
        """Открывает диалог и меняет Zipper-хоткей."""
        self.hotkey_management_use_cases.change_zipper_hotkey()

    def change_rsvp_hotkey(self) -> None:
        """Открывает диалог и меняет RSVP-хоткей."""
        self.hotkey_management_use_cases.change_rsvp_hotkey()

    def change_tts_hotkey(self) -> None:
        """Открывает диалог и меняет TTS-хоткей."""
        self.hotkey_management_use_cases.change_tts_hotkey()

    def request_accessibility_access(self) -> None:
        """Повторно запрашивает Accessibility."""
        self.hotkey_management_use_cases.request_accessibility_access()

    def request_input_monitoring_access(self) -> None:
        """Повторно запрашивает Input Monitoring."""
        self.hotkey_management_use_cases.request_input_monitoring_access()

    def toggle_recording_notification(self) -> None:
        """Переключает уведомление о старте записи."""
        self.settings_use_cases.toggle_recording_notification()

    def toggle_recording_overlay(self) -> None:
        """Переключает всплывающий индикатор у курсора."""
        self.settings_use_cases.toggle_recording_overlay()

    def toggle_recording_time_in_menu_bar(self) -> None:
        """Переключает отображение времени записи в menu bar."""
        self.settings_use_cases.toggle_recording_time_in_menu_bar()

    def toggle_high_quality_mac_builtin(self) -> None:
        """Переключает автоматический MacBook HQ-профиль."""
        self.settings_use_cases.toggle_high_quality_mac_builtin()

    def toggle_gain_normalization(self) -> None:
        """Переключает бережную нормализацию аудио."""
        self.settings_use_cases.toggle_gain_normalization()

    def toggle_audio_artifact_cleanup(self) -> None:
        """Переключает автоочистку диагностических WAV-записей."""
        self.settings_use_cases.toggle_audio_artifact_cleanup()

    def open_recordings_directory(self) -> None:
        """Открывает папку диагностических WAV-записей."""
        self.settings_use_cases.open_recordings_directory()

    def change_performance_mode(self, performance_mode: object) -> None:
        """Меняет баланс между задержкой и ресурсами."""
        self.settings_use_cases.change_performance_mode(performance_mode)
        self.tts_speaker.set_keep_model_loaded(self.performance_mode == Config.PERFORMANCE_MODE_FAST)

    def toggle_private_mode(self) -> None:
        """Переключает private mode для истории."""
        self.settings_use_cases.toggle_private_mode()

    def toggle_paste_cgevent(self) -> None:
        """Переключает метод вставки через CGEvent."""
        self.settings_use_cases.toggle_paste_cgevent()

    def toggle_paste_ax(self) -> None:
        """Переключает метод вставки через Accessibility API."""
        self.settings_use_cases.toggle_paste_ax()

    def toggle_paste_clipboard(self) -> None:
        """Переключает метод вставки через буфер обмена."""
        self.settings_use_cases.toggle_paste_clipboard()

    def toggle_llm_clipboard(self) -> None:
        """Переключает использование буфера обмена для LLM."""
        self.settings_use_cases.toggle_llm_clipboard()

    def toggle_capitalize_first_letter(self) -> None:
        """Переключает правило заглавной буквы после распознавания."""
        self.settings_use_cases.toggle_capitalize_first_letter()

    def toggle_remove_trailing_period_for_single_sentence(self) -> None:
        """Переключает удаление точки в конце одного предложения."""
        self.settings_use_cases.toggle_remove_trailing_period_for_single_sentence()

    def toggle_restore_trailing_period_on_next_dictation(self) -> None:
        """Переключает автоточку перед следующей диктовкой."""
        self.settings_use_cases.toggle_restore_trailing_period_on_next_dictation()

    def prune_expired_history(self) -> None:
        """Удаляет просроченную историю, если transcriber поддерживает это."""
        self.settings_use_cases.prune_expired_history()

    def copy_history_text(self, text: str) -> None:
        """Копирует текст из истории в системный буфер обмена."""
        self.clipboard_service.write_text(text)
        LOGGER.info("📋 Текст из истории скопирован в буфер обмена: %r", text[:80])
        self.system_integration_service.notify("MLX Whisper Dictation", "Текст скопирован в буфер обмена.")

    def start_recording(self) -> None:
        """Запускает обычный сценарий записи и распознавания."""
        self.recording_use_cases.start_recording()

    def stop_recording(self) -> None:
        """Останавливает активную запись и запускает этап распознавания."""
        self.recording_use_cases.stop_recording()

    def on_status_tick(self) -> None:
        """Обновляет счетчик времени записи и контролирует max_time."""
        if self.zipper_recording_active:
            self.zipper_use_cases.on_status_tick()
            return
        self.recording_use_cases.on_status_tick()

    def toggle(self) -> None:
        """Переключает обычный сценарий записи."""
        self.recording_use_cases.toggle()

    def toggle_llm(self) -> None:
        """Переключает сценарий запись → Whisper → LLM."""
        self.llm_pipeline_use_cases.toggle_llm()

    def toggle_zipper(self) -> None:
        """Переключает сценарий голосового агента Zipper."""
        LOGGER.info(
            "🧷 toggle_zipper вызван: enabled=%s, recording_active=%s, started=%s, state=%s",
            self.zipper_enabled,
            self.zipper_recording_active,
            self.started,
            self.state,
        )
        self.zipper_use_cases.toggle()

    def toggle_zipper_enabled(self) -> None:
        """Включает или выключает Zipper."""
        self.zipper_use_cases.toggle_enabled()

    def open_zipper_config(self) -> None:
        """Открывает пользовательский конфиг Zipper."""
        self.zipper_use_cases.open_config()

    def reload_zipper_config(self) -> None:
        """Перечитывает конфиг Zipper."""
        self.zipper_use_cases.reload_config()

    def toggle_zipper_debug_panel(self) -> None:
        """Включает или выключает debug-панель Zipper."""
        self.zipper_use_cases.toggle_debug_panel()

    def clear_zipper_context(self) -> None:
        """Очищает текущий контекст Zipper."""
        self.zipper_use_cases.clear_context()

    def clear_zipper_memory(self) -> None:
        """Очищает постоянную память Zipper."""
        self.zipper_use_cases.clear_memory()

    def handle_escape_keycode(self, keycode: int) -> None:
        """Отменяет запись при нажатии Escape."""
        if self.handle_reader_key("esc"):
            return
        if self.zipper_use_cases.handle_escape_keycode(keycode):
            return
        self.recording_use_cases.handle_escape_keycode(keycode)

    def cancel_recording(self) -> None:
        """Отменяет активную запись без распознавания."""
        if self.zipper_recording_active:
            self.zipper_use_cases.cancel_recording()
            return
        self.recording_use_cases.cancel_recording()

    def _is_llm_model_cached(self) -> bool:
        """Проверяет, что LLM-модель уже доступна локально."""
        return self.llm_pipeline_use_cases.is_model_cached()

    def download_llm_model(self) -> None:
        """Запускает загрузку LLM-модели и публикует прогресс в snapshot."""
        LOGGER.info("📥 Запрошена загрузка LLM-модели из runtime")
        self.llm_pipeline_use_cases.download_llm_model()

    def change_llm_prompt(self, prompt_name: str) -> None:
        """Переключает текущий пресет системного промпта LLM."""
        self.settings_use_cases.change_llm_prompt(prompt_name)

    def change_llm_model(self, model_name: str) -> None:
        """Переключает LLM-модель."""
        self.settings_use_cases.change_llm_model(model_name)
        self.reader_preferences = self.reader_preferences.with_preprocess_model(model_name)
        self.settings_store.save_str(Config.DEFAULTS_KEY_READER_PREPROCESS_MODEL, self.reader_preferences.preprocess_model)

    def change_reader_rsvp_wpm(self, wpm: int) -> None:
        """Меняет скорость RSVP."""
        self.reader_preferences = self.reader_preferences.with_rsvp_config(
            RSVPConfig.from_values(
                wpm=wpm,
                chunk_size=self.reader_rsvp_chunk_size,
                font_size=self.reader_rsvp_font_size,
            )
        )
        self.settings_store.save_int(Config.DEFAULTS_KEY_READER_RSVP_WPM, self.reader_rsvp_wpm)
        LOGGER.info("📖 RSVP скорость сохранена: %d wpm", self.reader_rsvp_wpm)
        self._notify_subscribers()

    def change_reader_rsvp_chunk_size(self, chunk_size: int) -> None:
        """Меняет размер chunk-а RSVP."""
        self.reader_preferences = self.reader_preferences.with_rsvp_config(
            RSVPConfig.from_values(
                wpm=self.reader_rsvp_wpm,
                chunk_size=chunk_size,
                font_size=self.reader_rsvp_font_size,
            )
        )
        self.settings_store.save_int(Config.DEFAULTS_KEY_READER_RSVP_CHUNK_SIZE, self.reader_rsvp_chunk_size)
        LOGGER.info("📖 RSVP chunk сохранён: %d", self.reader_rsvp_chunk_size)
        self._notify_subscribers()

    def change_reader_rsvp_font_size(self, font_size: int) -> None:
        """Меняет размер шрифта RSVP."""
        self.reader_preferences = self.reader_preferences.with_rsvp_config(
            RSVPConfig.from_values(
                wpm=self.reader_rsvp_wpm,
                chunk_size=self.reader_rsvp_chunk_size,
                font_size=font_size,
            )
        )
        self.settings_store.save_int(Config.DEFAULTS_KEY_READER_RSVP_FONT_SIZE, self.reader_rsvp_font_size)
        LOGGER.info("📖 RSVP размер шрифта сохранён: %d", self.reader_rsvp_font_size)
        self._notify_subscribers()

    def change_reader_tts_rate_multiplier(self, rate_multiplier: float) -> None:
        """Меняет множитель скорости TTS."""
        self.reader_preferences = self.reader_preferences.with_tts_config(
            TTSConfig.from_values(
                rate_multiplier=rate_multiplier,
                voice_id=self.reader_tts_voice_id,
                max_minutes=self.reader_tts_max_minutes,
                engine=self.reader_tts_engine,
                mlx_model=self.reader_tts_mlx_model,
                mlx_voice_description=self.reader_tts_mlx_voice_description,
                tone_instruction=self.reader_tts_tone_instruction,
            )
        )
        self.settings_store.save_str(Config.DEFAULTS_KEY_READER_TTS_RATE_MULTIPLIER, self.reader_tts_rate_multiplier)
        LOGGER.info("🔈 TTS скорость сохранена: %.2f×", self.reader_tts_rate_multiplier)
        self._notify_subscribers()

    def change_reader_tts_voice(self, voice_id: str | None) -> None:
        """Меняет системный голос TTS."""
        self.reader_preferences = self.reader_preferences.with_tts_config(
            TTSConfig.from_values(
                rate_multiplier=self.reader_tts_rate_multiplier,
                voice_id=voice_id,
                max_minutes=self.reader_tts_max_minutes,
                engine=self.reader_tts_engine,
                mlx_model=self.reader_tts_mlx_model,
                mlx_voice_description=self.reader_tts_mlx_voice_description,
                tone_instruction=self.reader_tts_tone_instruction,
            )
        )
        if self.reader_tts_voice_id is None:
            self.settings_store.remove_key(Config.DEFAULTS_KEY_READER_TTS_VOICE_ID)
        else:
            self.settings_store.save_str(Config.DEFAULTS_KEY_READER_TTS_VOICE_ID, self.reader_tts_voice_id)
        LOGGER.info("🔈 TTS голос сохранён: %s", self.reader_tts_voice_id or "auto")
        self._notify_subscribers()

    def change_reader_tts_max_minutes(self, max_minutes: int) -> None:
        """Меняет максимальную длительность TTS."""
        self.reader_preferences = self.reader_preferences.with_tts_config(
            TTSConfig.from_values(
                rate_multiplier=self.reader_tts_rate_multiplier,
                voice_id=self.reader_tts_voice_id,
                max_minutes=max_minutes,
                engine=self.reader_tts_engine,
                mlx_model=self.reader_tts_mlx_model,
                mlx_voice_description=self.reader_tts_mlx_voice_description,
                tone_instruction=self.reader_tts_tone_instruction,
            )
        )
        self.settings_store.save_int(Config.DEFAULTS_KEY_READER_TTS_MAX_MINUTES, self.reader_tts_max_minutes)
        LOGGER.info("🔈 TTS лимит длительности сохранён: %s", self.reader_tts_max_minutes or "без лимита")
        self._notify_subscribers()

    def change_reader_tts_engine(self, engine: str) -> None:
        """Меняет backend TTS."""
        self.reader_preferences = self.reader_preferences.with_tts_config(
            TTSConfig.from_values(
                rate_multiplier=self.reader_tts_rate_multiplier,
                voice_id=self.reader_tts_voice_id,
                max_minutes=self.reader_tts_max_minutes,
                engine=engine,
                mlx_model=self.reader_tts_mlx_model,
                mlx_voice_description=self.reader_tts_mlx_voice_description,
                tone_instruction=self.reader_tts_tone_instruction,
            )
        )
        self.settings_store.save_str(Config.DEFAULTS_KEY_READER_TTS_ENGINE, self.reader_tts_engine)
        LOGGER.info("🔈 TTS backend сохранён: %s", self.reader_tts_engine)
        self._notify_subscribers()

    def change_reader_tts_mlx_model(self, model_name: str) -> None:
        """Меняет MLX TTS-модель."""
        previous_model_name = self.reader_tts_mlx_model
        if model_name == previous_model_name:
            return
        self.reader_preferences = self.reader_preferences.with_tts_config(
            TTSConfig.from_values(
                rate_multiplier=self.reader_tts_rate_multiplier,
                voice_id=self.reader_tts_voice_id,
                max_minutes=self.reader_tts_max_minutes,
                engine=self.reader_tts_engine,
                mlx_model=model_name,
                mlx_voice_description=self.reader_tts_mlx_voice_description,
                tone_instruction=self.reader_tts_tone_instruction,
            )
        )
        self.settings_store.save_str(Config.DEFAULTS_KEY_READER_TTS_MLX_MODEL, self.reader_tts_mlx_model)
        self.release_runtime_model(previous_model_name)
        self.preload_tts_model(self.reader_tts_mlx_model)
        LOGGER.info("🔈 MLX TTS-модель сохранена: %s", self.reader_tts_mlx_model)
        self._notify_subscribers()

    def change_reader_tts_mlx_voice_description(self, description: str) -> None:
        """Меняет описание голоса для MLX VoiceDesign."""
        self.reader_preferences = self.reader_preferences.with_tts_config(
            TTSConfig.from_values(
                rate_multiplier=self.reader_tts_rate_multiplier,
                voice_id=self.reader_tts_voice_id,
                max_minutes=self.reader_tts_max_minutes,
                engine=self.reader_tts_engine,
                mlx_model=self.reader_tts_mlx_model,
                mlx_voice_description=description,
                tone_instruction=self.reader_tts_tone_instruction,
            )
        )
        self.settings_store.save_str(
            Config.DEFAULTS_KEY_READER_TTS_MLX_VOICE_DESCRIPTION,
            self.reader_tts_mlx_voice_description,
        )
        LOGGER.info("🔈 Описание MLX-голоса сохранено")
        self._notify_subscribers()

    def change_reader_tts_tone_instruction(self, tone_instruction: str) -> None:
        """Меняет свободную инструкцию по интонации TTS."""
        self.reader_preferences = self.reader_preferences.with_tts_config(
            TTSConfig.from_values(
                rate_multiplier=self.reader_tts_rate_multiplier,
                voice_id=self.reader_tts_voice_id,
                max_minutes=self.reader_tts_max_minutes,
                engine=self.reader_tts_engine,
                mlx_model=self.reader_tts_mlx_model,
                mlx_voice_description=self.reader_tts_mlx_voice_description,
                tone_instruction=tone_instruction,
            )
        )
        if self.reader_tts_tone_instruction:
            self.settings_store.save_str(Config.DEFAULTS_KEY_READER_TTS_TONE_INSTRUCTION, self.reader_tts_tone_instruction)
        else:
            self.settings_store.remove_key(Config.DEFAULTS_KEY_READER_TTS_TONE_INSTRUCTION)
        LOGGER.info("🔈 Интонация TTS сохранена: %s", self.reader_tts_tone_instruction or "не задана")
        self._notify_subscribers()

    def toggle_reader_preprocess(self) -> None:
        """Переключает LLM-предобработку reader."""
        self.reader_preferences = self.reader_preferences.with_preprocess_enabled(not self.reader_preprocess_enabled)
        self.settings_store.save_bool(Config.DEFAULTS_KEY_READER_PREPROCESS_ENABLED, self.reader_preprocess_enabled)
        LOGGER.info(
            "🤖 Reader LLM-предобработка: %s",
            "включена" if self.reader_preprocess_enabled else "выключена",
        )
        self._notify_subscribers()

    def reader_available_tts_voices(self) -> list[TTSVoice]:
        """Возвращает доступные системные голоса TTS."""
        try:
            return self.tts_speaker.available_voices()
        except Exception:
            LOGGER.exception("🔈 Не удалось получить список системных голосов")
            return []

    def toggle_rsvp(self) -> None:
        """Запускает или закрывает RSVP-сценарий reader."""
        if self.rsvp_display.is_running():
            self.rsvp_display.close()
            return
        self._start_reader_worker(
            "rsvp",
            lambda: self.play_rsvp_use_case.play(
                self.reader_preferences.rsvp_config,
                preprocess_enabled=self.reader_preprocess_enabled,
            ),
        )

    def toggle_tts(self) -> None:
        """Запускает или останавливает TTS-сценарий reader."""
        if self.tts_speaker.is_speaking():
            self.tts_speaker.stop()
            return
        self._start_reader_worker(
            "tts",
            lambda: self.play_tts_use_case.play(
                self.reader_preferences.tts_config,
                preprocess_enabled=self.reader_preprocess_enabled,
            ),
        )

    def _start_reader_worker(self, label: str, target: Callable[[], None]) -> None:
        """Запускает reader-сценарий в background thread."""
        if self._reader_worker is not None and self._reader_worker.is_alive():
            self.system_integration_service.notify("MLX Whisper Dictation", "Reader уже обрабатывает текст.")
            return

        def run() -> None:
            try:
                LOGGER.info("📖 Reader worker стартовал: %s", label)
                self.state = Config.STATUS_LLM_PROCESSING
                self._notify_subscribers()
                target()
            except ModelRequiredError as error:
                LOGGER.warning("📥 Reader запросил загрузку модели: label=%s, model=%s", error.label, error.model_name)
                self.download_required_model(error)
                self.system_integration_service.notify(
                    "MLX Whisper Dictation",
                    f"{error.label} ещё не готова. Запускаю загрузку; после завершения повторите reader-сценарий.",
                )
            except Exception:
                LOGGER.exception("❌ Ошибка reader-сценария: %s", label)
                self.system_integration_service.notify("MLX Whisper Dictation", "Ошибка reader. Подробности в логе.")
            finally:
                if not self.started and self.state == Config.STATUS_LLM_PROCESSING:
                    self.state = Config.STATUS_IDLE
                    self._notify_subscribers()
                LOGGER.info("📖 Reader worker завершён: %s", label)

        thread = threading.Thread(target=run, daemon=True)
        self._reader_worker = thread
        thread.start()

    def is_reader_active(self) -> bool:
        """Сообщает, активен ли RSVP/TTS reader или его worker."""
        worker_active = self._reader_worker is not None and self._reader_worker.is_alive()
        return bool(worker_active or self.rsvp_display.is_running() or self.tts_speaker.is_speaking())

    def shutdown_reader(self, join_timeout: float = READER_SHUTDOWN_JOIN_TIMEOUT_SECONDS) -> None:
        """Останавливает reader-сценарии и ждёт завершения их worker-а перед выходом."""
        self.tts_speaker.stop()
        self.rsvp_display.close()

        worker = self._reader_worker
        if worker is None or not worker.is_alive() or worker is threading.current_thread():
            return

        worker.join(timeout=max(float(join_timeout), 0.0))
        if worker.is_alive():
            LOGGER.warning("📖 Reader worker не завершился за %.1f с при выходе", join_timeout)

    def handle_reader_key(self, key_name: str) -> bool:
        """Обрабатывает клавиши управления reader-сценариями."""
        if self.rsvp_display.is_running() and self.rsvp_display.handle_key(key_name):
            return True
        if key_name == "esc" and self.tts_speaker.is_speaking():
            self.tts_speaker.stop()
            return True
        return False
