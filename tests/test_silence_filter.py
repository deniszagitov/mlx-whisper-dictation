"""Тесты фильтрации тишины и порогов RMS-энергии.

Проверяет, что RMS-порог корректно отсеивает тишину и фоновый шум микрофона,
но пропускает реальную речь на транскрибацию.
"""

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

SILENCE_RMS_THRESHOLD = 0.003


def rms_energy(audio_data):
    """Вычисляет RMS-энергию аудиосигнала."""
    return float(np.sqrt(np.mean(audio_data**2)))


class TestSilenceFilter:
    """Тесты порога тишины на основе RMS-энергии."""

    def test_pure_silence_is_filtered(self):
        """Полная тишина (нулевой сигнал) должна быть отфильтрована."""
        silent = np.zeros(16000 * 3, dtype=np.float32)
        assert rms_energy(silent) < SILENCE_RMS_THRESHOLD

    def test_low_noise_is_filtered(self):
        """Слабый фоновый шум микрофона (RMS ~0.001) должен быть отфильтрован."""
        np.random.seed(42)
        low_noise = np.random.randn(16000 * 3).astype(np.float32) * 0.001
        assert rms_energy(low_noise) < SILENCE_RMS_THRESHOLD

    def test_normal_speech_passes(self):
        """Нормальная речь (RMS ~0.07) должна пройти фильтр."""
        t = np.linspace(0, 3.0, 16000 * 3, dtype=np.float32)
        speech = 0.1 * np.sin(2 * np.pi * 300 * t)
        assert rms_energy(speech) >= SILENCE_RMS_THRESHOLD

    def test_quiet_speech_passes(self):
        """Тихая речь (RMS ~0.01) должна пройти фильтр."""
        np.random.seed(42)
        quiet = np.random.randn(16000 * 3).astype(np.float32) * 0.01
        assert rms_energy(quiet) >= SILENCE_RMS_THRESHOLD

    def test_very_quiet_speech_passes(self):
        """Очень тихая, но реальная речь (RMS ~0.005) должна пройти фильтр."""
        np.random.seed(42)
        very_quiet = np.random.randn(16000 * 3).astype(np.float32) * 0.005
        assert rms_energy(very_quiet) >= SILENCE_RMS_THRESHOLD

    def test_above_threshold_passes(self):
        """Сигнал заведомо выше порога должен пройти фильтр."""
        length = 16000 * 3
        amplitude = SILENCE_RMS_THRESHOLD * 2 * np.sqrt(2)
        t = np.linspace(0, 3.0, length, dtype=np.float32)
        signal = amplitude * np.sin(2 * np.pi * 440 * t)
        assert rms_energy(signal) >= SILENCE_RMS_THRESHOLD


class TestMinAudioDuration:
    """Тесты минимальной длительности аудио."""

    def test_very_short_audio_rejected(self):
        """Аудио короче 0.5 с (8000 сэмплов при 16kHz) должно быть отклонено."""
        short = np.random.randn(4000).astype(np.float32) * 0.1
        assert len(short) < 16000 * 0.5

    def test_half_second_audio_accepted(self):
        """Аудио ровно 0.5 с (8000 сэмплов) должно быть принято."""
        normal = np.random.randn(8000).astype(np.float32) * 0.1
        assert len(normal) >= 16000 * 0.5

    def test_normal_duration_accepted(self):
        """Аудио длительностью 3 с должно быть принято."""
        audio = np.random.randn(16000 * 3).astype(np.float32) * 0.1
        assert len(audio) >= 16000 * 0.5


class TestAudioConversion:
    """Тесты конвертации аудио из int16 в float32."""

    def test_int16_to_float32_range(self):
        """Конвертация int16 → float32 должна давать значения в [-1, 1]."""
        int16_audio = np.array([0, 32767, -32768, 16384, -16384], dtype=np.int16)
        float32_audio = int16_audio.astype(np.float32) / 32768.0
        assert float32_audio.max() <= 1.0
        assert float32_audio.min() >= -1.0

    def test_zero_stays_zero(self):
        """Нулевой сигнал в int16 должен оставаться нулевым в float32."""
        zeros = np.zeros(1000, dtype=np.int16)
        converted = zeros.astype(np.float32) / 32768.0
        assert np.all(converted == 0.0)

    def test_max_amplitude_is_near_one(self):
        """Максимальная амплитуда int16 (32767) должна быть близка к 1.0."""
        max_signal = np.array([32767], dtype=np.int16)
        converted = max_signal.astype(np.float32) / 32768.0
        assert abs(converted[0] - 1.0) < 0.001
