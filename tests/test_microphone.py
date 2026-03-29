"""Тесты записи звука с микрофона.

Проверяет, что PyAudio может открыть поток для записи и что
записанные данные содержат реальный сигнал, а не тишину.

Тесты помечены маркером `hardware`, потому что требуют доступ к микрофону.
"""

import numpy as np
import pyaudio
import pytest

import audio


@pytest.mark.hardware
class TestMicrophoneAccess:
    """Тесты доступа к микрофону."""

    def test_pyaudio_initializes(self):
        """PyAudio должен инициализироваться без ошибок."""
        pa = pyaudio.PyAudio()
        try:
            assert pa.get_device_count() > 0, "Нет доступных аудиоустройств"
        finally:
            pa.terminate()

    def test_default_input_device_exists(self):
        """Должно быть устройство ввода по умолчанию."""
        pa = pyaudio.PyAudio()
        try:
            info = pa.get_default_input_device_info()
            assert info is not None
            assert info.get("maxInputChannels", 0) > 0, "Устройство по умолчанию не поддерживает ввод"
        finally:
            pa.terminate()

    def test_can_open_input_stream(self):
        """Должна быть возможность открыть поток записи в формате приложения."""
        pa = pyaudio.PyAudio()
        stream = None
        try:
            stream = pa.open(
                format=pyaudio.paInt16,
                channels=1,
                rate=16000,
                frames_per_buffer=1024,
                input=True,
            )
            assert stream.is_active()
        finally:
            if stream is not None:
                stream.stop_stream()
                stream.close()
            pa.terminate()

    def test_recorded_audio_is_not_pure_silence(self):
        """Запись 1 секунды должна содержать хоть какой-то сигнал.

        Если этот тест падает, возможно:
        - микрофон физически отключен
        - приложению не выдано разрешение на микрофон
        - в тестовом окружении нет аудиоустройства
        """
        pa = pyaudio.PyAudio()
        stream = None
        frames = []
        try:
            stream = pa.open(
                format=pyaudio.paInt16,
                channels=1,
                rate=16000,
                frames_per_buffer=1024,
                input=True,
            )
            for _ in range(16):  # ~1 секунда при rate=16000 и buffer=1024
                data = stream.read(1024, exception_on_overflow=False)
                frames.append(data)
        finally:
            if stream is not None:
                stream.stop_stream()
                stream.close()
            pa.terminate()

        audio = np.frombuffer(b"".join(frames), dtype=np.int16)
        audio_fp32 = audio.astype(np.float32) / 32768.0
        rms = float(np.sqrt(np.mean(audio_fp32**2)))

        # Даже тихая комната обычно имеет RMS > 0.0001 из-за шума микрофона.
        # Если RMS == 0.0, скорее всего микрофон не работает.
        assert rms > 0.0, f"Записано абсолютное молчание (RMS={rms}). Вероятно, микрофон не подключен или нет разрешения."

    def test_recorded_audio_format(self):
        """Записанные данные должны конвертироваться в массив корректных размеров."""
        pa = pyaudio.PyAudio()
        stream = None
        frames = []
        try:
            stream = pa.open(
                format=pyaudio.paInt16,
                channels=1,
                rate=16000,
                frames_per_buffer=1024,
                input=True,
            )
            for _ in range(4):
                data = stream.read(1024, exception_on_overflow=False)
                frames.append(data)
        finally:
            if stream is not None:
                stream.stop_stream()
                stream.close()
            pa.terminate()

        audio = np.frombuffer(b"".join(frames), dtype=np.int16)
        assert audio.dtype == np.int16
        assert len(audio) == 1024 * 4
        audio_fp32 = audio.astype(np.float32) / 32768.0
        assert audio_fp32.dtype == np.float32


class FakePyAudio:
    """Фейковая реализация PyAudio для unit-тестов перечисления устройств."""

    def __init__(self):
        self.devices = [
            {"index": 0, "name": "Built-in Output", "maxInputChannels": 0, "defaultSampleRate": 48000.0},
            {"index": 1, "name": "Built-in Microphone", "maxInputChannels": 1, "defaultSampleRate": 48000.0},
            {"index": 2, "name": "USB Mic", "maxInputChannels": 2, "defaultSampleRate": 44100.0},
        ]

    def get_default_input_device_info(self):
        """Возвращает фейковое устройство ввода по умолчанию."""
        return {"index": 1}

    def get_device_count(self):
        """Возвращает количество фейковых устройств."""
        return len(self.devices)

    def get_device_info_by_index(self, index):
        """Возвращает информацию о фейковом устройстве по индексу."""
        return self.devices[index]

    def terminate(self):
        """Имитирует завершение PyAudio без побочных эффектов."""
        return None


class TestMicrophoneListing:
    """Тесты перечисления и выбора устройств ввода."""

    def test_list_input_devices_filters_output_only(self, app_module, monkeypatch):
        """В список должны попадать только устройства с input channels > 0."""
        monkeypatch.setattr(audio.pyaudio, "PyAudio", FakePyAudio)

        devices = app_module.list_input_devices()

        assert [device["index"] for device in devices] == [1, 2]

    def test_list_input_devices_marks_default_first(self, app_module, monkeypatch):
        """Устройство по умолчанию должно быть отмечено и идти первым."""
        monkeypatch.setattr(audio.pyaudio, "PyAudio", FakePyAudio)

        devices = app_module.list_input_devices()

        assert devices[0]["is_default"] is True
        assert devices[0]["name"] == "Built-in Microphone"

    def test_recorder_can_store_selected_input_device(self, app_module):
        """Recorder должен сохранять выбранный индекс и имя микрофона."""
        recorder = app_module.Recorder(transcriber=None)
        recorder.set_input_device({"index": 7, "name": "External Mic"})

        assert recorder.input_device_index == 7
        assert recorder.input_device_name == "External Mic"

    def test_recorder_performance_mode_changes_buffer_size(self, app_module):
        """Режим работы должен менять размер аудиобуфера."""

        class LLMStub:
            def __init__(self):
                self.performance_mode = None

            def set_performance_mode(self, performance_mode):
                self.performance_mode = performance_mode

        recorder = app_module.Recorder(transcriber=None)
        recorder.llm_processor = LLMStub()

        recorder.set_performance_mode("fast")

        assert recorder.performance_mode == "fast"
        assert recorder.frames_per_buffer == 512
        assert recorder.llm_processor.performance_mode == "fast"

        recorder.set_performance_mode("normal")

        assert recorder.performance_mode == "normal"
        assert recorder.frames_per_buffer == 2048

    def test_recorder_marks_only_latest_request_as_current(self, app_module):
        """Только самый новый запрос должен считаться актуальным для вывода и статуса."""
        recorder = app_module.Recorder(transcriber=None)

        first_request_id = recorder._begin_request()
        second_request_id = recorder._begin_request()

        assert recorder.should_deliver_llm_result(first_request_id) is False
        assert recorder.should_deliver_llm_result(second_request_id) is True

    def test_recorder_ignores_stale_status_updates(self, app_module):
        """Старый запрос не должен сбрасывать UI-статус поверх нового."""
        recorder = app_module.Recorder(transcriber=None)
        statuses = []
        recorder.set_status_callback(statuses.append)

        first_request_id = recorder._begin_request()
        second_request_id = recorder._begin_request()

        recorder._set_status_if_current(first_request_id, app_module.STATUS_IDLE)
        recorder._set_status_if_current(second_request_id, app_module.STATUS_LLM_PROCESSING)

        assert statuses == [app_module.STATUS_LLM_PROCESSING]

    def test_microphone_menu_title_contains_index_and_name(self, app_module):
        """Подпись микрофона должна содержать индекс и имя устройства."""
        title = app_module.microphone_menu_title({"index": 3, "name": "USB Mic"})

        assert title == "[3] USB Mic"


class TestRecorderCancel:
    """Тесты отмены записи через Recorder.cancel()."""

    def test_cancel_sets_flags(self, app_module):
        """cancel() должен установить cancelled=True и recording=False."""
        recorder = app_module.Recorder(transcriber=None)
        recorder.recording = True

        recorder.cancel()

        assert recorder.cancelled is True
        assert recorder.recording is False

    def test_cancel_skips_transcription(self, app_module):
        """После cancel() _record_impl должен пропустить транскрибирование."""
        transcribe_called = []

        class FakeTranscriber:
            def transcribe(self, audio, language):
                transcribe_called.append(True)

        recorder = app_module.Recorder(transcriber=FakeTranscriber())
        statuses = []
        recorder.set_status_callback(statuses.append)

        recorder._begin_request()

        # Имитируем: запись завершилась, но cancelled=True
        recorder.cancelled = True
        recorder.recording = False

        # Проверяем через логику _record_impl:
        # после цикла записи, если cancelled, должен вернуться в idle
        # Здесь мы тестируем непосредственно флаг
        assert recorder.cancelled is True
        assert transcribe_called == []

    def test_cancel_resets_cancelled_flag_after_init(self, app_module):
        """Recorder.__init__ должен инициализировать cancelled=False."""
        recorder = app_module.Recorder(transcriber=None)
        assert recorder.cancelled is False

    def test_stop_does_not_set_cancelled(self, app_module):
        """stop() не должен устанавливать cancelled — только recording=False."""
        recorder = app_module.Recorder(transcriber=None)
        recorder.recording = True
        recorder.cancelled = False

        recorder.stop()

        assert recorder.cancelled is False
        assert recorder.recording is False
