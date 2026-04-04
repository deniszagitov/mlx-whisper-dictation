"""Тесты persistence-адаптера быстрых профилей микрофона."""

from __future__ import annotations

import json

from src.domain.constants import Config
from src.domain.types import MicrophoneProfile
from src.infrastructure.persistence import microphone_profiles as microphone_profiles_module


def test_load_microphone_profiles_returns_empty_list_when_value_is_missing(monkeypatch):
    """При отсутствии сохранённого JSON адаптер должен вернуть пустой список."""
    monkeypatch.setattr(
        microphone_profiles_module.defaults,
        "load_str",
        lambda key, fallback="": "",
    )

    assert microphone_profiles_module._load_microphone_profiles() == []


def test_load_microphone_profiles_skips_invalid_payload(monkeypatch):
    """Некорректный JSON или не-список не должны ломать чтение профилей."""
    monkeypatch.setattr(
        microphone_profiles_module.defaults,
        "load_str",
        lambda key, fallback="": "{not-json}",
    )
    assert microphone_profiles_module._load_microphone_profiles() == []

    monkeypatch.setattr(
        microphone_profiles_module.defaults,
        "load_str",
        lambda key, fallback="": json.dumps({"unexpected": True}),
    )
    assert microphone_profiles_module._load_microphone_profiles() == []


def test_load_microphone_profiles_normalizes_and_limits_profiles(monkeypatch):
    """Загрузка должна нормализовать поля профиля и обрезать список по лимиту."""
    raw_profiles = [
        {
            "name": "  Основной  ",
            "input_device_index": "7",
            "input_device_name": "Mic",
            "model_repo": "",
            "language": "ru",
            "max_time": "30.0",
            "performance_mode": "turbo",
            "private_mode": 1,
            "paste_cgevent": False,
            "paste_ax": True,
            "paste_clipboard": True,
            "capitalize_first_letter": False,
            "remove_trailing_period_for_single_sentence": False,
            "restore_trailing_period_on_next_dictation": False,
            "llm_clipboard": False,
        },
        {"name": "", "input_device_index": 1},
    ]
    raw_profiles.extend(
        {
            "name": f"Профиль {index}",
            "input_device_index": index,
            "input_device_name": f"Mic {index}",
        }
        for index in range(1, Config.MAX_MICROPHONE_PROFILES + 5)
    )

    monkeypatch.setattr(
        microphone_profiles_module.defaults,
        "load_str",
        lambda key, fallback="": json.dumps(raw_profiles, ensure_ascii=False),
    )

    profiles = microphone_profiles_module._load_microphone_profiles()

    assert len(profiles) == Config.MAX_MICROPHONE_PROFILES - 1
    assert profiles[0].name == "Основной"
    assert profiles[0].input_device_index == 7
    assert profiles[0].max_time == 30
    assert profiles[0].model_repo == Config.DEFAULT_MODEL_NAME
    assert profiles[0].performance_mode == Config.DEFAULT_PERFORMANCE_MODE
    assert profiles[0].private_mode is True
    assert profiles[0].paste_cgevent is False
    assert profiles[0].paste_ax is True
    assert profiles[0].paste_clipboard is True
    assert profiles[0].capitalize_first_letter is False
    assert profiles[0].remove_trailing_period_for_single_sentence is False
    assert profiles[0].restore_trailing_period_on_next_dictation is False
    assert profiles[0].llm_clipboard is False


def test_save_microphone_profiles_writes_normalized_json(monkeypatch):
    """Сохранение должно сериализовать только безопасные и нормализованные профили."""
    saved_values: list[tuple[str, str]] = []

    monkeypatch.setattr(
        microphone_profiles_module.defaults,
        "save_str",
        lambda key, value: saved_values.append((key, value)),
    )

    microphone_profiles_module._save_microphone_profiles(
        [
            MicrophoneProfile.from_runtime(
                "Тестовый",
                input_device_index=3,
                input_device_name="USB Mic",
                model_repo="custom/model",
                language="en",
                max_time=12.5,
                performance_mode="fast",
                private_mode=False,
                paste_cgevent=True,
                paste_ax=False,
                paste_clipboard=True,
                capitalize_first_letter=False,
                remove_trailing_period_for_single_sentence=True,
                restore_trailing_period_on_next_dictation=False,
                llm_clipboard=True,
            ),
        ]
    )

    assert saved_values
    key, payload = saved_values[-1]
    assert key == Config.DEFAULTS_KEY_MICROPHONE_PROFILES

    saved_profiles = json.loads(payload)
    assert saved_profiles == [
        {
            "name": "Тестовый",
            "input_device_index": 3,
            "input_device_name": "USB Mic",
            "model_repo": "custom/model",
            "language": "en",
            "max_time": 12.5,
            "performance_mode": "fast",
            "private_mode": False,
            "paste_cgevent": True,
            "paste_ax": False,
            "paste_clipboard": True,
            "capitalize_first_letter": False,
            "remove_trailing_period_for_single_sentence": True,
            "restore_trailing_period_on_next_dictation": False,
            "llm_clipboard": True,
        }
    ]
