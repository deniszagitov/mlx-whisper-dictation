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
- `_ZIPPER_DIRECT_OUTPUT_TOOLS` = `{'show_text': 'window', 'speak_text': 'voice'}`
- `_ZIPPER_NO_INPUT_TOOLS` = `frozenset({'get_clipboard', 'current_datetime'})`
- `_ZIPPER_QWEN_MODEL_MARKER` = `'qwen'`
- `_ZIPPER_TOOL_CALL_RE` = `re.compile('<tool_call>\\s*(.*?)\\s*</tool_call>', re.DOTALL | re.IGNORECASE)`
- `_ZIPPER_THINK_RE` = `re.compile('<think>.*?</think>\\s*', re.DOTALL | re.IGNORECASE)`
- `_ZIPPER_FINAL_ANSWER_RE` = `re.compile('Final Answer\\s*:\\s*', re.IGNORECASE)`
- `_ZIPPER_SYSTEM_MESSAGE` = `'Ты Zipper, локальный голосовой агент Dictator. Выполняй только безопасные действия через доступные инструменты. Отвечай по-русски, кратко и практично.'`
- `_ZIPPER_PROMPT_TEMPLATE` = `'{system_message}\n\nИспользуй только перечисленные инструменты и не выполняй произвольный shell.\nДля финального ответа обязательно добавь строку output_mode: voice|window|both.\nПамять:\n{memory}\n\nПоследние события:\n{events}\n\nДоступные инструменты:\n{tools}\n\nИспользуй формат:\nQuestion: вход\nThought: размышление\nAction: один из [{tool_names}]\nAction Input: аргумент\nObservation: результат\n... при необходимости повтори ...\nFinal Answer: ответ пользователю\noutput_mode: voice|window|both\n\nQuestion: {input}\n{agent_scratchpad}'`
- `_ZIPPER_HERMES_PROMPT_TEMPLATE` = `'Работай в режиме function calling.\nЕсли для ответа нужен инструмент, верни только один или несколько блоков вида:\n<tool_call>{{"name": "tool_name", "arguments": {{"input": "аргумент"}}}}</tool_call>\nНе добавляй финальный ответ в то же сообщение, где есть <tool_call>.\nЕсли инструмент не нужен или результат уже получен, ответь пользователю и отдельной строкой добавь output_mode: voice|window|both.\nДля обычного ответа не вызывай show_text или speak_text: выбери output_mode. Эти инструменты используй только когда пользователь явно просит показать или озвучить отдельный текст.\n\nДоступные инструменты в JSON Schema:\n{tools_json}\n\nПоследние события:\n{events}\n\nПредыдущие шаги:\n{scratchpad}\n\nЗапрос пользователя:\n{input}'`
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

Весь агент Zipper: prompts, локальный agent loop и tools в одном месте.

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

Запускает агентский runtime Zipper через подходящий локальный tool-протокол.

#### `summarize_memory`

```python
summarize_memory(events_text: str, *, memory: str = '') -> str
```

Суммаризует старые события Zipper в постоянную память через текущую LLM.

#### `_uses_qwen_tool_protocol`

```python
_uses_qwen_tool_protocol() -> bool
```

_Внутренняя функция._

Определяет, нужна ли Qwen/Hermes-разметка инструментов вместо ReAct.

#### `_process_agent_prompt`

```python
_process_agent_prompt(prompt: str, system_message: str) -> str
```

_Внутренняя функция._

Вызывает локальную LLM для одного шага агентского runtime.

#### `_invoke_hermes`

```python
_invoke_hermes(request: str, *, memory: str, events: tuple[ZipperEvent, ...], tools: list[Tool], event: _ZipperEventSink) -> ZipperAgentResult
```

_Внутренняя функция._

Запускает Qwen-модели через Hermes-style function calling без ReAct stopwords.

#### `_render_hermes_prompt`

```python
_render_hermes_prompt(request: str, *, events: tuple[ZipperEvent, ...], tools: list[Tool], scratchpad: list[str]) -> str
```

_Внутренняя функция._

Рендерит prompt с Hermes-style описанием tools для Qwen.

#### `_hermes_tool_schema`

```python
_hermes_tool_schema(tools: list[Tool]) -> list[dict[str, Any]]
```

_Внутренняя функция._

Преобразует LangChain tools в JSON Schema, понятную Qwen function calling.

#### `_parse_hermes_tool_calls`

```python
_parse_hermes_tool_calls(text: str) -> list[tuple[str, dict[str, Any]]]
```

_Внутренняя функция._

Достаёт Hermes `<tool_call>` блоки из ответа Qwen.

#### `_direct_output_from_tool_calls`

```python
_direct_output_from_tool_calls(tool_calls: list[tuple[str, dict[str, Any]]], event: _ZipperEventSink) -> ZipperAgentResult | None
```

_Внутренняя функция._

Преобразует show_text/speak_text в финальный результат без двойного вывода.

#### `_tool_argument_to_string`

```python
_tool_argument_to_string(arguments: dict[str, Any]) -> str
```

_Внутренняя функция._

Приводит JSON-аргументы Hermes tool call к строке для текущих tools.

#### `_strip_thinking`

```python
_strip_thinking(text: str) -> str
```

_Внутренняя функция._

Удаляет Qwen `<think>` блоки перед парсингом tool calls и финального ответа.

#### `_normalize_final_answer`

```python
_normalize_final_answer(text: str) -> str
```

_Внутренняя функция._

Снимает ReAct-префикс, если локальная модель всё равно его добавила.

#### `_build_tools`

```python
_build_tools(config: ZipperConfig, event: _ZipperEventSink) -> list[Tool]
```

_Внутренняя функция._

Собирает LangChain tools: описание и код каждого tool находятся рядом.

#### `_parse_speak_text_argument`

```python
_parse_speak_text_argument(arg: str) -> str
```

_Внутренняя функция._

Поддерживает plain text и JSON с input для speak_text.

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
