"""Чистые типы доменного слоя приложения Dictator."""

from __future__ import annotations

from dataclasses import dataclass
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


@dataclass(slots=True)
class AppSnapshot:
    """Снимок состояния контроллера диктовки для UI и тестов."""

    state: str
    started: bool
    elapsed_time: int
    model_repo: str
    model_name: str
    hotkey_status: str
    secondary_hotkey_status: str
    llm_hotkey_status: str
    primary_key_combination: str
    secondary_key_combination: str
    llm_key_combination: str
    llm_prompt_name: str
    performance_mode: str
    max_time: float | None
    max_time_options: list[float | None]
    model_options: list[str]
    languages: list[str] | None
    current_language: str | None
    input_devices: list[AudioDeviceInfo]
    current_input_device: AudioDeviceInfo | None
    permission_status: dict[str, bool | None]
    microphone_profiles: list[MicrophoneProfile]
    show_recording_notification: bool
    show_recording_overlay: bool
    private_mode_enabled: bool
    paste_cgevent_enabled: bool
    paste_ax_enabled: bool
    paste_clipboard_enabled: bool
    llm_clipboard_enabled: bool
    history: list[str]
    total_tokens: int
    llm_download_title: str
    llm_download_interactive: bool
    use_double_command_hotkey: bool
