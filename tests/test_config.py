"""Юнит-тесты конфигурационных helper-функций."""

from types import SimpleNamespace

import config


class FakeDefaults:
    """Простой дублер NSUserDefaults для unit-тестов."""

    def __init__(self, object_value=None, bool_value=False, array_value=None):
        self.object_value = object_value
        self.bool_value = bool_value
        self.array_value = array_value
        self.saved_bool = None
        self.saved_object = None

    def objectForKey_(self, _key):  # noqa: N802
        """Эмулирует Objective-C API чтения объекта по ключу."""
        return self.object_value

    def boolForKey_(self, _key):  # noqa: N802
        """Эмулирует Objective-C API чтения bool по ключу."""
        return self.bool_value

    def setBool_forKey_(self, value, _key):  # noqa: N802
        """Эмулирует Objective-C API сохранения bool по ключу."""
        self.saved_bool = value

    def arrayForKey_(self, _key):  # noqa: N802
        """Эмулирует Objective-C API чтения списка по ключу."""
        return self.array_value

    def setObject_forKey_(self, value, _key):  # noqa: N802
        """Эмулирует Objective-C API сохранения объекта по ключу."""
        self.saved_object = value


def install_defaults(monkeypatch, fake_defaults):
    """Подменяет NSUserDefaults на тестовый дублер."""
    monkeypatch.setattr(
        config,
        "NSUserDefaults",
        SimpleNamespace(standardUserDefaults=lambda: fake_defaults),
    )


def test_load_defaults_bool_returns_fallback_when_key_missing(monkeypatch):
    """При отсутствии ключа helper должен вернуть fallback."""
    fake_defaults = FakeDefaults(object_value=None)
    install_defaults(monkeypatch, fake_defaults)

    assert config._load_defaults_bool("missing", True) is True


def test_load_defaults_bool_reads_saved_value(monkeypatch):
    """При наличии ключа helper должен вернуть сохраненное bool-значение."""
    fake_defaults = FakeDefaults(object_value="exists", bool_value=False)
    install_defaults(monkeypatch, fake_defaults)

    assert config._load_defaults_bool("saved", True) is False


def test_save_defaults_bool_persists_boolean(monkeypatch):
    """Сохранение bool должно приводить значение к булеву типу."""
    fake_defaults = FakeDefaults()
    install_defaults(monkeypatch, fake_defaults)

    config._save_defaults_bool("flag", 1)

    assert fake_defaults.saved_bool is True


def test_load_defaults_list_returns_empty_list_when_missing(monkeypatch):
    """При отсутствии списка helper должен вернуть пустой список."""
    fake_defaults = FakeDefaults(array_value=None)
    install_defaults(monkeypatch, fake_defaults)

    assert config._load_defaults_list("history") == []


def test_load_defaults_list_normalizes_items_to_strings(monkeypatch):
    """Список из NSUserDefaults должен нормализоваться к строкам."""
    fake_defaults = FakeDefaults(array_value=[1, "два", 3])
    install_defaults(monkeypatch, fake_defaults)

    assert config._load_defaults_list("history") == ["1", "два", "3"]


def test_save_defaults_list_stores_copy(monkeypatch):
    """Сохранение списка должно передавать обычный list в NSUserDefaults."""
    fake_defaults = FakeDefaults()
    install_defaults(monkeypatch, fake_defaults)

    config._save_defaults_list("history", ("a", "b"))

    assert fake_defaults.saved_object == ["a", "b"]
