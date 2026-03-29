"""Тесты импорта и контракта доменных TypedDict."""

from __future__ import annotations

from src.domain import types as domain_types


def test_domain_typed_dicts_expose_expected_fields() -> None:
    """Доменные TypedDict должны объявлять ожидаемые ключи для orchestration-слоя."""
    history_record: domain_types.HistoryRecord = {"text": "пример", "created_at": 1.0}
    audio_device: domain_types.AudioDeviceInfo = {
        "index": 0,
        "name": "Built-in Microphone",
        "max_input_channels": 2,
        "default_sample_rate": 44_100.0,
        "is_default": True,
    }
    microphone_profile: domain_types.MicrophoneProfile = {
        "name": "Основной",
        "input_device_index": 0,
        "input_device_name": "Built-in Microphone",
        "model_repo": "mlx-community/whisper-large-v3-turbo",
        "language": "ru",
        "max_time": 30.0,
        "performance_mode": "normal",
        "private_mode": False,
        "paste_cgevent": True,
        "paste_ax": False,
        "paste_clipboard": True,
        "llm_clipboard": True,
    }
    audio_diagnostics: domain_types.AudioDiagnostics = {
        "language": "ru",
        "duration_seconds": 1.5,
        "rms_energy": 0.2,
        "peak_amplitude": 0.9,
        "silence_threshold": 0.01,
        "hallucination_threshold": 0.001,
        "sample_rate": 16_000,
        "samples": 24_000,
        "first_samples": [0.1, 0.2, 0.3],
    }

    assert history_record["text"] == "пример"
    assert audio_device["is_default"] is True
    assert microphone_profile["model_repo"].endswith("turbo")
    assert audio_diagnostics["sample_rate"] == 16_000
    assert set(domain_types.HistoryRecord.__annotations__) == {"text", "created_at"}
    assert set(domain_types.AudioDeviceInfo.__annotations__) == {
        "index",
        "name",
        "max_input_channels",
        "default_sample_rate",
        "is_default",
    }
    assert set(domain_types.MicrophoneProfile.__annotations__) >= {
        "name",
        "performance_mode",
        "private_mode",
        "llm_clipboard",
    }
    assert set(domain_types.AudioDiagnostics.__annotations__) >= {
        "duration_seconds",
        "peak_amplitude",
        "first_samples",
    }
