"""Чистые типы доменного слоя приложения Dictator."""

from __future__ import annotations

from typing import TypedDict


class HistoryRecord(TypedDict):
    """Запись истории распознанного текста."""

    text: str
    created_at: float


class AudioDeviceInfo(TypedDict):
    """Информация об устройстве ввода PyAudio."""

    index: int
    name: str
    max_input_channels: int
    default_sample_rate: float
    is_default: bool


class MicrophoneProfile(TypedDict):
    """Быстрый профиль настроек микрофона."""

    name: str
    input_device_index: int | None
    input_device_name: str
    model_repo: str
    language: str | None
    max_time: float | None
    performance_mode: str
    private_mode: bool
    paste_cgevent: bool
    paste_ax: bool
    paste_clipboard: bool
    llm_clipboard: bool


class AudioDiagnostics(TypedDict):
    """Диагностика входного аудиосигнала."""

    language: str | None
    duration_seconds: float
    rms_energy: float
    peak_amplitude: float
    silence_threshold: float
    hallucination_threshold: float
    sample_rate: int
    samples: int
    first_samples: list[float]

