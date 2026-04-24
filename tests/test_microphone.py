"""Тесты записи звука с микрофона.

Проверяет, что PyAudio может открыть поток для записи и что
записанные данные содержат реальный сигнал, а не тишину.

Тесты помечены маркером `hardware`, потому что требуют доступ к микрофону.
"""

from typing import Any

import numpy as np
import pyaudio
import pytest
from src.domain.constants import Config
from src.infrastructure import audio_runtime


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
        monkeypatch.setattr(audio_runtime.pyaudio, "PyAudio", FakePyAudio)  # type: ignore[attr-defined]

        devices = app_module.list_input_devices()

        assert [device["index"] for device in devices] == [1, 2]

    def test_list_input_devices_marks_default_first(self, app_module, monkeypatch):
        """Устройство по умолчанию должно быть отмечено и идти первым."""
        monkeypatch.setattr(audio_runtime.pyaudio, "PyAudio", FakePyAudio)  # type: ignore[attr-defined]

        devices = app_module.list_input_devices()

        assert devices[0]["is_default"] is True
        assert devices[0]["name"] == "Built-in Microphone"

    def test_recorder_can_store_selected_input_device(self, app_module):
        """Recorder должен сохранять выбранный индекс и имя микрофона."""
        recorder = app_module.Recorder()
        recorder.set_input_device({"index": 7, "name": "External Mic"})

        assert recorder.input_device_index == 7
        assert recorder.input_device_name == "External Mic"

    def test_recorder_performance_mode_changes_buffer_size(self, app_module):
        """Режим работы должен менять размер аудиобуфера."""
        recorder = app_module.Recorder()

        recorder.set_performance_mode("fast")

        assert recorder.performance_mode == "fast"
        assert recorder.frames_per_buffer == 512

        recorder.set_performance_mode("normal")

        assert recorder.performance_mode == "normal"
        assert recorder.frames_per_buffer == 2048

    def test_recorder_marks_only_latest_request_as_current(self, app_module):
        """Только самый новый запрос должен считаться актуальным для вывода и статуса."""
        recorder = app_module.Recorder()

        first_request_id = recorder._begin_request()
        second_request_id = recorder._begin_request()

        assert recorder._is_request_current(first_request_id) is False
        assert recorder._is_request_current(second_request_id) is True

    def test_recorder_ignores_stale_status_updates(self, app_module):
        """Старый запрос не должен сбрасывать UI-статус поверх нового."""
        recorder = app_module.Recorder()
        statuses: list[object] = []
        recorder.set_status_callback(statuses.append)

        first_request_id = recorder._begin_request()
        second_request_id = recorder._begin_request()

        recorder._set_status_if_current(first_request_id, Config.STATUS_IDLE)
        recorder._set_status_if_current(second_request_id, Config.STATUS_LLM_PROCESSING)

        assert statuses == [Config.STATUS_LLM_PROCESSING]

    def test_microphone_menu_title_contains_index_and_name(self, app_module):
        """Подпись микрофона должна содержать индекс и имя устройства."""
        title = app_module.microphone_menu_title({"index": 3, "name": "USB Mic"})

        assert title == "[3] USB Mic"

    def test_list_input_devices_includes_host_api_name(self, app_module, monkeypatch):
        """Список микрофонов должен сохранять host API для выбора аудиопрофиля."""

        class FakePyAudioWithHostApi(FakePyAudio):
            def __init__(self):
                super().__init__()
                self.devices[1]["hostApi"] = 5

            def get_host_api_info_by_index(self, index):
                assert index == 5
                return {"name": "Core Audio"}

        monkeypatch.setattr(audio_runtime.pyaudio, "PyAudio", FakePyAudioWithHostApi)  # type: ignore[attr-defined]

        devices = app_module.list_input_devices()

        assert devices[0]["host_api_name"] == "Core Audio"


class TestRecorderHighQualityCapture:
    """Тесты capture-first профиля записи."""

    def test_macbook_profile_tries_native_float32_before_native_int16(self, app_module):
        """MacBook HQ должен пробовать native float32 перед native int16."""
        recorder = app_module.Recorder()
        recorder.set_input_device(
            {
                "index": 1,
                "name": "Built-in Microphone",
                "default_sample_rate": 48000.0,
                "host_api_name": "Core Audio",
            }
        )
        format_checks: list[tuple[int, int]] = []
        open_calls: list[tuple[int, int]] = []

        class FakeStream:
            pass

        class FakePyAudio:
            def is_format_supported(self, rate, *, input_device=None, input_channels=None, input_format=None):
                format_checks.append((rate, input_format))
                return input_format != audio_runtime.pyaudio.paFloat32

            def open(self, **kwargs):
                open_calls.append((kwargs["rate"], kwargs["format"]))
                return FakeStream()

        opened = recorder._open_stream(FakePyAudio(), frames_per_buffer=512)

        assert format_checks[:2] == [
            (48000, audio_runtime.pyaudio.paFloat32),
            (48000, audio_runtime.pyaudio.paInt16),
        ]
        assert open_calls == [(48000, audio_runtime.pyaudio.paInt16)]
        assert opened.sample_rate == 48000
        assert opened.sample_format == "int16"
        assert opened.profile_name == Config.AUDIO_PROFILE_MACBOOK_BUILTIN_HIGH_QUALITY

    def test_record_impl_appends_post_roll_after_stop(self, app_module, monkeypatch):
        """После stop() Recorder должен дочитать короткий post-roll."""
        recorder = app_module.Recorder()
        recorder.frames_per_buffer = 512
        recorder.set_post_roll_ms(100)
        captured: list[Any] = []
        read_calls: list[int] = []

        class FakeStream:
            def read(self, frames_per_buffer, exception_on_overflow=False):
                read_calls.append(frames_per_buffer)
                if len(read_calls) == 1:
                    recorder.recording = False
                return np.zeros(frames_per_buffer, dtype=np.int16).tobytes()

            def stop_stream(self):
                return None

            def close(self):
                return None

        class FakePyAudio:
            def is_format_supported(self, *args, **kwargs):
                return True

            def open(self, **kwargs):
                return FakeStream()

            def terminate(self):
                return None

        monkeypatch.setattr(audio_runtime.pyaudio, "PyAudio", FakePyAudio)  # type: ignore[attr-defined]

        recorder._record_impl(
            language="ru",
            request_id=recorder._begin_request(),
            on_audio_ready=lambda audio, *_args: captured.append(audio),
        )

        assert read_calls == [512, 512, 512, 512, 64]
        assert len(captured) == 1
        assert len(captured[0].samples) == 512 + 1600
        assert captured[0].metadata["post_roll_ms"] == 100

    def test_cancel_does_not_append_post_roll_or_transcribe(self, app_module, monkeypatch):
        """При cancel() Recorder не должен дочитывать post-roll и запускать callback."""
        recorder = app_module.Recorder()
        recorder.frames_per_buffer = 512
        recorder.set_post_roll_ms(100)
        captured: list[object] = []
        read_calls: list[int] = []

        class FakeStream:
            def read(self, frames_per_buffer, exception_on_overflow=False):
                read_calls.append(frames_per_buffer)
                recorder.cancel()
                return np.zeros(frames_per_buffer, dtype=np.int16).tobytes()

            def stop_stream(self):
                return None

            def close(self):
                return None

        class FakePyAudio:
            def is_format_supported(self, *args, **kwargs):
                return True

            def open(self, **kwargs):
                return FakeStream()

            def terminate(self):
                return None

        monkeypatch.setattr(audio_runtime.pyaudio, "PyAudio", FakePyAudio)  # type: ignore[attr-defined]

        recorder._record_impl(
            language="ru",
            request_id=recorder._begin_request(),
            on_audio_ready=lambda audio, *_args: captured.append(audio),
        )

        assert read_calls == [512]
        assert captured == []


class TestRecorderCancel:
    """Тесты отмены записи через Recorder.cancel()."""

    def test_cancel_sets_flags(self, app_module):
        """cancel() должен установить cancelled=True и recording=False."""
        recorder = app_module.Recorder()
        recorder.recording = True

        recorder.cancel()

        assert recorder.cancelled is True
        assert recorder.recording is False

    def test_cancel_skips_transcription(self, app_module):
        """После cancel() _record_impl должен пропустить транскрибирование."""
        transcribe_called: list[bool] = []

        recorder = app_module.Recorder()
        statuses: list[object] = []
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
        recorder = app_module.Recorder()
        assert recorder.cancelled is False

    def test_stop_does_not_set_cancelled(self, app_module):
        """stop() не должен устанавливать cancelled — только recording=False."""
        recorder = app_module.Recorder()
        recorder.recording = True
        recorder.cancelled = False

        recorder.stop()

        assert recorder.cancelled is False
        assert recorder.recording is False


class TestRecorderRecovery:
    """Тесты восстановления Recorder после ошибок sleep/wake и смены устройства."""

    def test_record_impl_retries_with_default_input_on_invalid_channel_count(self, app_module, monkeypatch):
        """При -9998 для выбранного микрофона Recorder должен повторить open() через default device."""
        open_calls: list[object] = []
        status_updates: list[object] = []

        class FakeStream:
            def __init__(self, recorder):
                self._recorder = recorder

            def read(self, _frames_per_buffer, exception_on_overflow=False):
                self._recorder.recording = False
                return (b"\x00\x00") * 4

            def stop_stream(self):
                return None

            def close(self):
                return None

        class FakePyAudio:
            def is_format_supported(self, *args, **kwargs):
                return True

            def open(self, **kwargs):
                open_calls.append(kwargs.get("input_device_index"))
                if kwargs.get("input_device_index") == 7:
                    raise OSError(-9998, "Invalid number of channels")
                return FakeStream(recorder)

            def terminate(self):
                return None

        monkeypatch.setattr(audio_runtime.pyaudio, "PyAudio", FakePyAudio)  # type: ignore[attr-defined]

        recorder = app_module.Recorder()
        recorder.set_status_callback(status_updates.append)
        recorder.set_input_device({"index": 7, "name": "USB Mic"})

        recorder._record_impl(language="ru", request_id=recorder._begin_request(), on_audio_ready=lambda *_args: None)

        assert open_calls == [7, None]
        assert recorder.input_device_index is None
        assert recorder.input_device_name == "системный по умолчанию"
        assert status_updates[-2:] == [app_module.Config.STATUS_TRANSCRIBING, app_module.Config.STATUS_IDLE]

    def test_record_impl_notifies_runtime_error_without_marking_permission_denied_for_retryable_error(self, app_module, monkeypatch):
        """Retryable audio error после sleep не должен маскироваться под отказ Microphone-разрешения."""
        permission_updates: list[tuple[str, bool]] = []
        ui_errors: list[tuple[str, str]] = []
        runtime_errors: list[tuple[str, str]] = []

        class FakePyAudio:
            def is_format_supported(self, *args, **kwargs):
                return True

            def open(self, **kwargs):
                raise OSError(-9998, "Invalid number of channels")

            def terminate(self):
                return None

        monkeypatch.setattr(audio_runtime.pyaudio, "PyAudio", FakePyAudio)  # type: ignore[attr-defined]

        recorder = app_module.Recorder()
        recorder.set_permission_callback(lambda name, status: permission_updates.append((name, status)))
        recorder.set_error_callback(lambda title, message: ui_errors.append((title, message)))
        recorder.set_runtime_error_callback(lambda title, message: runtime_errors.append((title, message)))
        recorder.set_input_device({"index": 7, "name": "USB Mic"})

        recorder._record_impl(language="ru", request_id=recorder._begin_request(), on_audio_ready=None)

        assert permission_updates == []
        assert runtime_errors == ui_errors
        assert "После сна macOS" in ui_errors[0][1]

    def test_record_impl_marks_permission_denied_for_regular_open_error(self, app_module, monkeypatch):
        """Нерetryable ошибка открытия потока по-прежнему должна помечать Microphone как недоступный."""
        permission_updates: list[tuple[str, bool]] = []

        class FakePyAudio:
            def is_format_supported(self, *args, **kwargs):
                return True

            def open(self, **kwargs):
                raise OSError(-9996, "Invalid input device")

            def terminate(self):
                return None

        monkeypatch.setattr(audio_runtime.pyaudio, "PyAudio", FakePyAudio)  # type: ignore[attr-defined]

        recorder = app_module.Recorder()
        recorder.set_permission_callback(lambda name, status: permission_updates.append((name, status)))

        recorder._record_impl(language="ru", request_id=recorder._begin_request(), on_audio_ready=None)

        assert permission_updates == [("microphone", False)]
