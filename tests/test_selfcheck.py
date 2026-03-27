"""Тесты self-check сценария."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace

SCRIPT_PATH = Path(__file__).resolve().parent.parent / "scripts" / "selfcheck.py"


def load_selfcheck_module():
    """Загружает scripts/selfcheck.py как тестируемый модуль."""
    spec = importlib.util.spec_from_file_location("dictator_selfcheck", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_parse_args_reads_coverage_flags(monkeypatch):
    """parse_args должен корректно разбирать coverage-опции."""
    selfcheck = load_selfcheck_module()

    monkeypatch.setattr(
        sys,
        "argv",
        ["selfcheck.py", "--coverage", "--min-coverage", "61", "--no-lint", "--build"],
    )

    args = selfcheck.parse_args()

    assert args.coverage is True
    assert args.min_coverage == 61
    assert args.no_lint is True
    assert args.build is True


def test_run_step_invokes_subprocess_in_repo_root(monkeypatch):
    """run_step должен запускать subprocess.run в корне репозитория."""
    selfcheck = load_selfcheck_module()
    calls = []

    monkeypatch.setattr(
        selfcheck.subprocess,
        "run",
        lambda command, cwd, check: calls.append((command, cwd, check)),
    )

    selfcheck.run_step("Pytest", ["uv", "run", "pytest"])

    assert calls == [(["uv", "run", "pytest"], selfcheck.ROOT, True)]


def test_main_runs_ruff_and_pytest_by_default(monkeypatch):
    """По умолчанию self-check должен запускать Ruff и Pytest."""
    selfcheck = load_selfcheck_module()
    steps = []

    monkeypatch.setattr(
        selfcheck,
        "parse_args",
        lambda: SimpleNamespace(
            build=False,
            slow=False,
            hardware=False,
            no_lint=False,
            coverage=False,
            min_coverage=56,
        ),
    )
    monkeypatch.setattr(selfcheck, "run_step", lambda title, command: steps.append((title, command)))

    exit_code = selfcheck.main()

    assert exit_code == 0
    assert [title for title, _command in steps] == ["Ruff", "Pytest"]
    assert steps[1][1] == ["uv", "run", "pytest", "tests/", "-q"]


def test_main_adds_coverage_flags(monkeypatch):
    """При --coverage self-check должен передавать pytest флаги покрытия."""
    selfcheck = load_selfcheck_module()
    steps = []

    monkeypatch.setattr(
        selfcheck,
        "parse_args",
        lambda: SimpleNamespace(
            build=False,
            slow=False,
            hardware=False,
            no_lint=True,
            coverage=True,
            min_coverage=77,
        ),
    )
    monkeypatch.setattr(selfcheck, "run_step", lambda title, command: steps.append((title, command)))

    exit_code = selfcheck.main()

    assert exit_code == 0
    assert len(steps) == 1
    assert steps[0][0] == "Pytest"
    assert "--cov=." in steps[0][1]
    assert "--cov-report=term-missing" in steps[0][1]
    assert "--cov-fail-under=77" in steps[0][1]


def test_main_skips_ruff_when_no_lint_enabled(monkeypatch):
    """Флаг --no-lint должен пропускать Ruff и оставлять только Pytest."""
    selfcheck = load_selfcheck_module()
    steps = []

    monkeypatch.setattr(
        selfcheck,
        "parse_args",
        lambda: SimpleNamespace(
            build=False,
            slow=False,
            hardware=False,
            no_lint=True,
            coverage=False,
            min_coverage=56,
        ),
    )
    monkeypatch.setattr(selfcheck, "run_step", lambda title, command: steps.append((title, command)))

    exit_code = selfcheck.main()

    assert exit_code == 0
    assert [title for title, _command in steps] == ["Pytest"]


def test_main_runs_build_and_marker_flags(monkeypatch):
    """Флаги build/slow/hardware должны попасть в Pytest и запустить py2app."""
    selfcheck = load_selfcheck_module()
    steps = []

    monkeypatch.setattr(
        selfcheck,
        "parse_args",
        lambda: SimpleNamespace(
            build=True,
            slow=True,
            hardware=True,
            no_lint=True,
            coverage=False,
            min_coverage=56,
        ),
    )
    monkeypatch.setattr(selfcheck, "run_step", lambda title, command: steps.append((title, command)))

    exit_code = selfcheck.main()

    assert exit_code == 0
    assert [title for title, _command in steps] == ["Pytest", "Py2app"]
    assert "--run-slow" in steps[0][1]
    assert "--run-hardware" in steps[0][1]
    assert "--run-build" in steps[0][1]
    assert steps[1][1] == ["uv", "run", "python", "setup.py", "py2app", "-A"]
