"""Тесты доменных value objects конфигурации."""

from __future__ import annotations

from src.domain import types as domain_types
from src.domain.constants import Config


def test_microphone_profile_from_payload_normalizes_fields() -> None:
    """Профиль микрофона должен нормализоваться в immutable dataclass."""
    profile = domain_types.MicrophoneProfile.from_payload(
        {
            "name": "  Основной  ",
            "input_device_index": "7",
            "input_device_name": "USB Mic",
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
        }
    )

    assert profile is not None
    assert profile.name == "Основной"
    assert profile.input_device_index == 7
    assert profile.model_repo == Config.DEFAULT_MODEL_NAME
    assert profile.max_time == 30
    assert profile.performance_mode == Config.DEFAULT_PERFORMANCE_MODE
    assert profile.private_mode is True
    assert profile.paste_ax is True
    assert profile.capitalize_first_letter is False
    assert profile.remove_trailing_period_for_single_sentence is False
    assert profile.restore_trailing_period_on_next_dictation is False
    assert profile.llm_clipboard is False


def test_microphone_profile_to_payload_roundtrip() -> None:
    """Профиль должен сериализоваться обратно в JSON-совместимый словарь."""
    profile = domain_types.MicrophoneProfile.from_runtime(
        "Звонки",
        input_device_index=4,
        input_device_name="USB Mic",
        model_repo="mlx-community/whisper-turbo",
        language="en",
        max_time=12.5,
        performance_mode=Config.PERFORMANCE_MODE_FAST,
        private_mode=False,
        paste_cgevent=True,
        paste_ax=False,
        paste_clipboard=True,
        capitalize_first_letter=True,
        remove_trailing_period_for_single_sentence=False,
        restore_trailing_period_on_next_dictation=False,
        llm_clipboard=True,
    )

    assert profile.to_payload() == {
        "name": "Звонки",
        "input_device_index": 4,
        "input_device_name": "USB Mic",
        "model_repo": "mlx-community/whisper-turbo",
        "language": "en",
        "max_time": 12.5,
        "performance_mode": Config.PERFORMANCE_MODE_FAST,
        "private_mode": False,
        "paste_cgevent": True,
        "paste_ax": False,
        "paste_clipboard": True,
        "capitalize_first_letter": True,
        "remove_trailing_period_for_single_sentence": False,
        "restore_trailing_period_on_next_dictation": False,
        "llm_clipboard": True,
    }


def test_launch_config_exposes_compatible_alias_properties() -> None:
    """LaunchConfig должен сохранять совместимые alias-свойства для runtime."""
    launch_config = domain_types.LaunchConfig.from_sources(
        model="mlx-community/whisper-turbo",
        language="ru,en",
        max_time="45",
        llm_model=Config.DEFAULT_LLM_MODEL_NAME,
        key_combination="Command+Option+Space",
        secondary_key_combination="Control+Shift+T",
        llm_key_combination="",
    )

    assert launch_config.model == "mlx-community/whisper-turbo"
    assert launch_config.language == ["ru", "en"]
    assert launch_config.max_time == 45
    assert launch_config.key_combination == "cmd+alt+space"
    assert launch_config.secondary_key_combination == "ctrl+shift+t"
    assert launch_config.llm_key_combination is None


def test_app_snapshot_type_annotations_stay_available() -> None:
    """AppSnapshot должен сохранять контракт полей для UI-слоя."""
    assert set(domain_types.AppSnapshot.__annotations__) >= {
        "model_repo",
        "hotkey_status",
        "microphone_profiles",
        "show_recording_overlay",
        "show_recording_time_in_menu_bar",
        "capitalize_first_letter_enabled",
        "remove_trailing_period_for_single_sentence_enabled",
        "restore_trailing_period_on_next_dictation_enabled",
    }
