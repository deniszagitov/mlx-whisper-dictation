"""Чистые аудио-утилиты приложения Dictator."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .types import AudioDeviceInfo


def microphone_menu_title(device_info: AudioDeviceInfo) -> str:
    """Формирует подпись микрофона для меню приложения."""
    name = str(device_info.get("name", "Неизвестное устройство"))
    return f"[{device_info['index']}] {name}"
