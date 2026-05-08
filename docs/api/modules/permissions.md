# Разрешения macOS

Исходный файл: `src/infrastructure/permissions.py`

Разрешения macOS и системные утилиты приложения Dictator.

Проверка и запрос Accessibility, Input Monitoring, уведомления,
открытие System Settings и информация об активном приложении.

## Константы

- `LOGGER` = `logging.getLogger(__name__)`

## Классы

## `_WorkspaceWakeObserver`

Observer NSWorkspaceDidWakeNotification для Python-callback.

### Методы

#### `observerWithCallback_`

```python
observerWithCallback_(callback: Callable[[], None]) -> Any
```

Создаёт observer и удерживает Python-callback.

#### `handleWake_`

```python
handleWake_(_notification: Any) -> None
```

Пробрасывает событие wake во внешний callback.

## `_WorkspaceSystemEventObserver`

Observer системных событий сна, экранов и пользовательской сессии.

### Методы

#### `observerWithCallback_`

```python
observerWithCallback_(callback: Callable[[str], None]) -> Any
```

Создаёт observer и удерживает Python-callback.

#### `handleWillSleep_`

```python
handleWillSleep_(_notification: Any) -> None
```

Пробрасывает событие ухода системы в sleep.

#### `handleDidWake_`

```python
handleDidWake_(_notification: Any) -> None
```

Пробрасывает событие пробуждения системы.

#### `handleScreensDidSleep_`

```python
handleScreensDidSleep_(_notification: Any) -> None
```

Пробрасывает событие сна экранов.

#### `handleScreensDidWake_`

```python
handleScreensDidWake_(_notification: Any) -> None
```

Пробрасывает событие пробуждения экранов.

#### `handleSessionDidResignActive_`

```python
handleSessionDidResignActive_(_notification: Any) -> None
```

Пробрасывает событие деактивации пользовательской сессии.

#### `handleSessionDidBecomeActive_`

```python
handleSessionDidBecomeActive_(_notification: Any) -> None
```

Пробрасывает событие возврата пользовательской сессии.

## `_WorkspaceApplicationObserver`

Observer NSWorkspaceDidActivateApplicationNotification для Python-callback.

### Методы

#### `observerWithCallback_`

```python
observerWithCallback_(callback: Callable[[dict[str, str | int] | None], None]) -> Any
```

Создаёт observer и удерживает Python-callback.

#### `handleApplicationActivate_`

```python
handleApplicationActivate_(_notification: Any) -> None
```

Пробрасывает смену активного приложения во внешний callback.

## Публичные функции

### `notify_user`

```python
notify_user(title: str, message: str) -> None
```

Показывает системное уведомление macOS.

Args:
    title: Заголовок уведомления.
    message: Основной текст уведомления.

### `open_system_settings`

```python
open_system_settings(url: str) -> bool
```

Открывает нужный раздел System Settings по специальной ссылке macOS.

### `open_path`

```python
open_path(path: str) -> bool
```

Открывает файл или папку в Finder через NSWorkspace.

### `register_wake_observer`

```python
register_wake_observer(on_wake_callback: Callable[[], None]) -> Any
```

Регистрирует observer события пробуждения macOS из sleep.

### `register_system_event_observer`

```python
register_system_event_observer(on_event_callback: Callable[[str], None]) -> Any
```

Регистрирует observer событий sleep/wake экранов и пользовательской сессии.

### `register_application_activation_observer`

```python
register_application_activation_observer(on_activate_callback: Callable[[dict[str, str | int] | None], None]) -> Any
```

Регистрирует observer смены активного приложения macOS.

### `frontmost_application_info`

```python
frontmost_application_info() -> dict[str, str | int] | None
```

Возвращает краткую информацию о текущем активном приложении.

### `is_accessibility_trusted`

```python
is_accessibility_trusted() -> bool
```

Проверяет, выдан ли процессу доступ к Accessibility на macOS.

Returns:
    True, если приложение может использовать глобальные события клавиатуры,
    иначе False.

### `permission_preflight_status`

```python
permission_preflight_status(function_name: str) -> bool | None
```

Вызывает preflight-функцию из ApplicationServices, если она доступна.

Args:
    function_name: Имя C-функции из ApplicationServices.

Returns:
    True, False или None, если статус нельзя определить.

### `get_accessibility_status`

```python
get_accessibility_status() -> bool | None
```

Возвращает статус доступа к Accessibility.

### `get_input_monitoring_status`

```python
get_input_monitoring_status() -> bool | None
```

Возвращает статус доступа к Input Monitoring.

### `request_accessibility_permission`

```python
request_accessibility_permission() -> bool
```

Запрашивает Accessibility через системный диалог macOS.

Вызывает AXIsProcessTrustedWithOptions с kAXTrustedCheckOptionPrompt=True,
чтобы macOS показала пользователю диалог с предложением открыть настройки.

Returns:
    True, если разрешение уже выдано, False если нужно выдать вручную.

### `request_input_monitoring_permission`

```python
request_input_monitoring_permission() -> bool
```

Запрашивает Input Monitoring через системный диалог macOS.

Вызывает CGRequestListenEventAccess, чтобы macOS показала пользователю
диалог с предложением открыть настройки Input Monitoring.

Returns:
    True, если разрешение уже выдано, False если нужно выдать вручную.

### `permission_label`

```python
permission_label(status: bool | None) -> str
```

Преобразует булев статус разрешения в строку для меню.

Args:
    status: True, False или None.

Returns:
    Строковое значение статуса.

### `warn_missing_accessibility_permission`

```python
warn_missing_accessibility_permission() -> None
```

Показывает пользователю предупреждение об отсутствии Accessibility-доступа.

### `warn_missing_input_monitoring_permission`

```python
warn_missing_input_monitoring_permission() -> None
```

Показывает пользователю предупреждение об отсутствии Input Monitoring.
