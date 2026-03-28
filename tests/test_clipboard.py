"""Тесты работы с буфером обмена macOS.

Проверяет, что приложение может корректно записывать текст в буфер обмена
и читать его обратно.
"""

import sys

import pytest
import src.infrastructure.text_input as text_input_module
from src.domain.constants import Config
from src.infrastructure.text_input import copy_to_clipboard


@pytest.mark.skipif(sys.platform != "darwin", reason="Тесты буфера обмена только для macOS")
class TestClipboard:
    """Тесты буфера обмена."""

    def test_copy_ascii_text(self, app_module):
        """Латинский текст должен сохраняться в буфере обмена."""
        test_text = "Hello World"
        copy_to_clipboard(test_text)

        import AppKit

        pasteboard = AppKit.NSPasteboard.generalPasteboard()
        result = str(pasteboard.stringForType_(AppKit.NSPasteboardTypeString))
        assert result == test_text

    def test_copy_cyrillic_text(self, app_module):
        """Кириллический текст должен сохраняться в буфере обмена."""
        test_text = "Привет мир, это тест транскрибации"
        copy_to_clipboard(test_text)

        import AppKit

        pasteboard = AppKit.NSPasteboard.generalPasteboard()
        result = str(pasteboard.stringForType_(AppKit.NSPasteboardTypeString))
        assert result == test_text

    def test_copy_empty_text(self, app_module):
        """Пустая строка должна корректно записываться в буфер обмена."""
        copy_to_clipboard("")

        import AppKit

        pasteboard = AppKit.NSPasteboard.generalPasteboard()
        result = str(pasteboard.stringForType_(AppKit.NSPasteboardTypeString))
        assert result == ""

    def test_copy_multiline_text(self, app_module):
        """Многострочный текст должен сохраняться целиком."""
        test_text = "Первая строка\nВторая строка\nТретья строка"
        copy_to_clipboard(test_text)

        import AppKit

        pasteboard = AppKit.NSPasteboard.generalPasteboard()
        result = str(pasteboard.stringForType_(AppKit.NSPasteboardTypeString))
        assert result == test_text

    def test_copy_overwrites_previous(self, app_module):
        """Новая запись в буфер должна перезаписывать предыдущую."""
        copy_to_clipboard("Первый текст")
        copy_to_clipboard("Второй текст")

        import AppKit

        pasteboard = AppKit.NSPasteboard.generalPasteboard()
        result = str(pasteboard.stringForType_(AppKit.NSPasteboardTypeString))
        assert result == "Второй текст"

    def test_paste_uses_quartz_cmd_v_events(self, app_module, monkeypatch):
        """Автовставка должна отправлять системные keyboard events для Cmd+V."""
        posted_events = []
        created_events = []

        monkeypatch.setattr(text_input_module.time, "sleep", lambda *_args: None)  # type: ignore[attr-defined]
        monkeypatch.setattr(text_input_module.Quartz, "CGEventSourceCreate", lambda *_args: object())  # type: ignore[attr-defined]

        def fake_create(_source, keycode, is_key_down):
            event = {"keycode": keycode, "is_key_down": is_key_down, "flags": None}
            created_events.append(event)
            return event

        monkeypatch.setattr(text_input_module.Quartz, "CGEventCreateKeyboardEvent", fake_create)  # type: ignore[attr-defined]
        monkeypatch.setattr(text_input_module.Quartz, "CGEventSetFlags", lambda event, flags: event.__setitem__("flags", flags))  # type: ignore[attr-defined]
        monkeypatch.setattr(text_input_module.Quartz, "CGEventPost", lambda tap, event: posted_events.append((tap, dict(event))))  # type: ignore[attr-defined]

        text_input_module.send_cmd_v(
            frontmost_app_info=lambda: {"name": "Obsidian", "bundle_id": "md.obsidian", "pid": 42},
        )

        assert [event["keycode"] for event in created_events] == [
            Config.KEYCODE_COMMAND,
            Config.KEYCODE_V,
            Config.KEYCODE_V,
            Config.KEYCODE_COMMAND,
        ]
        assert [event["is_key_down"] for event in created_events] == [True, True, False, False]
        assert posted_events[0][0] == text_input_module.Quartz.kCGHIDEventTap  # type: ignore[attr-defined]
        assert posted_events[1][1]["flags"] == text_input_module.Quartz.kCGEventFlagMaskCommand  # type: ignore[attr-defined]
        assert posted_events[2][1]["flags"] == text_input_module.Quartz.kCGEventFlagMaskCommand  # type: ignore[attr-defined]
