"""Протоколы внешних зависимостей доменного и прикладного слоя."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Protocol

if TYPE_CHECKING:
    from .types import AudioDeviceInfo, AudioDiagnostics, HistoryRecord, MicrophoneProfile


class ToggleableApp(Protocol):
    """Протокол приложения, управляемого через горячие клавиши."""

    started: bool

    def toggle(self) -> None:
        """Переключает приложение между состояниями записи и ожидания."""
        ...


class RecorderProtocol(Protocol):
    """Протокол runtime-записи звука."""

    def start(self, language: str | None = None, on_audio_ready: Any | None = None) -> None:
        """Запускает запись."""
        ...

    def stop(self) -> None:
        """Останавливает запись."""
        ...

    def cancel(self) -> None:
        """Отменяет запись."""
        ...

    def set_input_device(self, device_info: AudioDeviceInfo | None = None) -> None:
        """Меняет активное устройство ввода."""
        ...

    def set_performance_mode(self, performance_mode: str) -> None:
        """Переключает режим производительности."""
        ...

    def set_status_callback(self, status_callback: Any) -> None:
        """Регистрирует callback статуса."""
        ...

    def set_permission_callback(self, permission_callback: Any) -> None:
        """Регистрирует callback разрешений."""
        ...

    def set_error_callback(self, error_callback: Any) -> None:
        """Регистрирует callback ошибок."""
        ...


class RecordingOverlayProtocol(Protocol):
    """Протокол overlay-индикатора записи."""

    def show(self) -> None:
        """Показывает overlay."""
        ...

    def hide(self) -> None:
        """Скрывает overlay."""
        ...

    def update_time(self, elapsed_seconds: int) -> None:
        """Обновляет таймер overlay."""
        ...


class DiagnosticsStoreProtocol(Protocol):
    """Протокол persistence диагностических артефактов."""

    def artifact_stem(self) -> str:
        """Возвращает stem для новой группы артефактов."""
        ...

    def save_audio_recording(
        self,
        stem: str,
        audio_data: Any,
        diagnostics: AudioDiagnostics,
    ) -> None:
        """Сохраняет WAV-артефакт записи."""
        ...

    def save_transcription_artifacts(
        self,
        stem: str,
        diagnostics: AudioDiagnostics,
        result: Any = None,
        text: str = "",
        error_message: str | None = None,
    ) -> None:
        """Сохраняет артефакты распознавания."""
        ...


class SettingsStoreProtocol(Protocol):
    """Протокол чтения и записи runtime-настроек."""

    def load_bool(self, key: str, fallback: bool) -> bool:
        """Читает bool."""
        ...

    def save_bool(self, key: str, value: bool) -> None:
        """Сохраняет bool."""
        ...

    def load_list(self, key: str) -> list[str]:
        """Читает список строк."""
        ...

    def save_list(self, key: str, value: list[str]) -> None:
        """Сохраняет список строк."""
        ...

    def load_int(self, key: str, fallback: int) -> int:
        """Читает int."""
        ...

    def save_int(self, key: str, value: int) -> None:
        """Сохраняет int."""
        ...

    def load_str(self, key: str, fallback: str | None = None) -> str | None:
        """Читает строку."""
        ...

    def save_str(self, key: str, value: object) -> None:
        """Сохраняет строку."""
        ...

    def load_max_time(self, fallback: int | float | None) -> int | float | None:
        """Читает лимит записи."""
        ...

    def save_max_time(self, value: int | float | None) -> None:
        """Сохраняет лимит записи."""
        ...

    def load_input_device_index(self) -> int | None:
        """Читает индекс микрофона."""
        ...

    def save_input_device_index(self, value: int | None) -> None:
        """Сохраняет индекс микрофона."""
        ...

    def remove_key(self, key: str) -> None:
        """Удаляет ключ."""
        ...


class ClipboardPort(Protocol):
    """Протокол доступа к системному буферу обмена."""

    def read_text(self) -> str | None:
        """Читает текст из буфера."""
        ...

    def write_text(self, text: str) -> None:
        """Пишет текст в буфер."""
        ...


class HistoryStoreProtocol(Protocol):
    """Протокол persistence истории распознанного текста."""

    def load_items(self) -> list[Any]:
        """Читает сырые записи истории."""
        ...

    def save_records(self, records: list[HistoryRecord]) -> None:
        """Сохраняет нормализованные записи истории."""
        ...


class MicrophoneProfilesStoreProtocol(Protocol):
    """Протокол persistence быстрых профилей микрофона."""

    def load_profiles(self) -> list[MicrophoneProfile]:
        """Читает профили."""
        ...

    def save_profiles(self, profiles: list[MicrophoneProfile]) -> None:
        """Сохраняет профили."""
        ...


class SystemIntegrationPort(Protocol):
    """Протокол системных уведомлений и статусов разрешений."""

    def notify(self, title: str, message: str) -> None:
        """Показывает уведомление."""
        ...

    def get_accessibility_status(self) -> bool | None:
        """Возвращает статус Accessibility."""
        ...

    def get_input_monitoring_status(self) -> bool | None:
        """Возвращает статус Input Monitoring."""
        ...

    def request_accessibility_permission(self) -> bool:
        """Повторно запрашивает Accessibility."""
        ...

    def request_input_monitoring_permission(self) -> bool | None:
        """Повторно запрашивает Input Monitoring."""
        ...

    def warn_missing_accessibility_permission(self) -> None:
        """Показывает предупреждение об Accessibility."""
        ...

    def warn_missing_input_monitoring_permission(self) -> None:
        """Показывает предупреждение об Input Monitoring."""
        ...


class InputDeviceCatalogPort(Protocol):
    """Протокол перечисления устройств ввода."""

    def list_input_devices(self) -> list[AudioDeviceInfo]:
        """Возвращает список доступных устройств."""
        ...


class HotkeyRuntimePort(Protocol):
    """Протокол runtime-слушателя хоткеев."""

    def start(self) -> None:
        """Запускает listener."""
        ...

    def stop(self) -> None:
        """Останавливает listener."""
        ...

    def update_key_combinations(self, key_combinations: list[str]) -> None:
        """Обновляет набор активных комбинаций."""
        ...


class HotkeyCapturePort(Protocol):
    """Протокол UI-захвата новой комбинации клавиш."""

    def capture_combination(
        self,
        title: str,
        message: str,
        current_combination: str = "",
    ) -> str | None:
        """Открывает UI захвата хоткея."""
        ...


class LlmGatewayProtocol(Protocol):
    """Протокол доступа к LLM runtime."""

    last_token_usage: int
    download_progress_callback: Any | None

    def is_model_cached(self) -> bool:
        """Проверяет наличие модели в локальном кэше."""
        ...

    def set_performance_mode(self, performance_mode: str) -> None:
        """Меняет стратегию управления памятью."""
        ...

    def process_text(
        self,
        text: str,
        system_prompt: str,
        *,
        context: str | None = None,
    ) -> str:
        """Обрабатывает текст через LLM."""
        ...

    def ensure_model_downloaded(self) -> None:
        """Скачивает модель при необходимости."""
        ...
