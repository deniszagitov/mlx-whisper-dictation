"""Чистые правила нормализации и отображения горячих клавиш."""

from __future__ import annotations

from .constants import Config

KEY_NAME_ALIASES = {
    "ctrl": "ctrl",
    "control": "ctrl",
    "alt": "alt",
    "option": "alt",
    "opt": "alt",
    "shift": "shift",
    "cmd": "cmd",
    "command": "cmd",
    "meta": "cmd",
    "super": "cmd",
}

MODIFIER_DISPLAY_ORDER = [
    "ctrl",
    "ctrl_l",
    "ctrl_r",
    "alt",
    "alt_l",
    "alt_r",
    "shift",
    "shift_l",
    "shift_r",
    "cmd",
    "cmd_l",
    "cmd_r",
]


def normalize_key_name(raw_name: str) -> str:
    """Нормализует имя клавиши к каноническому виду."""
    lowered = raw_name.strip().lower()
    alias = KEY_NAME_ALIASES.get(lowered)
    return alias if alias is not None else lowered


def normalize_key_combination(key_combination: str) -> str:
    """Нормализует строку комбинации клавиш к внутреннему формату."""
    parts = [normalize_key_name(part) for part in key_combination.split("+") if part.strip()]
    if len(parts) < Config.MIN_HOTKEY_PARTS:
        raise ValueError("Комбинация клавиш должна содержать как минимум две клавиши.")
    return "+".join(parts)


def format_hotkey_status(key_combination: str | None = None, *, use_double_cmd: bool = False) -> str:
    """Преобразует настройку хоткея в строку для меню."""
    if use_double_cmd:
        return "двойное нажатие правой ⌘"

    display_names = {
        "cmd": "⌘",
        "cmd_l": "левая ⌘",
        "cmd_r": "правая ⌘",
        "alt": "⌥",
        "alt_l": "левая ⌥",
        "alt_r": "правая ⌥",
        "shift": "⇧",
        "shift_l": "левая ⇧",
        "shift_r": "правая ⇧",
        "ctrl": "⌃",
        "ctrl_l": "левая ⌃",
        "ctrl_r": "правая ⌃",
        "space": "Space",
    }
    parts = [normalize_key_name(part) for part in (key_combination or "").split("+") if part.strip()]
    return " + ".join(display_names[part] if part in display_names else part.upper() for part in parts)
