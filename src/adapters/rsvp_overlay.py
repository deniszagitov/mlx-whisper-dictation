"""RSVP overlay-адаптер на базе NSWindow."""

from __future__ import annotations

import logging
import threading
from dataclasses import replace
from typing import Any

import AppKit
import Foundation
import Quartz
from PyObjCTools.AppHelper import callAfter  # type: ignore[import-untyped]

from ..domain.reader_constants import rsvp_frame_interval_seconds
from ..domain.reader_types import RSVPConfig, RSVPFrame

LOGGER = logging.getLogger(__name__)
_HEX_COLOR_LENGTH = 6


def _call_on_main_thread(callback: Any, *args: Any) -> None:
    """Выполняет AppKit-операцию на главном потоке."""
    if AppKit.NSThread.isMainThread():
        callback(*args)
        return
    callAfter(callback, *args)


class RSVPOverlay:
    """Показывает текст из буфера обмена покадрово в borderless overlay."""

    _WINDOW_HEIGHT = 240
    _WINDOW_WIDTH_RATIO = 0.82
    _MIN_WINDOW_WIDTH = 720
    _MAX_WINDOW_WIDTH = 1_400
    _CORNER_RADIUS = 8
    _STEP_WORDS = 5
    _MIN_WPM = 100
    _MAX_WPM = 1_000

    def __init__(self) -> None:
        """Инициализирует RSVP overlay без создания окна."""
        self._lock = threading.RLock()
        self._window: Any | None = None
        self._label: Any | None = None
        self._frames: list[RSVPFrame] = []
        self._config = RSVPConfig()
        self._index = 0
        self._paused = False
        self._timer: threading.Timer | None = None

    def show_frames(self, frames: list[RSVPFrame], config: RSVPConfig) -> None:
        """Показывает overlay и запускает RSVP-воспроизведение."""
        with self._lock:
            self._cancel_timer_locked()
            self._frames = list(frames)
            self._config = config
            self._index = 0
            self._paused = False
        _call_on_main_thread(self._show_window)
        _call_on_main_thread(self._render_current_frame)
        self._schedule_next_frame()

    def close(self) -> None:
        """Закрывает overlay и останавливает таймеры."""
        with self._lock:
            self._cancel_timer_locked()
            self._frames = []
            self._index = 0
            self._paused = False
        _call_on_main_thread(self._close_window)

    def is_running(self) -> bool:
        """Сообщает, открыт ли RSVP overlay."""
        with self._lock:
            return bool(self._frames or self._window is not None)

    def handle_key(self, key_name: str) -> bool:
        """Обрабатывает управляющие клавиши RSVP."""
        if key_name == "esc":
            self.close()
            return True
        if not self.is_running():
            return False
        if key_name == "space":
            self._toggle_pause()
            return True
        if key_name == "left":
            self._seek_words(-self._STEP_WORDS)
            return True
        if key_name == "right":
            self._seek_words(self._STEP_WORDS)
            return True
        if key_name == "up":
            self._change_wpm(50)
            return True
        if key_name == "down":
            self._change_wpm(-50)
            return True
        return False

    def _show_window(self) -> None:
        """Создаёт NSWindow на главном потоке."""
        if not self._frames:
            return
        self._close_window()
        screen = AppKit.NSScreen.mainScreen()
        if screen is None:
            LOGGER.warning("📖 Нет доступного экрана для RSVP overlay")
            return

        screen_frame = screen.frame()
        width = min(max(screen_frame.size.width * self._WINDOW_WIDTH_RATIO, self._MIN_WINDOW_WIDTH), self._MAX_WINDOW_WIDTH)
        height = self._WINDOW_HEIGHT
        pos_x = screen_frame.origin.x + (screen_frame.size.width - width) / 2
        pos_y = screen_frame.origin.y + (screen_frame.size.height - height) / 2
        frame = ((pos_x, pos_y), (width, height))

        window = AppKit.NSWindow.alloc().initWithContentRect_styleMask_backing_defer_(
            frame,
            AppKit.NSWindowStyleMaskBorderless,
            AppKit.NSBackingStoreBuffered,
            False,
        )
        window.setLevel_(AppKit.NSStatusWindowLevel)
        window.setOpaque_(False)
        window.setIgnoresMouseEvents_(True)
        window.setHasShadow_(True)
        window.setReleasedWhenClosed_(False)
        window.setCollectionBehavior_(
            AppKit.NSWindowCollectionBehaviorCanJoinAllSpaces
            | AppKit.NSWindowCollectionBehaviorStationary
            | AppKit.NSWindowCollectionBehaviorFullScreenAuxiliary
        )
        window.setBackgroundColor_(AppKit.NSColor.clearColor())

        content_view = window.contentView()
        content_view.setWantsLayer_(True)
        layer = content_view.layer()
        layer.setCornerRadius_(self._CORNER_RADIUS)
        layer.setMasksToBounds_(True)
        layer.setBackgroundColor_(self._cg_color(self._config.background_color, alpha=0.94))

        label = AppKit.NSTextField.labelWithString_("")
        label.setFrame_(((0, 0), (width, height)))
        label.setAlignment_(AppKit.NSTextAlignmentCenter)
        label.setFont_(AppKit.NSFont.monospacedSystemFontOfSize_weight_(self._config.font_size, 0.0))
        label.setTextColor_(self._ns_color(self._config.text_color))
        label.setDrawsBackground_(False)
        label.setBezeled_(False)
        label.setEditable_(False)
        label.setSelectable_(False)
        content_view.addSubview_(label)

        window.orderFrontRegardless()
        self._window = window
        self._label = label
        LOGGER.info("📖 RSVP overlay открыт")

    def _close_window(self) -> None:
        """Закрывает NSWindow на главном потоке."""
        if self._window is None:
            self._label = None
            return
        self._window.orderOut_(None)
        self._window.close()
        self._window = None
        self._label = None
        LOGGER.info("📖 RSVP overlay закрыт")

    def _render_current_frame(self) -> None:
        """Рисует текущий RSVP-кадр."""
        if self._label is None:
            return
        with self._lock:
            if not self._frames:
                return
            frame = self._frames[min(self._index, len(self._frames) - 1)]
            config = self._config

        text = frame.text
        font = AppKit.NSFont.monospacedSystemFontOfSize_weight_(config.font_size, 0.0)
        attrs = {
            AppKit.NSFontAttributeName: font,
            AppKit.NSForegroundColorAttributeName: self._ns_color(config.text_color),
        }
        attributed = Foundation.NSMutableAttributedString.alloc().initWithString_attributes_(text, attrs)
        offset = 0
        orp_color = self._ns_color(config.orp_color)
        for token in frame.tokens:
            if token.text:
                location = offset + min(token.orp_index, len(token.text) - 1)
                attributed.addAttribute_value_range_(AppKit.NSForegroundColorAttributeName, orp_color, (location, 1))
            offset += len(token.text) + 1
        self._label.setAttributedStringValue_(attributed)

    def _schedule_next_frame(self) -> None:
        """Планирует следующий кадр без busy loop."""
        with self._lock:
            if self._paused or not self._frames:
                return
            interval = rsvp_frame_interval_seconds(self._config.chunk_size, self._config.wpm)
            self._cancel_timer_locked()
            timer = threading.Timer(interval, self._advance_frame)
            timer.daemon = True
            self._timer = timer
            timer.start()

    def _advance_frame(self) -> None:
        """Переходит к следующему RSVP-кадру."""
        with self._lock:
            self._timer = None
            if self._paused or not self._frames:
                return
            if self._index >= len(self._frames) - 1:
                should_close = True
            else:
                self._index += 1
                should_close = False

        if should_close:
            self.close()
            return

        _call_on_main_thread(self._render_current_frame)
        self._schedule_next_frame()

    def _toggle_pause(self) -> None:
        """Ставит RSVP на паузу или продолжает воспроизведение."""
        with self._lock:
            self._paused = not self._paused
            if self._paused:
                self._cancel_timer_locked()
                LOGGER.info("📖 RSVP поставлен на паузу")
                return
        LOGGER.info("📖 RSVP продолжен")
        self._schedule_next_frame()

    def _seek_words(self, word_delta: int) -> None:
        """Перемещает позицию RSVP примерно на заданное число слов."""
        with self._lock:
            if not self._frames:
                return
            frame_step = max(1, round(abs(word_delta) / max(1, self._config.chunk_size)))
            if word_delta < 0:
                self._index = max(0, self._index - frame_step)
            else:
                self._index = min(len(self._frames) - 1, self._index + frame_step)
            self._cancel_timer_locked()
        _call_on_main_thread(self._render_current_frame)
        self._schedule_next_frame()

    def _change_wpm(self, delta: int) -> None:
        """Меняет скорость RSVP на лету."""
        with self._lock:
            new_wpm = min(max(self._config.wpm + delta, self._MIN_WPM), self._MAX_WPM)
            self._config = replace(self._config, wpm=new_wpm)
            self._cancel_timer_locked()
        LOGGER.info("📖 RSVP скорость изменена: %d wpm", new_wpm)
        self._schedule_next_frame()

    def _cancel_timer_locked(self) -> None:
        """Отменяет активный таймер. Вызывать под lock."""
        timer = self._timer
        self._timer = None
        if timer is not None and timer.is_alive():
            timer.cancel()

    def _ns_color(self, hex_color: str) -> Any:
        """Преобразует hex-цвет в NSColor."""
        red, green, blue = self._rgb_components(hex_color)
        return AppKit.NSColor.colorWithCalibratedRed_green_blue_alpha_(red, green, blue, 1.0)

    def _cg_color(self, hex_color: str, *, alpha: float) -> Any:
        """Преобразует hex-цвет в CGColor."""
        red, green, blue = self._rgb_components(hex_color)
        return Quartz.CGColorCreateGenericRGB(red, green, blue, alpha)

    @staticmethod
    def _rgb_components(hex_color: str) -> tuple[float, float, float]:
        """Возвращает RGB-компоненты hex-строки."""
        normalized = hex_color.strip().lstrip("#")
        if len(normalized) != _HEX_COLOR_LENGTH:
            normalized = "111111"
        try:
            red = int(normalized[0:2], 16) / 255
            green = int(normalized[2:4], 16) / 255
            blue = int(normalized[4:6], 16) / 255
        except ValueError:
            return (0.07, 0.07, 0.07)
        return (red, green, blue)
