# Zipper use case

Исходный файл: `src/use_cases/zipper.py`

Use case-сценарии голосового агента Zipper.

## Константы

- `LOGGER` = `logging.getLogger(__name__)`
- `_KEYCODE_ESCAPE` = `53`
- `_MAX_TOOL_OUTPUT_CHARS` = `8000`
- `_MEMORY_SUMMARY_KEEP_EVENTS` = `40`

## Классы

## `ZipperUseCases`

Оркестрирует голосовой сценарий Zipper и инструменты агента.

### Свойства

#### `config`

```python
config() -> ZipperConfig
```

Возвращает текущий конфиг Zipper.

### Методы

#### `__init__`

```python
__init__(runtime: Any, recorder: Any, transcriber: Any, llm_processor: Any, config_provider: Any, memory_store: Any, agent_service: Any, clipboard_service: Any, text_output: Any, voice_output: Any, url_opener: Any, command_runner: Any, custom_tool_runner: Any, mcp_tool_provider: Any, system_integration_service: Any, recording_overlay: Any, publish_snapshot: Any) -> None
```

Конструктор класса.

#### `reload_config`

```python
reload_config() -> None
```

Перечитывает конфиг Zipper и обновляет состояние debug-панели.

#### `open_config`

```python
open_config() -> None
```

Открывает пользовательский конфиг Zipper.

#### `toggle_enabled`

```python
toggle_enabled() -> None
```

Включает или выключает Zipper в runtime.

#### `toggle_debug_panel`

```python
toggle_debug_panel() -> None
```

Включает или выключает debug-панель Zipper.

#### `clear_context`

```python
clear_context() -> None
```

Очищает текущий контекст Zipper, не трогая постоянную память.

#### `clear_memory`

```python
clear_memory() -> None
```

Очищает постоянную память Zipper, не трогая текущий контекст.

#### `toggle`

```python
toggle() -> None
```

Переключает сценарий записи голосовой команды Zipper.

#### `start_recording`

```python
start_recording() -> None
```

Запускает запись голосовой команды Zipper.

#### `stop_recording`

```python
stop_recording() -> None
```

Останавливает запись Zipper и запускает распознавание.

#### `cancel_recording`

```python
cancel_recording() -> None
```

Отменяет активную запись команды Zipper.

#### `handle_escape_keycode`

```python
handle_escape_keycode(keycode: int) -> bool
```

Обрабатывает Escape для активной записи Zipper.

#### `on_status_tick`

```python
on_status_tick() -> None
```

Обновляет длительность записи Zipper и применяет общий max_time.

#### `_on_audio_ready`

```python
_on_audio_ready(audio_data: Any, language: str | None, _set_status: Any, is_current: Any) -> None
```

_Внутренняя функция._

Распознаёт голосовую команду и передаёт её агенту.

#### `_download_required_model`

```python
_download_required_model(requirement: ModelRequiredError) -> None
```

_Внутренняя функция._

Делегирует загрузку модели управляющему runtime вне контекста агента.

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

### `_tool_name`

```python
_tool_name(prefix: str, raw_name: str) -> str
```

_Внутренняя функция._

Нормализует имя инструмента под ограничения LangChain.

### `_trim_tool_output`

```python
_trim_tool_output(text: str) -> str
```

_Внутренняя функция._

Ограничивает слишком длинный вывод инструмента для контекста агента.
