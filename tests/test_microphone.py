"""Тесты записи звука с микрофона.

Проверяет, что PyAudio может открыть поток для записи и что
записанные данные содержат реальный сигнал, а не тишину.

Тесты помечены маркером `hardware`, потому что требуют доступ к микрофону.
"""

import sys
from pathlib import Path

import numpy as np
import pyaudio
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

SILENCE_RMS_THRESHOLD = 0.003


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
