# CLI и запуск

Исходный файл: `main.py`

Приложение офлайн-диктовки для macOS на базе MLX Whisper.

Точка входа приложения: парсинг аргументов командной строки,
запуск menu bar приложения и глобальных обработчиков клавиш.

## Константы

- `LOGGER` = `logging.getLogger(__name__)`
- `CLI_FORCE_EXIT_DELAY_SECONDS` = `2.0`

## Публичные функции

### `parse_args`

```python
parse_args() -> LaunchConfig
```

Разбирает аргументы командной строки.

Returns:
    Нормализованная конфигурация запуска приложения.

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

### `_create_hotkey_dispatcher`

```python
_create_hotkey_dispatcher(app: Any) -> HotkeyDispatcher
```

_Внутренняя функция._

Создаёт единый runtime-dispatcher горячих клавиш.

### `_log_startup_configuration`

```python
_log_startup_configuration(args: LaunchConfig) -> None
```

_Внутренняя функция._

Пишет в лог итоговую конфигурацию запуска приложения.

### `_safe_shutdown_call`

```python
_safe_shutdown_call(label: str, callback: Any) -> None
```

_Внутренняя функция._

Выполняет шаг остановки приложения, не срывая общий shutdown.

### `_stop_runtime_for_cli_shutdown`

```python
_stop_runtime_for_cli_shutdown(*, app_controller: DictationApp, key_listener: Any, tts_speaker: Any, rsvp_display: Any, display_sleep_prevention_service: DisplaySleepPreventionService) -> None
```

_Внутренняя функция._

Останавливает runtime-ресурсы перед выходом из CLI.

### `_install_cli_signal_wait_thread`

```python
_install_cli_signal_wait_thread(handler: Any, *, signals: tuple[int, ...] = (signal.SIGINT, signal.SIGTERM), pthread_sigmask: Any = signal.pthread_sigmask, sigwait: Any = signal.sigwait, stdin_isatty: Any = None) -> Any | None
```

_Внутренняя функция._

Обрабатывает CLI-сигналы из отдельного потока, не полагаясь на Cocoa run loop.

### `_build_cli_shutdown_handler`

```python
_build_cli_shutdown_handler(*, app_controller: DictationApp, key_listener: Any, tts_speaker: Any, rsvp_display: Any, display_sleep_prevention_service: DisplaySleepPreventionService, quit_application: Any = None, force_exit: Any = None, timer_factory: Any = None, stop_runtime: Any = None) -> Any
```

_Внутренняя функция._

Создаёт обработчик SIGINT/SIGTERM для запуска из терминала.

### `_install_cli_shutdown_handlers`

```python
_install_cli_shutdown_handlers(*, app_controller: DictationApp, key_listener: Any, tts_speaker: Any, rsvp_display: Any, display_sleep_prevention_service: DisplaySleepPreventionService) -> None
```

_Внутренняя функция._

Регистрирует Ctrl-C/Ctrl-Term shutdown для запуска приложения из CLI.
