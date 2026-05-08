# LLM-обработка

Исходный файл: `src/use_cases/llm_pipeline.py`

Use case-сценарии LLM-пайплайна и загрузки модели.

## Константы

- `LOGGER` = `logging.getLogger(__name__)`

## Классы

## `LlmPipelineUseCases`

Оркестрирует сценарий запись → Whisper → LLM.

### Методы

#### `__init__`

```python
__init__(runtime: Any, recorder: Any, transcriber: Any, llm_processor: Any, clipboard_service: Any, system_integration_service: Any, recording_overlay: Any, stop_recording: Any, publish_snapshot: Any, obsidian_service: Any | None = None) -> None
```

Конструктор класса.

#### `toggle_llm`

```python
toggle_llm() -> None
```

Переключает сценарий запись → Whisper → LLM.

#### `is_model_cached`

```python
is_model_cached() -> bool
```

Проверяет, что LLM-модель уже доступна локально.

#### `download_llm_model`

```python
download_llm_model() -> None
```

Запускает загрузку LLM-модели и публикует прогресс.

## Внутренние функции

### `_prevent_display_sleep`

```python
_prevent_display_sleep(runtime: Any) -> None
```

_Внутренняя функция._

Включает временную защиту дисплея от сна, если runtime её поддерживает.

### `_release_display_sleep`

```python
_release_display_sleep(runtime: Any) -> None
```

_Внутренняя функция._

Отпускает временную защиту дисплея от сна, если runtime её поддерживает.
