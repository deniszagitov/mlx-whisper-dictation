"""Чистые аудио-утилиты приложения Dictator."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Sequence

    from .types import AudioDeviceInfo


def microphone_menu_title(device_info: AudioDeviceInfo) -> str:
    """Формирует подпись микрофона для меню приложения."""
    name = str(device_info.get("name", "Неизвестное устройство"))
    return f"[{device_info['index']}] {name}"


def normalize_input_device_name(name: object) -> str | None:
    """Нормализует имя устройства ввода для хранения и сравнения."""
    if name is None:
        return None
    normalized = " ".join(str(name).split())
    return normalized or None


def input_device_name_matches(expected_name: object, actual_name: object) -> bool:
    """Сравнивает два имени устройства без учёта регистра и лишних пробелов."""
    normalized_expected = normalize_input_device_name(expected_name)
    normalized_actual = normalize_input_device_name(actual_name)
    if normalized_expected is None or normalized_actual is None:
        return False
    return normalized_expected.casefold() == normalized_actual.casefold()


def resolve_input_device(
    devices: Sequence[AudioDeviceInfo],
    *,
    preferred_index: int | None = None,
    preferred_name: str | None = None,
    fallback_to_default: bool = True,
    fallback_to_first: bool = True,
) -> tuple[AudioDeviceInfo | None, str]:
    """Подбирает лучшее устройство ввода по индексу, имени и fallback-правилам."""
    if not devices:
        return None, "none"

    exact_match = None
    index_match = None
    name_match = None
    default_match = None
    has_preferred_name = normalize_input_device_name(preferred_name) is not None

    for device in devices:
        if device.get("is_default") and default_match is None:
            default_match = device

        if preferred_index is not None and int(device["index"]) == preferred_index:
            index_match = device
            if not has_preferred_name or input_device_name_matches(preferred_name, device.get("name")):
                exact_match = device

        if has_preferred_name and name_match is None and input_device_name_matches(preferred_name, device.get("name")):
            name_match = device

    if exact_match is not None:
        return exact_match, "exact"
    if name_match is not None:
        return name_match, "name"
    if not has_preferred_name and index_match is not None:
        return index_match, "index"
    if fallback_to_default and default_match is not None:
        return default_match, "default"
    if fallback_to_first:
        return devices[0], "first"
    return None, "none"
