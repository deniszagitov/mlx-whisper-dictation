# Menu bar UI

Исходный файл: `src/ui.py`

UI menu bar приложения Dictator.

Содержит StatusBarApp — основной класс меню, а также вспомогательные
функции для работы с профилями микрофона и диалоговыми окнами.

## Константы

- `LOGGER` = `logging.getLogger(__name__)`

## Классы

## `StatusBarApp`

Menu bar приложение для управления записью и распознаванием.

Attributes:
    languages: Доступные языки распознавания или None.
    current_language: Текущий выбранный язык или None.
    started: Флаг активной записи.
    recorder: Объект записи аудио.
    max_time: Максимальная длительность записи в секундах.
    elapsed_time: Количество секунд с начала текущей записи.
    status_timer: Таймер обновления индикатора в строке меню.

### Методы

#### `__init__`

```python
__init__(recorder, model_name, hotkey_status, languages = None, max_time = None, key_combination = None, secondary_hotkey_status = None, secondary_key_combination = None, llm_hotkey_status = None, llm_key_combination = None, use_double_command_hotkey = False)
```

Создает menu bar приложение.

Args:
    recorder: Объект Recorder для записи и распознавания.
    model_name: Имя модели, показываемое в меню приложения.
    hotkey_status: Строка для отображения текущего хоткея в меню.
    languages: Необязательный список доступных языков.
    max_time: Необязательный лимит длительности записи в секундах.
    key_combination: Нормализованная строка комбинации клавиш.
    secondary_hotkey_status: Строка для отображения дополнительного хоткея.
    secondary_key_combination: Нормализованная строка дополнительной комбинации.
    llm_hotkey_status: Строка для отображения LLM-хоткея.
    llm_key_combination: Нормализованная строка комбинации для LLM.
    use_double_command_hotkey: Включён ли режим запуска по двойному нажатию Command.

#### `_find_menu_item`

```python
_find_menu_item(container, title)
```

_Внутренняя функция._

Рекурсивно ищет пункт меню по заголовку.

#### `_menu_item`

```python
_menu_item(title)
```

_Внутренняя функция._

Возвращает пункт меню по заголовку.

Args:
    title: Текст пункта меню.

Returns:
    Объект пункта меню из rumps.

#### `_state_label`

```python
_state_label()
```

_Внутренняя функция._

Возвращает человекочитаемое имя текущего состояния.

#### `_format_input_device`

```python
_format_input_device()
```

_Внутренняя функция._

Возвращает строку текущего микрофона для меню.

#### `_format_language`

```python
_format_language()
```

_Внутренняя функция._

Возвращает строку текущего языка для меню.

#### `_model_menu_title`

```python
_model_menu_title(model_repo)
```

_Внутренняя функция._

Возвращает подпись пункта меню модели.

#### `_max_time_menu_title`

```python
_max_time_menu_title(max_time_value)
```

_Внутренняя функция._

Возвращает подпись пункта меню лимита записи.

#### `_permission_title`

```python
_permission_title(permission_name, permission_status)
```

_Внутренняя функция._

Формирует строку статуса разрешения для меню.

Args:
    permission_name: Имя разрешения.
    permission_status: Булев статус разрешения или None.

Returns:
    Строка для пункта меню.

#### `_format_total_tokens`

```python
_format_total_tokens(token_count)
```

_Внутренняя функция._

Форматирует число токенов для отображения в меню.

#### `_token_usage_title`

```python
_token_usage_title()
```

_Внутренняя функция._

Возвращает заголовок пункта меню со счётчиком токенов.

#### `_refresh_token_usage_item`

```python
_refresh_token_usage_item()
```

_Внутренняя функция._

Обновляет пункт меню с общим числом потраченных токенов.

#### `_refresh_permission_items`

```python
_refresh_permission_items()
```

_Внутренняя функция._

Обновляет пункты меню со статусами разрешений.

#### `_refresh_selection_states`

```python
_refresh_selection_states()
```

_Внутренняя функция._

Обновляет отметки выбранных пунктов в списках меню.

#### `_persist_microphone_profiles`

```python
_persist_microphone_profiles()
```

_Внутренняя функция._

Сохраняет быстрые профили микрофона.

#### `_active_input_device_index`

```python
_active_input_device_index()
```

_Внутренняя функция._

Возвращает индекс активного микрофона или None.

#### `_suggest_microphone_profile_name`

```python
_suggest_microphone_profile_name()
```

_Внутренняя функция._

Возвращает имя профиля по умолчанию для текущего микрофона.

#### `_unique_microphone_profile_name`

```python
_unique_microphone_profile_name(base_name)
```

_Внутренняя функция._

Делает имя профиля уникальным в пределах сохранённого списка.

#### `_current_microphone_profile`

```python
_current_microphone_profile(profile_name)
```

_Внутренняя функция._

Собирает профиль из текущих настроек приложения.

#### `_is_microphone_profile_active`

```python
_is_microphone_profile_active(profile)
```

_Внутренняя функция._

Проверяет, соответствует ли профиль текущим настройкам.

#### `_refresh_input_device_menu`

```python
_refresh_input_device_menu()
```

_Внутренняя функция._

Пересобирает подменю выбора микрофона.

#### `_refresh_microphone_profiles_menu`

```python
_refresh_microphone_profiles_menu()
```

_Внутренняя функция._

Пересобирает подменю быстрых профилей микрофона.

#### `_persist_hotkey_settings`

```python
_persist_hotkey_settings()
```

_Внутренняя функция._

Сохраняет активные хоткеи в NSUserDefaults.

#### `_refresh_title_and_status`

```python
_refresh_title_and_status()
```

_Внутренняя функция._

Обновляет иконку и строку статуса в меню.

#### `_active_key_combinations`

```python
_active_key_combinations()
```

_Внутренняя функция._

Возвращает список всех включенных комбинаций клавиш.

#### `_refresh_hotkey_items`

```python
_refresh_hotkey_items()
```

_Внутренняя функция._

Обновляет подписи пунктов меню с основным и дополнительным хоткеями.

#### `_can_update_hotkeys_runtime`

```python
_can_update_hotkeys_runtime()
```

_Внутренняя функция._

Проверяет, поддерживает ли текущий listener горячее обновление хоткеев.

#### `_apply_hotkey_changes`

```python
_apply_hotkey_changes()
```

_Внутренняя функция._

Применяет обновленные комбинации к меню и активному listener-у.

#### `_update_hotkey_value`

```python
_update_hotkey_value(*, is_secondary, new_combination)
```

_Внутренняя функция._

Обновляет основную или дополнительную комбинацию с проверкой на дубликаты.

#### `set_state`

```python
set_state(state)
```

Сохраняет новое состояние приложения.

Args:
    state: Новый идентификатор состояния.

#### `set_permission_status`

```python
set_permission_status(permission_name, status)
```

Сохраняет новый статус разрешения.

Args:
    permission_name: Имя разрешения.
    status: Булев статус разрешения.

#### `change_input_device`

```python
change_input_device(sender)
```

Переключает текущее устройство ввода.

#### `change_language`

```python
change_language(sender)
```

Переключает текущий язык распознавания.

Args:
    sender: Пункт меню, выбранный пользователем.

#### `change_model`

```python
change_model(sender)
```

Переключает модель распознавания из списка доступных.

#### `change_max_time`

```python
change_max_time(sender)
```

Переключает лимит длительности записи из списка.

#### `add_current_microphone_profile`

```python
add_current_microphone_profile(_)
```

Сохраняет текущие настройки как быстрый профиль микрофона.

#### `apply_microphone_profile`

```python
apply_microphone_profile(sender)
```

Применяет сохранённый быстрый профиль микрофона.

#### `delete_microphone_profile`

```python
delete_microphone_profile(sender)
```

Удаляет сохранённый быстрый профиль микрофона.

#### `change_hotkey`

```python
change_hotkey(_)
```

Открывает диалог для смены комбинации клавиш через захват нажатия.

#### `change_secondary_hotkey`

```python
change_secondary_hotkey(_)
```

Открывает диалог для смены дополнительной комбинации клавиш через захват.

#### `change_llm_hotkey`

```python
change_llm_hotkey(_)
```

Открывает диалог для смены LLM-хоткея через захват нажатия.

#### `request_accessibility_access`

```python
request_accessibility_access(_)
```

Повторно запрашивает у macOS доступ к Accessibility.

#### `request_input_monitoring_access`

```python
request_input_monitoring_access(_)
```

Повторно запрашивает у macOS доступ к Input Monitoring.

#### `toggle_recording_notification`

```python
toggle_recording_notification(sender)
```

Переключает системное уведомление о старте записи.

#### `change_performance_mode`

```python
change_performance_mode(sender)
```

Переключает баланс между задержкой и потреблением ресурсов.

#### `toggle_private_mode`

```python
toggle_private_mode(sender)
```

Переключает private mode для истории текста.

#### `toggle_paste_cgevent`

```python
toggle_paste_cgevent(sender)
```

Переключает метод вставки через CGEvent Unicode.

#### `toggle_paste_ax`

```python
toggle_paste_ax(sender)
```

Переключает метод вставки через Accessibility API.

#### `toggle_paste_clipboard`

```python
toggle_paste_clipboard(sender)
```

Переключает метод вставки через буфер обмена (Cmd+V).

#### `toggle_llm_clipboard`

```python
toggle_llm_clipboard(sender)
```

Переключает использование буфера обмена для LLM-контекста и ответа.

#### `_format_history_title`

```python
_format_history_title(text)
```

_Внутренняя функция._

Форматирует текст для отображения в подменю истории.

Заменяет переносы строк пробелами и обрезает до HISTORY_DISPLAY_LENGTH символов.

Args:
    text: Полный текст записи.

Returns:
    Сокращённая строка для пункта меню.

#### `_refresh_history_menu`

```python
_refresh_history_menu()
```

_Внутренняя функция._

Обновляет подменю «История текста» из данных transcriber.

Вызывается при каждом добавлении текста в историю.

#### `_copy_history_item`

```python
_copy_history_item(sender)
```

_Внутренняя функция._

Копирует выбранный элемент истории в буфер обмена.

Args:
    sender: Пункт меню, по которому кликнули.

#### `start_app`

```python
start_app(_)
```

Запускает запись и обновляет состояние интерфейса.

Args:
    _: Аргумент callback от rumps, который здесь не используется.

#### `stop_app`

```python
stop_app(_)
```

Останавливает запись и запускает этап распознавания.

Args:
    _: Аргумент callback от rumps, который здесь не используется.

#### `on_status_tick`

```python
on_status_tick(_)
```

Обновляет индикатор времени записи в строке меню.

Args:
    _: Аргумент timer callback, который здесь не используется.

#### `toggle`

```python
toggle()
```

Переключает приложение между состояниями записи и ожидания.

#### `toggle_llm`

```python
toggle_llm()
```

Переключает запись для LLM-пайплайна.

#### `_download_llm_model`

```python
_download_llm_model(_)
```

_Внутренняя функция._

Запускает загрузку LLM-модели в фоновом потоке с индикатором прогресса.

#### `_change_llm_prompt`

```python
_change_llm_prompt(sender)
```

_Внутренняя функция._

Переключает текущий пресет системного промпта для LLM.

Args:
    sender: Пункт меню с именем пресета.

## Публичные функции

### `prompt_text`

```python
prompt_text(title, message, default_text = '')
```

Открывает простое окно ввода текста и возвращает введённое значение.

## Внутренние функции

### `_normalize_microphone_profile`

```python
_normalize_microphone_profile(raw_profile)
```

_Внутренняя функция._

Нормализует сохранённый профиль микрофона.

### `_load_microphone_profiles`

```python
_load_microphone_profiles()
```

_Внутренняя функция._

Читает быстрые профили микрофона из NSUserDefaults.

### `_save_microphone_profiles`

```python
_save_microphone_profiles(profiles)
```

_Внутренняя функция._

Сохраняет быстрые профили микрофона в NSUserDefaults.
