"""Power assertion macOS для активной диктовки."""

from __future__ import annotations

import ctypes
import ctypes.util
import logging
import os
import subprocess
import sys
import threading
from typing import Any

from ..domain.constants import Config

LOGGER = logging.getLogger(__name__)

_IOPM_ASSERTION_LEVEL_ON = 255
_IOPM_SUCCESS = 0
_CF_STRING_ENCODING_UTF8 = 0x08000100
_NO_DISPLAY_SLEEP_ASSERTION = "NoDisplaySleepAssertion"
_DEFAULT_REASON = "MLX Whisper Dictation: запись и обработка"
_POWER_DIAGNOSTIC_OUTPUT_LIMIT = 8000
_POWER_DIAGNOSTIC_COMMANDS = (
    ("assertions", ("pmset", "-g", "assertions")),
    ("battery", ("pmset", "-g", "ps")),
)


def _command_output(command: tuple[str, ...]) -> str:
    """Возвращает безопасно обрезанный вывод диагностической команды."""
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
    return output[:_POWER_DIAGNOSTIC_OUTPUT_LIMIT] if len(output) > _POWER_DIAGNOSTIC_OUTPUT_LIMIT else output


def _power_diagnostics_enabled() -> bool:
    """Проверяет, включены ли подробные power-снимки через env-флаг."""
    return os.getenv(Config.POWER_DIAGNOSTICS_ENV) == "1"


def _log_power_diagnostics_sync(label: str, assertion_id: int | None) -> None:
    """Пишет снимок power-состояния macOS в лог приложения."""
    if sys.platform != "darwin":
        return

    LOGGER.info(
        "💡 Power snapshot [%s]: pid=%s, assertion_id=%s",
        label,
        os.getpid(),
        assertion_id,
    )
    for command_name, command in _POWER_DIAGNOSTIC_COMMANDS:
        try:
            output = _command_output(command)
        except Exception:
            LOGGER.exception("💡 Power snapshot [%s]: не удалось выполнить %s", label, " ".join(command))
            continue
        LOGGER.info("💡 Power snapshot [%s] %s:\n%s", label, command_name, output or "<empty>")


def log_power_diagnostics(label: str, assertion_id: int | None = None) -> None:
    """Асинхронно пишет системный power-снимок, не блокируя запись и вставку."""
    if sys.platform != "darwin" or not _power_diagnostics_enabled():
        return
    thread = threading.Thread(
        target=_log_power_diagnostics_sync,
        args=(label, assertion_id),
        name="dictator-power-diagnostics",
        daemon=True,
    )
    thread.start()


class MacOSDisplaySleepAssertion:
    """Держит macOS display-awake assertion на время записи и обработки."""

    def __init__(self, reason: str = _DEFAULT_REASON) -> None:
        self.reason = reason
        self._assertion_id: int | None = None
        self._iokit: Any | None = None
        self._core_foundation: Any | None = None

    @property
    def is_active(self) -> bool:
        """Возвращает True, если assertion сейчас удерживается."""
        return self._assertion_id is not None

    def acquire(self) -> bool:
        """Запрещает macOS гасить дисплей до вызова release()."""
        if self._assertion_id is not None:
            return True
        if sys.platform != "darwin":
            LOGGER.debug("💡 Power assertion доступен только на macOS")
            return False

        assertion_type: int | None = None
        assertion_name: int | None = None
        core_foundation: Any | None = None
        try:
            iokit, core_foundation = self._load_frameworks()
            assertion_type = self._create_cf_string(_NO_DISPLAY_SLEEP_ASSERTION)
            assertion_name = self._create_cf_string(self.reason)
            assertion_id = ctypes.c_uint32(0)
            result = iokit.IOPMAssertionCreateWithName(
                ctypes.c_void_p(assertion_type),
                ctypes.c_uint32(_IOPM_ASSERTION_LEVEL_ON),
                ctypes.c_void_p(assertion_name),
                ctypes.byref(assertion_id),
            )
        except Exception:
            LOGGER.exception("💡 Не удалось удержать дисплей от сна на время диктовки")
            return False
        finally:
            if core_foundation is not None:
                self._release_cf_value(core_foundation, assertion_type)
                self._release_cf_value(core_foundation, assertion_name)

        if result != _IOPM_SUCCESS:
            LOGGER.warning("💡 macOS не создала display sleep assertion: IOReturn=%s", result)
            log_power_diagnostics("acquire-failed", None)
            return False

        self._assertion_id = int(assertion_id.value)
        LOGGER.info("💡 Дисплей удерживается от сна на время диктовки: assertion_id=%s", self._assertion_id)
        log_power_diagnostics("acquired", self._assertion_id)
        return True

    def release(self) -> None:
        """Разрешает macOS снова гасить дисплей по системным настройкам."""
        assertion_id = self._assertion_id
        if assertion_id is None:
            return

        self._assertion_id = None
        log_power_diagnostics("before-release", assertion_id)
        try:
            iokit, _core_foundation = self._load_frameworks()
            result = iokit.IOPMAssertionRelease(ctypes.c_uint32(assertion_id))
        except Exception:
            LOGGER.exception("💡 Не удалось отпустить display sleep assertion: assertion_id=%s", assertion_id)
            return

        if result != _IOPM_SUCCESS:
            LOGGER.warning("💡 macOS вернула ошибку при отпускании display sleep assertion: IOReturn=%s", result)
            return

        LOGGER.info("💡 Дисплей снова может уходить в сон: assertion_id=%s", assertion_id)
        log_power_diagnostics("released", assertion_id)

    def _load_frameworks(self) -> tuple[Any, Any]:
        """Загружает IOKit и CoreFoundation через ctypes."""
        if self._iokit is not None and self._core_foundation is not None:
            return self._iokit, self._core_foundation

        iokit_path = ctypes.util.find_library("IOKit") or "/System/Library/Frameworks/IOKit.framework/IOKit"
        core_foundation_path = (
            ctypes.util.find_library("CoreFoundation") or "/System/Library/Frameworks/CoreFoundation.framework/CoreFoundation"
        )
        iokit = ctypes.CDLL(iokit_path)
        core_foundation = ctypes.CDLL(core_foundation_path)

        core_foundation.CFStringCreateWithCString.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_uint32]
        core_foundation.CFStringCreateWithCString.restype = ctypes.c_void_p
        core_foundation.CFRelease.argtypes = [ctypes.c_void_p]
        core_foundation.CFRelease.restype = None

        iokit.IOPMAssertionCreateWithName.argtypes = [
            ctypes.c_void_p,
            ctypes.c_uint32,
            ctypes.c_void_p,
            ctypes.POINTER(ctypes.c_uint32),
        ]
        iokit.IOPMAssertionCreateWithName.restype = ctypes.c_int32
        iokit.IOPMAssertionRelease.argtypes = [ctypes.c_uint32]
        iokit.IOPMAssertionRelease.restype = ctypes.c_int32

        self._iokit = iokit
        self._core_foundation = core_foundation
        return iokit, core_foundation

    def _create_cf_string(self, value: str) -> int:
        """Создаёт CFStringRef для вызова IOKit."""
        if self._core_foundation is None:
            raise RuntimeError("CoreFoundation не загружен")
        cf_value = self._core_foundation.CFStringCreateWithCString(
            None,
            value.encode("utf-8"),
            _CF_STRING_ENCODING_UTF8,
        )
        if not cf_value:
            raise RuntimeError(f"Не удалось создать CFString для {value!r}")
        return int(cf_value)

    def _release_cf_value(self, core_foundation: Any, value: int | None) -> None:
        """Отпускает временную CFStringRef, если она была создана."""
        if value is None:
            return
        core_foundation.CFRelease(ctypes.c_void_p(value))
