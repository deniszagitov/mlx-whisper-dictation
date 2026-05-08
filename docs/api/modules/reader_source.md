# Reader source

Исходный файл: `src/use_cases/reader_source.py`

Общие правила чтения источника reader-сценариев из буфера обмена.

## Публичные функции

### `read_reader_source`

```python
read_reader_source(clipboard: ReaderClipboardPort, notify: Notify) -> ReaderSourceText | None
```

Читает и валидирует текст из буфера обмена для reader-сценария.
