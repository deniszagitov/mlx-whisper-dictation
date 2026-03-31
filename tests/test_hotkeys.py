"""Тесты разбора горячих клавиш и аргументов командной строки.

Проверяет корректность парсинга комбинаций клавиш, форматирования
для отображения в меню и обработки аргументов командной строки.
"""

import sys
from types import SimpleNamespace

import pytest
from src.domain.constants import Config


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

    def test_four_keys(self, app_module):
        """Комбинация из четырёх клавиш должна парситься."""
        result = app_module.parse_key_combination("ctrl+shift+alt+t")
        assert len(result) == 4

    def test_case_insensitive(self, app_module):
        """Регистр имён клавиш не должен иметь значения."""
        result = app_module.parse_key_combination("Ctrl+Shift+Alt+T")
        assert len(result) == 4

    def test_aliases_are_normalized(self, app_module):
        """Человекочитаемые алиасы должны нормализоваться."""
        result = app_module.parse_key_combination("Control+Option+t")
        assert len(result) == 3


class TestNormalizeKeyName:
    """Тесты нормализации имён клавиш."""

    def test_lowercase_passthrough(self, app_module):
        """Уже нормализованные имена должны проходить без изменений."""
        assert app_module.normalize_key_name("ctrl") == "ctrl"

    def test_uppercase_to_lower(self, app_module):
        """Имена в верхнем регистре должны приводиться к нижнему."""
        assert app_module.normalize_key_name("Ctrl") == "ctrl"

    def test_control_alias(self, app_module):
        """Control должен нормализоваться в ctrl."""
        assert app_module.normalize_key_name("Control") == "ctrl"

    def test_option_alias(self, app_module):
        """Option должен нормализоваться в alt."""
        assert app_module.normalize_key_name("Option") == "alt"

    def test_command_alias(self, app_module):
        """Command должен нормализоваться в cmd."""
        assert app_module.normalize_key_name("Command") == "cmd"

    def test_unknown_key_lowered(self, app_module):
        """Неизвестные клавиши просто приводятся к нижнему регистру."""
        assert app_module.normalize_key_name("T") == "t"

    def test_specific_side_preserved(self, app_module):
        """Конкретная сторона модификатора не должна теряться."""
        assert app_module.normalize_key_name("cmd_l") == "cmd_l"
        assert app_module.normalize_key_name("alt_r") == "alt_r"


class TestNormalizeKeyCombination:
    """Тесты нормализации полной комбинации клавиш."""

    def test_aliases_and_whitespace_are_normalized(self, app_module):
        """Полная комбинация должна приводиться к каноническому виду."""
        result = app_module.normalize_key_combination(" Command + Option + Space ")
        assert result == "cmd+alt+space"

    def test_single_key_raises(self, app_module):
        """Одиночная клавиша должна отклоняться и на этапе нормализации."""
        with pytest.raises(ValueError, match="как минимум две клавиши"):
            app_module.normalize_key_combination("space")


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

    def test_space_key(self, app_module):
        """Клавиша space должна отображаться как Space."""
        result = app_module.format_hotkey_status("cmd_l+space")
        assert "Space" in result

    def test_four_modifiers(self, app_module):
        """Комбинация ctrl+shift+alt+t должна корректно отображаться."""
        result = app_module.format_hotkey_status("ctrl+shift+alt+t")
        assert "⌃" in result
        assert "⇧" in result
        assert "⌥" in result
        assert "T" in result

    def test_case_insensitive_display(self, app_module):
        """Алиасы в разном регистре должны корректно отображаться."""
        result = app_module.format_hotkey_status("Control+Shift+Option+T")
        assert "⌃" in result
        assert "⇧" in result
        assert "⌥" in result


class TestFormatMaxTimeStatus:
    """Тесты форматирования лимита длительности записи."""

    def test_none_is_no_limit(self, app_module):
        """None должен стать 'без лимита'."""
        assert Config.format_max_time_status(None) == "без лимита"

    def test_integer_seconds(self, app_module):
        """Целые секунды должны отображаться без дробной части."""
        assert Config.format_max_time_status(30) == "30 с"

    def test_float_seconds(self, app_module):
        """Дробные секунды должны отображаться с дробной частью."""
        assert Config.format_max_time_status(10.5) == "10.5 с"


class TestParseArgs:
    """Тесты аргументов командной строки для нескольких хоткеев."""

    @pytest.fixture(autouse=True)
    def _clean_defaults(self, app_module, monkeypatch):
        """Изолирует parse_args-тесты от реальных NSUserDefaults пользователя."""
        import src.infrastructure.persistence.defaults as defaults_module

        class EmptyDefaults:
            def objectForKey_(self, _key):
                return None

            def boolForKey_(self, _key):
                return False

            def integerForKey_(self, _key):
                return -1

        empty_defaults = EmptyDefaults()

        def standard_user_defaults():
            return empty_defaults

        monkeypatch.setattr(
            defaults_module,
            "NSUserDefaults",
            SimpleNamespace(standardUserDefaults=standard_user_defaults),
        )

    def test_secondary_hotkey_is_normalized(self, app_module, monkeypatch):
        """Дополнительный хоткей должен нормализоваться так же, как основной."""
        monkeypatch.setattr(
            sys,
            "argv",
            [
                "main.py",
                "-k",
                "Command+Option+Space",
                "--secondary_key_combination",
                "Control+Shift+T",
            ],
        )

        args = app_module.parse_args()

        assert args.key_combination == "cmd+alt+space"
        assert args.secondary_key_combination == "ctrl+shift+t"

    def test_secondary_hotkey_cannot_duplicate_primary(self, app_module, monkeypatch):
        """Основной и дополнительный хоткей не должны совпадать."""
        monkeypatch.setattr(
            sys,
            "argv",
            [
                "main.py",
                "-k",
                "cmd_l+alt",
                "--secondary_key_combination",
                "cmd_l+alt",
            ],
        )

        with pytest.raises(SystemExit):
            app_module.parse_args()

    def test_default_secondary_hotkey(self, app_module, monkeypatch):
        """По умолчанию дополнительный хоткей должен быть ctrl+shift+alt+t."""
        monkeypatch.setattr(
            sys,
            "argv",
            ["main.py"],
        )

        args = app_module.parse_args()

        assert args.secondary_key_combination == "ctrl+shift+alt+t"

    def test_empty_secondary_disables_it(self, app_module, monkeypatch):
        """Пустая строка в --secondary_key_combination должна отключить доп. хоткей."""
        monkeypatch.setattr(
            sys,
            "argv",
            ["main.py", "--secondary_key_combination", ""],
        )

        args = app_module.parse_args()

        assert args.secondary_key_combination is None

    def test_parse_args_uses_saved_preferences_when_cli_not_overrides(self, app_module, monkeypatch):
        """При отсутствии явных CLI-флагов приложение должно поднять сохранённые настройки."""
        import src.infrastructure.persistence.defaults as config_module

        class FakeDefaults:
            def __init__(self):
                self.values = {
                    Config.DEFAULTS_KEY_MODEL: "mlx-community/whisper-turbo",
                    Config.DEFAULTS_KEY_LANGUAGE: "en",
                    Config.DEFAULTS_KEY_MAX_TIME: "60",
                    Config.DEFAULTS_KEY_PRIMARY_HOTKEY: "ctrl+alt+d",
                    Config.DEFAULTS_KEY_SECONDARY_HOTKEY: "",
                    Config.DEFAULTS_KEY_LLM_HOTKEY: "ctrl+shift+l",
                }

            def objectForKey_(self, key):
                return self.values.get(key)

            def boolForKey_(self, _key):
                return False

            def integerForKey_(self, _key):
                return -1

        fake_defaults = FakeDefaults()

        def standard_user_defaults():
            return fake_defaults

        fake_ns = SimpleNamespace(standardUserDefaults=standard_user_defaults)
        monkeypatch.setattr(config_module, "NSUserDefaults", fake_ns)
        monkeypatch.setattr(sys, "argv", ["main.py"])

        args = app_module.parse_args()

        assert args.model == "mlx-community/whisper-turbo"
        assert args.language == ["en"]
        assert args.max_time == 60
        assert args.key_combination == "ctrl+alt+d"
        assert args.secondary_key_combination is None
        assert args.llm_key_combination == "ctrl+shift+l"


class TestModifierOnlyCombination:
    """Тесты классификации modifier-only комбинаций."""

    def test_returns_true_for_modifier_only(self, app_module):
        assert app_module.is_modifier_only_combination("cmd_l+alt") is True

    def test_returns_false_for_regular_hotkey(self, app_module):
        assert app_module.is_modifier_only_combination("ctrl+shift+space") is False


class TestMultiHotkeyListener:
    """Тесты управления несколькими глобальными хоткеями."""

    def _make_fake_app(self):
        """Создаёт фейковый app с атрибутом toggle."""

        class FakeApp:
            def __init__(self):
                self.toggle_count = 0

            def toggle(self):
                self.toggle_count += 1

        return FakeApp()

    def test_init_creates_listeners_for_each_combination(self, app_module):
        """При создании должен быть listener для каждой непустой комбинации."""
        fake_app = self._make_fake_app()
        multi = app_module.MultiHotkeyListener(fake_app, ["cmd_l+alt", "ctrl+shift+alt+t"])

        assert len(multi.listeners) == 2
        assert len(multi.key_combinations) == 2

    def test_init_skips_empty_combinations(self, app_module):
        """Пустые строки и None в списке должны пропускаться."""
        fake_app = self._make_fake_app()
        multi = app_module.MultiHotkeyListener(fake_app, ["cmd_l+alt", None, ""])

        assert len(multi.listeners) == 1

    def test_init_raises_if_all_empty(self, app_module):
        """Если все комбинации пустые, должен быть ValueError."""
        fake_app = self._make_fake_app()
        with pytest.raises(ValueError, match="хотя бы один хоткей"):
            app_module.MultiHotkeyListener(fake_app, [None, ""])

    def test_update_recreates_listeners(self, app_module):
        """update_key_combinations должен пересоздать listener-ы."""
        fake_app = self._make_fake_app()
        multi = app_module.MultiHotkeyListener(fake_app, ["cmd_l+alt"])
        old_listeners = multi.listeners[:]

        multi.update_key_combinations(["ctrl+shift+alt+t", "cmd_r+shift"])

        assert len(multi.listeners) == 2
        assert multi.listeners != old_listeners

    def test_update_normalizes_combinations(self, app_module):
        """update_key_combinations должен нормализовать имена клавиш."""
        fake_app = self._make_fake_app()
        multi = app_module.MultiHotkeyListener(fake_app, ["cmd_l+alt"])

        multi.update_key_combinations(["Control+Shift+Alt+T"])

        assert multi.key_combinations == ["ctrl+shift+alt+t"]

    def test_update_raises_if_all_empty(self, app_module):
        """update_key_combinations должен отклонить пустой список."""
        fake_app = self._make_fake_app()
        multi = app_module.MultiHotkeyListener(fake_app, ["cmd_l+alt"])

        with pytest.raises(ValueError, match="хотя бы один хоткей"):
            multi.update_key_combinations([None, ""])

    def test_listeners_have_correct_key_combinations(self, app_module):
        """Каждый listener должен получить свою комбинацию."""
        fake_app = self._make_fake_app()
        multi = app_module.MultiHotkeyListener(fake_app, ["cmd_l+alt", "ctrl+shift+alt+t"])

        assert multi.listeners[0].key_combination == "cmd_l+alt"
        assert multi.listeners[1].key_combination == "ctrl+shift+alt+t"


class TestEventKeyNameStatic:
    """Тесты статической функции извлечения имени клавиши из NSEvent."""

    def _make_event(self, key_code, characters=""):
        """Создаёт фейковый NSEvent-подобный объект."""

        class FakeEvent:
            def __init__(self, kc, chars):
                self._key_code = kc
                self._chars = chars

            def keyCode(self):
                return self._key_code

            def charactersIgnoringModifiers(self):
                return self._chars

        return FakeEvent(key_code, characters)

    def test_space_keycode(self, app_module):
        """Keycode 49 должен вернуть space."""
        assert app_module._event_key_name_static(self._make_event(49)) == "space"

    def test_enter_keycode(self, app_module):
        """Keycode 36 должен вернуть enter."""
        assert app_module._event_key_name_static(self._make_event(36)) == "enter"

    def test_tab_keycode(self, app_module):
        """Keycode 48 должен вернуть tab."""
        assert app_module._event_key_name_static(self._make_event(48)) == "tab"

    def test_esc_keycode(self, app_module):
        """Keycode 53 должен вернуть esc."""
        assert app_module._event_key_name_static(self._make_event(53)) == "esc"

    def test_character_key(self, app_module):
        """Обычная буквенная клавиша должна вернуть символ в нижнем регистре."""
        assert app_module._event_key_name_static(self._make_event(17, "T")) == "t"

    def test_empty_characters(self, app_module):
        """Пустые characters должны вернуть пустую строку."""
        assert app_module._event_key_name_static(self._make_event(999, "")) == ""


class TestKeycodeToChar:
    """Тесты преобразования keycode в символ через Carbon API."""

    def test_returns_none_when_carbon_unavailable(self, app_module, monkeypatch):
        """Если Carbon API недоступен, функция должна вернуть None."""
        import src.infrastructure.hotkeys as hotkeys_module

        monkeypatch.setattr(hotkeys_module, "_CARBON_AVAILABLE", False)
        result = hotkeys_module._keycode_to_char(0)
        assert result is None

    def test_called_by_event_key_name_static(self, app_module, monkeypatch):
        """_event_key_name_static должен вызывать _keycode_to_char для не-именованных клавиш."""
        import src.infrastructure.hotkeys as hotkeys_module

        calls = []

        def tracking_keycode_to_char(keycode):
            calls.append(keycode)
            return "q"

        monkeypatch.setattr(hotkeys_module, "_keycode_to_char", tracking_keycode_to_char)

        class FakeEvent:
            def keyCode(self):
                return 12  # keycode для Q

            def charactersIgnoringModifiers(self):
                return "q"

        result = hotkeys_module._event_key_name_static(FakeEvent())
        assert result == "q"
        assert 12 in calls

    def test_carbon_result_overrides_characters(self, app_module, monkeypatch):
        """Результат _keycode_to_char имеет приоритет над charactersIgnoringModifiers."""
        import src.infrastructure.hotkeys as hotkeys_module

        monkeypatch.setattr(hotkeys_module, "_keycode_to_char", lambda kc: "a")

        class FakeEvent:
            def keyCode(self):
                return 0

            def charactersIgnoringModifiers(self):
                return "ф"  # русская раскладка

        result = hotkeys_module._event_key_name_static(FakeEvent())
        assert result == "a"

    def test_falls_back_to_characters_when_carbon_returns_none(self, app_module, monkeypatch):
        """Если _keycode_to_char вернул None, используется charactersIgnoringModifiers."""
        import src.infrastructure.hotkeys as hotkeys_module

        monkeypatch.setattr(hotkeys_module, "_keycode_to_char", lambda kc: None)

        class FakeEvent:
            def keyCode(self):
                return 999

            def charactersIgnoringModifiers(self):
                return "X"

        result = hotkeys_module._event_key_name_static(FakeEvent())
        assert result == "x"


class TestCheckKeyDown:
    """Тесты _check_key_down — проверки совпадения keyDown с хоткеем."""

    def _make_fake_app(self):
        class FakeApp:
            def __init__(self):
                self.toggle_count = 0

            def toggle(self):
                self.toggle_count += 1

        return FakeApp()

    def _make_event(self, key_code, characters=""):
        class FakeEvent:
            def __init__(self, kc, chars):
                self._key_code = kc
                self._chars = chars

            def keyCode(self):
                return self._key_code

            def charactersIgnoringModifiers(self):
                return self._chars

        return FakeEvent(key_code, characters)

    def test_returns_true_when_hotkey_matches(self, app_module, monkeypatch):
        """_check_key_down возвращает True, если все модификаторы нажаты и клавиша совпадает."""
        import src.infrastructure.hotkeys as hotkeys_module

        monkeypatch.setattr(hotkeys_module, "_keycode_to_char", lambda kc: None)
        fake_app = self._make_fake_app()
        listener = app_module.GlobalKeyListener(fake_app, "ctrl+alt+t")
        listener.pressed_modifier_names = {"ctrl_l", "alt_l"}
        event = self._make_event(17, "t")  # keycode 17 = T

        result = listener._check_key_down(event)

        assert result is True
        assert fake_app.toggle_count == 1

    def test_returns_false_when_modifiers_not_pressed(self, app_module, monkeypatch):
        """_check_key_down возвращает False, если модификаторы не нажаты."""
        import src.infrastructure.hotkeys as hotkeys_module

        monkeypatch.setattr(hotkeys_module, "_keycode_to_char", lambda kc: None)
        fake_app = self._make_fake_app()
        listener = app_module.GlobalKeyListener(fake_app, "ctrl+alt+t")
        listener.pressed_modifier_names = set()
        event = self._make_event(17, "t")

        result = listener._check_key_down(event)

        assert result is False
        assert fake_app.toggle_count == 0

    def test_returns_false_when_wrong_key(self, app_module, monkeypatch):
        """_check_key_down возвращает False, если клавиша не совпадает с хоткеем."""
        import src.infrastructure.hotkeys as hotkeys_module

        monkeypatch.setattr(hotkeys_module, "_keycode_to_char", lambda kc: None)
        fake_app = self._make_fake_app()
        listener = app_module.GlobalKeyListener(fake_app, "ctrl+alt+t")
        listener.pressed_modifier_names = {"ctrl_l", "alt_l"}
        event = self._make_event(0, "a")

        result = listener._check_key_down(event)

        assert result is False
        assert fake_app.toggle_count == 0

    def test_returns_false_when_already_triggered(self, app_module, monkeypatch):
        """_check_key_down возвращает False, если хоткей уже сработал (защита от повтора)."""
        import src.infrastructure.hotkeys as hotkeys_module

        monkeypatch.setattr(hotkeys_module, "_keycode_to_char", lambda kc: None)
        fake_app = self._make_fake_app()
        listener = app_module.GlobalKeyListener(fake_app, "ctrl+alt+t")
        listener.pressed_modifier_names = {"ctrl_l", "alt_l"}
        listener.triggered = True
        event = self._make_event(17, "t")

        result = listener._check_key_down(event)

        assert result is False
        assert fake_app.toggle_count == 0

    def test_returns_false_for_modifier_only_hotkey(self, app_module):
        """Для хоткея без обычной клавиши _check_key_down всегда возвращает False."""
        fake_app = self._make_fake_app()
        listener = app_module.GlobalKeyListener(fake_app, "ctrl+alt")
        listener.pressed_modifier_names = {"ctrl_l", "alt_l"}

        class FakeEvent:
            def keyCode(self):
                return 17

            def charactersIgnoringModifiers(self):
                return "t"

        result = listener._check_key_down(FakeEvent())

        assert result is False


class TestCGEventTapCallback:
    """Тесты CGEventTap callback — подавление символа хоткея."""

    def _make_fake_app(self):
        class FakeApp:
            def __init__(self):
                self.toggle_count = 0

            def toggle(self):
                self.toggle_count += 1

        return FakeApp()

    def test_suppresses_hotkey_event(self, app_module, monkeypatch):
        """Callback должен вернуть None для подавления символа хоткея."""
        import src.infrastructure.hotkeys as hotkeys_module

        monkeypatch.setattr(hotkeys_module, "_keycode_to_char", lambda kc: None)
        fake_app = self._make_fake_app()
        listener = app_module.GlobalKeyListener(fake_app, "ctrl+alt+t")
        listener.pressed_modifier_names = {"ctrl_l", "alt_l"}

        class FakeNSEvent:
            def keyCode(self):
                return 17

            def charactersIgnoringModifiers(self):
                return "t"

        # Mock _ns_event_from_cgevent to return our fake NSEvent
        listener._ns_event_from_cgevent = lambda cg_event: FakeNSEvent()

        import Quartz

        result = listener._cgevent_tap_callback(None, Quartz.kCGEventKeyDown, "fake_cg_event", None)

        assert result is None
        assert fake_app.toggle_count == 1

    def test_passes_through_non_hotkey_event(self, app_module, monkeypatch):
        """Callback должен вернуть cg_event, если клавиша не является хоткеем."""
        import src.infrastructure.hotkeys as hotkeys_module

        monkeypatch.setattr(hotkeys_module, "_keycode_to_char", lambda kc: None)
        fake_app = self._make_fake_app()
        listener = app_module.GlobalKeyListener(fake_app, "ctrl+alt+t")
        listener.pressed_modifier_names = set()  # no modifiers pressed

        class FakeNSEvent:
            def keyCode(self):
                return 0

            def charactersIgnoringModifiers(self):
                return "a"

        listener._ns_event_from_cgevent = lambda cg_event: FakeNSEvent()

        import Quartz

        sentinel = object()
        result = listener._cgevent_tap_callback(None, Quartz.kCGEventKeyDown, sentinel, None)

        assert result is sentinel

    def test_reenables_tap_on_timeout(self, app_module, monkeypatch):
        """При kCGEventTapDisabledByTimeout callback должен включить tap и вернуть cg_event."""
        import Quartz as _quartz_mod  # noqa: N813

        fake_app = self._make_fake_app()
        listener = app_module.GlobalKeyListener(fake_app, "ctrl+alt+t")
        listener._event_tap = "fake_tap"

        enabled_calls = []
        monkeypatch.setattr(_quartz_mod, "CGEventTapEnable", lambda tap, enable: enabled_calls.append((tap, enable)))

        sentinel = object()
        result = listener._cgevent_tap_callback(None, _quartz_mod.kCGEventTapDisabledByTimeout, sentinel, None)
        assert result is sentinel
        assert enabled_calls == [("fake_tap", True)]

    def test_returns_cgevent_when_ns_event_conversion_fails(self, app_module):
        """Если конвертация CGEvent → NSEvent не удалась, возвращаем cg_event."""
        fake_app = self._make_fake_app()
        listener = app_module.GlobalKeyListener(fake_app, "ctrl+alt+t")
        listener._ns_event_from_cgevent = lambda cg_event: None

        import Quartz

        sentinel = object()
        result = listener._cgevent_tap_callback(None, Quartz.kCGEventKeyDown, sentinel, None)

        assert result is sentinel


class TestHotkeyDispatcher:
    """Тесты единого dispatcher-а для primary/secondary/LLM и Escape."""

    class _FakeApp:
        def __init__(self):
            self.primary_key_combination = "cmd_l+alt"
            self.secondary_key_combination = "ctrl+shift+space"
            self.llm_key_combination = "ctrl+shift+l"
            self.started = False
            self.toggle_count = 0
            self.toggle_llm_count = 0
            self.escape_keycodes: list[int] = []

        def toggle(self):
            self.toggle_count += 1

        def toggle_llm(self):
            self.toggle_llm_count += 1

        def handle_escape_keycode(self, keycode: int):
            self.escape_keycodes.append(keycode)
            if keycode == 53:
                self.started = False

    class _FakeEvent:
        def __init__(self, key_code, characters="", modifier_flags=0):
            self._key_code = key_code
            self._characters = characters
            self._modifier_flags = modifier_flags

        def keyCode(self):
            return self._key_code

        def charactersIgnoringModifiers(self):
            return self._characters

        def modifierFlags(self):
            return self._modifier_flags

    def test_modifier_only_hotkey_triggers_toggle(self, app_module):
        dispatcher = app_module.HotkeyDispatcher(self._FakeApp())
        event = self._FakeEvent(58, modifier_flags=app_module.MODIFIER_FLAG_MASKS["alt_l"])

        dispatcher.pressed_modifier_names = {"cmd_l"}

        assert dispatcher._handle_flags_changed(event) is True
        assert dispatcher.app.toggle_count == 1

    def test_regular_hotkey_triggers_toggle_and_suppresses_keyup(self, app_module, monkeypatch):
        import src.infrastructure.hotkeys as hotkeys_module

        monkeypatch.setattr(hotkeys_module, "_keycode_to_char", lambda _kc: None)
        dispatcher = app_module.HotkeyDispatcher(self._FakeApp())
        dispatcher.pressed_modifier_names = {"ctrl_l", "shift_l"}

        key_down = self._FakeEvent(49, " ")
        key_up = self._FakeEvent(49, " ")

        assert dispatcher._handle_key_down(key_down) is True
        assert dispatcher.app.toggle_count == 1
        assert dispatcher._handle_key_up(key_up) is True

    def test_llm_hotkey_triggers_llm_callback(self, app_module, monkeypatch):
        import src.infrastructure.hotkeys as hotkeys_module

        monkeypatch.setattr(hotkeys_module, "_keycode_to_char", lambda _kc: None)
        dispatcher = app_module.HotkeyDispatcher(self._FakeApp())
        dispatcher.pressed_modifier_names = {"ctrl_l", "shift_l"}

        event = self._FakeEvent(37, "l")

        assert dispatcher._handle_key_down(event) is True
        assert dispatcher.app.toggle_llm_count == 1

    def test_escape_is_suppressed_only_while_recording(self, app_module):
        fake_app = self._FakeApp()
        fake_app.started = True
        dispatcher = app_module.HotkeyDispatcher(fake_app)
        escape_event = self._FakeEvent(53)

        assert dispatcher._handle_key_down(escape_event) is True
        assert fake_app.escape_keycodes == [53]
        assert dispatcher._handle_key_up(escape_event) is True

    def test_escape_passes_when_not_recording(self, app_module):
        dispatcher = app_module.HotkeyDispatcher(self._FakeApp())
        escape_event = self._FakeEvent(53)

        assert dispatcher._handle_key_down(escape_event) is False
        assert dispatcher.app.escape_keycodes == []

    def test_update_hotkeys_replaces_binding_set(self, app_module):
        dispatcher = app_module.HotkeyDispatcher(self._FakeApp())

        dispatcher.update_hotkeys("ctrl+alt+d", "", "ctrl+shift+space")

        assert {binding.key_combination for binding in dispatcher._bindings} == {
            "ctrl+shift+space",
            "ctrl+alt+d",
        }


class TestModifierConstants:
    """Тесты общих констант для клавиш-модификаторов."""

    def test_modifier_keycodes_map_has_all_modifiers(self, app_module):
        """Карта keycodes должна содержать все основные модификаторы."""
        values = set(app_module.MODIFIER_KEYCODES_MAP.values())
        expected = {"cmd_r", "cmd_l", "shift_l", "shift_r", "alt_l", "alt_r", "ctrl_l", "ctrl_r"}
        assert values == expected

    def test_modifier_flag_masks_has_all_sides(self, app_module):
        """Маски флагов должны покрывать все стороны модификаторов."""
        assert set(app_module.MODIFIER_FLAG_MASKS.keys()) == {"alt_l", "alt_r", "ctrl_l", "ctrl_r", "shift_l", "shift_r", "cmd_l", "cmd_r"}

    def test_modifier_display_order_contains_all_modifiers(self, app_module):
        """Порядок отображения должен включать все модификаторы."""
        order = app_module.MODIFIER_DISPLAY_ORDER
        assert "ctrl" in order
        assert "alt" in order
        assert "shift" in order
        assert "cmd" in order
