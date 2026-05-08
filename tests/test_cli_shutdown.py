"""Тесты завершения приложения из CLI."""

from __future__ import annotations

import signal
from types import SimpleNamespace
from typing import Any, ClassVar


class FakeTimer:
    """Фейковый timer, который не вызывает callback сам."""

    instances: ClassVar[list[FakeTimer]] = []

    def __init__(self, delay: float, callback: Any) -> None:
        self.delay = delay
        self.callback = callback
        self.daemon = False
        self.started = False
        self.__class__.instances.append(self)

    def start(self) -> None:
        """Запоминает старт timer-а."""
        self.started = True


def test_cli_shutdown_handler_stops_runtime_and_quits(app_module):
    """Первый Ctrl-C должен остановить runtime и попросить rumps завершиться."""
    events: list[str] = []
    forced_exits: list[int] = []
    FakeTimer.instances = []
    app_controller = SimpleNamespace(
        recording_overlay=SimpleNamespace(hide=lambda: events.append("overlay_hide")),
        cancel_recording=lambda: events.append("cancel_recording"),
    )
    key_listener = SimpleNamespace(stop=lambda: events.append("hotkeys_stop"))
    tts_speaker = SimpleNamespace(stop=lambda: events.append("tts_stop"))
    rsvp_display = SimpleNamespace(close=lambda: events.append("rsvp_close"))
    display_sleep = SimpleNamespace(release=lambda: events.append("display_release"))
    handler = app_module._build_cli_shutdown_handler(
        app_controller=app_controller,
        key_listener=key_listener,
        tts_speaker=tts_speaker,
        rsvp_display=rsvp_display,
        display_sleep_prevention_service=display_sleep,
        quit_application=lambda _sender: events.append("quit"),
        force_exit=forced_exits.append,
        timer_factory=FakeTimer,
    )

    handler(signal.SIGINT, None)

    assert events == [
        "cancel_recording",
        "hotkeys_stop",
        "tts_stop",
        "rsvp_close",
        "overlay_hide",
        "display_release",
        "quit",
    ]
    assert forced_exits == []
    assert FakeTimer.instances[0].delay == app_module.CLI_FORCE_EXIT_DELAY_SECONDS
    assert FakeTimer.instances[0].daemon is True
    assert FakeTimer.instances[0].started is True


def test_cli_shutdown_handler_forces_exit_on_second_signal(app_module):
    """Повторный Ctrl-C должен выходить принудительно, если normal shutdown завис."""
    forced_exits: list[int] = []
    FakeTimer.instances = []
    app_controller = SimpleNamespace(recording_overlay=SimpleNamespace(hide=lambda: None), cancel_recording=lambda: None)
    noop = SimpleNamespace(stop=lambda: None)
    handler = app_module._build_cli_shutdown_handler(
        app_controller=app_controller,
        key_listener=noop,
        tts_speaker=noop,
        rsvp_display=SimpleNamespace(close=lambda: None),
        display_sleep_prevention_service=SimpleNamespace(release=lambda: None),
        quit_application=lambda _sender: None,
        force_exit=forced_exits.append,
        timer_factory=FakeTimer,
    )

    handler(signal.SIGINT, None)
    handler(signal.SIGINT, None)

    assert forced_exits == [130]


def test_install_cli_shutdown_handlers_reinstalls_mach_signal_after_rumps(app_module, monkeypatch):
    """rumps ставит свой Mach handler перед run loop, поэтому наш handler переустанавливается в before_start."""
    standard_signals: list[int] = []
    mach_signals: list[int] = []
    before_start_callbacks: list[Any] = []
    before_quit_callbacks: list[Any] = []
    monkeypatch.setattr(app_module.signal, "signal", lambda signum, _handler: standard_signals.append(signum))
    monkeypatch.setattr(app_module.rumps.events.before_start, "register", before_start_callbacks.append)
    monkeypatch.setattr(app_module.rumps.events.before_quit, "register", before_quit_callbacks.append)

    from PyObjCTools import MachSignals  # type: ignore[import-untyped]

    monkeypatch.setattr(MachSignals, "signal", lambda signum, _handler: mach_signals.append(signum))
    app_controller = SimpleNamespace(recording_overlay=SimpleNamespace(hide=lambda: None), cancel_recording=lambda: None)
    noop = SimpleNamespace(stop=lambda: None)

    app_module._install_cli_shutdown_handlers(
        app_controller=app_controller,
        key_listener=noop,
        tts_speaker=noop,
        rsvp_display=SimpleNamespace(close=lambda: None),
        display_sleep_prevention_service=SimpleNamespace(release=lambda: None),
    )
    before_start_callbacks[0]()

    assert standard_signals == [signal.SIGINT, signal.SIGTERM]
    assert mach_signals == [signal.SIGINT, signal.SIGTERM]
    assert before_quit_callbacks
