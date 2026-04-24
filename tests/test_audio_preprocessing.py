"""Тесты capture-first preprocessing аудио."""

import logging
from typing import cast

import numpy as np
from src.domain.audio import audio_profile_for_input_device
from src.domain.constants import Config
from src.domain.types import AudioDeviceInfo, RecordedAudio
from src.infrastructure import audio_preprocessing


def make_recorded_audio(
    samples,
    *,
    sample_rate=16000,
    sample_format="float32",
    profile_name=Config.AUDIO_PROFILE_GENERIC,
):
    """Создаёт RecordedAudio для unit-тестов preprocessing."""
    return RecordedAudio(
        samples=np.asarray(samples),
        sample_rate=sample_rate,
        channels=1,
        sample_format=sample_format,
        device_index=0,
        device_name="Built-in Microphone",
        profile_name=profile_name,
        metadata={"post_roll_ms": 300},
    )


def test_int16_to_float32_conversion_keeps_expected_scale(monkeypatch):
    """int16-запись должна превращаться в float32 waveform ожидаемого масштаба."""
    monkeypatch.setattr(audio_preprocessing, "_run_webrtc_vad", lambda _audio: (0.0, 0.0, None))
    recorded = make_recorded_audio(
        np.array([0, 16384, -16384, 0], dtype=np.int16),
        sample_format="int16",
    )

    preprocessed = audio_preprocessing.preprocess_recorded_audio(recorded, "ru", enable_gain_normalization=False)

    assert preprocessed.audio.dtype == np.float32
    assert np.allclose(preprocessed.audio, np.array([0.0, 0.5, -0.5, 0.0], dtype=np.float32))
    assert preprocessed.sample_rate == 16000


def test_float32_cleanup_removes_nan_inf_and_dc_offset(monkeypatch):
    """float32 path должен чистить NaN/Inf и убирать DC offset."""
    monkeypatch.setattr(audio_preprocessing, "_run_webrtc_vad", lambda _audio: (0.0, 0.0, None))
    recorded = make_recorded_audio(np.array([np.nan, np.inf, -np.inf, 0.25], dtype=np.float32))

    preprocessed = audio_preprocessing.preprocess_recorded_audio(recorded, "ru", enable_gain_normalization=False)

    assert np.isfinite(preprocessed.audio).all()
    assert abs(float(np.mean(preprocessed.audio))) < 1e-7


def test_resamples_48khz_to_16khz(monkeypatch):
    """Native 48 kHz capture должен явно ресемплиться в 16 kHz."""
    monkeypatch.setattr(audio_preprocessing, "_run_webrtc_vad", lambda _audio: (0.0, 0.0, None))
    recorded = make_recorded_audio(np.zeros(48000, dtype=np.float32), sample_rate=48000)

    preprocessed = audio_preprocessing.preprocess_recorded_audio(recorded, "ru", enable_gain_normalization=False)

    assert preprocessed.sample_rate == 16000
    assert len(preprocessed.audio) == 16000
    assert preprocessed.diagnostics["resampled"] is True


def test_macbook_builtin_profile_requires_coreaudio_when_host_api_known():
    """MacBook HQ-профиль включается только для встроенного микрофона CoreAudio."""
    coreaudio_device = cast("AudioDeviceInfo", {
        "index": 0,
        "name": "Built-in Microphone",
        "max_input_channels": 1,
        "default_sample_rate": 48000.0,
        "is_default": True,
        "host_api_name": "Core Audio",
    })
    non_coreaudio_device = cast("AudioDeviceInfo", {**coreaudio_device, "host_api_name": "Other API"})

    assert (
        audio_profile_for_input_device(coreaudio_device, high_quality_mac_builtin_enabled=True)
        == Config.AUDIO_PROFILE_MACBOOK_BUILTIN_HIGH_QUALITY
    )
    assert (
        audio_profile_for_input_device(non_coreaudio_device, high_quality_mac_builtin_enabled=True)
        == Config.AUDIO_PROFILE_GENERIC
    )


def test_vad_does_not_trim_leading_trailing_or_internal_silence(monkeypatch):
    """VAD не должен обрезать края или паузы внутри диктовки."""
    monkeypatch.setattr(audio_preprocessing, "_run_webrtc_vad", lambda _audio: (0.30, 0.30, 0.02))
    audio = np.concatenate(
        [
            np.zeros(4000, dtype=np.float32),
            np.full(4000, 0.02, dtype=np.float32),
            np.zeros(4000, dtype=np.float32),
            np.full(4000, -0.02, dtype=np.float32),
        ]
    )
    recorded = make_recorded_audio(audio)

    preprocessed = audio_preprocessing.preprocess_recorded_audio(recorded, "ru", enable_gain_normalization=False)

    assert len(preprocessed.audio) == len(audio)
    assert preprocessed.speech_detected is True


def test_no_speech_skip_only_for_extremely_quiet_audio(monkeypatch):
    """ASR skip должен срабатывать только для уверенной тишины."""
    monkeypatch.setattr(audio_preprocessing, "_run_webrtc_vad", lambda _audio: (0.0, 0.0, None))
    recorded = make_recorded_audio(np.zeros(16000, dtype=np.float32))

    preprocessed = audio_preprocessing.preprocess_recorded_audio(recorded, "ru", enable_gain_normalization=True)

    assert preprocessed.speech_detected is False
    assert preprocessed.diagnostics["skip_asr"] is True


def test_gain_normalization_is_capped(monkeypatch):
    """Бережная нормализация не должна превышать max_gain_db."""
    monkeypatch.setattr(audio_preprocessing, "_run_webrtc_vad", lambda _audio: (1.0, 1.0, 0.001))
    recorded = make_recorded_audio(np.tile(np.array([0.001, -0.001], dtype=np.float32), 8000))

    preprocessed = audio_preprocessing.preprocess_recorded_audio(recorded, "ru", enable_gain_normalization=True)

    assert preprocessed.diagnostics["gain_applied_db"] <= Config.AUDIO_MAX_GAIN_DB + 0.01


def test_peak_limiter_caps_normalized_output(monkeypatch):
    """Нормализация должна ограничивать итоговый peak."""
    monkeypatch.setattr(audio_preprocessing, "_run_webrtc_vad", lambda _audio: (1.0, 1.0, 0.01))
    recorded = make_recorded_audio(np.tile(np.array([0.5, -0.5], dtype=np.float32), 8000))

    preprocessed = audio_preprocessing.preprocess_recorded_audio(recorded, "ru", enable_gain_normalization=True)

    assert preprocessed.diagnostics["final_peak"] <= Config.AUDIO_PEAK_LIMIT + 1e-6


def test_clipping_diagnostics_warns(caplog, monkeypatch):
    """Клиппированный вход должен попадать в диагностику и warning log."""
    monkeypatch.setattr(audio_preprocessing, "_run_webrtc_vad", lambda _audio: (1.0, 1.0, 0.9))
    recorded = make_recorded_audio(np.ones(16000, dtype=np.float32))

    with caplog.at_level(logging.WARNING):
        preprocessed = audio_preprocessing.preprocess_recorded_audio(recorded, "ru", enable_gain_normalization=False)

    assert preprocessed.diagnostics["clipping_ratio"] > Config.AUDIO_CLIPPING_WARNING_RATIO
    assert "клиппированным" in caplog.text
