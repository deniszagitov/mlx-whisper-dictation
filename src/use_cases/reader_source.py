"""Общие правила чтения источника reader-сценариев из буфера обмена."""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING

from ..domain.reader_constants import READER_CLIPBOARD_CHAR_LIMIT
from .preprocess_text import ReaderSourceText, prepare_reader_source_text

if TYPE_CHECKING:
    from ..domain.reader_types import ReaderClipboardPort

Notify = Callable[[str, str], None]


def read_reader_source(clipboard: ReaderClipboardPort, notify: Notify) -> ReaderSourceText | None:
    """Читает и валидирует текст из буфера обмена для reader-сценария."""
    content = clipboard.read_content()
    if not content.has_text_type:
        notify("MLX Whisper Dictation", "В буфере не текст.")
        return None
    if content.text is None or not content.text.strip():
        notify("MLX Whisper Dictation", "Буфер пуст.")
        return None

    source = prepare_reader_source_text(content.text)
    if source.truncated:
        notify(
            "MLX Whisper Dictation",
            f"Текст длиннее {READER_CLIPBOARD_CHAR_LIMIT} символов. Использую первые {READER_CLIPBOARD_CHAR_LIMIT}.",
        )
    return source
