# Zipper runtime

Исходный файл: `src/infrastructure/zipper_runtime.py`

Инфраструктурные адаптеры Zipper: память, инструменты, URL и агент.

## Константы

- `LOGGER` = `logging.getLogger(__name__)`
- `_ZIPPER_AGENT_MAX_ITERATIONS` = `4`
- `_ZIPPER_AGENT_MAX_EXECUTION_SECONDS` = `60`

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

## `ZipperUrlOpener`

Открывает URL в браузере по умолчанию.

### Методы

#### `open_url`

```python
open_url(url: str) -> bool
```

Открывает URL через стандартный браузер.

## `ZipperCommandRunner`

Запускает только команды, явно описанные в конфиге Zipper.

### Методы

#### `run`

```python
run(command: ZipperCliCommand, _argument: str = '') -> str
```

Выполняет разрешённую команду без shell.

## `ZipperCustomToolRunner`

Выполняет простые пользовательские инструменты из конфига.

### Методы

#### `run`

```python
run(tool: ZipperCustomTool, argument: str = '') -> str
```

Выполняет пользовательский инструмент по его kind.

## `ZipperMCPToolProvider`

Подключает MCP-инструменты из конфига, если доступен langchain-mcp-adapters.

### Методы

#### `tools_for_config`

```python
tools_for_config(config: ZipperConfig) -> tuple[list[ZipperToolSpec], list[str]]
```

Возвращает MCP-инструменты и список ошибок подключения.

## `LangChainZipperAgent`

LangChain-агент Zipper поверх текущего локального MLX LLM gateway.

### Методы

#### `__init__`

```python
__init__(llm_processor: Any) -> None
```

Конструктор класса.

#### `invoke`

```python
invoke(request: str, *, system_message: str, memory: str, events: tuple[ZipperEvent, ...], tools: list[ZipperToolSpec], config: ZipperConfig) -> ZipperAgentResult
```

Запускает LangChain ReAct agent или безопасный fallback без произвольных команд.

## Внутренние функции

### `_await_any`

```python
_await_any(awaitable: Any) -> Any
```

_Внутренняя функция._

Ожидает произвольный awaitable объект MCP-адаптера.
