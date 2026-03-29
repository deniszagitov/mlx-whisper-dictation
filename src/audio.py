"""Запись звука и работа с устройствами ввода приложения Dictator.

Содержит класс Recorder для записи аудио с микрофона, а также утилиты
для перечисления и отображения устройств ввода.
"""

import logging
import threading

import numpy as np
import pyaudio

from config import STATUS_IDLE, STATUS_LLM_PROCESSING, STATUS_TRANSCRIBING
from permissions import notify_user

LOGGER = logging.getLogger(__name__)

PERFORMANCE_MODE_NORMAL = "normal"
PERFORMANCE_MODE_FAST = "fast"
NORMAL_FRAMES_PER_BUFFER = 2048
FAST_FRAMES_PER_BUFFER = 512


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
        self.llm_processor = None
        self.llm_system_prompt = ""
        self.llm_prompt_name = ""
        self.status_callback = None
        self.permission_callback = None
        self.input_device_index = None
        self.input_device_name = "системный по умолчанию"
        self.performance_mode = PERFORMANCE_MODE_NORMAL
        self.frames_per_buffer = NORMAL_FRAMES_PER_BUFFER
        self._request_lock = threading.Lock()
        self._next_request_id = 0
        self._latest_request_id = 0

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

    def set_performance_mode(self, performance_mode):
        """Переключает режим работы записи и связанных подсистем."""
        normalized_mode = performance_mode if performance_mode == PERFORMANCE_MODE_FAST else PERFORMANCE_MODE_NORMAL
        self.performance_mode = normalized_mode
        self.frames_per_buffer = FAST_FRAMES_PER_BUFFER if normalized_mode == PERFORMANCE_MODE_FAST else NORMAL_FRAMES_PER_BUFFER

        if self.llm_processor is not None and hasattr(self.llm_processor, "set_performance_mode"):
            self.llm_processor.set_performance_mode(normalized_mode)

    def start(self, language=None):
        """Запускает запись в отдельном потоке.

        Args:
            language: Необязательный код языка для последующего распознавания.
        """
        request_id = self._begin_request()
        thread = threading.Thread(target=self._record_impl, args=(language, request_id))
        thread.daemon = True
        thread.start()

    def start_llm(self, language=None):
        """Запускает запись с последующей обработкой через LLM.

        Args:
            language: Необязательный код языка для последующего распознавания.
        """
        request_id = self._begin_request()
        thread = threading.Thread(target=self._record_llm_impl, args=(language, request_id))
        thread.daemon = True
        thread.start()

    def stop(self):
        """Останавливает активную запись."""
        self.recording = False

    def _begin_request(self):
        """Регистрирует новый запрос записи и возвращает его идентификатор."""
        with self._request_lock:
            self._next_request_id += 1
            self._latest_request_id = self._next_request_id
            return self._latest_request_id

    def _is_request_current(self, request_id):
        """Проверяет, что запрос всё ещё последний и может менять UI/вывод."""
        with self._request_lock:
            return request_id == self._latest_request_id

    def _set_status_if_current(self, request_id, status):
        """Обновляет статус только для актуального запроса."""
        if self._is_request_current(request_id):
            self._set_status(status)

    def should_deliver_llm_result(self, request_id):
        """Разрешает вывод результата LLM только для актуального запроса."""
        return self._is_request_current(request_id)

    def _record_impl(self, language, request_id):
        """Выполняет запись, конвертацию аудио и запуск распознавания.

        Args:
            language: Необязательный код языка для последующего распознавания.
            request_id: Идентификатор активного запроса записи для защиты от гонок.
        """
        self.recording = True
        frames_per_buffer = self.frames_per_buffer
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
            self._set_status_if_current(request_id, STATUS_IDLE)
            return

        audio_data = np.frombuffer(b"".join(frames), dtype=np.int16)
        audio_data_fp32 = audio_data.astype(np.float32) / 32768.0
        LOGGER.info(
            "✅ Запись завершена: фреймов=%s, сэмплов=%s, длительность=%.2f с",
            len(frames),
            len(audio_data_fp32),
            len(audio_data_fp32) / 16000,
        )
        self._set_status_if_current(request_id, STATUS_TRANSCRIBING)
        self.transcriber.transcribe(audio_data_fp32, language)
        self._set_status_if_current(request_id, STATUS_IDLE)

    def _record_llm_impl(self, language, request_id):
        """Выполняет запись и передаёт аудио в LLM-пайплайн.

        Args:
            language: Необязательный код языка для последующего распознавания.
            request_id: Идентификатор активного запроса записи для защиты от гонок.
        """
        self.recording = True
        frames_per_buffer = self.frames_per_buffer
        audio_interface = pyaudio.PyAudio()
        stream = None
        frames = []

        try:
            LOGGER.info(
                "🎙️🤖 Открываю поток записи для LLM: input_device_index=%s, input_device_name=%s",
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
            LOGGER.exception("❌ Ошибка записи (LLM-пайплайн)")
            notify_user("MLX Whisper Dictation", "Ошибка записи с микрофона. Смотрите stderr.log.")
            return
        finally:
            if stream is not None:
                stream.stop_stream()
                stream.close()
            audio_interface.terminate()

        if not frames:
            LOGGER.warning("⚠️ Запись остановлена без аудиофреймов (LLM-пайплайн)")
            self._set_status_if_current(request_id, STATUS_IDLE)
            return

        audio_data = np.frombuffer(b"".join(frames), dtype=np.int16)
        audio_data_fp32 = audio_data.astype(np.float32) / 32768.0
        LOGGER.info(
            "✅ Запись для LLM завершена: фреймов=%s, длительность=%.2f с",
            len(frames),
            len(audio_data_fp32) / 16000,
        )
        self._set_status_if_current(request_id, STATUS_TRANSCRIBING)
        self.transcriber.transcribe_for_llm(
            audio_data_fp32,
            language,
            llm_processor=self.llm_processor,
            system_prompt=self.llm_system_prompt,
            prompt_name=self.llm_prompt_name,
            on_llm_processing_started=lambda: self._set_status_if_current(request_id, STATUS_LLM_PROCESSING),
            should_deliver_result=lambda: self.should_deliver_llm_result(request_id),
        )
        self._set_status_if_current(request_id, STATUS_IDLE)
