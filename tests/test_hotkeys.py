"""Тесты разбора горячих клавиш и аргументов командной строки.

Проверяет корректность парсинга комбинаций клавиш, форматирования
для отображения в меню и обработки аргументов командной строки.
"""

import pytest


class TestParseKeyCombination:
    """Тесты разбора строки с комбинацией клавиш."""

    def test_two_keys(self, app_module):
        """Комбинация из двух клавиш должна парситься."""
        result = app_module.parse_key_combination("cmd_l+alt")
        assert len(result) == 2

    def test_three_keys(self, app_module):
        """Комбинация из трёх клавиш должна парситься."""
        result = app_module.parse_key_combination("cmd_l+shift+space")
        assert len(result) == 3

    def test_single_key_raises(self, app_module):
        """Одна клавиша должна вызвать ValueError."""
        with pytest.raises(ValueError, match="как минимум две клавиши"):
            app_module.parse_key_combination("cmd_l")

    def test_empty_raises(self, app_module):
        """Пустая строка должна вызвать ValueError."""
        with pytest.raises(ValueError, match="как минимум две клавиши"):
            app_module.parse_key_combination("")

    def test_whitespace_handling(self, app_module):
        """Пробелы вокруг клавиш должны игнорироваться."""
        result = app_module.parse_key_combination("cmd_l + alt")
        assert len(result) == 2


class TestHotkeyNameMatches:
    """Тесты сопоставления имён клавиш с учётом лево/право вариантов."""

    def test_exact_match(self, app_module):
        """Одинаковые имена должны совпадать."""
        assert app_module.hotkey_name_matches("cmd_l", "cmd_l")

    def test_cmd_matches_cmd_l(self, app_module):
        """Cmd должен совпадать с cmd_l."""
        assert app_module.hotkey_name_matches("cmd", "cmd_l")

    def test_cmd_matches_cmd_r(self, app_module):
        """Cmd должен совпадать с cmd_r."""
        assert app_module.hotkey_name_matches("cmd", "cmd_r")

    def test_alt_matches_alt_l(self, app_module):
        """Alt должен совпадать с alt_l."""
        assert app_module.hotkey_name_matches("alt", "alt_l")

    def test_cmd_l_matches_cmd_r_via_generic_cmd(self, app_module):
        """cmd_l и cmd_r совпадают через общий вариант cmd — это ожидаемое поведение."""
        assert app_module.hotkey_name_matches("cmd_l", "cmd_r")

    def test_unrelated_keys_dont_match(self, app_module):
        """Несвязанные клавиши не должны совпадать."""
        assert not app_module.hotkey_name_matches("cmd", "alt")

    def test_shift_variants(self, app_module):
        """Shift должен совпадать с shift_l и shift_r."""
        assert app_module.hotkey_name_matches("shift", "shift_l")
        assert app_module.hotkey_name_matches("shift", "shift_r")


class TestFormatHotkeyStatus:
    """Тесты форматирования хоткея для отображения в меню."""

    def test_cmd_alt(self, app_module):
        """cmd_l+alt должен отображаться с символами."""
        result = app_module.format_hotkey_status("cmd_l+alt")
        assert "⌘" in result
        assert "⌥" in result

    def test_double_cmd(self, app_module):
        """Режим двойного нажатия должен показать соответствующий текст."""
        result = app_module.format_hotkey_status(use_double_cmd=True)
        assert "двойное нажатие" in result

    def test_space_key(self, app_module):
        """Клавиша space должна отображаться как Space."""
        result = app_module.format_hotkey_status("cmd_l+space")
        assert "Space" in result


class TestFormatMaxTimeStatus:
    """Тесты форматирования лимита длительности записи."""

    def test_none_is_no_limit(self, app_module):
        """None должен стать 'без лимита'."""
        assert app_module.format_max_time_status(None) == "без лимита"

    def test_integer_seconds(self, app_module):
        """Целые секунды должны отображаться без дробной части."""
        assert app_module.format_max_time_status(30) == "30 с"

    def test_float_seconds(self, app_module):
        """Дробные секунды должны отображаться с дробной частью."""
        assert app_module.format_max_time_status(10.5) == "10.5 с"
