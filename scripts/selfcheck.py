"""Единый self-check сценарий для локальной проверки Dictator.

Скрипт нужен для быстрого цикла разработки: одна команда прогоняет линт,
основные тесты и при необходимости сборку alias-приложения.
"""

from __future__ import annotations

import argparse
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def run_step(title: str, command: list[str]) -> None:
    """Запускает отдельный шаг self-check и завершает скрипт при ошибке."""
    print(f"\n== {title} ==")
    print("$", " ".join(command))
    subprocess.run(command, cwd=ROOT, check=True)


def parse_args() -> argparse.Namespace:
    """Разбирает аргументы командной строки self-check сценария."""
    parser = argparse.ArgumentParser(description="Локальный self-check для Dictator")
    parser.add_argument(
        "--build",
        action="store_true",
        help="дополнительно собрать alias .app через py2app -A",
    )
    parser.add_argument(
        "--slow",
        action="store_true",
        help="включить slow-тесты с реальной моделью mlx_whisper",
    )
    parser.add_argument(
        "--hardware",
        action="store_true",
        help="включить hardware-тесты, требующие реальный микрофон",
    )
    parser.add_argument(
        "--no-lint",
        action="store_true",
        help="пропустить ruff check",
    )
    return parser.parse_args()


def main() -> int:
    """Запускает выбранный набор локальных проверок."""
    args = parse_args()

    if not args.no_lint:
        run_step("Ruff", ["uv", "run", "ruff", "check", "."])

    pytest_command = ["uv", "run", "pytest", "tests/", "-q"]
    if args.slow:
        pytest_command.append("--run-slow")
    if args.hardware:
        pytest_command.append("--run-hardware")
    if args.build:
        pytest_command.append("--run-build")
    run_step("Pytest", pytest_command)

    if args.build:
        run_step("Py2app", ["uv", "run", "python", "setup.py", "py2app", "-A"])

    print("\nSelf-check завершен успешно.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
