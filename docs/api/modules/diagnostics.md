# Диагностика

Исходный файл: `src/infrastructure/persistence/diagnostics.py`

Логирование и сохранение диагностических артефактов приложения.

## Классы

## `MaxLevelFilter`

Пропускает записи не выше заданного уровня логирования.

### Методы

#### `__init__`

```python
__init__(level: int) -> None
```

Сохраняет максимальный уровень логов для фильтрации.

#### `filter`

```python
filter(record: logging.LogRecord) -> bool
```

Возвращает True, если запись не превышает допустимый уровень.

## `DailyRetentionFileHandler`

Ротирует лог-файл раз в 24 часа и удаляет старые файлы.

### Методы

#### `__init__`

```python
__init__(filename: str | Path, *, retention_seconds: float = Config.ARTIFACT_TTL_SECONDS, **kwargs: Any) -> None
```

Конструктор класса.

#### `doRollover`

```python
doRollover() -> None
```

Создает новый суточный лог-файл и чистит просроченные ротации.

#### `_cleanup_expired_log_family`

```python
_cleanup_expired_log_family() -> None
```

_Внутренняя функция._

Удаляет старые файлы текущего лог-семейства.

## `DiagnosticsStore`

Изолирует сохранение диагностических артефактов от основного runtime-кода.

### Свойства

#### `recordings_dir`

```python
recordings_dir() -> Path
```

Возвращает путь к папке с диагностическими аудиозаписями.

#### `transcriptions_dir`

```python
transcriptions_dir() -> Path
```

Возвращает путь к папке с диагностическими транскрипциями.

### Методы

#### `__init__`

```python
__init__(root_dir: str | Path = Config.LOG_DIR, enabled: bool = True, max_artifacts: int = Config.MAX_DEBUG_ARTIFACTS, retention_seconds: float = Config.ARTIFACT_TTL_SECONDS) -> None
```

Создает хранилище диагностических файлов.

Args:
    root_dir: Корневая директория логов и артефактов.
    enabled: Нужно ли сохранять диагностические файлы.
    max_artifacts: Устаревший аргумент, сохранён только для совместимости.
    retention_seconds: Время жизни диагностических артефактов в секундах.

#### `artifact_stem`

```python
artifact_stem() -> str
```

Возвращает уникальное имя группы диагностических файлов.

#### `_cleanup_directory`

```python
_cleanup_directory(directory: Path) -> None
```

_Внутренняя функция._

Удаляет диагностические файлы старше retention_seconds.

#### `build_audio_diagnostics`

```python
build_audio_diagnostics(audio_data: npt.NDArray[np.float32], language: str | None) -> AudioDiagnostics
```

Собирает компактную диагностику входного аудиосигнала.

#### `save_audio_recording`

```python
save_audio_recording(stem: str, audio_data: npt.NDArray[np.float32], diagnostics: AudioDiagnostics) -> Path | None
```

Сохраняет аудиозапись и метаданные, если диагностика включена.

#### `save_transcription_artifacts`

```python
save_transcription_artifacts(stem: str, diagnostics: AudioDiagnostics, result: Any = None, text: str = '', error_message: str | None = None) -> Path | None
```

Сохраняет результат распознавания и метаданные, если диагностика включена.

## Публичные функции

### `setup_logging`

```python
setup_logging() -> None
```

Настраивает консольное и файловое логирование приложения.

## Внутренние функции

### `_cleanup_expired_files`

```python
_cleanup_expired_files(directory: Path, pattern: str, retention_seconds: float, *, include_current_file: bool = False) -> None
```

_Внутренняя функция._

Удаляет файлы старше retention_seconds.
