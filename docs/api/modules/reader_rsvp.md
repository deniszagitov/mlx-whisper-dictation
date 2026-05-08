# Reader RSVP

Исходный файл: `src/use_cases/play_rsvp.py`

Use case запуска RSVP-чтения текста из буфера обмена.

## Константы

- `LOGGER` = `logging.getLogger(__name__)`

## Классы

## `PlayRSVPUseCase`

Оркестрирует сценарий буфер обмена → LLM → RSVP overlay.

### Методы

#### `__init__`

```python
__init__(*, clipboard: ReaderClipboardPort, preprocessor: PreprocessTextUseCase, display: RSVPDisplayPort, notify: Notify) -> None
```

Конструктор класса.

#### `toggle`

```python
toggle(config: RSVPConfig, *, preprocess_enabled: bool) -> None
```

Запускает RSVP или закрывает уже открытый overlay повторным хоткеем.

#### `play`

```python
play(config: RSVPConfig, *, preprocess_enabled: bool) -> None
```

Запускает полный RSVP-сценарий для текущего текста в буфере.
