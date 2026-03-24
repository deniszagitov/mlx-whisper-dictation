"""Тесты разрешений macOS (Accessibility, Input Monitoring, Microphone).

Проверяет, что функции проверки разрешений возвращают корректные типы
и что вспомогательная логика приложения правильно обрабатывает все возможные
значения разрешений.
"""


class TestPermissionLabel:
    """Тесты преобразования статуса разрешения в строку для меню."""

    def test_granted(self, app_module):
        """True должен стать 'есть'."""
        assert app_module.permission_label(True) == "есть"

    def test_denied(self, app_module):
        """False должен стать 'нет'."""
        assert app_module.permission_label(False) == "нет"

    def test_unknown(self, app_module):
        """None должен стать 'неизвестно'."""
        assert app_module.permission_label(None) == "неизвестно"


class TestPermissionPreflightStatus:
    """Тесты вызова preflight-функций разрешений."""

    def test_accessibility_returns_bool_or_none(self, app_module):
        """get_accessibility_status должен вернуть True, False или None."""
        result = app_module.get_accessibility_status()
        assert result is True or result is False or result is None

    def test_input_monitoring_returns_bool_or_none(self, app_module):
        """get_input_monitoring_status должен вернуть True, False или None."""
        result = app_module.get_input_monitoring_status()
        assert result is True or result is False or result is None

    def test_nonexistent_function_returns_none(self, app_module):
        """Несуществующая функция должна вернуть None."""
        result = app_module.permission_preflight_status("NonExistentFunction12345")
        assert result is None

    def test_is_accessibility_trusted_returns_bool(self, app_module):
        """is_accessibility_trusted должен вернуть True или False."""
        result = app_module.is_accessibility_trusted()
        assert isinstance(result, bool)
