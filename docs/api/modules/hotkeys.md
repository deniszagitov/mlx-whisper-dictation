# Глобальные хоткеи

Исходный файл: `src/infrastructure/hotkeys.py`

Горячие клавиши и единый keyboard dispatcher приложения Dictator.

## Константы

- `LOGGER` = `logging.getLogger(__name__)`
- `MODIFIER_KEYCODES_MAP` = `{54: 'cmd_r', 55: 'cmd_l', 56: 'shift_l', 58: 'alt_l', 59: 'ctrl_l', 60: 'shift_r', 61: 'alt_r', 62: 'ctrl_r'}`
- `MODIFIER_FLAG_MASKS` = `{'alt_l': 524288, 'alt_r': 524288, 'ctrl_l': 262144, 'ctrl_r': 262144, 'shift_l': 131072, 'shift_r': 131072, 'cmd_l': 1048576, 'cmd_r': 1048576}`
- `_KEYCODE_ESCAPE` = `53`
- `NAMED_KEYCODES_MAP` = `{36: 'enter', 48: 'tab', 49: 'space', 51: 'backspace', _KEYCODE_ESCAPE: 'esc', 123: 'left', 124: 'right', 125: 'down', 126: 'up'}`
- `_UC_KEY_ACTION_DOWN` = `0`
- `_UC_KEY_TRANSLATE_NO_DEAD_KEYS_BIT` = `2`

## Классы

## `_HotkeyBinding`

Скомпилированное правило хоткея для dispatcher-а.

## `HotkeyDispatcher`

Единая точка обработки primary/secondary/LLM хоткеев и Escape.

### Методы

#### `__init__`

```python
__init__(app: Any) -> None
```

Конструктор класса.

#### `start`

```python
start() -> None
```

Запускает единый CGEventTap без leaky-fallback режима.

#### `stop`

```python
stop() -> None
```

Останавливает единый keyboard dispatcher.

#### `on_system_wake`

```python
on_system_wake() -> None
```

Восстанавливает CGEventTap после выхода системы из sleep.

#### `update_hotkeys`

```python
update_hotkeys(primary: str, secondary: str, llm: str, rsvp: str = '', tts: str = '', zipper: str = '') -> None
```

Обновляет набор активных хоткеев без пересоздания dispatcher-а.

#### `_invoke_binding_callback`

```python
_invoke_binding_callback(binding: _HotkeyBinding) -> None
```

_Внутренняя функция._

Логирует и вызывает callback хоткея с защитой от тихих падений.

#### `_has_regular_extension`

```python
_has_regular_extension(modifier_binding: _HotkeyBinding) -> bool
```

_Внутренняя функция._

Проверяет, есть ли обычный хоткей с теми же модификаторами.

#### `_sync_modifier_state_from_event`

```python
_sync_modifier_state_from_event(event: Any) -> None
```

_Внутренняя функция._

Удаляет из runtime-state модификаторы, которых уже нет в текущем event.

## `GlobalKeyListener`

Совместимый single-hotkey listener для unit-тестов.

### Методы

#### `__init__`

```python
__init__(app: ToggleableApp, key_combination: str, callback: Any | None = None) -> None
```

Конструктор класса.

#### `start`

```python
start() -> None
```

Совместимый no-op запуск listener-а.

#### `stop`

```python
stop() -> None
```

Совместимая no-op остановка listener-а.

#### `update_key_combination`

```python
update_key_combination(key_combination: str) -> None
```

Обновляет одну тестовую комбинацию без системной регистрации.

## `MultiHotkeyListener`

Совместимый multi-listener для unit-тестов.

### Методы

#### `__init__`

```python
__init__(app: ToggleableApp, key_combinations: list[str]) -> None
```

Конструктор класса.

#### `start`

```python
start() -> None
```

Совместимо запускает вложенные listener-ы.

#### `stop`

```python
stop() -> None
```

Совместимо останавливает вложенные listener-ы.

#### `update_key_combinations`

```python
update_key_combinations(key_combinations: list[str]) -> None
```

Пересобирает тестовый набор вложенных listener-ов.

#### `on_system_wake`

```python
on_system_wake() -> None
```

Перезапускает тестовые listener-ы после выхода системы из sleep.

## Публичные функции

### `parse_key`

```python
parse_key(key_name: str) -> str
```

Возвращает нормализованное строковое имя клавиши.

### `parse_key_combination`

```python
parse_key_combination(key_combination: str) -> tuple[str, ...]
```

Разбирает строку с комбинацией клавиш в tuple имён.

## Внутренние функции

### `_keycode_to_char`

```python
_keycode_to_char(keycode: int) -> str | None
```

_Внутренняя функция._

Преобразует виртуальный keycode в символ через ASCII-совместимую раскладку.

### `_event_key_name_static`

```python
_event_key_name_static(event: Any) -> str
```

_Внутренняя функция._

Извлекает имя обычной клавиши из NSEvent.
