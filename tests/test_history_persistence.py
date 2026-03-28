"""Тесты persistence-адаптера истории распознанного текста."""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

from src.domain.constants import Config
from src.infrastructure.persistence import history as history_module

if TYPE_CHECKING:
    from src.domain.types import HistoryRecord


class _FakeDefaults:
    """Минимальная заглушка NSUserDefaults для unit-тестов."""

    def __init__(self) -> None:
        self.storage: dict[str, object] = {}

    def objectForKey_(self, key: str) -> object | None:
        """Возвращает значение по ключу."""
        return self.storage.get(key)

    def setObject_forKey_(self, value: object, key: str) -> None:
        """Сохраняет значение по ключу."""
        self.storage[key] = value


class _FakeNSUserDefaults:
    """Подмена класса NSUserDefaults с singleton defaults."""

    defaults = _FakeDefaults()

    @classmethod
    def standardUserDefaults(cls) -> _FakeDefaults:
        """Возвращает singleton defaults."""
        return cls.defaults


def test_load_history_items_returns_empty_list_when_key_is_missing(monkeypatch):
    """При отсутствии ключа адаптер должен вернуть пустую историю."""
    monkeypatch.setattr(history_module, "NSUserDefaults", _FakeNSUserDefaults)
    _FakeNSUserDefaults.defaults.storage.clear()

    assert history_module.load_history_items() == []


def test_save_history_records_writes_safe_python_types(monkeypatch):
    """При сохранении история должна сериализоваться в обычные dict/list типы."""
    monkeypatch.setattr(history_module, "NSUserDefaults", _FakeNSUserDefaults)
    _FakeNSUserDefaults.defaults.storage.clear()

    records = [
        cast("HistoryRecord", {"text": "Привет", "created_at": 123.5}),
        cast("HistoryRecord", {"text": "Мир", "created_at": 456}),
    ]

    history_module.save_history_records(records)

    assert _FakeNSUserDefaults.defaults.storage[Config.DEFAULTS_KEY_HISTORY] == [
        {"text": "Привет", "created_at": 123.5},
        {"text": "Мир", "created_at": 456.0},
    ]


def test_load_history_items_returns_saved_raw_objects(monkeypatch):
    """Загрузка должна отдавать сырой список объектов для последующей нормализации в transcriber."""
    monkeypatch.setattr(history_module, "NSUserDefaults", _FakeNSUserDefaults)
    _FakeNSUserDefaults.defaults.storage[Config.DEFAULTS_KEY_HISTORY] = [
        {"text": "текст", "created_at": 42.0},
        "legacy entry",
    ]

    assert history_module.load_history_items() == [
        {"text": "текст", "created_at": 42.0},
        "legacy entry",
    ]
