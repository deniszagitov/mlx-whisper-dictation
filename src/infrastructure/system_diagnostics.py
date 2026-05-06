"""Расширенная диагностика macOS для расследования sleep/lock/display-сбоев."""

from __future__ import annotations

import logging
import os
import platform
import subprocess
import threading
from typing import Any

import AppKit
import Quartz

from ..domain.constants import Config

LOGGER = logging.getLogger(__name__)

_DIAGNOSTIC_OUTPUT_LIMIT = 12000
_USB_OUTPUT_LIMIT = 16000
_USB_FILTER_MARKERS = (
    "USB Product Name",
    "USB Vendor Name",
    "locationID",
    "idVendor",
    "idProduct",
    "kUSBCurrentAvailable",
    "kUSBCurrentRequired",
    "bMaxPower",
    "MX Brio",
    "PHL",
    "Hub",
)
_COMMANDS = (
    ("pmset_assertions", ("pmset", "-g", "assertions")),
    ("pmset_power_source", ("pmset", "-g", "ps")),
    ("display_profiler", ("system_profiler", "SPDisplaysDataType", "-detailLevel", "mini")),
    ("usb_ioreg", ("ioreg", "-p", "IOUSB", "-l", "-w0")),
    ("hid_idle", ("ioreg", "-r", "-c", "IOHIDSystem", "-l", "-w0")),
)


def _system_diagnostics_enabled() -> bool:
    """Проверяет, включены ли подробные системные снимки через env-флаг."""
    return os.getenv(Config.SYSTEM_DIAGNOSTICS_ENV) == "1"


def _command_output(command: tuple[str, ...]) -> str:
    """Возвращает stdout/stderr диагностической команды с таймаутом."""
    completed = subprocess.run(
        command,
        check=False,
        capture_output=True,
        text=True,
        timeout=Config.POWER_DIAGNOSTICS_COMMAND_TIMEOUT_SECONDS,
    )
    output = (completed.stdout or completed.stderr or "").strip()
    if completed.returncode != 0:
        output = f"exit={completed.returncode}\n{output}".strip()
    return output


def _limit_output(output: str, limit: int = _DIAGNOSTIC_OUTPUT_LIMIT) -> str:
    """Обрезает слишком большой вывод команды."""
    return output[:limit] if len(output) > limit else output


def _filter_usb_output(output: str) -> str:
    """Оставляет из IOUSB-дерева строки, полезные для питания/устройств."""
    filtered = [line for line in output.splitlines() if any(marker in line for marker in _USB_FILTER_MARKERS)]
    return _limit_output("\n".join(filtered), _USB_OUTPUT_LIMIT)


def _session_state() -> dict[str, str]:
    """Возвращает состояние текущей пользовательской сессии macOS."""
    try:
        session = Quartz.CGSessionCopyCurrentDictionary()
    except Exception:
        LOGGER.exception("🧪 Не удалось прочитать CGSessionCopyCurrentDictionary")
        return {}
    if session is None:
        return {}
    return {str(key): str(value) for key, value in dict(session).items()}


def _screen_snapshot() -> list[dict[str, Any]]:
    """Возвращает краткий снимок подключённых NSScreen."""
    snapshots: list[dict[str, Any]] = []
    try:
        screens = list(AppKit.NSScreen.screens() or [])
    except Exception:
        LOGGER.exception("🧪 Не удалось прочитать список экранов NSScreen")
        return snapshots

    for index, screen in enumerate(screens):
        frame = screen.frame()
        visible_frame = screen.visibleFrame()
        device_description = dict(screen.deviceDescription() or {})
        snapshots.append(
            {
                "index": index,
                "frame": (frame.origin.x, frame.origin.y, frame.size.width, frame.size.height),
                "visible_frame": (
                    visible_frame.origin.x,
                    visible_frame.origin.y,
                    visible_frame.size.width,
                    visible_frame.size.height,
                ),
                "device": {str(key): str(value) for key, value in device_description.items()},
            }
        )
    return snapshots


def _capture_system_diagnostics_sync(label: str) -> None:
    """Синхронно пишет расширенный снимок состояния macOS в stdout.log."""
    if platform.system() != "Darwin":
        return

    LOGGER.info("🧪 System snapshot [%s] session: %s", label, _session_state())
    LOGGER.info("🧪 System snapshot [%s] screens: %s", label, _screen_snapshot())

    for command_name, command in _COMMANDS:
        try:
            output = _command_output(command)
        except Exception:
            LOGGER.exception("🧪 System snapshot [%s]: не удалось выполнить %s", label, " ".join(command))
            continue
        output = _filter_usb_output(output) if command_name == "usb_ioreg" else _limit_output(output)
        LOGGER.info("🧪 System snapshot [%s] %s:\n%s", label, command_name, output or "<empty>")


def capture_system_diagnostics(label: str) -> None:
    """Асинхронно запускает расширенную диагностику macOS."""
    if platform.system() != "Darwin" or not _system_diagnostics_enabled():
        return
    thread = threading.Thread(
        target=_capture_system_diagnostics_sync,
        args=(label,),
        name="dictator-system-diagnostics",
        daemon=True,
    )
    thread.start()
