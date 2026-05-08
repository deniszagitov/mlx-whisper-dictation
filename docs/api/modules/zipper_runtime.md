# Zipper runtime

Исходный файл: `src/infrastructure/zipper_runtime.py`

Инфраструктурные адаптеры Zipper: память, инструменты, URL и агент.

## Константы

- `LOGGER` = `logging.getLogger(__name__)`
- `_MAX_TOOL_OUTPUT_CHARS` = `8000`
- `_ZIPPER_AGENT_MAX_ITERATIONS` = `4`
- `_ZIPPER_AGENT_MAX_EXECUTION_SECONDS` = `60`
- `_ZIPPER_AGENT_MAX_TOKENS` = `1000`
- `_ZIPPER_MEMORY_SUMMARY_MAX_TOKENS` = `1000`
- `_ZIPPER_RECENT_EVENTS_LIMIT` = `20`
- `_ZIPPER_SYSTEM_MESSAGE` = `'Ты Zipper, локальный голосовой агент Dictator. Выполняй только безопасные действия через доступные инструменты. Отвечай по-русски, кратко и практично.'`
- `_ZIPPER_PROMPT_TEMPLATE` = `'{system_message}\n\nИспользуй только перечисленные инструменты и не выполняй произвольный shell.\nДля финального ответа обязательно добавь строку output_mode: voice|window|both.\nПамять:\n{memory}\n\nПоследние события:\n{events}\n\nДоступные инструменты:\n{tools}\n\nИспользуй формат:\nQuestion: вход\nThought: размышление\nAction: один из [{tool_names}]\nAction Input: аргумент\nObservation: результат\n... при необходимости повтори ...\nFinal Answer: ответ пользователю\noutput_mode: voice|window|both\n\nQuestion: {input}\n{agent_scratchpad}'`
- `_ZIPPER_MEMORY_SUMMARY_PROMPT` = `'Суммаризуй события Zipper в постоянную память. Сохрани важные факты, устойчивые предпочтения, повторяющиеся действия, часто используемые команды и полезные выводы. Не дублируй уже известную память.'`

## Классы

## `FileZipperMemoryStore`

Хранит контекст и постоянную память Zipper в Application Support.

### Методы

#### `__init__`

```python
__init__(path: Path | None = None) -> None
```

Конструктор класса.

#### `load`

```python
load() -> ZipperMemorySnapshot
```

Читает память и события Zipper с диска.

#### `save`

```python
save(snapshot: ZipperMemorySnapshot) -> None
```

Сохраняет память и события Zipper на диск.

## `LangChainZipperAgent`

Весь агент Zipper: prompts, LangChain runtime и tools в одном месте.

### Методы

#### `__init__`

```python
__init__(llm_processor: Any, *, clipboard_service: Any | None = None, text_output: Any | None = None, voice_output: Any | None = None) -> None
```

Конструктор класса.

#### `invoke`

```python
invoke(request: str, *, memory: str, events: tuple[ZipperEvent, ...], config: ZipperConfig, emit_event: _ZipperEventSink | None = None) -> ZipperAgentResult
```

Запускает агентский runtime Zipper через LangChain и настроенные tools.

#### `summarize_memory`

```python
summarize_memory(events_text: str, *, memory: str = '') -> str
```

Суммаризует старые события Zipper в постоянную память через текущую LLM.

#### `_build_tools`

```python
_build_tools(config: ZipperConfig, event: _ZipperEventSink) -> list[Tool]
```

_Внутренняя функция._

Собирает LangChain tools: описание и код каждого tool находятся рядом.

## Внутренние функции

### `_noop_event`

```python
_noop_event(_kind: str, _message: str, _payload: dict[str, Any] | None = None) -> None
```

_Внутренняя функция._

Игнорирует события Zipper в прямых тестах runtime.

### `_trim_tool_output`

```python
_trim_tool_output(text: str) -> str
```

_Внутренняя функция._

Ограничивает слишком длинный вывод инструмента для контекста агента.

### `_await_any`

```python
_await_any(awaitable: Any) -> Any
```

_Внутренняя функция._

Ожидает произвольный awaitable объект MCP-адаптера.
