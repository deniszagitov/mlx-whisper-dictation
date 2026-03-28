"""Persistence истории распознанного текста через NSUserDefaults."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from Foundation import NSUserDefaults

from ...domain.constants import Config

if TYPE_CHECKING:
    from ...domain.types import HistoryRecord


def load_history_items() -> list[Any]:
    """Читает сырые записи истории из NSUserDefaults."""
    value = NSUserDefaults.standardUserDefaults().objectForKey_(Config.DEFAULTS_KEY_HISTORY)
    if value is None:
        return []
    return list(value)


def save_history_records(records: list[HistoryRecord]) -> None:
    """Сохраняет историю в NSUserDefaults в формате с timestamp."""
    safe_records = [{"text": str(record["text"]), "created_at": float(record["created_at"])} for record in records]
    NSUserDefaults.standardUserDefaults().setObject_forKey_(safe_records, Config.DEFAULTS_KEY_HISTORY)
