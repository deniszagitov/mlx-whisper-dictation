"""Runtime-запись звука и перечисление устройств ввода через PyAudio."""

from __future__ import annotations

import logging
import threading
from typing import TYPE_CHECKING, Any

import numpy as np
import pyaudio

from ..domain.constants import Config

if TYPE_CHECKING:
    from collections.abc import Callable

    from ..domain.types import AudioDeviceInfo

LOGGER = logging.getLogger(__name__)

PERFORMANCE_MODE_NORMAL = "normal"
PERFORMANCE_MODE_FAST = "fast"
NORMAL_FRAMES_PER_BUFFER = 2048
FAST_FRAMES_PER_BUFFER = 512
DEFAULT_SAMPLE_RATE = 16000
DEFAULT_CHANNELS = 1
RETRYABLE_AUDIO_ERROR_CODES = {-9998, -9996}
PERMISSION_ERROR_CODES = {-9996}


class Recorder:
    """Записывает звук с микрофона."""

    def __init__(self) -> None:
        """Создает объект записи."""
        self.recording = False
        self.cancelled = False
        self.status_callback: Callable[[str], None] | None = None
        self.permission_callback: Callable[[str, bool], None] | None = None
        self.error_callback: Callable[[str, str], None] | None = None
        self.runtime_error_callback: Callable[[str, str], None] | None = None
        self.input_device_index: int | None = None
        self.input_device_name = "системный по умолчанию"
        self.performance_mode = PERFORMANCE_MODE_NORMAL
        self.frames_per_buffer = NORMAL_FRAMES_PER_BUFFER
        self._request_lock = threading.Lock()
        self._next_request_id = 0
        self._latest_request_id = 0

    def set_status_callback(self, status_callback: Callable[[str], None]) -> None:
        """Регистрирует callback для обновления UI-статуса."""
        self.status_callback = status_callback

    def _set_status(self, status: str) -> None:
        """Передает новый статус во внешний callback."""
        if self.status_callback is not None:
            self.status_callback(status)

    def set_permission_callback(self, permission_callback: Callable[[str, bool], None]) -> None:
        """Регистрирует callback для обновления статусов разрешений."""
        self.permission_callback = permission_callback

    def _set_permission_status(self, permission_name: str, status: bool) -> None:
        """Передает обновленный статус разрешения во внешний callback."""
        if self.permission_callback is not None:
            self.permission_callback(permission_name, status)

    def set_error_callback(self, error_callback: Callable[[str, str], None]) -> None:
        """Регистрирует callback уведомления о runtime-ошибках записи."""
        self.error_callback = error_callback

    def _notify_error(self, title: str, message: str) -> None:
        """Уведомляет внешний слой о runtime-ошибке записи."""
        if self.error_callback is not None:
            self.error_callback(title, message)

    def set_runtime_error_callback(self, runtime_error_callback: Callable[[str, str], None]) -> None:
        """Регистрирует callback для восстановления runtime-состояния после ошибки записи."""
        self.runtime_error_callback = runtime_error_callback

    def _notify_runtime_error(self, title: str, message: str) -> None:
        """Уведомляет orchestration-слой о необходимости сбросить состояние записи."""
        if self.runtime_error_callback is not None:
            self.runtime_error_callback(title, message)

    def set_input_device(self, device_info: AudioDeviceInfo | None = None) -> None:
        """Сохраняет выбранное устройство ввода для последующей записи."""
        if device_info is None:
            self.input_device_index = None
            self.input_device_name = "системный по умолчанию"
            return

        self.input_device_index = int(device_info["index"])
        self.input_device_name = str(device_info["name"])

    def set_performance_mode(self, performance_mode: str) -> None:
        """Переключает режим работы записи и связанных подсистем."""
        normalized_mode = performance_mode if performance_mode == PERFORMANCE_MODE_FAST else PERFORMANCE_MODE_NORMAL
        self.performance_mode = normalized_mode
        self.frames_per_buffer = FAST_FRAMES_PER_BUFFER if normalized_mode == PERFORMANCE_MODE_FAST else NORMAL_FRAMES_PER_BUFFER

    def start(self, language: str | None = None, on_audio_ready: Callable[..., None] | None = None) -> None:
        """Запускает запись в отдельном потоке."""
        request_id = self._begin_request()
        thread = threading.Thread(target=self._record_impl, args=(language, request_id, on_audio_ready))
        thread.daemon = True
        thread.start()

    def stop(self) -> None:
        """Останавливает активную запись."""
        self.recording = False

    def cancel(self) -> None:
        """Отменяет запись без последующего распознавания."""
        self.cancelled = True
        self.recording = False

    def _begin_request(self) -> int:
        """Регистрирует новый запрос записи и возвращает его идентификатор."""
        with self._request_lock:
            self._next_request_id += 1
            self._latest_request_id = self._next_request_id
            return self._latest_request_id

    def _is_request_current(self, request_id: int) -> bool:
        """Проверяет, что запрос всё ещё последний и может менять UI/вывод."""
        with self._request_lock:
            return request_id == self._latest_request_id

    def _set_status_if_current(self, request_id: int, status: str) -> None:
        """Обновляет статус только для актуального запроса."""
        if self._is_request_current(request_id):
            self._set_status(status)

    def _audio_error_code(self, error: BaseException) -> int | None:
        """Извлекает числовой код ошибки PortAudio/PyAudio, если он доступен."""
        error_args = getattr(error, "args", ())
        if not error_args:
            return None
        candidate = error_args[0]
        if isinstance(candidate, int):
            return candidate
        if isinstance(candidate, str) and candidate.lstrip("-").isdigit():
            return int(candidate)
        return None

    def _should_retry_with_default_device(self, error: BaseException) -> bool:
        """Определяет, стоит ли повторить открытие потока через default input device."""
        error_code = self._audio_error_code(error)
        return self.input_device_index is not None and error_code in RETRYABLE_AUDIO_ERROR_CODES

    def _can_open_stream(self, audio_interface: pyaudio.PyAudio, *, device_index: int | None) -> bool:
        """Проверяет поддержку текущего аудиоформата до открытия stream."""
        try:
            return bool(
                audio_interface.is_format_supported(
                    DEFAULT_SAMPLE_RATE,
                    input_device=device_index,
                    input_channels=DEFAULT_CHANNELS,
                    input_format=pyaudio.paInt16,
                )
            )
        except ValueError as error:
            LOGGER.warning(
                "🎙️ Формат записи не поддерживается: input_device_index=%s, error=%s",
                device_index,
                error,
            )
            return False
        except Exception:
            LOGGER.warning(
                "🎙️ Не удалось выполнить preflight формата записи: input_device_index=%s",
                device_index,
                exc_info=True,
            )
            return True

    def _open_stream(self, audio_interface: pyaudio.PyAudio, *, frames_per_buffer: int) -> Any:
        """Открывает поток записи, при необходимости повторяя попытку через default input."""
        requested_device_index = self.input_device_index
        open_kwargs = {
            "format": pyaudio.paInt16,
            "channels": DEFAULT_CHANNELS,
            "rate": DEFAULT_SAMPLE_RATE,
            "frames_per_buffer": frames_per_buffer,
            "input": True,
            "input_device_index": requested_device_index,
        }

        LOGGER.info(
            "🎙️ Открываю поток записи: input_device_index=%s, input_device_name=%s",
            requested_device_index,
            self.input_device_name,
        )

        if not self._can_open_stream(audio_interface, device_index=requested_device_index):
            raise OSError(-9998, "Invalid number of channels")

        try:
            return audio_interface.open(**open_kwargs)
        except OSError as error:
            if not self._should_retry_with_default_device(error):
                raise

            LOGGER.warning(
                "🎙️ Поток не открылся для выбранного микрофона, повторяю через системный default: index=%s, name=%s, error=%s",
                requested_device_index,
                self.input_device_name,
                error,
            )
            open_kwargs["input_device_index"] = None
            if not self._can_open_stream(audio_interface, device_index=None):
                raise
            stream = audio_interface.open(**open_kwargs)
            self.input_device_index = None
            self.input_device_name = "системный по умолчанию"
            return stream

    def _record_impl(self, language: str | None, request_id: int, on_audio_ready: Callable[..., None] | None = None) -> None:
        """Выполняет запись, конвертацию аудио и запуск распознавания."""
        self.recording = True
        self.cancelled = False
        frames_per_buffer = self.frames_per_buffer
        audio_interface = pyaudio.PyAudio()
        stream = None
        frames = []

        try:
            stream = self._open_stream(audio_interface, frames_per_buffer=frames_per_buffer)
            self._set_permission_status("microphone", True)

            while self.recording:
                data = stream.read(frames_per_buffer, exception_on_overflow=False)
                frames.append(data)
        except Exception as error:
            self.recording = False
            self.cancelled = False
            if self._audio_error_code(error) in PERMISSION_ERROR_CODES:
                self._set_permission_status("microphone", False)
            LOGGER.exception("❌ Ошибка записи")
            message = "Ошибка записи с микрофона. Смотрите stderr.log."
            if self._audio_error_code(error) in RETRYABLE_AUDIO_ERROR_CODES:
                message = (
                    "После сна macOS аудиоустройство стало недоступно или сменило конфигурацию. "
                    "Список микрофонов обновлён, попробуйте начать запись ещё раз."
                )
            self._notify_error("MLX Whisper Dictation", message)
            self._notify_runtime_error("MLX Whisper Dictation", message)
            return
        finally:
            if stream is not None:
                stream.stop_stream()
                stream.close()
            audio_interface.terminate()
            self.recording = False

        if not frames:
            LOGGER.warning("⚠️ Запись остановлена без захваченных аудиофреймов")
            self._set_status_if_current(request_id, Config.STATUS_IDLE)
            return

        if self.cancelled:
            self.cancelled = False
            LOGGER.info("❌ Запись отменена, аудио отброшено (фреймов=%s)", len(frames))
            self._set_status_if_current(request_id, Config.STATUS_IDLE)
            return

        audio_data = np.frombuffer(b"".join(frames), dtype=np.int16)
        audio_data_fp32 = audio_data.astype(np.float32) / 32768.0
        LOGGER.info(
            "✅ Запись завершена: фреймов=%s, сэмплов=%s, длительность=%.2f с",
            len(frames),
            len(audio_data_fp32),
            len(audio_data_fp32) / 16000,
        )

        def set_status(status: str) -> None:
            self._set_status_if_current(request_id, status)

        def is_current() -> bool:
            return self._is_request_current(request_id)

        set_status(Config.STATUS_TRANSCRIBING)
        if on_audio_ready is not None:
            on_audio_ready(audio_data_fp32, language, set_status, is_current)
        set_status(Config.STATUS_IDLE)


def list_input_devices() -> list[AudioDeviceInfo]:
    """Возвращает список доступных устройств ввода из PyAudio."""
    audio_interface = pyaudio.PyAudio()
    devices: list[AudioDeviceInfo] = []
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
            normalized: AudioDeviceInfo = {
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
