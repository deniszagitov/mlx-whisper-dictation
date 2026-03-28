"""Единый self-check сценарий для локальной проверки Dictator.

Скрипт нужен для быстрого цикла разработки: одна команда прогоняет линт,
основные тесты и при необходимости сборку alias-приложения.
"""

from __future__ import annotations

import argparse
import logging
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LOGGER = logging.getLogger(__name__)


def _configure_logging() -> None:
    """Настраивает лаконичный вывод self-check через logging."""
    logging.basicConfig(level=logging.INFO, format="%(message)s")


def run_step(title: str, command: list[str]) -> None:
    """Запускает отдельный шаг self-check и завершает скрипт при ошибке."""
    LOGGER.info("\n== %s ==", title)
    LOGGER.info("$ %s", " ".join(command))
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
    parser.add_argument(
        "--coverage",
        action="store_true",
        help="включить отчет по покрытию тестами",
    )
    parser.add_argument(
        "--min-coverage",
        type=int,
        default=56,
        help="минимальный допустимый процент покрытия при --coverage",
    )
    return parser.parse_args()


def main() -> int:
    """Запускает выбранный набор локальных проверок."""
    _configure_logging()
    args = parse_args()

    if not args.no_lint:
        run_step("Ruff", ["uv", "run", "ruff", "check", "."])
        run_step("Import-linter", ["uv", "run", "lint-imports"])

    pytest_command = ["uv", "run", "pytest", "tests/", "-q"]
    if args.coverage:
        pytest_command.extend(
            [
                "--cov=.",
                "--cov-report=term",
                f"--cov-fail-under={args.min_coverage}",
            ]
        )
    if args.slow:
        pytest_command.append("--run-slow")
    if args.hardware:
        pytest_command.append("--run-hardware")
    if args.build:
        pytest_command.append("--run-build")
    run_step("Pytest", pytest_command)

    if args.build:
        run_step("Py2app", ["uv", "run", "python", "setup.py", "py2app", "-A"])

    LOGGER.info("\nSelf-check завершен успешно.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
