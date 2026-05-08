"""Разовая проверка CLI shutdown через AppKit run loop и MachSignals."""

from __future__ import annotations

import argparse
import os
import signal
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parent.parent
CHILD_FLAG = "--child"
DEFAULT_TIMEOUT_SECONDS = 8.0
SEND_SIGNAL_DELAY_SECONDS = 0.05
FALLBACK_EXIT_DELAY_SECONDS = 4.0


def parse_args() -> argparse.Namespace:
    """Разбирает параметры ручной проверки."""
    parser = argparse.ArgumentParser(description="Проверяет, что Ctrl-C из AppKit run loop не падает в PyObjC abort.")
    parser.add_argument(CHILD_FLAG, action="store_true", help=argparse.SUPPRESS)
    parser.add_argument(
        "--timeout",
        type=float,
        default=DEFAULT_TIMEOUT_SECONDS,
        help="Сколько секунд ждать дочерний процесс проверки.",
    )
    return parser.parse_args()


def _print_stream(title: str, value: str | bytes | None) -> None:
    """Печатает stdout/stderr дочернего процесса, если там есть данные."""
    if value is None:
        return
    text = value.decode() if isinstance(value, bytes) else value
    if text.strip():
        print(f"\n{title}:\n{text.rstrip()}")


def _run_parent(timeout: float) -> int:
    """Запускает crash-prone сценарий в отдельном процессе."""
    if sys.platform != "darwin":
        print("Проверка доступна только на macOS.")
        return 0

    command = [sys.executable, str(Path(__file__).resolve()), CHILD_FLAG]
    env = os.environ.copy()
    env.setdefault("PYTHONFAULTHANDLER", "1")
    python_path = env.get("PYTHONPATH")
    env["PYTHONPATH"] = f"{ROOT}{os.pathsep}{python_path}" if python_path else str(ROOT)

    try:
        completed = subprocess.run(
            command,
            cwd=ROOT,
            env=env,
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as error:
        print("Проверка зависла: AppKit shutdown не завершился за отведённое время.")
        _print_stream("stdout", error.stdout)
        _print_stream("stderr", error.stderr)
        return 1

    if completed.returncode != 0:
        print(f"Проверка упала: дочерний процесс завершился с кодом {completed.returncode}.")
        _print_stream("stdout", completed.stdout)
        _print_stream("stderr", completed.stderr)
        return completed.returncode

    if "will_terminate" not in completed.stdout:
        print("Проверка не увидела applicationWillTerminate от дочернего процесса.")
        _print_stream("stdout", completed.stdout)
        _print_stream("stderr", completed.stderr)
        return 1

    print(completed.stdout.rstrip())
    return 0


def _child_main() -> int:
    """Поднимает минимальный AppKit loop, отправляет SIGINT и ждёт штатный выход."""
    import AppKit  # type: ignore[import-untyped]  # noqa: PLC0415
    import main as app_main  # noqa: PLC0415
    from Foundation import NSObject  # type: ignore[import-untyped]  # noqa: PLC0415
    from PyObjCTools import AppHelper, MachSignals  # type: ignore[import-untyped]  # noqa: PLC0415

    application = AppKit.NSApplication.sharedApplication()
    application.setActivationPolicy_(AppKit.NSApplicationActivationPolicyAccessory)

    def record(event: str) -> None:
        print(event, flush=True)

    def force_exit(code: int) -> None:
        record(f"force_exit {code}")
        os._exit(code)

    class ShutdownDelegate(NSObject):  # type: ignore[misc, valid-type]
        """Фиксирует фактический AppKit terminate перед выходом процесса."""

        def applicationWillTerminate_(self, _notification: object) -> None:  # noqa: N802
            """Пишет маркер штатного завершения AppKit."""
            record("will_terminate")

    delegate = ShutdownDelegate.alloc().init()
    application.setDelegate_(delegate)

    app_controller = SimpleNamespace(
        recording_overlay=SimpleNamespace(hide=lambda: record("overlay_hide")),
        cancel_recording=lambda: record("cancel_recording"),
    )
    key_listener = SimpleNamespace(stop=lambda: record("hotkeys_stop"))
    tts_speaker = SimpleNamespace(stop=lambda: record("tts_stop"))
    rsvp_display = SimpleNamespace(close=lambda: record("rsvp_close"))
    display_sleep = SimpleNamespace(release=lambda: record("display_release"))

    handler = app_main._build_cli_shutdown_handler(
        app_controller=app_controller,
        key_listener=key_listener,
        tts_speaker=tts_speaker,
        rsvp_display=rsvp_display,
        display_sleep_prevention_service=display_sleep,
        force_exit=force_exit,
    )

    signal.signal(signal.SIGINT, lambda _signum, _frame: None)
    MachSignals.signal(signal.SIGINT, lambda signum: handler(signum, None))

    AppHelper.callLater(SEND_SIGNAL_DELAY_SECONDS, lambda: os.kill(os.getpid(), signal.SIGINT))
    AppHelper.callLater(FALLBACK_EXIT_DELAY_SECONDS, lambda: force_exit(1))

    record("loop_started")
    application.run()
    record("clean_exit")
    return 0


def main() -> int:
    """Запускает родительский или дочерний режим проверки."""
    args = parse_args()
    if args.child:
        return _child_main()
    return _run_parent(args.timeout)


if __name__ == "__main__":
    raise SystemExit(main())
