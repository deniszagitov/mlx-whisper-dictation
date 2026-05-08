# LLM runtime

Исходный файл: `src/infrastructure/llm_runtime.py`

Runtime-адаптеры для генерации через локальные MLX LLM/VLM.

## Константы

- `LOGGER` = `logging.getLogger(__name__)`
- `PERFORMANCE_MODE_NORMAL` = `'normal'`
- `PERFORMANCE_MODE_FAST` = `'fast'`

## Классы

## `LlmGateway`

Concrete gateway для обработки текста через MLX LLM.

### Методы

#### `__init__`

```python
__init__(model_name: str = Config.DEFAULT_LLM_MODEL_NAME, runtime_loader: Callable[[str], tuple[Any, Any]] | None = None, generation_runner: Callable[[Any, Any, str, int], Any] | None = None, model_cache_checker: Callable[[str], bool] | None = None, model_downloader: Callable[..., None] | None = None, memory_cleanup: Callable[[], None] | None = None, vlm_runtime_loader: Callable[[str], tuple[Any, Any]] | None = None, vlm_generation_runner: Callable[[Any, Any, str, int], Any] | None = None, model_releaser: Callable[[str], None] | None = None, model_preloader: Callable[[str], None] | None = None) -> None
```

Создаёт gateway к LLM runtime.

#### `set_model_memory_loading_callback`

```python
set_model_memory_loading_callback(callback: Callable[[bool, str, str], None] | None) -> None
```

Назначает callback статуса загрузки LLM/VLM в память.

#### `_apply_backend_for_model`

```python
_apply_backend_for_model(model_name: str) -> None
```

_Внутренняя функция._

Выбирает правильный backend (LM или VLM) для модели.

#### `set_performance_mode`

```python
set_performance_mode(performance_mode: str) -> None
```

Переключает стратегию управления памятью для LLM.

#### `_load_runtime_objects`

```python
_load_runtime_objects() -> tuple[Any, Any]
```

_Внутренняя функция._

Возвращает модель и токенизатор через единый runtime-cache.

#### `_emit_model_memory_loading`

```python
_emit_model_memory_loading(active: bool) -> None
```

_Внутренняя функция._

Сообщает управляющему слою, что MLX загружает модель в память.

#### `change_model`

```python
change_model(model_name: str) -> None
```

Переключает LLM-модель и автоматически выбирает backend.

#### `_unload_cached_model`

```python
_unload_cached_model() -> None
```

_Внутренняя функция._

Очищает legacy-ссылки gateway без владения shared runtime-cache.

#### `is_model_cached`

```python
is_model_cached() -> bool
```

Проверяет, скачана ли модель в локальный кэш.

#### `model_download_label`

```python
model_download_label() -> str
```

Возвращает пользовательскую метку текущей модели для общего downloader-а.

#### `ensure_model_downloaded`

```python
ensure_model_downloaded() -> None
```

Скачивает модель в кэш Hugging Face с отслеживанием прогресса.

#### `_count_tokens`

```python
_count_tokens(tokenizer: Any, text: str) -> int
```

_Внутренняя функция._

Возвращает количество токенов для текста через tokenizer.encode.

#### `process_text`

```python
process_text(text: str, system_prompt: str, *, context: str | None = None, max_tokens: int | None = None, sanitize: bool = True, keep_loaded: bool = False) -> str
```

Отправляет текст в LLM и возвращает очищенный ответ.

## Публичные функции

### `load_llm_runtime_objects`

```python
load_llm_runtime_objects(model_name: str) -> tuple[Any, Any]
```

Загружает MLX LLM-модель и токенизатор по имени модели.

### `generate_llm_text`

```python
generate_llm_text(model: Any, tokenizer: Any, prompt: str, max_tokens: int = Config.LLM_MAX_TOKENS) -> str
```

Генерирует текст через загруженные runtime-объекты MLX LLM.

### `load_vlm_runtime_objects`

```python
load_vlm_runtime_objects(model_name: str) -> tuple[Any, Any]
```

Загружает VLM-модель и процессор по имени модели.

### `generate_vlm_text`

```python
generate_vlm_text(model: Any, processor: Any, prompt: str, max_tokens: int = Config.LLM_MAX_TOKENS) -> str
```

Генерирует текст через загруженные runtime-объекты MLX VLM.

### `cleanup_llm_runtime_memory`

```python
cleanup_llm_runtime_memory() -> None
```

Освобождает память после выгрузки LLM-модели.

### `is_llm_model_cached`

```python
is_llm_model_cached(model_name: str) -> bool
```

Проверяет, скачана ли модель в кэш Hugging Face.

### `ensure_llm_model_downloaded`

```python
ensure_llm_model_downloaded(model_name: str, progress_callback: Callable[[str, float, int], None] | None = None) -> None
```

Скачивает модель в кэш Hugging Face с пробросом прогресса в callback.

## Внутренние функции

### `_coerce_generated_text`

```python
_coerce_generated_text(result: Any) -> str
```

_Внутренняя функция._

Достаёт текст из ответа MLX runtime без служебного repr объекта.
