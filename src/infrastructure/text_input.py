"""Runtime-вставка текста и работа с буфером обмена через macOS API."""

from __future__ import annotations

import importlib
import logging
import time
from typing import TYPE_CHECKING, Any

import AppKit
import Quartz

from ..domain.constants import Config

if TYPE_CHECKING:
    from collections.abc import Callable

LOGGER = logging.getLogger(__name__)


def read_clipboard() -> str | None:
    """Читает текстовое содержимое из системного буфера обмена."""
    pasteboard = AppKit.NSPasteboard.generalPasteboard()
    result: str | None = pasteboard.stringForType_(AppKit.NSPasteboardTypeString)
    return result


def copy_to_clipboard(text: str) -> None:
    """Копирует текст в системный буфер обмена."""
    pasteboard = AppKit.NSPasteboard.generalPasteboard()
    pasteboard.clearContents()
    pasteboard.setString_forType_(text, AppKit.NSPasteboardTypeString)


def type_text_via_cgevent(
    text: str,
    *,
    frontmost_app_info: Callable[[], Any | None] | None = None,
) -> None:
    """Вставляет текст через отправку Unicode-символов посредством CGEvent."""
    time.sleep(0.05)
    active_app = frontmost_app_info() if frontmost_app_info is not None else None
    if active_app is not None:
        LOGGER.info(
            "⌨️ CGEvent Unicode ввод в приложение: name=%s, bundle_id=%s, pid=%s",
            active_app["name"],
            active_app["bundle_id"],
            active_app["pid"],
        )

    event_source = Quartz.CGEventSourceCreate(Quartz.kCGEventSourceStateHIDSystemState)
    if event_source is None:
        raise RuntimeError("Не удалось создать источник системных keyboard events")

    for i in range(0, len(text), Config.CGEVENT_UNICODE_CHUNK_SIZE):
        chunk = text[i : i + Config.CGEVENT_UNICODE_CHUNK_SIZE]

        event_down = Quartz.CGEventCreateKeyboardEvent(event_source, 0, True)
        if event_down is None:
            raise RuntimeError("Не удалось создать keyDown event для CGEvent Unicode ввода")
        Quartz.CGEventKeyboardSetUnicodeString(event_down, len(chunk), chunk)
        Quartz.CGEventPost(Quartz.kCGHIDEventTap, event_down)

        event_up = Quartz.CGEventCreateKeyboardEvent(event_source, 0, False)
        if event_up is None:
            raise RuntimeError("Не удалось создать keyUp event для CGEvent Unicode ввода")
        Quartz.CGEventKeyboardSetUnicodeString(event_up, len(chunk), chunk)
        Quartz.CGEventPost(Quartz.kCGHIDEventTap, event_up)

        if i + Config.CGEVENT_UNICODE_CHUNK_SIZE < len(text):
            time.sleep(Config.CGEVENT_CHUNK_DELAY)


def insert_text_via_ax(text: str) -> None:
    """Вставляет текст через macOS Accessibility API."""
    hiservices = importlib.import_module("HIServices")
    system_wide = hiservices.AXUIElementCreateSystemWide()

    err, focused_element = hiservices.AXUIElementCopyAttributeValue(system_wide, hiservices.kAXFocusedUIElementAttribute, None)
    if err != 0 or focused_element is None:
        raise RuntimeError(f"Не удалось получить сфокусированный UI-элемент (AXError={err})")

    err = hiservices.AXUIElementSetAttributeValue(focused_element, hiservices.kAXSelectedTextAttribute, text)
    if err != 0:
        raise RuntimeError(f"Не удалось записать текст через AX API (AXError={err})")


def send_cmd_v(*, frontmost_app_info: Callable[[], Any | None] | None = None) -> None:
    """Отправляет системные keyboard events для Cmd+V."""
    time.sleep(0.05)
    active_app = frontmost_app_info() if frontmost_app_info is not None else None
    if active_app is not None:
        LOGGER.info(
            "🎤 Пытаюсь вставить в активное приложение: name=%s, bundle_id=%s, pid=%s",
            active_app["name"],
            active_app["bundle_id"],
            active_app["pid"],
        )

    event_source = Quartz.CGEventSourceCreate(Quartz.kCGEventSourceStateHIDSystemState)
    if event_source is None:
        raise RuntimeError("Не удалось создать источник системных keyboard events")

    command_down = Quartz.CGEventCreateKeyboardEvent(event_source, Config.KEYCODE_COMMAND, True)
    paste_down = Quartz.CGEventCreateKeyboardEvent(event_source, Config.KEYCODE_V, True)
    paste_up = Quartz.CGEventCreateKeyboardEvent(event_source, Config.KEYCODE_V, False)
    command_up = Quartz.CGEventCreateKeyboardEvent(event_source, Config.KEYCODE_COMMAND, False)

    if not all((command_down, paste_down, paste_up, command_up)):
        raise RuntimeError("Не удалось создать keyboard events для Cmd+V")

    Quartz.CGEventSetFlags(command_down, Quartz.kCGEventFlagMaskCommand)
    Quartz.CGEventSetFlags(paste_down, Quartz.kCGEventFlagMaskCommand)
    Quartz.CGEventSetFlags(paste_up, Quartz.kCGEventFlagMaskCommand)

    Quartz.CGEventPost(Quartz.kCGHIDEventTap, command_down)
    Quartz.CGEventPost(Quartz.kCGHIDEventTap, paste_down)
    Quartz.CGEventPost(Quartz.kCGHIDEventTap, paste_up)
    Quartz.CGEventPost(Quartz.kCGHIDEventTap, command_up)
