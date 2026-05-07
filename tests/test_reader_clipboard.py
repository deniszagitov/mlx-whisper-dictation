"""Тесты read-only clipboard reader для reader-модуля."""

from types import SimpleNamespace

import src.infrastructure.clipboard_reader as clipboard_reader_module
from src.infrastructure.clipboard_reader import PasteboardReader


class FakePasteboard:
    """Фейковый NSPasteboard для unit-тестов."""

    def __init__(self, text, *, has_text=True):
        self.text = text
        self.has_text = has_text
        self.clear_calls = 0
        self.write_calls = 0

    def availableTypeFromArray_(self, _types):
        return clipboard_reader_module.AppKit.NSPasteboardTypeString if self.has_text else None

    def stringForType_(self, _text_type):
        return self.text

    def clearContents(self):
        self.clear_calls += 1

    def setString_forType_(self, _text, _text_type):
        self.write_calls += 1


def test_clipboard_reader_returns_non_empty_text(monkeypatch):
    pasteboard = FakePasteboard("текст")
    monkeypatch.setattr(clipboard_reader_module, "AppKit", SimpleNamespace(NSPasteboardTypeString="public.utf8-plain-text"))

    result = PasteboardReader(lambda: pasteboard).read_content()

    assert result.has_text_type is True
    assert result.text == "текст"
    assert pasteboard.clear_calls == 0
    assert pasteboard.write_calls == 0


def test_clipboard_reader_distinguishes_empty_text(monkeypatch):
    pasteboard = FakePasteboard("")
    monkeypatch.setattr(clipboard_reader_module, "AppKit", SimpleNamespace(NSPasteboardTypeString="public.utf8-plain-text"))

    result = PasteboardReader(lambda: pasteboard).read_content()

    assert result.has_text_type is True
    assert result.text == ""


def test_clipboard_reader_distinguishes_non_text(monkeypatch):
    pasteboard = FakePasteboard(None, has_text=False)
    monkeypatch.setattr(clipboard_reader_module, "AppKit", SimpleNamespace(NSPasteboardTypeString="public.utf8-plain-text"))

    result = PasteboardReader(lambda: pasteboard).read_content()

    assert result.has_text_type is False
    assert result.text is None
