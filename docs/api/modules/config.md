# Domain и настройки

Исходный файл: `src/domain/constants.py`

Чистые константы и helper-функции приложения Dictator.

## Классы

## `Config`

Константы и пресеты приложения Dictator.

### Методы

#### `format_max_time_status`

```python
format_max_time_status(max_time: int | float | None) -> str
```

Преобразует лимит длительности записи в строку для меню.

#### `performance_mode_label`

```python
performance_mode_label(performance_mode: str) -> str
```

Возвращает человекочитаемое имя режима работы.

#### `normalize_performance_mode`

```python
normalize_performance_mode(performance_mode: object) -> str
```

Нормализует идентификатор режима работы.

#### `audio_profile_label`

```python
audio_profile_label(profile_name: str) -> str
```

Возвращает человекочитаемую подпись аудиопрофиля.
