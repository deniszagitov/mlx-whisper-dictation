# Аудио и микрофон

Исходный файл: `src/audio.py`

Запись звука и работа с устройствами ввода приложения Dictator.

Содержит класс Recorder для записи аудио с микрофона, а также утилиты
для перечисления и отображения устройств ввода.

## Константы

- `LOGGER` = `logging.getLogger(__name__)`
- `PERFORMANCE_MODE_NORMAL` = `'normal'`
- `PERFORMANCE_MODE_FAST` = `'fast'`
- `NORMAL_FRAMES_PER_BUFFER` = `2048`
- `FAST_FRAMES_PER_BUFFER` = `512`

## Классы

## `Recorder`

Записывает звук с микрофона и передает его в распознавание.

Attributes:
    recording: Флаг активной записи.
    transcriber: Объект распознавания, который обрабатывает аудио.

### Методы

#### `__init__`

```python
__init__(transcriber)
```

Создает объект записи.

Args:
    transcriber: Экземпляр SpeechTranscriber для обработки записанного аудио.

#### `set_status_callback`

```python
set_status_callback(status_callback)
```

Регистрирует callback для обновления UI-статуса.

Args:
    status_callback: Функция, принимающая строковый статус.

#### `_set_status`

```python
_set_status(status)
```

_Внутренняя функция._

Передает новый статус во внешний callback.

Args:
    status: Идентификатор состояния приложения.

#### `set_permission_callback`

```python
set_permission_callback(permission_callback)
```

Регистрирует callback для обновления статусов разрешений.

Args:
    permission_callback: Функция, принимающая имя разрешения и его статус.

#### `_set_permission_status`

```python
_set_permission_status(permission_name, status)
```

_Внутренняя функция._

Передает обновленный статус разрешения во внешний callback.

Args:
    permission_name: Имя разрешения.
    status: Булев статус разрешения.

#### `set_input_device`

```python
set_input_device(device_info = None)
```

Сохраняет выбранное устройство ввода для последующей записи.

#### `set_performance_mode`

```python
set_performance_mode(performance_mode)
```

Переключает режим работы записи и связанных подсистем.

#### `start`

```python
start(language = None)
```

Запускает запись в отдельном потоке.

Args:
    language: Необязательный код языка для последующего распознавания.

#### `start_llm`

```python
start_llm(language = None)
```

Запускает запись с последующей обработкой через LLM.

Args:
    language: Необязательный код языка для последующего распознавания.

#### `stop`

```python
stop()
```

Останавливает активную запись.

#### `_begin_request`

```python
_begin_request()
```

_Внутренняя функция._

Регистрирует новый запрос записи и возвращает его идентификатор.

#### `_is_request_current`

```python
_is_request_current(request_id)
```

_Внутренняя функция._

Проверяет, что запрос всё ещё последний и может менять UI/вывод.

#### `_set_status_if_current`

```python
_set_status_if_current(request_id, status)
```

_Внутренняя функция._

Обновляет статус только для актуального запроса.

#### `should_deliver_llm_result`

```python
should_deliver_llm_result(request_id)
```

Разрешает вывод результата LLM только для актуального запроса.

#### `_record_impl`

```python
_record_impl(language, request_id)
```

_Внутренняя функция._

Выполняет запись, конвертацию аудио и запуск распознавания.

Args:
    language: Необязательный код языка для последующего распознавания.

#### `_record_llm_impl`

```python
_record_llm_impl(language, request_id)
```

_Внутренняя функция._

Выполняет запись и передаёт аудио в LLM-пайплайн.

Args:
    language: Необязательный код языка для последующего распознавания.

## Публичные функции

### `microphone_menu_title`

```python
microphone_menu_title(device_info)
```

Формирует подпись микрофона для меню приложения.

### `list_input_devices`

```python
list_input_devices()
```

Возвращает список доступных устройств ввода из PyAudio.
