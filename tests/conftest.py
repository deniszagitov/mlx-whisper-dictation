"""Конфигурация pytest для проекта MLX Whisper Dictation."""

import pytest


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


def pytest_configure(config):
    """Регистрирует пользовательские маркеры."""
    config.addinivalue_line("markers", "slow: медленные тесты (модель, транскрибация)")
    config.addinivalue_line("markers", "hardware: тесты, требующие доступ к аппаратуре")


def pytest_collection_modifyitems(config, items):
    """Пропускает тесты с маркерами slow/hardware, если не указаны соответствующие флаги."""
    skip_slow = pytest.mark.skip(reason="нужен флаг --run-slow для запуска")
    skip_hardware = pytest.mark.skip(reason="нужен флаг --run-hardware для запуска")
    for item in items:
        if "slow" in item.keywords and not config.getoption("--run-slow"):
            item.add_marker(skip_slow)
        if "hardware" in item.keywords and not config.getoption("--run-hardware"):
            item.add_marker(skip_hardware)
