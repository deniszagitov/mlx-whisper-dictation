# LLM-обработка

Исходный файл: `src/llm.py`

Обработка текста через LLM-модели приложения Dictator.

Содержит LLMProcessor для генерации ответов через MLX LLM
с загрузкой модели по требованию и выгрузкой после использования.

## Константы

- `LOGGER` = `logging.getLogger(__name__)`
- `_THINK_BLOCK_RE` = `re.compile('<think>.*?</think>', re.DOTALL)`
- `_THINK_TAIL_RE` = `re.compile('^.*?</think>', re.DOTALL)`
- `_FINAL_ANSWER_MARKER_RE` = `re.compile('(?:^|\\n)\\s*(?:final answer|answer|ответ)\\s*[:：]\\s*', re.IGNORECASE)`
- `_SECTION_LINE_RE` = `re.compile('^\\s*(?:\\d+\\.\\s*)?(?:[*-]\\s*)?(?P<label>[^:\\n]{1,80}?)\\s*[:：]\\s*(?P<value>.+?)\\s*$', re.IGNORECASE)`
- `_ANSWER_SECTION_LABELS` = `frozenset({'draft', 'final answer', 'answer', 'response', 'черновик', 'определение ответа', 'ответ'})`
- `_STRUCTURED_PREFIX_RE` = `re.compile('^\\s*(?:\\d+\\.|[*#>-]|[-*]\\s)')`
- `PERFORMANCE_MODE_NORMAL` = `'normal'`
- `PERFORMANCE_MODE_FAST` = `'fast'`

## Классы

## `LLMProcessor`

Обрабатывает текст через LLM-модель с загрузкой по требованию.

Загружает модель при первом вызове, генерирует ответ и выгружает
модель из памяти для экономии ресурсов.

Attributes:
    model_name: Имя или путь к модели MLX LLM.
    download_progress_callback: Callback для обновления UI прогресса загрузки.

### Методы

#### `__init__`

```python
__init__(model_name = DEFAULT_LLM_MODEL_NAME)
```

Создаёт LLM-процессор.

Args:
    model_name: Имя модели Hugging Face или локальный путь.

#### `set_performance_mode`

```python
set_performance_mode(performance_mode)
```

Переключает стратегию управления памятью для LLM.

#### `_load_runtime_objects`

```python
_load_runtime_objects()
```

_Внутренняя функция._

Возвращает модель и токенизатор, используя кэш в быстром режиме.

#### `_unload_cached_model`

```python
_unload_cached_model()
```

_Внутренняя функция._

Выгружает LLM-модель и токенизатор из памяти.

#### `is_model_cached`

```python
is_model_cached()
```

Проверяет, скачана ли модель в кэш Hugging Face.

Returns:
    True, если модель уже доступна локально.

#### `ensure_model_downloaded`

```python
ensure_model_downloaded()
```

Скачивает модель в стандартный кэш HuggingFace с отслеживанием прогресса.

Использует ``~/.cache/huggingface/hub/`` — общая директория с Ollama,
transformers и другими библиотеками. Если модель уже скачана,
повторная загрузка не происходит.

#### `_count_tokens`

```python
_count_tokens(tokenizer, text)
```

_Внутренняя функция._

Возвращает количество токенов для текста через tokenizer.encode.

#### `process_text`

```python
process_text(text, system_prompt, *, context = None)
```

Отправляет текст в LLM и возвращает ответ.

Загружает модель, генерирует ответ и выгружает модель из памяти.

Args:
    text: Пользовательский текст (транскрипция).
    system_prompt: Системный промпт для модели.
    context: Необязательный контекст из буфера обмена.

Returns:
    Строка с ответом модели.

Raises:
    Exception: Если модель не удалось загрузить или произошла ошибка генерации.

## Публичные функции

### `strip_think_blocks`

```python
strip_think_blocks(text)
```

Удаляет блоки рассуждений из ответа LLM.

Некоторые модели (Qwen, DeepSeek) генерируют блок рассуждений
внутри тегов <think>...</think>. Обрабатывает три случая:
- Полный блок: <think>рассуждения</think>ответ
- Без открывающего тега: рассуждения</think>ответ
- Незакрытый блок: <think>рассуждения (без </think>)

Args:
    text: Строка с ответом модели.

Returns:
    Текст без блоков рассуждений.

### `sanitize_llm_response`

```python
sanitize_llm_response(text)
```

Возвращает только безопасный финальный текст для UI и вставки.

## Внутренние функции

### `_extract_final_answer_segment`

```python
_extract_final_answer_segment(text)
```

_Внутренняя функция._

Возвращает хвост после последнего маркера финального ответа.

### `_strip_markdown_emphasis`

```python
_strip_markdown_emphasis(text)
```

_Внутренняя функция._

Убирает markdown-обрамление, мешающее распознаванию служебных секций.

### `_extract_answer_section`

```python
_extract_answer_section(text)
```

_Внутренняя функция._

Достаёт payload из строк вида «Черновик: ...» или «Ответ: ...».

### `_is_answer_section_label`

```python
_is_answer_section_label(label)
```

_Внутренняя функция._

Определяет, что метка секции содержит финальный ответ.

### `_is_plain_text_response`

```python
_is_plain_text_response(text)
```

_Внутренняя функция._

Пропускает в UI только простой финальный текст без структурных маркеров.

### `_normalize_response_whitespace`

```python
_normalize_response_whitespace(text)
```

_Внутренняя функция._

Сводит ответ к одной аккуратной строке без лишних пробелов.

### `_truncate_response`

```python
_truncate_response(text, limit = LLM_RESPONSE_CHAR_LIMIT)
```

_Внутренняя функция._

Обрезает ответ до лимита, стараясь сохранить целое предложение.
