# CLI и запуск

Исходный файл: `main.py`

Приложение офлайн-диктовки для macOS на базе MLX Whisper.

Точка входа приложения: парсинг аргументов командной строки,
запуск menu bar приложения и глобальных обработчиков клавиш.

## Константы

- `LOGGER` = `logging.getLogger(__name__)`

## Публичные функции

### `parse_args`

```python
parse_args() -> argparse.Namespace
```

Разбирает аргументы командной строки.

Returns:
    Пространство имен argparse с настройками запуска приложения.

Raises:
    SystemExit: Если передана некорректная комбинация клавиш.
    ValueError: Если выбран несовместимый язык для модели с суффиксом `.en`.

### `main`

```python
main() -> None
```

Запускает приложение диктовки и глобальные обработчики клавиш.

## Внутренние функции

### `_cli_option_was_provided`

```python
_cli_option_was_provided(*option_names: str) -> bool
```

_Внутренняя функция._

Проверяет, был ли аргумент командной строки передан явно.

### `_load_saved_runtime_preferences`

```python
_load_saved_runtime_preferences(args: argparse.Namespace) -> None
```

_Внутренняя функция._

Подставляет сохранённые настройки, если их не переопределили через CLI.

### `_log_startup_configuration`

```python
_log_startup_configuration(args: argparse.Namespace) -> None
```

_Внутренняя функция._

Пишет в лог итоговую конфигурацию запуска приложения.
