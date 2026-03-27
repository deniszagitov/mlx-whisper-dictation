# Разрешения macOS

Исходный файл: `src/permissions.py`

Разрешения macOS и системные утилиты приложения Dictator.

Проверка и запрос Accessibility, Input Monitoring, уведомления,
открытие System Settings и информация об активном приложении.

## Константы

- `LOGGER` = `logging.getLogger(__name__)`

## Публичные функции

### `notify_user`

```python
notify_user(title, message)
```

Показывает системное уведомление macOS.

Args:
    title: Заголовок уведомления.
    message: Основной текст уведомления.

### `open_system_settings`

```python
open_system_settings(url)
```

Открывает нужный раздел System Settings по специальной ссылке macOS.

### `frontmost_application_info`

```python
frontmost_application_info()
```

Возвращает краткую информацию о текущем активном приложении.

### `is_accessibility_trusted`

```python
is_accessibility_trusted()
```

Проверяет, выдан ли процессу доступ к Accessibility на macOS.

Returns:
    True, если приложение может использовать глобальные события клавиатуры,
    иначе False.

### `permission_preflight_status`

```python
permission_preflight_status(function_name)
```

Вызывает preflight-функцию из ApplicationServices, если она доступна.

Args:
    function_name: Имя C-функции из ApplicationServices.

Returns:
    True, False или None, если статус нельзя определить.

### `get_accessibility_status`

```python
get_accessibility_status()
```

Возвращает статус доступа к Accessibility.

### `get_input_monitoring_status`

```python
get_input_monitoring_status()
```

Возвращает статус доступа к Input Monitoring.

### `request_accessibility_permission`

```python
request_accessibility_permission()
```

Запрашивает Accessibility через системный диалог macOS.

Вызывает AXIsProcessTrustedWithOptions с kAXTrustedCheckOptionPrompt=True,
чтобы macOS показала пользователю диалог с предложением открыть настройки.

Returns:
    True, если разрешение уже выдано, False если нужно выдать вручную.

### `request_input_monitoring_permission`

```python
request_input_monitoring_permission()
```

Запрашивает Input Monitoring через системный диалог macOS.

Вызывает CGRequestListenEventAccess, чтобы macOS показала пользователю
диалог с предложением открыть настройки Input Monitoring.

Returns:
    True, если разрешение уже выдано, False если нужно выдать вручную.

### `permission_label`

```python
permission_label(status)
```

Преобразует булев статус разрешения в строку для меню.

Args:
    status: True, False или None.

Returns:
    Строковое значение статуса.

### `warn_missing_accessibility_permission`

```python
warn_missing_accessibility_permission()
```

Показывает пользователю предупреждение об отсутствии Accessibility-доступа.

### `warn_missing_input_monitoring_permission`

```python
warn_missing_input_monitoring_permission()
```

Показывает пользователю предупреждение об отсутствии Input Monitoring.
