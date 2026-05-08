# Аудио и микрофон

Исходный файл: `src/infrastructure/audio_runtime.py`

Runtime-запись звука и перечисление устройств ввода через PyAudio.

## Константы

- `LOGGER` = `logging.getLogger(__name__)`
- `PERFORMANCE_MODE_NORMAL` = `'normal'`
- `PERFORMANCE_MODE_FAST` = `'fast'`
- `NORMAL_FRAMES_PER_BUFFER` = `2048`
- `FAST_FRAMES_PER_BUFFER` = `512`
- `DEFAULT_SAMPLE_RATE` = `16000`
- `DEFAULT_CHANNELS` = `1`
- `RETRYABLE_AUDIO_ERROR_CODES` = `{-9998, -9996}`
- `PERMISSION_ERROR_CODES` = `{-9996}`

## Классы

## `_StreamCandidate`

Кандидат формата открытия PyAudio stream.

## `_OpenedStream`

Открытый PyAudio stream с фактическими параметрами записи.

## `Recorder`

Записывает звук с микрофона.

### Методы

#### `__init__`

```python
__init__() -> None
```

Создает объект записи.

#### `set_status_callback`

```python
set_status_callback(status_callback: Callable[[str], None]) -> None
```

Регистрирует callback для обновления UI-статуса.

#### `_set_status`

```python
_set_status(status: str) -> None
```

_Внутренняя функция._

Передает новый статус во внешний callback.

#### `set_permission_callback`

```python
set_permission_callback(permission_callback: Callable[[str, bool], None]) -> None
```

Регистрирует callback для обновления статусов разрешений.

#### `_set_permission_status`

```python
_set_permission_status(permission_name: str, status: bool) -> None
```

_Внутренняя функция._

Передает обновленный статус разрешения во внешний callback.

#### `set_error_callback`

```python
set_error_callback(error_callback: Callable[[str, str], None]) -> None
```

Регистрирует callback уведомления о runtime-ошибках записи.

#### `_notify_error`

```python
_notify_error(title: str, message: str) -> None
```

_Внутренняя функция._

Уведомляет внешний слой о runtime-ошибке записи.

#### `set_runtime_error_callback`

```python
set_runtime_error_callback(runtime_error_callback: Callable[[str, str], None]) -> None
```

Регистрирует callback для восстановления runtime-состояния после ошибки записи.

#### `_notify_runtime_error`

```python
_notify_runtime_error(title: str, message: str) -> None
```

_Внутренняя функция._

Уведомляет orchestration-слой о необходимости сбросить состояние записи.

#### `set_input_device`

```python
set_input_device(device_info: AudioDeviceInfo | None = None) -> None
```

Сохраняет выбранное устройство ввода для последующей записи.

#### `set_high_quality_mac_builtin`

```python
set_high_quality_mac_builtin(enabled: object) -> None
```

Переключает автоматический MacBook HQ-профиль записи.

#### `set_post_roll_ms`

```python
set_post_roll_ms(post_roll_ms: object) -> None
```

Сохраняет длительность хвоста записи после stop().

#### `set_performance_mode`

```python
set_performance_mode(performance_mode: str) -> None
```

Переключает режим работы записи и связанных подсистем.

#### `start`

```python
start(language: str | None = None, on_audio_ready: Callable[..., None] | None = None) -> None
```

Запускает запись в отдельном потоке.

#### `stop`

```python
stop() -> None
```

Останавливает активную запись.

#### `cancel`

```python
cancel() -> None
```

Отменяет запись без последующего распознавания.

#### `_begin_request`

```python
_begin_request() -> int
```

_Внутренняя функция._

Регистрирует новый запрос записи и возвращает его идентификатор.

#### `_is_request_current`

```python
_is_request_current(request_id: int) -> bool
```

_Внутренняя функция._

Проверяет, что запрос всё ещё последний и может менять UI/вывод.

#### `_set_status_if_current`

```python
_set_status_if_current(request_id: int, status: str) -> None
```

_Внутренняя функция._

Обновляет статус только для актуального запроса.

#### `_audio_error_code`

```python
_audio_error_code(error: BaseException) -> int | None
```

_Внутренняя функция._

Извлекает числовой код ошибки PortAudio/PyAudio, если он доступен.

#### `_should_retry_with_default_device`

```python
_should_retry_with_default_device(error: BaseException) -> bool
```

_Внутренняя функция._

Определяет, стоит ли повторить открытие потока через default input device.

#### `_current_device_info`

```python
_current_device_info() -> AudioDeviceInfo | None
```

_Внутренняя функция._

Возвращает текущие параметры выбранного устройства ввода.

#### `_current_audio_profile`

```python
_current_audio_profile() -> str
```

_Внутренняя функция._

Выбирает аудиопрофиль для следующей записи.

#### `_stream_candidates`

```python
_stream_candidates(profile_name: str) -> list[_StreamCandidate]
```

_Внутренняя функция._

Возвращает порядок форматов открытия stream.

#### `_can_open_stream`

```python
_can_open_stream(audio_interface: pyaudio.PyAudio, *, device_index: int | None, candidate: _StreamCandidate) -> bool
```

_Внутренняя функция._

Проверяет поддержку текущего аудиоформата до открытия stream.

#### `_open_candidate`

```python
_open_candidate(audio_interface: pyaudio.PyAudio, *, device_index: int | None, frames_per_buffer: int, candidate: _StreamCandidate, profile_name: str) -> _OpenedStream
```

_Внутренняя функция._

Открывает stream с одним набором параметров.

#### `_open_stream`

```python
_open_stream(audio_interface: pyaudio.PyAudio, *, frames_per_buffer: int) -> _OpenedStream
```

_Внутренняя функция._

Открывает поток записи, при необходимости повторяя попытку через default input.

#### `_record_impl`

```python
_record_impl(language: str | None, request_id: int, on_audio_ready: Callable[..., None] | None = None) -> None
```

_Внутренняя функция._

Выполняет запись, конвертацию аудио и запуск распознавания.

## Публичные функции

### `list_input_devices`

```python
list_input_devices() -> list[AudioDeviceInfo]
```

Возвращает список доступных устройств ввода из PyAudio.
