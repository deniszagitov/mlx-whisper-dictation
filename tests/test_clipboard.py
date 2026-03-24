"""Тесты работы с буфером обмена macOS.

Проверяет, что приложение может корректно записывать текст в буфер обмена
и читать его обратно.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


@pytest.mark.skipif(sys.platform != "darwin", reason="Тесты буфера обмена только для macOS")
class TestClipboard:
    """Тесты буфера обмена."""

    def test_copy_ascii_text(self):
        """Латинский текст должен сохраняться в буфере обмена."""
        from importlib import import_module

        wd = import_module("whisper-dictation")
        transcriber = wd.SpeechTranscriber("dummy-model")
        test_text = "Hello World"
        transcriber._copy_text_to_clipboard(test_text)

        import AppKit

        pasteboard = AppKit.NSPasteboard.generalPasteboard()
        result = str(pasteboard.stringForType_(AppKit.NSPasteboardTypeString))
        assert result == test_text

    def test_copy_cyrillic_text(self):
        """Кириллический текст должен сохраняться в буфере обмена."""
        from importlib import import_module

        wd = import_module("whisper-dictation")
        transcriber = wd.SpeechTranscriber("dummy-model")
        test_text = "Привет мир, это тест транскрибации"
        transcriber._copy_text_to_clipboard(test_text)

        import AppKit

        pasteboard = AppKit.NSPasteboard.generalPasteboard()
        result = str(pasteboard.stringForType_(AppKit.NSPasteboardTypeString))
        assert result == test_text

    def test_copy_empty_text(self):
        """Пустая строка должна корректно записываться в буфер обмена."""
        from importlib import import_module

        wd = import_module("whisper-dictation")
        transcriber = wd.SpeechTranscriber("dummy-model")
        transcriber._copy_text_to_clipboard("")

        import AppKit

        pasteboard = AppKit.NSPasteboard.generalPasteboard()
        result = str(pasteboard.stringForType_(AppKit.NSPasteboardTypeString))
        assert result == ""

    def test_copy_multiline_text(self):
        """Многострочный текст должен сохраняться целиком."""
        from importlib import import_module

        wd = import_module("whisper-dictation")
        transcriber = wd.SpeechTranscriber("dummy-model")
        test_text = "Первая строка\nВторая строка\nТретья строка"
        transcriber._copy_text_to_clipboard(test_text)

        import AppKit

        pasteboard = AppKit.NSPasteboard.generalPasteboard()
        result = str(pasteboard.stringForType_(AppKit.NSPasteboardTypeString))
        assert result == test_text

    def test_copy_overwrites_previous(self):
        """Новая запись в буфер должна перезаписывать предыдущую."""
        from importlib import import_module

        wd = import_module("whisper-dictation")
        transcriber = wd.SpeechTranscriber("dummy-model")
        transcriber._copy_text_to_clipboard("Первый текст")
        transcriber._copy_text_to_clipboard("Второй текст")

        import AppKit

        pasteboard = AppKit.NSPasteboard.generalPasteboard()
        result = str(pasteboard.stringForType_(AppKit.NSPasteboardTypeString))
        assert result == "Второй текст"
