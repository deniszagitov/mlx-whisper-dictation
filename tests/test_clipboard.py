"""Тесты работы с буфером обмена macOS.

Проверяет, что приложение может корректно записывать текст в буфер обмена
и читать его обратно.
"""

import sys

import pytest
import src.transcriber as transcriber_module


@pytest.mark.skipif(sys.platform != "darwin", reason="Тесты буфера обмена только для macOS")
class TestClipboard:
    """Тесты буфера обмена."""

    def test_copy_ascii_text(self, app_module):
        """Латинский текст должен сохраняться в буфере обмена."""
        transcriber = app_module.SpeechTranscriber("dummy-model", diagnostics_store=app_module.DiagnosticsStore(enabled=False))
        test_text = "Hello World"
        transcriber._copy_text_to_clipboard(test_text)

        import AppKit

        pasteboard = AppKit.NSPasteboard.generalPasteboard()
        result = str(pasteboard.stringForType_(AppKit.NSPasteboardTypeString))
        assert result == test_text

    def test_copy_cyrillic_text(self, app_module):
        """Кириллический текст должен сохраняться в буфере обмена."""
        transcriber = app_module.SpeechTranscriber("dummy-model", diagnostics_store=app_module.DiagnosticsStore(enabled=False))
        test_text = "Привет мир, это тест транскрибации"
        transcriber._copy_text_to_clipboard(test_text)

        import AppKit

        pasteboard = AppKit.NSPasteboard.generalPasteboard()
        result = str(pasteboard.stringForType_(AppKit.NSPasteboardTypeString))
        assert result == test_text

    def test_copy_empty_text(self, app_module):
        """Пустая строка должна корректно записываться в буфер обмена."""
        transcriber = app_module.SpeechTranscriber("dummy-model", diagnostics_store=app_module.DiagnosticsStore(enabled=False))
        transcriber._copy_text_to_clipboard("")

        import AppKit

        pasteboard = AppKit.NSPasteboard.generalPasteboard()
        result = str(pasteboard.stringForType_(AppKit.NSPasteboardTypeString))
        assert result == ""

    def test_copy_multiline_text(self, app_module):
        """Многострочный текст должен сохраняться целиком."""
        transcriber = app_module.SpeechTranscriber("dummy-model", diagnostics_store=app_module.DiagnosticsStore(enabled=False))
        test_text = "Первая строка\nВторая строка\nТретья строка"
        transcriber._copy_text_to_clipboard(test_text)

        import AppKit

        pasteboard = AppKit.NSPasteboard.generalPasteboard()
        result = str(pasteboard.stringForType_(AppKit.NSPasteboardTypeString))
        assert result == test_text

    def test_copy_overwrites_previous(self, app_module):
        """Новая запись в буфер должна перезаписывать предыдущую."""
        transcriber = app_module.SpeechTranscriber("dummy-model", diagnostics_store=app_module.DiagnosticsStore(enabled=False))
        transcriber._copy_text_to_clipboard("Первый текст")
        transcriber._copy_text_to_clipboard("Второй текст")

        import AppKit

        pasteboard = AppKit.NSPasteboard.generalPasteboard()
        result = str(pasteboard.stringForType_(AppKit.NSPasteboardTypeString))
        assert result == "Второй текст"

    def test_paste_uses_quartz_cmd_v_events(self, app_module, monkeypatch):
        """Автовставка должна отправлять системные keyboard events для Cmd+V."""
        transcriber = app_module.SpeechTranscriber("dummy-model", diagnostics_store=app_module.DiagnosticsStore(enabled=False))
        posted_events = []
        created_events = []

        monkeypatch.setattr(transcriber_module.time, "sleep", lambda *_args: None)
        monkeypatch.setattr(
            transcriber_module,
            "frontmost_application_info",
            lambda: {"name": "Obsidian", "bundle_id": "md.obsidian", "pid": 42},
        )
        monkeypatch.setattr(transcriber_module.Quartz, "CGEventSourceCreate", lambda *_args: object())

        def fake_create(_source, keycode, is_key_down):
            event = {"keycode": keycode, "is_key_down": is_key_down, "flags": None}
            created_events.append(event)
            return event

        monkeypatch.setattr(transcriber_module.Quartz, "CGEventCreateKeyboardEvent", fake_create)
        monkeypatch.setattr(transcriber_module.Quartz, "CGEventSetFlags", lambda event, flags: event.__setitem__("flags", flags))
        monkeypatch.setattr(transcriber_module.Quartz, "CGEventPost", lambda tap, event: posted_events.append((tap, dict(event))))

        transcriber._send_cmd_v()

        assert [event["keycode"] for event in created_events] == [
            app_module.KEYCODE_COMMAND,
            app_module.KEYCODE_V,
            app_module.KEYCODE_V,
            app_module.KEYCODE_COMMAND,
        ]
        assert [event["is_key_down"] for event in created_events] == [True, True, False, False]
        assert posted_events[0][0] == transcriber_module.Quartz.kCGHIDEventTap
        assert posted_events[1][1]["flags"] == transcriber_module.Quartz.kCGEventFlagMaskCommand
        assert posted_events[2][1]["flags"] == transcriber_module.Quartz.kCGEventFlagMaskCommand
