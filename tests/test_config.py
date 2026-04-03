"""Юнит-тесты объектной модели конфигурации и Defaults."""

from __future__ import annotations

from types import SimpleNamespace

from src.domain.constants import Config
from src.domain.types import AppPreferences, HotkeyConfig, LaunchConfig, TranscriberPreferences
from src.infrastructure.persistence import defaults as defaults_module
from src.infrastructure.persistence.defaults import Defaults


class FakeNSUserDefaults:
    """Простой дублёр NSUserDefaults для unit-тестов."""

    def __init__(self, *, object_values=None, bool_values=None, int_values=None, array_value=None):
        self.object_values = dict(object_values or {})
        self.bool_values = dict(bool_values or {})
        self.int_values = dict(int_values or {})
        self.array_value = array_value
        self.saved_bool = None
        self.saved_object = None

    def objectForKey_(self, key):
        """Эмулирует Objective-C API чтения объекта по ключу."""
        return self.object_values.get(key)

    def boolForKey_(self, key):
        """Эмулирует Objective-C API чтения bool по ключу."""
        return self.bool_values.get(key, False)

    def integerForKey_(self, key):
        """Эмулирует Objective-C API чтения int по ключу."""
        return self.int_values.get(key, -1)

    def setBool_forKey_(self, value, _key):
        """Эмулирует Objective-C API сохранения bool по ключу."""
        self.saved_bool = value

    def arrayForKey_(self, _key):
        """Эмулирует Objective-C API чтения списка по ключу."""
        return self.array_value

    def setObject_forKey_(self, value, _key):
        """Эмулирует Objective-C API сохранения объекта по ключу."""
        self.saved_object = value

    def removeObjectForKey_(self, key):
        """Эмулирует Objective-C API удаления значения по ключу."""
        self.object_values.pop(key, None)


class FakeSettingsStore:
    """Фейковое key-value хранилище для конфигурационных объектов."""

    def __init__(self, *, values=None, bool_values=None, int_values=None):
        self.values = dict(values or {})
        self.bool_values = dict(bool_values or {})
        self.int_values = dict(int_values or {})

    def contains_key(self, key):
        return key in self.values or key in self.bool_values or key in self.int_values

    def load_str(self, key, fallback=None):
        value = self.values.get(key, fallback)
        return fallback if value is None else str(value)

    def load_bool(self, key, fallback):
        return self.bool_values.get(key, fallback)

    def load_int(self, key, fallback):
        return self.int_values.get(key, fallback)

    def load_list(self, _key):
        return []

    def save_bool(self, _key, _value):
        return None

    def save_list(self, _key, _value):
        return None

    def save_int(self, _key, _value):
        return None

    def save_str(self, _key, _value):
        return None

    def load_max_time(self, fallback):
        return fallback

    def save_max_time(self, _value):
        return None

    def load_input_device_index(self):
        return None

    def load_input_device_name(self):
        return None

    def save_input_device_index(self, _value):
        return None

    def save_input_device_name(self, _value):
        return None

    def remove_key(self, _key):
        return None


def install_defaults(monkeypatch, fake_defaults):
    """Подменяет NSUserDefaults на тестовый дублёр."""
    monkeypatch.setattr(
        defaults_module,
        "NSUserDefaults",
        SimpleNamespace(standardUserDefaults=lambda: fake_defaults),
    )


def test_defaults_contains_key_returns_presence(monkeypatch):
    """Defaults.contains_key должен проверять наличие objectForKey_."""
    fake_defaults = FakeNSUserDefaults(object_values={"existing": "value"})
    install_defaults(monkeypatch, fake_defaults)

    defaults = Defaults.__new__(Defaults)

    assert defaults.contains_key("existing") is True
    assert defaults.contains_key("missing") is False


def test_load_defaults_bool_returns_fallback_when_key_missing(monkeypatch):
    """При отсутствии ключа helper должен вернуть fallback."""
    fake_defaults = FakeNSUserDefaults()
    install_defaults(monkeypatch, fake_defaults)

    defaults = Defaults.__new__(Defaults)
    assert defaults.load_bool("missing", True) is True


def test_load_defaults_list_normalizes_items_to_strings(monkeypatch):
    """Список из NSUserDefaults должен нормализоваться к строкам."""
    fake_defaults = FakeNSUserDefaults(array_value=[1, "два", 3])
    install_defaults(monkeypatch, fake_defaults)

    defaults = Defaults.__new__(Defaults)
    assert defaults.load_list("history") == ["1", "два", "3"]


def test_save_defaults_list_stores_copy(monkeypatch):
    """Сохранение списка должно передавать обычный list в NSUserDefaults."""
    fake_defaults = FakeNSUserDefaults()
    install_defaults(monkeypatch, fake_defaults)

    defaults = Defaults.__new__(Defaults)
    defaults.save_list("history", ("a", "b"))  # type: ignore[arg-type]

    assert fake_defaults.saved_object == ["a", "b"]


def test_launch_config_merges_cli_and_saved_preferences():
    """LaunchConfig должен объединять CLI и сохранённые настройки."""
    settings_store = FakeSettingsStore(
        values={
            Config.DEFAULTS_KEY_MODEL: "mlx-community/whisper-turbo",
            Config.DEFAULTS_KEY_LANGUAGE: "en",
            Config.DEFAULTS_KEY_MAX_TIME: "60",
            Config.DEFAULTS_KEY_PRIMARY_HOTKEY: "ctrl+alt+d",
            Config.DEFAULTS_KEY_SECONDARY_HOTKEY: "",
            Config.DEFAULTS_KEY_LLM_HOTKEY: "ctrl+shift+l",
        }
    )

    config = LaunchConfig.from_sources(
        model=Config.DEFAULT_MODEL_NAME,
        language="ru",
        max_time=30,
        llm_model=Config.DEFAULT_LLM_MODEL_NAME,
        key_combination="cmd_l+alt",
        secondary_key_combination="ctrl+shift+alt+t",
        llm_key_combination="ctrl+shift+alt+l",
        settings_store=settings_store,
        cli_overrides=set(),
    )

    assert config.model == "mlx-community/whisper-turbo"
    assert config.language == ["en"]
    assert config.max_time == 60
    assert config.key_combination == "ctrl+alt+d"
    assert config.secondary_key_combination is None
    assert config.llm_key_combination == "ctrl+shift+l"


def test_launch_config_rejects_duplicate_hotkeys():
    """Конфиг запуска должен запрещать одинаковые primary/secondary хоткеи."""
    try:
        LaunchConfig.from_sources(
            model=Config.DEFAULT_MODEL_NAME,
            language="ru",
            max_time=30,
            llm_model=Config.DEFAULT_LLM_MODEL_NAME,
            key_combination="cmd_l+alt",
            secondary_key_combination="cmd_l+alt",
            llm_key_combination="ctrl+shift+alt+l",
        )
    except ValueError as error:
        assert "Дополнительный хоткей" in str(error)
    else:
        raise AssertionError("Ожидался ValueError для дублирующегося хоткея")


def test_launch_config_rejects_non_english_language_for_en_model():
    """Для `.en` модели нельзя указывать язык, отличный от `en`."""
    try:
        LaunchConfig.from_sources(
            model="mlx-community/whisper-tiny.en",
            language="ru",
            max_time=30,
            llm_model=Config.DEFAULT_LLM_MODEL_NAME,
            key_combination="cmd_l+alt",
            secondary_key_combination=None,
            llm_key_combination=None,
        )
    except ValueError as error:
        assert ".en" in str(error)
    else:
        raise AssertionError("Ожидался ValueError для несовместимого языка")


def test_hotkey_config_serializes_empty_optional_hotkeys():
    """Отключённые хоткеи должны сериализоваться пустой строкой."""
    hotkeys = HotkeyConfig.from_values(
        primary_key_combination="cmd_l+alt",
        secondary_key_combination="",
        llm_key_combination=None,
    )

    assert hotkeys.secondary_key_combination is None
    assert hotkeys.secondary_store_value == ""
    assert hotkeys.llm_store_value == ""


def test_app_preferences_reads_and_normalizes_store_values():
    """AppPreferences должен читать и валидировать сохранённые настройки."""
    settings_store = FakeSettingsStore(
        values={
            Config.DEFAULTS_KEY_LLM_PROMPT: "Несуществующий промпт",
            Config.DEFAULTS_KEY_PERFORMANCE_MODE: "turbo",
            Config.DEFAULTS_KEY_LANGUAGE: "en",
            Config.DEFAULTS_KEY_INPUT_DEVICE_NAME: "  USB Mic  ",
        },
        bool_values={
            Config.DEFAULTS_KEY_RECORDING_NOTIFICATION: False,
            Config.DEFAULTS_KEY_RECORDING_OVERLAY: True,
        },
        int_values={Config.DEFAULTS_KEY_INPUT_DEVICE_INDEX: 7},
    )

    preferences = AppPreferences.from_store(settings_store)

    assert preferences.llm_prompt_name == Config.DEFAULT_LLM_PROMPT_NAME
    assert preferences.performance_mode == Config.DEFAULT_PERFORMANCE_MODE
    assert preferences.selected_language == "en"
    assert preferences.selected_input_device_index == 7
    assert preferences.selected_input_device_name == "USB Mic"
    assert preferences.show_recording_notification is False
    assert preferences.show_recording_overlay is True


def test_defaults_save_input_device_name_removes_key_for_empty_value(monkeypatch):
    """Пустое имя микрофона не должно сохраняться в NSUserDefaults."""
    removed_keys: list[str] = []

    class TrackingNSUserDefaults(FakeNSUserDefaults):
        def removeObjectForKey_(self, key):
            removed_keys.append(key)
            super().removeObjectForKey_(key)

    fake_defaults = TrackingNSUserDefaults()
    install_defaults(monkeypatch, fake_defaults)
    defaults = Defaults.__new__(Defaults)

    defaults.save_input_device_name("   ")

    assert removed_keys == [Config.DEFAULTS_KEY_INPUT_DEVICE_NAME]


def test_defaults_load_input_device_name_normalizes_value(monkeypatch):
    """Имя микрофона должно читаться из NSUserDefaults с trim-нормализацией."""
    fake_defaults = FakeNSUserDefaults(object_values={Config.DEFAULTS_KEY_INPUT_DEVICE_NAME: "  Studio Mic  "})
    install_defaults(monkeypatch, fake_defaults)
    defaults = Defaults.__new__(Defaults)

    assert defaults.load_input_device_name() == "Studio Mic"


def test_transcriber_preferences_reads_typed_flags_and_token_count():
    """TranscriberPreferences должен собираться из typed store-значений."""
    settings_store = FakeSettingsStore(
        bool_values={
            Config.DEFAULTS_KEY_PASTE_CGEVENT: False,
            Config.DEFAULTS_KEY_PASTE_AX: True,
            Config.DEFAULTS_KEY_PASTE_CLIPBOARD: True,
            Config.DEFAULTS_KEY_LLM_CLIPBOARD: False,
            Config.DEFAULTS_KEY_PRIVATE_MODE: True,
        },
        int_values={Config.DEFAULTS_KEY_TOTAL_TOKENS: 123},
    )

    preferences = TranscriberPreferences.from_store(settings_store)

    assert preferences.paste_cgevent_enabled is False
    assert preferences.paste_ax_enabled is True
    assert preferences.paste_clipboard_enabled is True
    assert preferences.llm_clipboard_enabled is False
    assert preferences.private_mode_enabled is True
    assert preferences.total_tokens == 123
