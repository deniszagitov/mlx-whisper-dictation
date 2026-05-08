# Zipper config

Исходный файл: `src/infrastructure/zipper_config.py`

Загрузка и нормализация TOML-конфига Zipper.

## Константы

- `LOGGER` = `logging.getLogger(__name__)`

## Классы

## `ZipperConfigProvider`

Читает конфиг Zipper из example/local/user TOML-файлов.

### Методы

#### `__init__`

```python
__init__(*, example_path: Path | None = None, local_path: Path | None = None, user_path: Path | None = None, open_path: Any | None = None) -> None
```

Конструктор класса.

#### `ensure_user_config`

```python
ensure_user_config() -> None
```

Создаёт пользовательский конфиг установленного приложения, если его нет.

#### `config_path`

```python
config_path() -> str
```

Возвращает путь пользовательского конфига.

#### `load_config`

```python
load_config() -> ZipperConfig
```

Загружает конфиг с приоритетом user > local > example.

#### `open_config`

```python
open_config() -> bool
```

Открывает пользовательский конфиг через системную интеграцию.

## Публичные функции

### `example_config_path`

```python
example_config_path() -> Path
```

Возвращает путь к закоммиченному примеру конфига Zipper.

### `local_config_path`

```python
local_config_path() -> Path
```

Возвращает путь к локальному dev-конфигу для запуска через uv.

### `user_config_path`

```python
user_config_path() -> Path
```

Возвращает путь к пользовательскому конфигу установленного приложения.

### `normalize_config`

```python
normalize_config(raw: dict[str, Any]) -> ZipperConfig
```

Преобразует сырой TOML-словарь в доменный конфиг Zipper.
