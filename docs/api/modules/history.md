# История распознавания

Исходный файл: `src/infrastructure/persistence/history.py`

Persistence истории распознанного текста через NSUserDefaults.

## Публичные функции

### `load_history_items`

```python
load_history_items() -> list[Any]
```

Читает сырые записи истории из NSUserDefaults.

### `save_history_records`

```python
save_history_records(records: list[HistoryRecord]) -> None
```

Сохраняет историю в NSUserDefaults в формате с timestamp.
