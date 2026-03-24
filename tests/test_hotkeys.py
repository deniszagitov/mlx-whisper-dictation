"""Тесты разбора горячих клавиш и аргументов командной строки.

Проверяет корректность парсинга комбинаций клавиш, форматирования
для отображения в меню и обработки аргументов командной строки.
"""

import sys
from importlib import import_module
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

wd = import_module("whisper-dictation")


class TestParseKeyCombination:
    """Тесты разбора строки с комбинацией клавиш."""

    def test_two_keys(self):
        """Комбинация из двух клавиш должна парситься."""
        result = wd.parse_key_combination("cmd_l+alt")
        assert len(result) == 2

    def test_three_keys(self):
        """Комбинация из трёх клавиш должна парситься."""
        result = wd.parse_key_combination("cmd_l+shift+space")
        assert len(result) == 3

    def test_single_key_raises(self):
        """Одна клавиша должна вызвать ValueError."""
        with pytest.raises(ValueError, match="как минимум две клавиши"):
            wd.parse_key_combination("cmd_l")

    def test_empty_raises(self):
        """Пустая строка должна вызвать ValueError."""
        with pytest.raises(ValueError, match="как минимум две клавиши"):
            wd.parse_key_combination("")

    def test_whitespace_handling(self):
        """Пробелы вокруг клавиш должны игнорироваться."""
        result = wd.parse_key_combination("cmd_l + alt")
        assert len(result) == 2


class TestHotkeyNameMatches:
    """Тесты сопоставления имён клавиш с учётом лево/право вариантов."""

    def test_exact_match(self):
        """Одинаковые имена должны совпадать."""
        assert wd.hotkey_name_matches("cmd_l", "cmd_l")

    def test_cmd_matches_cmd_l(self):
        """Cmd должен совпадать с cmd_l."""
        assert wd.hotkey_name_matches("cmd", "cmd_l")

    def test_cmd_matches_cmd_r(self):
        """Cmd должен совпадать с cmd_r."""
        assert wd.hotkey_name_matches("cmd", "cmd_r")

    def test_alt_matches_alt_l(self):
        """Alt должен совпадать с alt_l."""
        assert wd.hotkey_name_matches("alt", "alt_l")

    def test_cmd_l_matches_cmd_r_via_generic_cmd(self):
        """cmd_l и cmd_r совпадают через общий вариант cmd — это ожидаемое поведение."""
        assert wd.hotkey_name_matches("cmd_l", "cmd_r")

    def test_unrelated_keys_dont_match(self):
        """Несвязанные клавиши не должны совпадать."""
        assert not wd.hotkey_name_matches("cmd", "alt")

    def test_shift_variants(self):
        """Shift должен совпадать с shift_l и shift_r."""
        assert wd.hotkey_name_matches("shift", "shift_l")
        assert wd.hotkey_name_matches("shift", "shift_r")


class TestFormatHotkeyStatus:
    """Тесты форматирования хоткея для отображения в меню."""

    def test_cmd_alt(self):
        """cmd_l+alt должен отображаться с символами."""
        result = wd.format_hotkey_status("cmd_l+alt")
        assert "⌘" in result
        assert "⌥" in result

    def test_double_cmd(self):
        """Режим двойного нажатия должен показать соответствующий текст."""
        result = wd.format_hotkey_status(use_double_cmd=True)
        assert "двойное нажатие" in result

    def test_space_key(self):
        """Клавиша space должна отображаться как Space."""
        result = wd.format_hotkey_status("cmd_l+space")
        assert "Space" in result


class TestFormatMaxTimeStatus:
    """Тесты форматирования лимита длительности записи."""

    def test_none_is_no_limit(self):
        """None должен стать 'без лимита'."""
        assert wd.format_max_time_status(None) == "без лимита"

    def test_integer_seconds(self):
        """Целые секунды должны отображаться без дробной части."""
        assert wd.format_max_time_status(30) == "30 с"

    def test_float_seconds(self):
        """Дробные секунды должны отображаться с дробной частью."""
        assert wd.format_max_time_status(10.5) == "10.5 с"
