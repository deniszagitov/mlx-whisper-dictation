"""Тесты расширенной системной диагностики macOS."""

from __future__ import annotations

import logging

import src.infrastructure.system_diagnostics as diagnostics_module


def test_filter_usb_output_keeps_power_and_device_lines():
    """USB-фильтр должен оставлять строки про устройства, питание и хабы."""
    output = "\n".join(
        [
            '    "USB Product Name" = "MX Brio 705 for Business"',
            '    "kUSBCurrentRequired" = 896',
            '    "Some Unrelated Key" = "noise"',
            '    "USB Product Name" = "USB3.1 Hub"',
        ]
    )

    filtered = diagnostics_module._filter_usb_output(output)

    assert "MX Brio" in filtered
    assert "kUSBCurrentRequired" in filtered
    assert "USB3.1 Hub" in filtered
    assert "Some Unrelated Key" not in filtered


def test_capture_system_diagnostics_sync_logs_session_screens_and_commands(monkeypatch, caplog):
    """Синхронный снимок должен логировать session, screens и вывод команд."""
    monkeypatch.setattr(diagnostics_module.platform, "system", lambda: "Darwin")
    monkeypatch.setattr(
        diagnostics_module.Quartz,
        "CGSessionCopyCurrentDictionary",
        lambda: {"CGSSessionScreenIsLocked": True},
    )
    monkeypatch.setattr(
        diagnostics_module.AppKit,
        "NSScreen",
        type("ScreenStub", (), {"screens": staticmethod(lambda: [])}),
    )
    monkeypatch.setattr(diagnostics_module, "_COMMANDS", (("usb_ioreg", ("ioreg",)),))
    monkeypatch.setattr(
        diagnostics_module,
        "_command_output",
        lambda _command: '"USB Product Name" = "MX Brio 705 for Business"\nnoise',
    )

    with caplog.at_level(logging.INFO):
        diagnostics_module._capture_system_diagnostics_sync("test")

    assert "CGSSessionScreenIsLocked" in caplog.text
    assert "screens: []" in caplog.text
    assert "MX Brio 705 for Business" in caplog.text
    assert "noise" not in caplog.text


def test_capture_system_diagnostics_skips_thread_without_env(monkeypatch):
    """Подробная системная диагностика не должна запускаться без env-флага."""
    started_threads: list[bool] = []
    monkeypatch.setattr(diagnostics_module.platform, "system", lambda: "Darwin")
    monkeypatch.delenv(diagnostics_module.Config.SYSTEM_DIAGNOSTICS_ENV, raising=False)
    monkeypatch.setattr(
        diagnostics_module.threading,
        "Thread",
        lambda **_kwargs: type("ThreadStub", (), {"start": lambda self: started_threads.append(True)})(),
    )

    diagnostics_module.capture_system_diagnostics("test")

    assert started_threads == []


def test_capture_system_diagnostics_starts_thread_with_env(monkeypatch):
    """Env-флаг должен включать подробную системную диагностику."""
    started_threads: list[bool] = []
    monkeypatch.setattr(diagnostics_module.platform, "system", lambda: "Darwin")
    monkeypatch.setenv(diagnostics_module.Config.SYSTEM_DIAGNOSTICS_ENV, "1")
    monkeypatch.setattr(
        diagnostics_module.threading,
        "Thread",
        lambda **_kwargs: type("ThreadStub", (), {"start": lambda self: started_threads.append(True)})(),
    )

    diagnostics_module.capture_system_diagnostics("test")

    assert started_threads == [True]
