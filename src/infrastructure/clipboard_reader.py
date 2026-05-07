"""Read-only чтение системного буфера обмена для reader-модуля."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import AppKit

from ..domain.reader_types import ClipboardContent

if TYPE_CHECKING:
    from collections.abc import Callable


class PasteboardReader:
    """Читает текст из NSPasteboard без изменения содержимого буфера."""

    def __init__(self, pasteboard_factory: Callable[[], Any] | None = None) -> None:
        self._pasteboard_factory = pasteboard_factory or AppKit.NSPasteboard.generalPasteboard

    def read_content(self) -> ClipboardContent:
        """Возвращает текстовый снимок NSPasteboard.general."""
        pasteboard = self._pasteboard_factory()
        text_type = AppKit.NSPasteboardTypeString
        has_text_type = self._has_text_type(pasteboard, text_type)
        if not has_text_type:
            return ClipboardContent(text=None, has_text_type=False)
        value = pasteboard.stringForType_(text_type)
        return ClipboardContent(text=None if value is None else str(value), has_text_type=True)

    @staticmethod
    def _has_text_type(pasteboard: Any, text_type: str) -> bool:
        """Проверяет наличие текстового типа в pasteboard."""
        if hasattr(pasteboard, "availableTypeFromArray_"):
            return pasteboard.availableTypeFromArray_([text_type]) is not None
        return pasteboard.stringForType_(text_type) is not None
