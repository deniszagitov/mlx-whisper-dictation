"""Окна вывода и debug-панель Zipper для macOS menu bar приложения."""

from __future__ import annotations

import logging
import threading
from typing import TYPE_CHECKING, Any

import AppKit
from PyObjCTools.AppHelper import callAfter  # type: ignore[import-untyped]

from ..domain.model_downloads import ModelRequiredError
from ..domain.reader_types import TTSConfig

if TYPE_CHECKING:
    from ..domain.zipper import ZipperEvent

LOGGER = logging.getLogger(__name__)


def _on_main_thread(callback: Any, *args: Any) -> None:
    """Выполняет UI-действие на главном потоке AppKit."""
    if AppKit.NSThread.isMainThread():
        callback(*args)
        return
    callAfter(callback, *args)


class ZipperTextOutput:
    """Показывает текстовые ответы Zipper и поток debug-событий."""

    def __init__(self) -> None:
        self._debug_window: Any | None = None
        self._debug_text_view: Any | None = None
        self._debug_events: list[ZipperEvent] = []

    def show_text(self, title: str, text: str) -> None:
        """Показывает текстовое окно с результатом Zipper."""
        _on_main_thread(self._show_text_on_main_thread, title, text)

    def confirm(self, title: str, message: str) -> bool:
        """Запрашивает подтверждение потенциально опасного действия."""
        if AppKit.NSThread.isMainThread():
            return self._confirm_on_main_thread(title, message)

        done = threading.Event()
        result: dict[str, bool] = {"confirmed": False}

        def ask() -> None:
            result["confirmed"] = self._confirm_on_main_thread(title, message)
            done.set()

        callAfter(ask)
        done.wait()
        return result["confirmed"]

    def _confirm_on_main_thread(self, title: str, message: str) -> bool:
        """Показывает modal confirmation alert на главном потоке."""
        alert = AppKit.NSAlert.alloc().init()
        alert.setMessageText_(title)
        alert.setInformativeText_(message)
        alert.addButtonWithTitle_("Выполнить")
        alert.addButtonWithTitle_("Отмена")
        return bool(alert.runModal() == AppKit.NSAlertFirstButtonReturn)

    def set_debug_visible(self, visible: bool) -> None:
        """Показывает или скрывает debug-панель Zipper."""
        _on_main_thread(self._set_debug_visible_on_main_thread, visible)

    def append_debug_event(self, event: ZipperEvent) -> None:
        """Добавляет событие в debug-панель."""
        self._debug_events.append(event)
        _on_main_thread(self._append_debug_event_on_main_thread, event)

    def debug_events(self) -> list[ZipperEvent]:
        """Возвращает накопленные debug-события."""
        return list(self._debug_events)

    def _show_text_on_main_thread(self, title: str, text: str) -> None:
        AppKit.NSApplication.sharedApplication().activateIgnoringOtherApps_(True)
        alert = AppKit.NSAlert.alloc().init()
        alert.setMessageText_(title)
        alert.setInformativeText_(text)
        alert.addButtonWithTitle_("ОК")
        alert.runModal()

    def _set_debug_visible_on_main_thread(self, visible: bool) -> None:
        if visible:
            self._ensure_debug_window()
            if self._debug_window is not None:
                self._debug_window.orderFrontRegardless()
            return
        if self._debug_window is not None:
            self._debug_window.orderOut_(None)

    def _ensure_debug_window(self) -> None:
        if self._debug_window is not None:
            return
        screen = AppKit.NSScreen.mainScreen()
        if screen is None:
            return
        frame = screen.visibleFrame()
        width = 360
        panel_frame = ((frame.origin.x + frame.size.width - width, frame.origin.y), (width, frame.size.height))
        window = AppKit.NSWindow.alloc().initWithContentRect_styleMask_backing_defer_(
            panel_frame,
            AppKit.NSWindowStyleMaskTitled | AppKit.NSWindowStyleMaskClosable | AppKit.NSWindowStyleMaskResizable,
            AppKit.NSBackingStoreBuffered,
            False,
        )
        window.setTitle_("Zipper Debug")
        window.setLevel_(AppKit.NSFloatingWindowLevel)
        window.setCollectionBehavior_(AppKit.NSWindowCollectionBehaviorCanJoinAllSpaces | AppKit.NSWindowCollectionBehaviorStationary)

        scroll_view = AppKit.NSScrollView.alloc().initWithFrame_(((0, 0), (width, frame.size.height)))
        scroll_view.setAutoresizingMask_(AppKit.NSViewWidthSizable | AppKit.NSViewHeightSizable)
        text_view = AppKit.NSTextView.alloc().initWithFrame_(((0, 0), (width, frame.size.height)))
        text_view.setEditable_(False)
        text_view.setSelectable_(True)
        text_view.setFont_(AppKit.NSFont.monospacedSystemFontOfSize_weight_(12, 0.0))
        text_view.setString_(self._format_debug_events())
        scroll_view.setDocumentView_(text_view)
        scroll_view.setHasVerticalScroller_(True)
        window.setContentView_(scroll_view)

        self._debug_window = window
        self._debug_text_view = text_view

    def _append_debug_event_on_main_thread(self, _event: ZipperEvent) -> None:
        if self._debug_text_view is None:
            return
        self._debug_text_view.setString_(self._format_debug_events())
        self._debug_text_view.scrollRangeToVisible_((len(str(self._debug_text_view.string())), 0))

    def _format_debug_events(self) -> str:
        return "\n".join(f"[{event.kind}] {event.message}\n{event.payload}\n" for event in self._debug_events[-500:])


class ZipperVoiceOutput:
    """Озвучивает короткие ответы Zipper через текущий TTS backend."""

    def __init__(self, speaker: Any, config_factory: Any | None = None) -> None:
        self.speaker = speaker
        self.config_factory = config_factory

    def speak(self, text: str) -> None:
        """Озвучивает текст через TTS router."""
        try:
            config = self.config_factory() if self.config_factory is not None else TTSConfig.from_values(rate_multiplier=1.0, voice_id=None)
            self.speaker.speak(text, config)
        except ModelRequiredError:
            raise
        except Exception:
            LOGGER.exception("🧷 Не удалось озвучить ответ Zipper")
