"""Orchestration-слой приложения Dictator.

Содержит DictationApp — объект приложения без UI-меню. Он хранит
runtime-state, управляет записью и LLM-сценарием, синхронизирует
настройки и уведомляет подписчиков о смене состояния через snapshot.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from .domain.audio import microphone_menu_title as format_microphone_menu_title
from .domain.constants import Config
from .domain.types import AppPreferences, AppSnapshot, LaunchConfig, MicrophoneProfile
from .use_cases.hotkey_management import HotkeyManagementUseCases
from .use_cases.llm_pipeline import LlmPipelineUseCases
from .use_cases.microphone_profiles import MicrophoneProfilesUseCases
from .use_cases.recording import RecordingUseCases
from .use_cases.settings import SettingsUseCases

if TYPE_CHECKING:
    from collections.abc import Callable

    from .domain.ports import LlmGatewayProtocol, RecorderProtocol, SettingsStoreProtocol
    from .domain.types import AudioDeviceInfo
    from .use_cases.transcription import TranscriptionUseCases

LOGGER = logging.getLogger(__name__)


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
class SystemIntegrationService:
    """Concrete bundle для уведомлений и статусов системных разрешений."""

    notify: Callable[[str, str], None]
    get_accessibility_status: Callable[[], bool | None]
    get_input_monitoring_status: Callable[[], bool | None]
    request_accessibility_permission: Callable[[], bool]
    request_input_monitoring_permission: Callable[[], bool | None]
    warn_missing_accessibility_permission: Callable[[], None]
    warn_missing_input_monitoring_permission: Callable[[], None]


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


def _empty_input_devices() -> list[AudioDeviceInfo]:
    """Возвращает пустой список устройств ввода по умолчанию."""
    return []


def _create_null_hotkey_listener(_app: Any) -> _NullHotkeyListener:
    """Создаёт no-op dispatcher горячих клавиш по умолчанию."""
    return _NullHotkeyListener()


def _noop_capture_combination(_title: str, _message: str, _current_combination: str = "") -> str | None:
    """Возвращает отсутствие новой комбинации клавиш по умолчанию."""
    return None


class _NullHotkeyListener:
    """Null-object для runtime-dispatcher'а горячих клавиш."""

    def start(self) -> None:
        """Игнорирует запуск listener'а."""
        return None

    def stop(self) -> None:
        """Игнорирует остановку listener'а."""
        return None

    def update_hotkeys(self, _primary: str, _secondary: str, _llm: str) -> None:
        """Игнорирует обновление набора горячих клавиш."""
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

    def save_input_device_index(self, value: int | None) -> None:
        """Сохраняет индекс микрофона."""
        self._values[Config.DEFAULTS_KEY_INPUT_DEVICE_INDEX] = value

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
        app_preferences: AppPreferences | None = None,
        clipboard_service: ClipboardService | None = None,
        microphone_profiles_service: MicrophoneProfilesService | None = None,
        system_integration_service: SystemIntegrationService | None = None,
        input_device_catalog: InputDeviceCatalogService | None = None,
        hotkey_capture_service: HotkeyCaptureService | None = None,
        hotkey_listener_factory: HotkeyListenerFactoryService | None = None,
        recording_overlay: Any | None = None,
        settings_store: SettingsStoreProtocol | None = None,
    ) -> None:
        self.settings_store = settings_store or _InMemorySettingsStore()
        self.recorder = recorder
        self.transcriber = transcriber
        self.llm_processor = llm_processor
        self.launch_config = launch_config
        self.app_preferences = app_preferences or AppPreferences.from_store(self.settings_store)
        self.hotkey_status = self.launch_config.hotkeys.hotkey_status
        self.secondary_hotkey_status = self.launch_config.hotkeys.secondary_hotkey_status
        self.llm_hotkey_status = self.launch_config.hotkeys.llm_hotkey_status
        self.clipboard_service = clipboard_service or ClipboardService(read_text=lambda: None, write_text=lambda _text: None)
        self.microphone_profiles_service = microphone_profiles_service or MicrophoneProfilesService(
            load_profiles=lambda: [],
            save_profiles=lambda _profiles: None,
        )
        self.system_integration_service = system_integration_service or SystemIntegrationService(
            notify=_null_system_notify,
            get_accessibility_status=_null_permission_status,
            get_input_monitoring_status=_null_permission_status,
            request_accessibility_permission=_null_bool_permission_request,
            request_input_monitoring_permission=_null_optional_permission_request,
            warn_missing_accessibility_permission=_null_permission_warning,
            warn_missing_input_monitoring_permission=_null_permission_warning,
        )
        self.input_device_catalog = input_device_catalog or InputDeviceCatalogService(list_input_devices=_empty_input_devices)
        self.hotkey_capture_service = hotkey_capture_service or HotkeyCaptureService(capture_combination=_noop_capture_combination)
        self.hotkey_listener_factory = hotkey_listener_factory or HotkeyListenerFactoryService(
            create_listener=_create_null_hotkey_listener,
        )
        self.recording_overlay = recording_overlay or _NullRecordingOverlay()

        self.model_options = list(Config.MODEL_PRESETS)
        if self.launch_config.model not in self.model_options:
            self.model_options.insert(0, self.launch_config.model)
        self.max_time_options: list[float | None] = list(Config.MAX_TIME_PRESETS)
        if self.launch_config.max_time not in self.max_time_options:
            self.max_time_options.insert(0, self.launch_config.max_time)

        self.model_name = self.launch_config.model.rsplit("/", maxsplit=1)[-1]
        self.input_devices = self.input_device_catalog.list_input_devices()
        initial_language = self.languages[0] if self.languages is not None else None
        if self.languages is not None and self.app_preferences.selected_language in self.languages:
            initial_language = self.app_preferences.selected_language
        self.current_language = initial_language

        self.current_input_device = next((device for device in self.input_devices if device["is_default"]), None)
        saved_input_device_index = self.app_preferences.selected_input_device_index
        if saved_input_device_index is not None:
            saved_input_device = next(
                (device for device in self.input_devices if device["index"] == saved_input_device_index),
                None,
            )
            if saved_input_device is not None:
                self.current_input_device = saved_input_device
        if self.current_input_device is None and self.input_devices:
            self.current_input_device = self.input_devices[0]

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
        self.show_recording_notification = self.app_preferences.show_recording_notification
        self.show_recording_overlay = self.app_preferences.show_recording_overlay
        self.started = False
        self.start_time = 0.0
        self.elapsed_time = 0
        self.key_listener: Any = None
        self._llm_downloading = False

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
        )
        self.hotkey_management_use_cases = HotkeyManagementUseCases(
            runtime=self,
            settings_store=self.settings_store,
            system_integration_service=self.system_integration_service,
            capture_hotkey_combination=self.hotkey_capture_service.capture_combination,
            publish_snapshot=self._notify_subscribers,
        )

        self.recorder.set_input_device(self.current_input_device)
        if hasattr(self.recorder, "set_performance_mode"):
            self.recorder.set_performance_mode(self.performance_mode)
        if hasattr(self.recorder, "set_error_callback"):
            self.recorder.set_error_callback(self.system_integration_service.notify)
        if self.llm_processor is not None:
            self.llm_processor.set_performance_mode(self.performance_mode)
        self.recorder.set_status_callback(self.set_state)
        self.recorder.set_permission_callback(self.set_permission_status)
        self.transcriber.history_callback = self._notify_subscribers
        self.transcriber.token_usage_callback = self._notify_subscribers
        self._refresh_hotkey_statuses()

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
            primary_key_combination=self.primary_key_combination,
            secondary_key_combination=self.secondary_key_combination,
            llm_key_combination=self.llm_key_combination,
            llm_prompt_name=self.llm_prompt_name,
            performance_mode=self.performance_mode,
            max_time=self.max_time,
            max_time_options=list(self.max_time_options),
            model_options=list(self.model_options),
            languages=None if self.languages is None else list(self.languages),
            current_language=self.current_language,
            input_devices=list(self.input_devices),
            current_input_device=self.current_input_device,
            permission_status=dict(self.permission_status),
            microphone_profiles=list(self.microphone_profiles),
            show_recording_notification=self.show_recording_notification,
            show_recording_overlay=self.show_recording_overlay,
            private_mode_enabled=bool(getattr(self.transcriber, "private_mode_enabled", False)),
            paste_cgevent_enabled=bool(getattr(self.transcriber, "paste_cgevent_enabled", True)),
            paste_ax_enabled=bool(getattr(self.transcriber, "paste_ax_enabled", False)),
            paste_clipboard_enabled=bool(getattr(self.transcriber, "paste_clipboard_enabled", False)),
            llm_clipboard_enabled=bool(getattr(self.transcriber, "llm_clipboard_enabled", True)),
            history=list(getattr(self.transcriber, "history", [])),
            total_tokens=int(getattr(self.transcriber, "total_tokens", 0)),
            llm_download_title=self._llm_download_title,
            llm_download_interactive=not self._llm_downloading and not self._is_llm_model_cached(),
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
        self._notify_subscribers()

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

    def change_performance_mode(self, performance_mode: object) -> None:
        """Меняет баланс между задержкой и ресурсами."""
        self.settings_use_cases.change_performance_mode(performance_mode)

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
        self.recording_use_cases.on_status_tick()

    def toggle(self) -> None:
        """Переключает обычный сценарий записи."""
        self.recording_use_cases.toggle()

    def toggle_llm(self) -> None:
        """Переключает сценарий запись → Whisper → LLM."""
        self.llm_pipeline_use_cases.toggle_llm()

    def handle_escape_keycode(self, keycode: int) -> None:
        """Отменяет запись при нажатии Escape."""
        self.recording_use_cases.handle_escape_keycode(keycode)

    def cancel_recording(self) -> None:
        """Отменяет активную запись без распознавания."""
        self.recording_use_cases.cancel_recording()

    def _is_llm_model_cached(self) -> bool:
        """Проверяет, что LLM-модель уже доступна локально."""
        return self.llm_pipeline_use_cases.is_model_cached()

    def download_llm_model(self) -> None:
        """Запускает загрузку LLM-модели и публикует прогресс в snapshot."""
        self.llm_pipeline_use_cases.download_llm_model()

    def change_llm_prompt(self, prompt_name: str) -> None:
        """Переключает текущий пресет системного промпта LLM."""
        self.settings_use_cases.change_llm_prompt(prompt_name)
