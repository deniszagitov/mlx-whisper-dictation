"""Всплывающий индикатор записи рядом с курсором ввода."""

from __future__ import annotations

import logging

import AppKit
import Quartz

LOGGER = logging.getLogger(__name__)


class RecordingOverlay:
    """Всплывающий индикатор записи рядом с курсором ввода.

    Показывает полупрозрачное окошко с красной точкой и таймером записи.
    Окошко появляется рядом с текстовым курсором (кареткой) при старте записи
    и остаётся на месте до завершения или отмены записи.
    Если получить позицию каретки невозможно, используется позиция мыши.

    Attributes:
        _window: NSWindow окошко или None, если не показано.
        _label: NSTextField для отображения текста таймера.
    """

    _WINDOW_WIDTH = 110
    _WINDOW_HEIGHT = 30
    _FONT_SIZE = 14
    _CORNER_RADIUS = 8
    _CARET_OFFSET_X = 4
    _CARET_OFFSET_Y = 4
    _MOUSE_OFFSET_X = 20
    _MOUSE_OFFSET_Y = 10
    _LABEL_HEIGHT = 20

    def __init__(self) -> None:
        """Инициализирует overlay без создания окна."""
        self._window = None
        self._label = None

    @staticmethod
    def _get_caret_position() -> tuple[float, float, float] | None:
        """Определяет экранную позицию курсора ввода через Accessibility API.

        Запрашивает у сфокусированного UI-элемента диапазон выделения
        (kAXSelectedTextRangeAttribute), затем получает его экранные
        координаты через kAXBoundsForRangeParameterizedAttribute.

        Returns:
            Кортеж (x, y, height) в координатах Quartz (origin сверху-слева)
            или None, если курсор ввода определить не удалось.
        """
        try:
            import HIServices  # noqa: PLC0415

            system_wide = HIServices.AXUIElementCreateSystemWide()
            err, focused = HIServices.AXUIElementCopyAttributeValue(
                system_wide, HIServices.kAXFocusedUIElementAttribute, None,
            )
            if err != 0 or focused is None:
                return None

            err, text_range = HIServices.AXUIElementCopyAttributeValue(
                focused, "AXSelectedTextRange", None,
            )
            if err != 0 or text_range is None:
                return None

            err, bounds_value = HIServices.AXUIElementCopyParameterizedAttributeValue(
                focused, "AXBoundsForRange", text_range, None,
            )
            if err != 0 or bounds_value is None:
                return None

            # bounds_value — AXValue типа CGRect
            if hasattr(bounds_value, "x"):
                # Прямой CGRect/NSRect
                return (bounds_value.origin.x, bounds_value.origin.y, bounds_value.size.height)

            # AXValueGetValue распаковывает AXValue в CGRect
            import ctypes as _ct  # noqa: PLC0415

            class _CGRect(_ct.Structure):
                class _CGPoint(_ct.Structure):
                    _fields_ = [("x", _ct.c_double), ("y", _ct.c_double)]

                class _CGSize(_ct.Structure):
                    _fields_ = [("width", _ct.c_double), ("height", _ct.c_double)]

                _fields_ = [("origin", _CGPoint), ("size", _CGSize)]

            rect = _CGRect()
            # kAXValueTypeCGRect = 4
            ok = HIServices.AXValueGetValue(bounds_value, 4, _ct.byref(rect))
            if not ok:
                return None
            return (rect.origin.x, rect.origin.y, rect.size.height)  # noqa: TRY300
        except Exception:
            LOGGER.debug("🎯 Не удалось определить позицию каретки через AX API", exc_info=True)
            return None

    def show(self) -> None:
        """Показывает индикатор записи рядом с курсором ввода (или мыши)."""
        try:
            self.hide()

            screen = AppKit.NSScreen.mainScreen()
            if screen is None:
                LOGGER.warning("🎯 Нет доступного экрана для показа индикатора")
                return

            screen_frame = screen.frame()
            screen_height = screen_frame.size.height

            # Пробуем получить позицию каретки (координаты Quartz: origin сверху-слева)
            caret = self._get_caret_position()
            if caret is not None:
                qx, qy, caret_h = caret
                # Конвертируем Quartz → Cocoa (origin снизу-слева)
                cocoa_y = screen_height - qy - caret_h
                pos_x = qx + self._CARET_OFFSET_X
                pos_y = cocoa_y - self._WINDOW_HEIGHT - self._CARET_OFFSET_Y
                LOGGER.info("🎯 Позиция каретки: Quartz(%.0f, %.0f), Cocoa(%.0f, %.0f)", qx, qy, pos_x, pos_y)
            else:
                # Фоллбэк: позиция мыши (уже в координатах Cocoa)
                mouse_loc = AppKit.NSEvent.mouseLocation()
                pos_x = mouse_loc.x + self._MOUSE_OFFSET_X
                pos_y = mouse_loc.y + self._MOUSE_OFFSET_Y
                LOGGER.info("🎯 Каретка не найдена, используем позицию мыши: (%.0f, %.0f)", pos_x, pos_y)

            # Следим, чтобы окошко не выходило за границы экрана
            if pos_x + self._WINDOW_WIDTH > screen_frame.origin.x + screen_frame.size.width:
                pos_x = pos_x - self._WINDOW_WIDTH - self._CARET_OFFSET_X * 2
            pos_y = max(pos_y, screen_frame.origin.y)
            if pos_y + self._WINDOW_HEIGHT > screen_frame.origin.y + screen_frame.size.height:
                pos_y = screen_frame.origin.y + screen_frame.size.height - self._WINDOW_HEIGHT

            frame = ((pos_x, pos_y), (self._WINDOW_WIDTH, self._WINDOW_HEIGHT))

            # NSWindowStyleMaskBorderless = 0 — окно без рамки и заголовка
            window = AppKit.NSWindow.alloc().initWithContentRect_styleMask_backing_defer_(
                frame,
                0,
                AppKit.NSBackingStoreBuffered,
                False,
            )
            window.setLevel_(AppKit.NSFloatingWindowLevel)
            window.setOpaque_(False)
            window.setIgnoresMouseEvents_(True)
            window.setHasShadow_(True)
            window.setMovableByWindowBackground_(False)
            window.setReleasedWhenClosed_(False)
            window.setCollectionBehavior_(
                AppKit.NSWindowCollectionBehaviorCanJoinAllSpaces
                | AppKit.NSWindowCollectionBehaviorStationary
            )

            # Прозрачный фон окна, визуал рисуем через content view
            window.setBackgroundColor_(AppKit.NSColor.clearColor())

            content_view = window.contentView()
            content_view.setWantsLayer_(True)
            layer = content_view.layer()
            layer.setCornerRadius_(self._CORNER_RADIUS)
            layer.setMasksToBounds_(True)
            layer.setBackgroundColor_(
                Quartz.CGColorCreateGenericRGB(0.15, 0.15, 0.15, 0.88)
            )

            label = AppKit.NSTextField.labelWithString_("🔴 00:00")
            label_y = (self._WINDOW_HEIGHT - self._LABEL_HEIGHT) / 2.0
            label.setFrame_(((0, label_y), (self._WINDOW_WIDTH, self._LABEL_HEIGHT)))
            label.setAlignment_(AppKit.NSTextAlignmentCenter)
            label.setTextColor_(AppKit.NSColor.whiteColor())
            label.setFont_(AppKit.NSFont.monospacedSystemFontOfSize_weight_(self._FONT_SIZE, 0.0))
            label.setDrawsBackground_(False)
            label.setBezeled_(False)
            content_view.addSubview_(label)

            window.orderFrontRegardless()

            self._window = window
            self._label = label
            LOGGER.info("🎯 Индикатор записи показан: (%.0f, %.0f)", pos_x, pos_y)
        except Exception:
            LOGGER.exception("❌ Не удалось показать индикатор записи")

    def update_time(self, elapsed_seconds: float) -> None:
        """Обновляет отображение таймера.

        Args:
            elapsed_seconds: Количество прошедших секунд записи.
        """
        if self._label is None:
            return
        minutes, seconds = divmod(int(elapsed_seconds), 60)
        self._label.setStringValue_(f"🔴 {minutes:02d}:{seconds:02d}")

    def hide(self) -> None:
        """Скрывает и уничтожает окошко индикатора."""
        if self._window is not None:
            self._window.orderOut_(None)
            self._window.close()
            self._window = None
            self._label = None
            LOGGER.info("🎯 Индикатор записи скрыт")

    @property
    def is_visible(self) -> bool:
        """Возвращает True, если индикатор сейчас показан."""
        return self._window is not None
