# Reader TTS

Исходный файл: `src/use_cases/play_tts.py`

Use case запуска ускоренного TTS из буфера обмена.

## Константы

- `LOGGER` = `logging.getLogger(__name__)`

## Классы

## `PlayTTSUseCase`

Оркестрирует сценарий буфер обмена → LLM → локальное озвучивание.

### Методы

#### `__init__`

```python
__init__(*, clipboard: ReaderClipboardPort, preprocessor: PreprocessTextUseCase, speaker: TTSPort, notify: Notify) -> None
```

Конструктор класса.

#### `toggle`

```python
toggle(config: TTSConfig, *, preprocess_enabled: bool) -> None
```

Запускает TTS или останавливает воспроизведение повторным хоткеем.

#### `play`

```python
play(config: TTSConfig, *, preprocess_enabled: bool) -> None
```

Запускает полный TTS-сценарий для текущего текста в буфере.

#### `stop`

```python
stop() -> None
```

Останавливает TTS, если оно активно.
