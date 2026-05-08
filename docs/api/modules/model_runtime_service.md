# Model runtime service

Исходный файл: `src/infrastructure/model_runtime_service.py`

Единый runtime-сервис загруженных MLX-моделей.

## Константы

- `LOGGER` = `logging.getLogger(__name__)`
- `BACKEND_LM` = `'lm'`
- `BACKEND_VLM` = `'vlm'`
- `BACKEND_QWEN_ASR` = `'qwen-asr'`
- `BACKEND_MLX_TTS` = `'mlx-tts'`
- `BACKEND_WHISPER` = `'whisper'`
- `_VLM_MODEL_INDICATORS` = `('gemma-4', 'gemma4', '-vlm', 'vision')`
- `_BACKEND_LABELS` = `{BACKEND_LM: 'LLM-модель', BACKEND_VLM: 'VLM-модель', BACKEND_QWEN_ASR: 'ASR-модель', BACKEND_MLX_TTS: 'TTS-модель', BACKEND_WHISPER: 'ASR-модель'}`

## Классы

## `ModelRuntimeKey`

Ключ runtime-экземпляра модели: backend плюс исходный model_id.

## `_InflightLoad`

Состояние single-flight загрузки модели.

## `ModelRuntimeService`

Хранит загруженные MLX runtime-объекты и объединяет параллельные загрузки.

### Методы

#### `__init__`

```python
__init__(*, lm_loader: Callable[[str], tuple[Any, Any]] | None = None, vlm_loader: Callable[[str], tuple[Any, Any]] | None = None, qwen_asr_loader: Callable[[str], Any] | None = None, mlx_tts_loader: Callable[[str], Any] | None = None, whisper_loader: Callable[[str], Any] | None = None, memory_cleanup: Callable[[], None] | None = None, model_memory_loading_callback: Callable[[bool, str, str], None] | None = None) -> None
```

Конструктор класса.

#### `set_model_memory_loading_callback`

```python
set_model_memory_loading_callback(callback: Callable[[bool, str, str], None] | None) -> None
```

Назначает callback фактической загрузки runtime-модели в память.

#### `get_lm`

```python
get_lm(model_id: str) -> tuple[Any, Any]
```

Возвращает загруженную LM-модель и tokenizer через общий cache.

#### `get_vlm`

```python
get_vlm(model_id: str) -> tuple[Any, Any]
```

Возвращает загруженную VLM-модель и processor через общий cache.

#### `get_qwen_asr`

```python
get_qwen_asr(model_id: str) -> Any
```

Возвращает загруженную Qwen3-ASR модель через общий cache.

#### `get_mlx_tts`

```python
get_mlx_tts(model_id: str) -> Any
```

Возвращает загруженную MLX TTS-модель через общий cache.

#### `get_whisper`

```python
get_whisper(model_id: str) -> Any
```

Возвращает загруженную Whisper-модель и подготавливает ModelHolder.

#### `preload_selected_models`

```python
preload_selected_models(*, asr_model: str | None = None, llm_model: str | None = None, tts_model: str | None = None, wait: bool = False) -> list[threading.Thread]
```

Запускает прогрев выбранных ASR, LLM/VLM и MLX TTS моделей.

#### `preload_model`

```python
preload_model(model_id: str, *, label: str, loader: Callable[[str], Any]) -> threading.Thread
```

Запускает фоновый прогрев одной модели и не пробрасывает ошибку в UI-поток.

#### `preload_asr_model`

```python
preload_asr_model(model_id: str) -> threading.Thread
```

Запускает фоновый прогрев выбранной ASR-модели.

#### `preload_llm_model`

```python
preload_llm_model(model_id: str) -> threading.Thread
```

Запускает фоновый прогрев выбранной LLM/VLM-модели.

#### `preload_tts_model`

```python
preload_tts_model(model_id: str) -> threading.Thread
```

Запускает фоновый прогрев выбранной MLX TTS-модели.

#### `release_model`

```python
release_model(model_id: str) -> None
```

Освобождает все runtime-экземпляры указанного model_id.

#### `shutdown`

```python
shutdown() -> None
```

Очищает runtime-cache всех моделей при завершении приложения.

#### `_get_or_load`

```python
_get_or_load(key: ModelRuntimeKey, loader: Callable[[str], Any]) -> Any
```

_Внутренняя функция._

Возвращает модель из cache или ждёт единственную текущую загрузку.

#### `_emit_model_memory_loading`

```python
_emit_model_memory_loading(active: bool, key: ModelRuntimeKey) -> None
```

_Внутренняя функция._

Публикует статус только для фактической загрузки runtime-модели.

## Публичные функции

### `is_vlm_model`

```python
is_vlm_model(model_name: str) -> bool
```

Определяет, нужен ли mlx_vlm для данной LLM-модели.

### `is_qwen_asr_model_name`

```python
is_qwen_asr_model_name(model_name: str) -> bool
```

Определяет, что ASR-модель должна идти через mlx-audio Qwen backend.

## Внутренние функции

### `_default_memory_cleanup`

```python
_default_memory_cleanup() -> None
```

_Внутренняя функция._

Очищает Python и MLX cache после выгрузки runtime-моделей.

### `_default_lm_loader`

```python
_default_lm_loader(model_name: str) -> tuple[Any, Any]
```

_Внутренняя функция._

Загружает MLX LM-модель напрямую через mlx-lm.

### `_default_vlm_loader`

```python
_default_vlm_loader(model_name: str) -> tuple[Any, Any]
```

_Внутренняя функция._

Загружает VLM-модель напрямую через mlx-vlm.

### `_default_qwen_asr_loader`

```python
_default_qwen_asr_loader(model_name: str) -> Any
```

_Внутренняя функция._

Загружает Qwen3-ASR модель напрямую через mlx-audio.

### `_default_mlx_tts_loader`

```python
_default_mlx_tts_loader(model_name: str) -> Any
```

_Внутренняя функция._

Загружает streaming MLX TTS-модель напрямую через mlx-audio.

### `_set_whisper_model_holder`

```python
_set_whisper_model_holder(model_path: str, model: Any) -> None
```

_Внутренняя функция._

Заполняет singleton ModelHolder библиотеки mlx_whisper.

### `_default_whisper_loader`

```python
_default_whisper_loader(model_name: str) -> Any
```

_Внутренняя функция._

Загружает Whisper-модель и регистрирует её в ModelHolder.
