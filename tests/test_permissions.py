"""Тесты разрешений macOS (Accessibility, Input Monitoring, Microphone).

Проверяет, что функции проверки разрешений возвращают корректные типы
и что вспомогательная логика приложения правильно обрабатывает все возможные
значения разрешений.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


class TestPermissionLabel:
    """Тесты преобразования статуса разрешения в строку для меню."""

    def test_granted(self):
        """True должен стать 'есть'."""
        from importlib import import_module

        wd = import_module("whisper-dictation")
        assert wd.permission_label(True) == "есть"

    def test_denied(self):
        """False должен стать 'нет'."""
        from importlib import import_module

        wd = import_module("whisper-dictation")
        assert wd.permission_label(False) == "нет"

    def test_unknown(self):
        """None должен стать 'неизвестно'."""
        from importlib import import_module

        wd = import_module("whisper-dictation")
        assert wd.permission_label(None) == "неизвестно"


class TestPermissionPreflightStatus:
    """Тесты вызова preflight-функций разрешений."""

    def test_accessibility_returns_bool_or_none(self):
        """get_accessibility_status должен вернуть True, False или None."""
        from importlib import import_module

        wd = import_module("whisper-dictation")
        result = wd.get_accessibility_status()
        assert result is True or result is False or result is None

    def test_input_monitoring_returns_bool_or_none(self):
        """get_input_monitoring_status должен вернуть True, False или None."""
        from importlib import import_module

        wd = import_module("whisper-dictation")
        result = wd.get_input_monitoring_status()
        assert result is True or result is False or result is None

    def test_nonexistent_function_returns_none(self):
        """Несуществующая функция должна вернуть None."""
        from importlib import import_module

        wd = import_module("whisper-dictation")
        result = wd.permission_preflight_status("NonExistentFunction12345")
        assert result is None

    def test_is_accessibility_trusted_returns_bool(self):
        """is_accessibility_trusted должен вернуть True или False."""
        from importlib import import_module

        wd = import_module("whisper-dictation")
        result = wd.is_accessibility_trusted()
        assert isinstance(result, bool)
