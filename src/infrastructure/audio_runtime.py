"""Runtime-запись звука и перечисление устройств ввода через PyAudio."""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

import numpy as np
import pyaudio

from ..domain.audio import audio_profile_for_input_device
from ..domain.constants import Config
from ..domain.types import RecordedAudio

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


@dataclass(frozen=True, slots=True)
class _StreamCandidate:
    """Кандидат формата открытия PyAudio stream."""

    sample_rate: int
    pyaudio_format: int
    sample_format: str


@dataclass(frozen=True, slots=True)
class _OpenedStream:
    """Открытый PyAudio stream с фактическими параметрами записи."""

    stream: Any
    sample_rate: int
    channels: int
    sample_format: str
    profile_name: str


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
        self.input_device_default_sample_rate = float(DEFAULT_SAMPLE_RATE)
        self.input_device_host_api_name: str | None = None
        self.performance_mode = PERFORMANCE_MODE_NORMAL
        self.frames_per_buffer = NORMAL_FRAMES_PER_BUFFER
        self.high_quality_mac_builtin_enabled = True
        self.post_roll_ms = Config.AUDIO_POST_ROLL_MS_DEFAULT
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
            self.input_device_default_sample_rate = float(DEFAULT_SAMPLE_RATE)
            self.input_device_host_api_name = None
            return

        self.input_device_index = int(device_info["index"])
        self.input_device_name = str(device_info["name"])
        self.input_device_default_sample_rate = float(device_info.get("default_sample_rate", DEFAULT_SAMPLE_RATE))
        self.input_device_host_api_name = device_info.get("host_api_name")

    def set_high_quality_mac_builtin(self, enabled: object) -> None:
        """Переключает автоматический MacBook HQ-профиль записи."""
        self.high_quality_mac_builtin_enabled = bool(enabled)

    def set_post_roll_ms(self, post_roll_ms: object) -> None:
        """Сохраняет длительность хвоста записи после stop()."""
        if isinstance(post_roll_ms, bool):
            value = int(post_roll_ms)
        elif isinstance(post_roll_ms, int):
            value = post_roll_ms
        elif isinstance(post_roll_ms, float):
            value = int(post_roll_ms)
        elif isinstance(post_roll_ms, str):
            try:
                value = int(post_roll_ms.strip())
            except ValueError:
                value = Config.AUDIO_POST_ROLL_MS_DEFAULT
        else:
            value = Config.AUDIO_POST_ROLL_MS_DEFAULT
        self.post_roll_ms = min(max(value, Config.AUDIO_POST_ROLL_MS_MIN), Config.AUDIO_POST_ROLL_MS_MAX)

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

    def _current_device_info(self) -> AudioDeviceInfo | None:
        """Возвращает текущие параметры выбранного устройства ввода."""
        if self.input_device_index is None:
            return None
        return {
            "index": self.input_device_index,
            "name": self.input_device_name,
            "max_input_channels": DEFAULT_CHANNELS,
            "default_sample_rate": self.input_device_default_sample_rate,
            "is_default": False,
            "host_api_name": self.input_device_host_api_name,
        }

    def _current_audio_profile(self) -> str:
        """Выбирает аудиопрофиль для следующей записи."""
        profile_name = audio_profile_for_input_device(
            self._current_device_info(),
            high_quality_mac_builtin_enabled=self.high_quality_mac_builtin_enabled,
        )
        if profile_name == Config.AUDIO_PROFILE_MACBOOK_BUILTIN_HIGH_QUALITY:
            LOGGER.info(
                "🎙️ Включён аудиопрофиль MacBook HQ: input_device_index=%s, input_device_name=%s, host_api=%s",
                self.input_device_index,
                self.input_device_name,
                self.input_device_host_api_name,
            )
        return profile_name

    def _stream_candidates(self, profile_name: str) -> list[_StreamCandidate]:
        """Возвращает порядок форматов открытия stream."""
        if profile_name != Config.AUDIO_PROFILE_MACBOOK_BUILTIN_HIGH_QUALITY:
            return [_StreamCandidate(DEFAULT_SAMPLE_RATE, pyaudio.paInt16, "int16")]

        native_sample_rate = round(self.input_device_default_sample_rate) or DEFAULT_SAMPLE_RATE
        return [
            _StreamCandidate(native_sample_rate, pyaudio.paFloat32, "float32"),
            _StreamCandidate(native_sample_rate, pyaudio.paInt16, "int16"),
            _StreamCandidate(DEFAULT_SAMPLE_RATE, pyaudio.paInt16, "int16"),
        ]

    def _can_open_stream(
        self,
        audio_interface: pyaudio.PyAudio,
        *,
        device_index: int | None,
        candidate: _StreamCandidate,
    ) -> bool:
        """Проверяет поддержку текущего аудиоформата до открытия stream."""
        try:
            return bool(
                audio_interface.is_format_supported(
                    candidate.sample_rate,
                    input_device=device_index,
                    input_channels=DEFAULT_CHANNELS,
                    input_format=candidate.pyaudio_format,
                )
            )
        except ValueError as error:
            LOGGER.warning(
                "🎙️ Формат записи не поддерживается: input_device_index=%s, sample_rate=%s, format=%s, error=%s",
                device_index,
                candidate.sample_rate,
                candidate.sample_format,
                error,
            )
            return False
        except Exception:
            LOGGER.warning(
                "🎙️ Не удалось выполнить preflight формата записи: input_device_index=%s, sample_rate=%s, format=%s",
                device_index,
                candidate.sample_rate,
                candidate.sample_format,
                exc_info=True,
            )
            return True

    def _open_candidate(
        self,
        audio_interface: pyaudio.PyAudio,
        *,
        device_index: int | None,
        frames_per_buffer: int,
        candidate: _StreamCandidate,
        profile_name: str,
    ) -> _OpenedStream:
        """Открывает stream с одним набором параметров."""
        if not self._can_open_stream(audio_interface, device_index=device_index, candidate=candidate):
            raise OSError(-9998, "Unsupported input format")

        stream = audio_interface.open(
            format=candidate.pyaudio_format,
            channels=DEFAULT_CHANNELS,
            rate=candidate.sample_rate,
            frames_per_buffer=frames_per_buffer,
            input=True,
            input_device_index=device_index,
        )
        return _OpenedStream(
            stream=stream,
            sample_rate=candidate.sample_rate,
            channels=DEFAULT_CHANNELS,
            sample_format=candidate.sample_format,
            profile_name=profile_name,
        )

    def _open_stream(self, audio_interface: pyaudio.PyAudio, *, frames_per_buffer: int) -> _OpenedStream:
        """Открывает поток записи, при необходимости повторяя попытку через default input."""
        requested_device_index = self.input_device_index
        profile_name = self._current_audio_profile()
        candidates = self._stream_candidates(profile_name)

        LOGGER.info(
            "🎙️ Открываю поток записи: input_device_index=%s, input_device_name=%s, profile=%s",
            requested_device_index,
            self.input_device_name,
            profile_name,
        )

        last_error: OSError | None = None
        for candidate in candidates:
            try:
                return self._open_candidate(
                    audio_interface,
                    device_index=requested_device_index,
                    frames_per_buffer=frames_per_buffer,
                    candidate=candidate,
                    profile_name=profile_name,
                )
            except OSError as error:
                last_error = error
                if self._audio_error_code(error) not in RETRYABLE_AUDIO_ERROR_CODES:
                    raise
                LOGGER.warning(
                    "🎙️ Не открылся кандидат записи: input_device_index=%s, sample_rate=%s, format=%s, error=%s",
                    requested_device_index,
                    candidate.sample_rate,
                    candidate.sample_format,
                    error,
                )

        if last_error is None:
            last_error = OSError(-9998, "No supported input format")

        if not self._should_retry_with_default_device(last_error):
            raise last_error

        LOGGER.warning(
            "🎙️ Поток не открылся для выбранного микрофона, повторяю через системный default: index=%s, name=%s, error=%s",
            requested_device_index,
            self.input_device_name,
            last_error,
        )
        default_candidate = _StreamCandidate(DEFAULT_SAMPLE_RATE, pyaudio.paInt16, "int16")
        opened = self._open_candidate(
            audio_interface,
            device_index=None,
            frames_per_buffer=frames_per_buffer,
            candidate=default_candidate,
            profile_name=Config.AUDIO_PROFILE_GENERIC,
        )
        self.input_device_index = None
        self.input_device_name = "системный по умолчанию"
        self.input_device_default_sample_rate = float(DEFAULT_SAMPLE_RATE)
        self.input_device_host_api_name = None
        return opened

    def _record_impl(self, language: str | None, request_id: int, on_audio_ready: Callable[..., None] | None = None) -> None:
        """Выполняет запись, конвертацию аудио и запуск распознавания."""
        self.recording = True
        self.cancelled = False
        frames_per_buffer = self.frames_per_buffer
        audio_interface = pyaudio.PyAudio()
        opened_stream: _OpenedStream | None = None
        frames = []

        try:
            opened_stream = self._open_stream(audio_interface, frames_per_buffer=frames_per_buffer)
            stream = opened_stream.stream
            self._set_permission_status("microphone", True)

            while self.recording:
                data = stream.read(frames_per_buffer, exception_on_overflow=False)
                frames.append(data)

            if not self.cancelled:
                post_roll_frames = int(opened_stream.sample_rate * (self.post_roll_ms / 1000.0))
                remaining_frames = post_roll_frames
                while remaining_frames > 0:
                    chunk_frames = min(frames_per_buffer, remaining_frames)
                    data = stream.read(chunk_frames, exception_on_overflow=False)
                    frames.append(data)
                    remaining_frames -= chunk_frames
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
            if opened_stream is not None:
                opened_stream.stream.stop_stream()
                opened_stream.stream.close()
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

        assert opened_stream is not None
        sample_dtype = np.float32 if opened_stream.sample_format == "float32" else np.int16
        audio_data = np.frombuffer(b"".join(frames), dtype=sample_dtype)
        device_index = self.input_device_index
        device_name = None if self.input_device_name == "системный по умолчанию" else self.input_device_name
        recorded_audio = RecordedAudio(
            samples=audio_data,
            sample_rate=opened_stream.sample_rate,
            channels=opened_stream.channels,
            sample_format=opened_stream.sample_format,
            device_index=device_index,
            device_name=device_name,
            profile_name=opened_stream.profile_name,
            metadata={
                "pre_roll_ms": 0,
                "post_roll_ms": self.post_roll_ms,
                "frames_per_buffer": frames_per_buffer,
                "frame_chunks": len(frames),
                "host_api_name": self.input_device_host_api_name,
            },
        )
        LOGGER.info(
            "✅ Запись завершена: фреймов=%s, сэмплов=%s, длительность=%.2f с, sample_rate=%s, format=%s, profile=%s",
            len(frames),
            len(audio_data),
            len(audio_data) / max(opened_stream.sample_rate, 1),
            opened_stream.sample_rate,
            opened_stream.sample_format,
            opened_stream.profile_name,
        )

        def set_status(status: str) -> None:
            self._set_status_if_current(request_id, status)

        def is_current() -> bool:
            return self._is_request_current(request_id)

        set_status(Config.STATUS_TRANSCRIBING)
        if on_audio_ready is not None:
            on_audio_ready(recorded_audio, language, set_status, is_current)
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
            host_api_name = None
            host_api_index = info.get("hostApi")
            if host_api_index is not None and hasattr(audio_interface, "get_host_api_info_by_index"):
                try:
                    host_api_info = audio_interface.get_host_api_info_by_index(int(host_api_index))
                    host_api_name = str(host_api_info.get("name", "")).strip() or None
                except Exception:
                    LOGGER.debug("🎙️ Не удалось прочитать host API устройства index=%s", device_index, exc_info=True)
            normalized: AudioDeviceInfo = {
                "index": int(info.get("index", device_index)),
                "name": str(info.get("name", f"Input {device_index}")),
                "max_input_channels": int(info.get("maxInputChannels", 0)),
                "default_sample_rate": float(info.get("defaultSampleRate", 16000.0)),
                "is_default": int(info.get("index", device_index)) == default_input,
                "host_api_name": host_api_name,
            }
            devices.append(normalized)
    finally:
        audio_interface.terminate()

    devices.sort(key=lambda item: (not item["is_default"], item["index"]))
    return devices
