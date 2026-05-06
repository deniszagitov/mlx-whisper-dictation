"""Тесты macOS power assertion и opt-in power diagnostics."""

from __future__ import annotations

import src.infrastructure.power as power_module


def test_log_power_diagnostics_skips_thread_without_env(monkeypatch):
    """Power-снимки не должны запускаться без env-флага."""
    started_threads: list[bool] = []
    monkeypatch.setattr(power_module.sys, "platform", "darwin")
    monkeypatch.delenv(power_module.Config.POWER_DIAGNOSTICS_ENV, raising=False)
    monkeypatch.setattr(
        power_module.threading,
        "Thread",
        lambda **_kwargs: type("ThreadStub", (), {"start": lambda self: started_threads.append(True)})(),
    )

    power_module.log_power_diagnostics("test", 42)

    assert started_threads == []


def test_log_power_diagnostics_starts_thread_with_env(monkeypatch):
    """Env-флаг должен включать подробные power-снимки."""
    started_threads: list[bool] = []
    monkeypatch.setattr(power_module.sys, "platform", "darwin")
    monkeypatch.setenv(power_module.Config.POWER_DIAGNOSTICS_ENV, "1")
    monkeypatch.setattr(
        power_module.threading,
        "Thread",
        lambda **_kwargs: type("ThreadStub", (), {"start": lambda self: started_threads.append(True)})(),
    )

    power_module.log_power_diagnostics("test", 42)

    assert started_threads == [True]
