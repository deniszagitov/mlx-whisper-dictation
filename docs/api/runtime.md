# Runtime API

Исходный файл: `whisper-dictation.py`

Приложение офлайн-диктовки для macOS на базе MLX Whisper.

Модуль содержит menu bar приложение, которое записывает звук с микрофона,
распознает речь локально через MLX Whisper и вставляет результат в активное
поле ввода.

## Константы

- `DEFAULT_MODEL_NAME` = `'mlx-community/whisper-large-v3-turbo'`
- `MODEL_PRESETS` = `['mlx-community/whisper-large-v3-turbo', 'mlx-community/whisper-large-v3-mlx', 'mlx-community/whisper-turbo']`
- `MAX_TIME_PRESETS` = `[15, 30, 45, 60, 90, None]`
- `MIN_HOTKEY_PARTS` = `2`
- `DOUBLE_COMMAND_PRESS_INTERVAL` = `0.5`
- `STATUS_IDLE` = `'idle'`
- `STATUS_RECORDING` = `'recording'`
- `STATUS_TRANSCRIBING` = `'transcribing'`
- `PERMISSION_GRANTED` = `'есть'`
- `PERMISSION_DENIED` = `'нет'`
- `PERMISSION_UNKNOWN` = `'неизвестно'`
- `SILENCE_RMS_THRESHOLD` = `0.0005`
- `HALLUCINATION_RMS_THRESHOLD` = `0.002`
- `SHORT_AUDIO_WARNING_SECONDS` = `0.3`
- `MAX_DEBUG_ARTIFACTS` = `10`
- `LOG_DIR` = `Path.home() / 'Library/Logs/whisper-dictation'`
- `ACCESSIBILITY_SETTINGS_URL` = `'x-apple.systempreferences:com.apple.preference.security?Privacy_Accessibility'`
- `INPUT_MONITORING_SETTINGS_URL` = `'x-apple.systempreferences:com.apple.preference.security?Privacy_ListenEvent'`
- `KEYCODE_COMMAND` = `55`
- `KEYCODE_V` = `9`
- `KNOWN_HALLUCINATIONS` = `{'спасибо за внимание', 'спасибо за просмотр', 'продолжение следует', 'thank you', 'thank you.', 'продолжение следует...'}`
- `LOGGER` = `logging.getLogger(__name__)`
- `KEY_NAME_ALIASES` = `{'ctrl': 'ctrl', 'control': 'ctrl', 'alt': 'alt', 'option': 'alt', 'opt': 'alt', 'shift': 'shift', 'cmd': 'cmd', 'command': 'cmd', 'meta': 'cmd', 'super': 'cmd'}`
- `MODIFIER_KEYCODES_MAP` = `{54: 'cmd_r', 55: 'cmd_l', 56: 'shift_l', 58: 'alt_l', 59: 'ctrl_l', 60: 'shift_r', 61: 'alt_r', 62: 'ctrl_r'}`
- `MODIFIER_FLAG_MASKS` = `{'alt_l': 524288, 'alt_r': 524288, 'ctrl_l': 262144, 'ctrl_r': 262144, 'shift_l': 131072, 'shift_r': 131072, 'cmd_l': 1048576, 'cmd_r': 1048576}`
- `NAMED_KEYCODES_MAP` = `{36: 'enter', 48: 'tab', 49: 'space', 51: 'backspace', 53: 'esc'}`
- `MODIFIER_DISPLAY_ORDER` = `['ctrl', 'ctrl_l', 'ctrl_r', 'alt', 'alt_l', 'alt_r', 'shift', 'shift_l', 'shift_r', 'cmd', 'cmd_l', 'cmd_r']`

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

## `SpeechTranscriber`

Распознает аудио и вставляет текст в активное приложение.

Attributes:
    pykeyboard: Контроллер клавиатуры pynput для вставки текста.
    diagnostics_store: Изолированное хранилище диагностических артефактов.
    model_name: Имя или путь к модели MLX Whisper.

### Методы

#### `__init__`

```python
__init__(model_name, diagnostics_store = None)
```

Создает объект распознавания.

Args:
    model_name: Имя модели Hugging Face или локальный путь к модели.
    diagnostics_store: Необязательное хранилище диагностических файлов.

#### `_copy_text_to_clipboard`

```python
_copy_text_to_clipboard(text)
```

_Внутренняя функция._

Копирует текст в системный буфер обмена.

Args:
    text: Текст для сохранения в буфере обмена.

#### `_paste_text`

```python
_paste_text()
```

_Внутренняя функция._

Вставляет текущий текст из буфера обмена через Cmd+V.

#### `_run_transcription`

```python
_run_transcription(audio_data, language)
```

_Внутренняя функция._

Запускает один проход распознавания с заданными параметрами языка.

#### `transcribe`

```python
transcribe(audio_data, language = None)
```

Распознает аудио и вставляет результат в активное приложение.

Args:
    audio_data: Массив с аудио в формате float32.
    language: Необязательный код языка для улучшения распознавания.

## `Recorder`

Записывает звук с микрофона и передает его в распознавание.

Attributes:
    recording: Флаг активной записи.
    transcriber: Объект распознавания, который обрабатывает аудио.

### Методы

#### `__init__`

```python
__init__(transcriber)
```

Создает объект записи.

Args:
    transcriber: Экземпляр SpeechTranscriber для обработки записанного аудио.

#### `set_status_callback`

```python
set_status_callback(status_callback)
```

Регистрирует callback для обновления UI-статуса.

Args:
    status_callback: Функция, принимающая строковый статус.

#### `_set_status`

```python
_set_status(status)
```

_Внутренняя функция._

Передает новый статус во внешний callback.

Args:
    status: Идентификатор состояния приложения.

#### `set_permission_callback`

```python
set_permission_callback(permission_callback)
```

Регистрирует callback для обновления статусов разрешений.

Args:
    permission_callback: Функция, принимающая имя разрешения и его статус.

#### `_set_permission_status`

```python
_set_permission_status(permission_name, status)
```

_Внутренняя функция._

Передает обновленный статус разрешения во внешний callback.

Args:
    permission_name: Имя разрешения.
    status: Булев статус разрешения.

#### `set_input_device`

```python
set_input_device(device_info = None)
```

Сохраняет выбранное устройство ввода для последующей записи.

#### `start`

```python
start(language = None)
```

Запускает запись в отдельном потоке.

Args:
    language: Необязательный код языка для последующего распознавания.

#### `stop`

```python
stop()
```

Останавливает активную запись.

#### `_record_impl`

```python
_record_impl(language)
```

_Внутренняя функция._

Выполняет запись, конвертацию аудио и запуск распознавания.

Args:
    language: Необязательный код языка для последующего распознавания.

## `GlobalKeyListener`

Обрабатывает глобальную комбинацию клавиш для запуска диктовки.

Attributes:
    app: Экземпляр StatusBarApp, которым управляет listener.
    keys: Кортеж клавиш, которые образуют хоткей.
    pressed_keys: Набор клавиш, зажатых в текущий момент.
    triggered: Флаг, защищающий от повторного срабатывания при удержании.

### Методы

#### `__init__`

```python
__init__(app, key_combination)
```

Создает listener для заданной комбинации клавиш.

Args:
    app: Экземпляр приложения, у которого будет вызван toggle.
    key_combination: Строка с комбинацией клавиш.

#### `stop`

```python
stop()
```

Удаляет глобальные мониторы событий клавиатуры.

#### `update_key_combination`

```python
update_key_combination(key_combination)
```

Обновляет комбинацию клавиш без пересоздания listener.

#### `start`

```python
start()
```

Запускает глобальный монитор событий клавиатуры через AppKit.

#### `_required_modifiers_are_pressed`

```python
_required_modifiers_are_pressed()
```

_Внутренняя функция._

Проверяет, зажаты ли нужные modifier-клавиши.

#### `_event_is_modifier_pressed`

```python
_event_is_modifier_pressed(event, modifier_name)
```

_Внутренняя функция._

Определяет, находится ли modifier в нажатом состоянии для flagsChanged-события.

Args:
    event: Системное NSEvent.
    modifier_name: Имя modifier-клавиши.

Returns:
    True, если соответствующий modifier сейчас зажат.

#### `_handle_flags_changed`

```python
_handle_flags_changed(event)
```

_Внутренняя функция._

Обрабатывает глобальные изменения modifier-клавиш.

Args:
    event: Системное NSEvent.

#### `_event_key_name`

```python
_event_key_name(event)
```

_Внутренняя функция._

Преобразует NSEvent в строковое имя клавиши.

#### `_handle_key_down`

```python
_handle_key_down(event)
```

_Внутренняя функция._

Обрабатывает глобальные события обычных клавиш.

Args:
    event: Системное NSEvent.

## `MultiHotkeyListener`

Управляет несколькими глобальными хоткеями одновременно.

### Методы

#### `__init__`

```python
__init__(app, key_combinations)
```

Создает набор listener-ов для списка комбинаций клавиш.

#### `start`

```python
start()
```

Запускает все глобальные listener-ы.

#### `stop`

```python
stop()
```

Останавливает все глобальные listener-ы.

#### `_build_listeners`

```python
_build_listeners(key_combinations)
```

_Внутренняя функция._

Нормализует комбинации и создаёт listener-ы без запуска.

#### `update_key_combinations`

```python
update_key_combinations(key_combinations)
```

Пересоздает listener-ы для нового списка комбинаций и запускает их.

## `DoubleCommandKeyListener`

Обрабатывает режим управления через правую клавишу Command.

Attributes:
    app: Экземпляр приложения, у которого будет вызван toggle.
    key: Клавиша, используемая для переключения записи.
    last_press_time: Время предыдущего нажатия для определения двойного клика.

### Методы

#### `__init__`

```python
__init__(app)
```

Создает listener для режима двойного нажатия Command.

Args:
    app: Экземпляр приложения, у которого будет вызван toggle.

#### `on_key_press`

```python
on_key_press(key)
```

Обрабатывает нажатие правой клавиши Command.

Args:
    key: Объект клавиши из pynput.

#### `on_key_release`

```python
on_key_release(key)
```

Игнорирует отпускание клавиши в этом режиме.

Args:
    key: Объект клавиши из pynput.

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
__init__(recorder, model_name, hotkey_status, languages = None, max_time = None, key_combination = None, secondary_hotkey_status = None, secondary_key_combination = None)
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

### `normalize_key_name`

```python
normalize_key_name(raw_name)
```

Нормализует имя клавиши к каноническому виду.

Поддерживает человекочитаемые алиасы (Ctrl, Control, Option, Command)
и приводит регистр к нижнему.

Args:
    raw_name: Строковое имя клавиши, например `Ctrl`, `cmd_l` или `T`.

Returns:
    Нормализованное имя клавиши.

### `parse_key`

```python
parse_key(key_name)
```

Преобразует строковое имя клавиши в объект pynput.

Args:
    key_name: Имя клавиши, например `cmd_l`, `alt` или `space`.

Returns:
    Объект клавиши или код символа, который понимает pynput.

### `normalize_key_combination`

```python
normalize_key_combination(key_combination)
```

Нормализует строку комбинации клавиш к внутреннему формату.

Args:
    key_combination: Строка вида `cmd_l+alt` или `Command+Option+space`.

Returns:
    Нормализованная строка комбинации клавиш.

Raises:
    ValueError: Если в комбинации меньше двух клавиш.

### `parse_key_combination`

```python
parse_key_combination(key_combination)
```

Разбирает строку с комбинацией клавиш.

Args:
    key_combination: Строка вида `cmd_l+alt`, `ctrl+shift+alt+t`
        или `Ctrl+Shift+Alt+T`.

Returns:
    Кортеж объектов клавиш в том порядке, в котором они указаны.

Raises:
    ValueError: Если в комбинации меньше двух клавиш.

### `format_max_time_status`

```python
format_max_time_status(max_time)
```

Преобразует лимит длительности записи в строку для меню.

Args:
    max_time: Максимальная длительность записи в секундах.

Returns:
    Человекочитаемая строка ограничения.

### `microphone_menu_title`

```python
microphone_menu_title(device_info)
```

Формирует подпись микрофона для меню приложения.

### `list_input_devices`

```python
list_input_devices()
```

Возвращает список доступных устройств ввода из PyAudio.

### `hotkey_name_matches`

```python
hotkey_name_matches(expected_name, actual_name)
```

Проверяет, считаются ли два строковых имени клавиш эквивалентными.

Args:
    expected_name: Имя клавиши из конфигурации хоткея.
    actual_name: Имя клавиши, полученное из системного события.

Returns:
    True, если клавиши эквивалентны.

### `format_hotkey_status`

```python
format_hotkey_status(key_combination = None, *, use_double_cmd = False)
```

Преобразует настройку хоткея в строку для меню.

Args:
    key_combination: Строка комбинации клавиш.
    use_double_cmd: Флаг режима двойного нажатия правой Command.

Returns:
    Человекочитаемая строка хоткея.

### `capture_hotkey_combination`

```python
capture_hotkey_combination(title, message, current_combination = '')
```

Открывает модальное окно для захвата комбинации клавиш по нажатию.

Показывает NSAlert с текстовым полем, которое отображает текущую
комбинацию по мере нажатия клавиш. Пользователь нажимает модификаторы
и обычную клавишу, комбинация фиксируется и показывается в поле.

Args:
    title: Заголовок диалогового окна.
    message: Подсказка для пользователя.
    current_combination: Текущая комбинация для отображения по умолчанию.

Returns:
    Нормализованную строку комбинации клавиш или None, если отменено.

### `parse_args`

```python
parse_args()
```

Разбирает аргументы командной строки.

Returns:
    Пространство имен argparse с настройками запуска приложения.

Raises:
    SystemExit: Если передана некорректная комбинация клавиш.
    ValueError: Если выбран несовместимый язык для модели с суффиксом `.en`.

### `main`

```python
main()
```

Запускает приложение диктовки и глобальные обработчики клавиш.

## Внутренние функции

### `_event_key_name_static`

```python
_event_key_name_static(event)
```

_Внутренняя функция._

Извлекает имя обычной клавиши из NSEvent.
