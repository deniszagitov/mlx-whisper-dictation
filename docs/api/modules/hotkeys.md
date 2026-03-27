# Глобальные хоткеи

Исходный файл: `src/hotkeys.py`

Горячие клавиши и слушатели клавиатуры приложения Dictator.

Парсинг комбинаций клавиш, глобальные мониторы нажатий через AppKit,
режим двойного нажатия Command и модальный захват хоткея.

## Константы

- `LOGGER` = `logging.getLogger(__name__)`
- `KEY_NAME_ALIASES` = `{'ctrl': 'ctrl', 'control': 'ctrl', 'alt': 'alt', 'option': 'alt', 'opt': 'alt', 'shift': 'shift', 'cmd': 'cmd', 'command': 'cmd', 'meta': 'cmd', 'super': 'cmd'}`
- `MODIFIER_KEYCODES_MAP` = `{54: 'cmd_r', 55: 'cmd_l', 56: 'shift_l', 58: 'alt_l', 59: 'ctrl_l', 60: 'shift_r', 61: 'alt_r', 62: 'ctrl_r'}`
- `MODIFIER_FLAG_MASKS` = `{'alt_l': 524288, 'alt_r': 524288, 'ctrl_l': 262144, 'ctrl_r': 262144, 'shift_l': 131072, 'shift_r': 131072, 'cmd_l': 1048576, 'cmd_r': 1048576}`
- `NAMED_KEYCODES_MAP` = `{36: 'enter', 48: 'tab', 49: 'space', 51: 'backspace', 53: 'esc'}`
- `MODIFIER_DISPLAY_ORDER` = `['ctrl', 'ctrl_l', 'ctrl_r', 'alt', 'alt_l', 'alt_r', 'shift', 'shift_l', 'shift_r', 'cmd', 'cmd_l', 'cmd_r']`

## Классы

## `GlobalKeyListener`

Обрабатывает глобальную комбинацию клавиш для запуска диктовки.

Attributes:
    app: Экземпляр StatusBarApp, которым управляет listener.
    keys: Кортеж клавиш, которые образуют хоткей.
    pressed_keys: Набор клавиш, зажатых в текущий момент.
    triggered: Флаг, защищающий от повторного срабатывания при удержании.

### Методы

#### `__init__`

```python
__init__(app, key_combination, callback = None)
```

Создает listener для заданной комбинации клавиш.

Args:
    app: Экземпляр приложения, у которого будет вызван toggle.
    key_combination: Строка с комбинацией клавиш.
    callback: Функция, вызываемая при срабатывании. По умолчанию app.toggle.

#### `stop`

```python
stop()
```

Удаляет глобальные мониторы событий клавиатуры.

#### `update_key_combination`

```python
update_key_combination(key_combination)
```

Обновляет комбинацию клавиш без пересоздания listener.

#### `start`

```python
start()
```

Запускает глобальный монитор событий клавиатуры через AppKit.

#### `_required_modifiers_are_pressed`

```python
_required_modifiers_are_pressed()
```

_Внутренняя функция._

Проверяет, зажаты ли нужные modifier-клавиши.

#### `_event_is_modifier_pressed`

```python
_event_is_modifier_pressed(event, modifier_name)
```

_Внутренняя функция._

Определяет, находится ли modifier в нажатом состоянии для flagsChanged-события.

Args:
    event: Системное NSEvent.
    modifier_name: Имя modifier-клавиши.

Returns:
    True, если соответствующий modifier сейчас зажат.

#### `_handle_flags_changed`

```python
_handle_flags_changed(event)
```

_Внутренняя функция._

Обрабатывает глобальные изменения modifier-клавиш.

Args:
    event: Системное NSEvent.

#### `_event_key_name`

```python
_event_key_name(event)
```

_Внутренняя функция._

Преобразует NSEvent в строковое имя клавиши.

#### `_handle_key_down`

```python
_handle_key_down(event)
```

_Внутренняя функция._

Обрабатывает глобальные события обычных клавиш.

Args:
    event: Системное NSEvent.

## `MultiHotkeyListener`

Управляет несколькими глобальными хоткеями одновременно.

### Методы

#### `__init__`

```python
__init__(app, key_combinations)
```

Создает набор listener-ов для списка комбинаций клавиш.

#### `start`

```python
start()
```

Запускает все глобальные listener-ы.

#### `stop`

```python
stop()
```

Останавливает все глобальные listener-ы.

#### `_build_listeners`

```python
_build_listeners(key_combinations)
```

_Внутренняя функция._

Нормализует комбинации и создаёт listener-ы без запуска.

#### `update_key_combinations`

```python
update_key_combinations(key_combinations)
```

Пересоздает listener-ы для нового списка комбинаций и запускает их.

## `DoubleCommandKeyListener`

Обрабатывает режим управления через правую клавишу Command.

Attributes:
    app: Экземпляр приложения, у которого будет вызван toggle.
    key: Клавиша, используемая для переключения записи.
    last_press_time: Время предыдущего нажатия для определения двойного клика.

### Методы

#### `__init__`

```python
__init__(app)
```

Создает listener для режима двойного нажатия Command.

Args:
    app: Экземпляр приложения, у которого будет вызван toggle.

#### `on_key_press`

```python
on_key_press(key)
```

Обрабатывает нажатие правой клавиши Command.

Args:
    key: Объект клавиши из pynput.

#### `on_key_release`

```python
on_key_release(key)
```

Игнорирует отпускание клавиши в этом режиме.

Args:
    key: Объект клавиши из pynput.

## Публичные функции

### `normalize_key_name`

```python
normalize_key_name(raw_name)
```

Нормализует имя клавиши к каноническому виду.

Поддерживает человекочитаемые алиасы (Ctrl, Control, Option, Command)
и приводит регистр к нижнему.

Args:
    raw_name: Строковое имя клавиши, например `Ctrl`, `cmd_l` или `T`.

Returns:
    Нормализованное имя клавиши.

### `parse_key`

```python
parse_key(key_name)
```

Преобразует строковое имя клавиши в объект pynput.

Args:
    key_name: Имя клавиши, например `cmd_l`, `alt` или `space`.

Returns:
    Объект клавиши или код символа, который понимает pynput.

### `normalize_key_combination`

```python
normalize_key_combination(key_combination)
```

Нормализует строку комбинации клавиш к внутреннему формату.

Args:
    key_combination: Строка вида `cmd_l+alt` или `Command+Option+space`.

Returns:
    Нормализованная строка комбинации клавиш.

Raises:
    ValueError: Если в комбинации меньше двух клавиш.

### `parse_key_combination`

```python
parse_key_combination(key_combination)
```

Разбирает строку с комбинацией клавиш.

Args:
    key_combination: Строка вида `cmd_l+alt`, `ctrl+shift+alt+t`
        или `Ctrl+Shift+Alt+T`.

Returns:
    Кортеж объектов клавиш в том порядке, в котором они указаны.

Raises:
    ValueError: Если в комбинации меньше двух клавиш.

### `hotkey_name_matches`

```python
hotkey_name_matches(expected_name, actual_name)
```

Проверяет, считаются ли два строковых имени клавиш эквивалентными.

Args:
    expected_name: Имя клавиши из конфигурации хоткея.
    actual_name: Имя клавиши, полученное из системного события.

Returns:
    True, если клавиши эквивалентны.

### `format_hotkey_status`

```python
format_hotkey_status(key_combination = None, *, use_double_cmd = False)
```

Преобразует настройку хоткея в строку для меню.

Args:
    key_combination: Строка комбинации клавиш.
    use_double_cmd: Флаг режима двойного нажатия правой Command.

Returns:
    Человекочитаемая строка хоткея.

### `capture_hotkey_combination`

```python
capture_hotkey_combination(title, message, current_combination = '')
```

Открывает модальное окно для захвата комбинации клавиш по нажатию.

Показывает NSAlert с текстовым полем, которое отображает текущую
комбинацию по мере нажатия клавиш. Пользователь нажимает модификаторы
и обычную клавишу, комбинация фиксируется и показывается в поле.

Args:
    title: Заголовок диалогового окна.
    message: Подсказка для пользователя.
    current_combination: Текущая комбинация для отображения по умолчанию.

Returns:
    Нормализованную строку комбинации клавиш или None, если отменено.

## Внутренние функции

### `_event_key_name_static`

```python
_event_key_name_static(event)
```

_Внутренняя функция._

Извлекает имя обычной клавиши из NSEvent.
