"""Тесты завершения приложения из CLI."""

from __future__ import annotations

import queue
import signal
import subprocess
import sys
import textwrap
import time
from pathlib import Path
from types import SimpleNamespace
from typing import Any, ClassVar

import pytest

CHECK_SCRIPT_PATH = Path(__file__).resolve().parent.parent / "scripts" / "check_cli_signal_shutdown.py"


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


def test_cli_signal_wait_thread_dispatches_sigint(app_module):
    """sigwait-поток должен доставлять Ctrl-C из Cocoa run loop в shutdown handler."""
    signal_queue: queue.Queue[int] = queue.Queue()
    received_signals: list[int] = []
    masks: list[tuple[int, tuple[int, ...] | set[int]]] = []

    def fake_pthread_sigmask(how: int, mask: tuple[int, ...] | set[int]) -> set[int]:
        masks.append((how, mask))
        return set()

    def fake_sigwait(_signals: tuple[int, ...]) -> int:
        return signal_queue.get(timeout=1)

    cleanup = app_module._install_cli_signal_wait_thread(
        lambda signum, _frame: received_signals.append(signum),
        pthread_sigmask=fake_pthread_sigmask,
        sigwait=fake_sigwait,
        stdin_isatty=lambda: True,
    )
    assert cleanup is not None

    signal_queue.put(signal.SIGINT)
    deadline = time.time() + 1.0
    while not received_signals and time.time() < deadline:
        time.sleep(0.01)
    cleanup()
    signal_queue.put(0)

    assert received_signals == [signal.SIGINT]
    assert masks == [
        (signal.SIG_BLOCK, (signal.SIGINT, signal.SIGTERM)),
        (signal.SIG_SETMASK, set()),
    ]


def test_cli_ctrl_c_e2e_subprocess_reaches_shutdown_handler():
    """E2E: реальный SIGINT в отдельном процессе должен попасть в shutdown handler."""
    script = textwrap.dedent(
        """
        import os
        import signal
        import time

        from PyObjCTools import MachSignals

        import main

        def handler(signum, _frame=None):
            print(f"handled {signum}", flush=True)
            os._exit(0)

        main._install_cli_signal_wait_thread(handler, stdin_isatty=lambda: True)
        signal.signal(signal.SIGINT, lambda _signum, _frame: None)
        MachSignals.signal(signal.SIGINT, lambda signum: handler(signum, None))
        os.kill(os.getpid(), signal.SIGINT)
        time.sleep(2)
        print("missed", flush=True)
        os._exit(1)
        """
    )

    completed = subprocess.run(
        [sys.executable, "-c", script],
        check=False,
        capture_output=True,
        text=True,
        timeout=5,
    )

    assert completed.returncode == 0
    assert "handled 2" in completed.stdout


@pytest.mark.slow
@pytest.mark.skipif(sys.platform != "darwin", reason="AppKit run loop и MachSignals доступны только на macOS")
def test_cli_signal_shutdown_reproducer_exits_without_pyobjc_abort():
    """Разовый reproducer должен штатно выходить из AppKit run loop после SIGINT."""
    completed = subprocess.run(
        [sys.executable, str(CHECK_SCRIPT_PATH), "--timeout", "10"],
        check=False,
        capture_output=True,
        text=True,
        timeout=12,
    )

    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert "will_terminate" in completed.stdout


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


def test_install_cli_shutdown_handlers_runs_before_quit_cleanup_once(app_module, monkeypatch):
    """Повторный before_quit не должен повторно останавливать reader и signal cleanup."""
    events: list[str] = []
    before_quit_callbacks: list[Any] = []

    monkeypatch.setattr(app_module.signal, "signal", lambda _signum, _handler: None)
    monkeypatch.setattr(app_module.rumps.events.before_start, "register", lambda _callback: None)
    monkeypatch.setattr(app_module.rumps.events.before_quit, "register", before_quit_callbacks.append)
    monkeypatch.setattr(app_module, "_install_cli_signal_wait_thread", lambda _handler: lambda: events.append("signal_cleanup"))

    app_controller = SimpleNamespace(
        recording_overlay=SimpleNamespace(hide=lambda: events.append("overlay_hide")),
        cancel_recording=lambda: events.append("cancel_recording"),
        shutdown_reader=lambda: events.append("reader_shutdown"),
    )
    key_listener = SimpleNamespace(stop=lambda: events.append("hotkeys_stop"))
    tts_speaker = SimpleNamespace(stop=lambda: events.append("tts_stop"))
    rsvp_display = SimpleNamespace(close=lambda: events.append("rsvp_close"))
    display_sleep = SimpleNamespace(release=lambda: events.append("display_release"))

    app_module._install_cli_shutdown_handlers(
        app_controller=app_controller,
        key_listener=key_listener,
        tts_speaker=tts_speaker,
        rsvp_display=rsvp_display,
        display_sleep_prevention_service=display_sleep,
    )

    before_quit_callbacks[0]()
    before_quit_callbacks[0]()

    assert events == [
        "cancel_recording",
        "hotkeys_stop",
        "reader_shutdown",
        "overlay_hide",
        "display_release",
        "signal_cleanup",
    ]
