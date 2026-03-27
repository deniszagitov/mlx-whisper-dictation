"""Общая pytest-конфигурация для Dictator."""

import importlib.util
import sys
from pathlib import Path

import pytest

# Добавляем src/ в sys.path, чтобы тесты могли импортировать модули напрямую
_SRC_DIR = str(Path(__file__).resolve().parent.parent / "src")
if _SRC_DIR not in sys.path:
    sys.path.insert(0, _SRC_DIR)

MODULE_PATH = Path(__file__).resolve().parent.parent / "whisper-dictation.py"


def pytest_addoption(parser):
    """Добавляет опции командной строки для управления тестами."""
    parser.addoption(
        "--run-slow",
        action="store_true",
        default=False,
        help="Запустить медленные тесты (загрузка модели, транскрибация)",
    )
    parser.addoption(
        "--run-hardware",
        action="store_true",
        default=False,
        help="Запустить тесты, требующие доступ к аппаратуре (микрофон)",
    )
    parser.addoption(
        "--run-build",
        action="store_true",
        default=False,
        help="Запустить тесты сборки .app через py2app",
    )


def pytest_configure(config):
    """Регистрирует пользовательские маркеры."""
    config.addinivalue_line("markers", "slow: медленные тесты (модель, транскрибация)")
    config.addinivalue_line("markers", "hardware: тесты, требующие доступ к аппаратуре")
    config.addinivalue_line("markers", "build: тесты сборки .app через py2app")


def pytest_collection_modifyitems(config, items):
    """Пропускает тесты с маркерами slow/hardware, если не указаны соответствующие флаги."""
    skip_slow = pytest.mark.skip(reason="нужен флаг --run-slow для запуска")
    skip_hardware = pytest.mark.skip(reason="нужен флаг --run-hardware для запуска")
    skip_build = pytest.mark.skip(reason="нужен флаг --run-build для запуска")
    for item in items:
        if "slow" in item.keywords and not config.getoption("--run-slow"):
            item.add_marker(skip_slow)
        if "hardware" in item.keywords and not config.getoption("--run-hardware"):
            item.add_marker(skip_hardware)
        if "build" in item.keywords and not config.getoption("--run-build"):
            item.add_marker(skip_build)


@pytest.fixture
def app_module():
    """Загружает runtime-модуль приложения для unit-тестов."""
    spec = importlib.util.spec_from_file_location("whisper_dictation_app", MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module
