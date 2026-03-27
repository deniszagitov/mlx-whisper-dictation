# Диагностика

Исходный файл: `src/diagnostics.py`

Логирование и диагностика приложения Dictator.

Содержит настройку логирования, фильтры, хранилище диагностических
артефактов и функцию проверки галлюцинаций Whisper.

## Классы

## `MaxLevelFilter`

Пропускает записи не выше заданного уровня логирования.

### Методы

#### `__init__`

```python
__init__(level)
```

Сохраняет максимальный уровень логов для фильтрации.

#### `filter`

```python
filter(record)
```

Возвращает True, если запись не превышает допустимый уровень.

## `DiagnosticsStore`

Изолирует сохранение диагностических артефактов от основного runtime-кода.

### Свойства

#### `recordings_dir`

```python
recordings_dir()
```

Возвращает путь к папке с диагностическими аудиозаписями.

#### `transcriptions_dir`

```python
transcriptions_dir()
```

Возвращает путь к папке с диагностическими транскрипциями.

### Методы

#### `__init__`

```python
__init__(root_dir = LOG_DIR, enabled = True, max_artifacts = MAX_DEBUG_ARTIFACTS)
```

Создает хранилище диагностических файлов.

Args:
    root_dir: Корневая директория логов и артефактов.
    enabled: Нужно ли сохранять диагностические файлы.
    max_artifacts: Сколько последних наборов артефактов хранить.

#### `artifact_stem`

```python
artifact_stem()
```

Возвращает уникальное имя группы диагностических файлов.

#### `_cleanup_directory`

```python
_cleanup_directory(directory)
```

_Внутренняя функция._

Оставляет только последние диагностические файлы в указанной директории.

#### `build_audio_diagnostics`

```python
build_audio_diagnostics(audio_data, language)
```

Собирает компактную диагностику входного аудиосигнала.

#### `save_audio_recording`

```python
save_audio_recording(stem, audio_data, diagnostics)
```

Сохраняет аудиозапись и метаданные, если диагностика включена.

#### `save_transcription_artifacts`

```python
save_transcription_artifacts(stem, diagnostics, result = None, text = '', error_message = None)
```

Сохраняет результат распознавания и метаданные, если диагностика включена.

## Публичные функции

### `setup_logging`

```python
setup_logging()
```

Настраивает консольное и файловое логирование приложения.

### `looks_like_hallucination`

```python
looks_like_hallucination(text)
```

Проверяет, похож ли результат на типичную галлюцинацию Whisper.
