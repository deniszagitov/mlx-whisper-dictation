# LLM runtime

Исходный файл: `src/infrastructure/llm_runtime.py`

Runtime-адаптеры для загрузки, генерации и выгрузки MLX LLM.

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
