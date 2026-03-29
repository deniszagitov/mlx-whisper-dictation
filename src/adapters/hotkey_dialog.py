"""UI-диалог захвата комбинации горячих клавиш."""

from __future__ import annotations

from typing import Any

import AppKit

from ..domain.constants import Config
from ..domain.hotkeys import MODIFIER_DISPLAY_ORDER, format_hotkey_status
from ..infrastructure.hotkeys import (
    MODIFIER_FLAG_MASKS,
    MODIFIER_KEYCODES_MAP,
    _event_key_name_static,
)


def capture_hotkey_combination(title: str, message: str, current_combination: str = "") -> str | None:
    """Открывает модальное окно для захвата комбинации клавиш по нажатию."""
    captured_parts: list[str] = []
    pressed_modifiers: set[str] = set()
    confirmed_combination: list[str | None] = [None]

    alert = AppKit.NSAlert.alloc().init()
    alert.setMessageText_(title)
    alert.setInformativeText_(message)
    alert.addButtonWithTitle_("Применить")
    alert.addButtonWithTitle_("Отмена")

    input_field = AppKit.NSTextField.alloc().initWithFrame_(((0, 0), (280, 24)))
    input_field.setStringValue_(format_hotkey_status(current_combination) if current_combination else "")
    input_field.setEditable_(False)
    input_field.setSelectable_(False)
    input_field.setAlignment_(AppKit.NSTextAlignmentCenter)
    font = AppKit.NSFont.systemFontOfSize_(14)
    input_field.setFont_(font)
    alert.setAccessoryView_(input_field)

    def _update_display() -> None:
        """Обновляет текстовое поле с текущей комбинацией."""
        if captured_parts:
            combo = "+".join(captured_parts)
            input_field.setStringValue_(format_hotkey_status(combo))
        elif pressed_modifiers:
            sorted_mods = sorted(
                pressed_modifiers,
                key=lambda modifier: MODIFIER_DISPLAY_ORDER.index(modifier)
                if modifier in MODIFIER_DISPLAY_ORDER
                else 99,
            )
            combo = "+".join(sorted_mods)
            input_field.setStringValue_(format_hotkey_status(combo) + " + …")

    def _handle_flags(event: Any) -> Any:
        """Обрабатывает нажатия модификаторов внутри диалога."""
        key_code = int(event.keyCode())
        modifier_name = MODIFIER_KEYCODES_MAP.get(key_code)
        if modifier_name is None:
            return event

        modifier_flags = int(event.modifierFlags())
        mask = MODIFIER_FLAG_MASKS.get(modifier_name, 0)
        if modifier_flags & mask:
            pressed_modifiers.add(modifier_name)
        else:
            pressed_modifiers.discard(modifier_name)

        if not captured_parts:
            _update_display()
        return event

    def _handle_key_down(event: Any) -> Any | None:
        """Фиксирует обычную клавишу при зажатых модификаторах."""
        if not pressed_modifiers:
            return event

        key_name = _event_key_name_static(event)
        if not key_name:
            return event

        all_modifier_names = {
            "alt",
            "alt_l",
            "alt_r",
            "shift",
            "shift_l",
            "shift_r",
            "ctrl",
            "ctrl_l",
            "ctrl_r",
            "cmd",
            "cmd_l",
            "cmd_r",
        }
        if key_name in all_modifier_names:
            return event

        sorted_mods = sorted(
            pressed_modifiers,
            key=lambda modifier: MODIFIER_DISPLAY_ORDER.index(modifier)
            if modifier in MODIFIER_DISPLAY_ORDER
            else 99,
        )
        captured_parts.clear()
        captured_parts.extend(sorted_mods)
        captured_parts.append(key_name)
        _update_display()
        return None

    flags_mask = AppKit.NSEventMaskFlagsChanged
    key_down_mask = AppKit.NSEventMaskKeyDown

    local_flags_monitor = AppKit.NSEvent.addLocalMonitorForEventsMatchingMask_handler_(flags_mask, _handle_flags)
    local_key_monitor = AppKit.NSEvent.addLocalMonitorForEventsMatchingMask_handler_(key_down_mask, _handle_key_down)
    global_flags_monitor = AppKit.NSEvent.addGlobalMonitorForEventsMatchingMask_handler_(flags_mask, _handle_flags)
    global_key_monitor = AppKit.NSEvent.addGlobalMonitorForEventsMatchingMask_handler_(key_down_mask, _handle_key_down)

    try:
        response = alert.runModal()
    finally:
        AppKit.NSEvent.removeMonitor_(local_flags_monitor)
        AppKit.NSEvent.removeMonitor_(local_key_monitor)
        AppKit.NSEvent.removeMonitor_(global_flags_monitor)
        AppKit.NSEvent.removeMonitor_(global_key_monitor)

    _nsalert_first_button = 1000
    if response != _nsalert_first_button:
        return None

    if captured_parts:
        confirmed_combination[0] = "+".join(captured_parts)
    elif pressed_modifiers and len(pressed_modifiers) >= Config.MIN_HOTKEY_PARTS:
        sorted_mods = sorted(
            pressed_modifiers,
            key=lambda modifier: MODIFIER_DISPLAY_ORDER.index(modifier)
            if modifier in MODIFIER_DISPLAY_ORDER
            else 99,
        )
        confirmed_combination[0] = "+".join(sorted_mods)

    return confirmed_combination[0]
