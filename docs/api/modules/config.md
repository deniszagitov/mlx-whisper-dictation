# Конфигурация

Исходный файл: `src/config.py`

Константы и настройки приложения Dictator.

Содержит все конфигурационные значения, пресеты и хелперы для работы
с NSUserDefaults.

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
- `DEFAULTS_KEY_PASTE_CGEVENT` = `'paste_method_cgevent'`
- `DEFAULTS_KEY_PASTE_AX` = `'paste_method_ax'`
- `DEFAULTS_KEY_PASTE_CLIPBOARD` = `'paste_method_clipboard'`
- `DEFAULTS_KEY_HISTORY` = `'transcription_history'`
- `DEFAULTS_KEY_PRIVATE_MODE` = `'private_mode'`
- `DEFAULTS_KEY_TOTAL_TOKENS` = `'total_token_usage'`
- `MAX_HISTORY_SIZE` = `20`
- `HISTORY_DISPLAY_LENGTH` = `100`
- `CGEVENT_UNICODE_CHUNK_SIZE` = `20`
- `CGEVENT_CHUNK_DELAY` = `0.005`
- `CLIPBOARD_RESTORE_DELAY` = `0.15`
- `DEFAULT_LLM_MODEL_NAME` = `'mlx-community/Huihui-Qwen3.5-4B-Claude-4.6-Opus-abliterated-6bit'`
- `LLM_MAX_TOKENS` = `150`
- `LLM_RESPONSE_CHAR_LIMIT` = `180`
- `LLM_NOTIFICATION_CHAR_LIMIT` = `LLM_RESPONSE_CHAR_LIMIT`
- `DOWNLOAD_COMPLETE_PCT` = `100`
- `DEFAULTS_KEY_MODEL` = `'selected_model'`
- `DEFAULTS_KEY_LANGUAGE` = `'selected_language'`
- `DEFAULTS_KEY_INPUT_DEVICE_INDEX` = `'input_device_index'`
- `DEFAULTS_KEY_MAX_TIME` = `'max_recording_seconds'`
- `DEFAULTS_KEY_PRIMARY_HOTKEY` = `'primary_hotkey'`
- `DEFAULTS_KEY_SECONDARY_HOTKEY` = `'secondary_hotkey'`
- `DEFAULTS_KEY_LLM_HOTKEY` = `'llm_hotkey'`
- `DEFAULTS_KEY_LLM_PROMPT` = `'llm_prompt_preset'`
- `DEFAULTS_KEY_LLM_CLIPBOARD` = `'llm_clipboard_enabled'`
- `DEFAULTS_KEY_RECORDING_NOTIFICATION` = `'show_recording_notification'`
- `DEFAULTS_KEY_PERFORMANCE_MODE` = `'performance_mode'`
- `DEFAULTS_KEY_MICROPHONE_PROFILES` = `'microphone_profiles'`
- `MAX_MICROPHONE_PROFILES` = `10`
- `STATUS_LLM_PROCESSING` = `'llm_processing'`
- `PERFORMANCE_MODE_NORMAL` = `'normal'`
- `PERFORMANCE_MODE_FAST` = `'fast'`
- `DEFAULT_PERFORMANCE_MODE` = `PERFORMANCE_MODE_NORMAL`
- `PERFORMANCE_MODE_LABELS` = `{PERFORMANCE_MODE_NORMAL: 'Обычный', PERFORMANCE_MODE_FAST: 'Быстрый'}`
- `LLM_PROMPT_PRESETS` = `{'Универсальный помощник': 'ПРАВИЛА: отвечай ОДНИМ предложением, максимум 180 символов. НЕ используй markdown, списки, нумерацию, заголовки. НЕ показывай анализ, рассуждения, черновик, ограничения или служебные шаги. Верни только готовое красивое сообщение plain text; можно добавить 1 уместный эмодзи.', 'Исправь текст': 'ПРАВИЛА: верни ТОЛЬКО исправленный текст, ничего больше. НЕ добавляй комментариев, пояснений, markdown. Максимум 180 символов. Если текст корректен — верни его как есть.', 'Переведи на English': 'RULES: return ONLY the English translation, nothing else. NO comments, NO markdown, NO explanations. Max 180 characters. Plain text only.', 'Переведи на русский': 'ПРАВИЛА: верни ТОЛЬКО перевод на русский, ничего больше. БЕЗ комментариев, БЕЗ markdown. Максимум 180 символов. Только plain text.', 'Резюме': 'ПРАВИЛА: сделай резюме ОДНИМ предложением, максимум 180 символов. БЕЗ markdown, БЕЗ списков, БЕЗ заголовков. Только plain text.'}`
- `DEFAULT_LLM_PROMPT_NAME` = `'Универсальный помощник'`
- `KNOWN_HALLUCINATIONS` = `{'thank you.', 'thank you', 'спасибо за внимание', 'продолжение следует...', 'продолжение следует', 'спасибо за просмотр'}`

## Публичные функции

### `format_max_time_status`

```python
format_max_time_status(max_time)
```

Преобразует лимит длительности записи в строку для меню.

## Внутренние функции

### `_load_defaults_bool`

```python
_load_defaults_bool(key, fallback)
```

_Внутренняя функция._

Читает булево значение из NSUserDefaults.

Если ключ ещё не был записан, возвращает fallback.

Args:
    key: Строковый ключ в NSUserDefaults.
    fallback: Значение по умолчанию, если ключ отсутствует.

Returns:
    Сохранённое значение или fallback.

### `_save_defaults_bool`

```python
_save_defaults_bool(key, value)
```

_Внутренняя функция._

Сохраняет булево значение в NSUserDefaults.

Args:
    key: Строковый ключ.
    value: Булево значение для сохранения.

### `_load_defaults_list`

```python
_load_defaults_list(key)
```

_Внутренняя функция._

Читает список строк из NSUserDefaults.

Args:
    key: Строковый ключ.

Returns:
    Список строк или пустой список, если ключ отсутствует.

### `_save_defaults_list`

```python
_save_defaults_list(key, value)
```

_Внутренняя функция._

Сохраняет список строк в NSUserDefaults.

Args:
    key: Строковый ключ.
    value: Список строк для сохранения.

### `_load_defaults_int`

```python
_load_defaults_int(key, fallback)
```

_Внутренняя функция._

Читает целое значение из NSUserDefaults.

Args:
    key: Строковый ключ в NSUserDefaults.
    fallback: Значение по умолчанию, если ключ отсутствует.

Returns:
    Сохранённое целое значение или fallback.

### `_save_defaults_int`

```python
_save_defaults_int(key, value)
```

_Внутренняя функция._

Сохраняет целое значение в NSUserDefaults.

Args:
    key: Строковый ключ.
    value: Целое значение для сохранения.

### `_load_defaults_str`

```python
_load_defaults_str(key, fallback = None)
```

_Внутренняя функция._

Читает строковое значение из NSUserDefaults.

### `_save_defaults_str`

```python
_save_defaults_str(key, value)
```

_Внутренняя функция._

Сохраняет строковое значение в NSUserDefaults.

### `_load_defaults_max_time`

```python
_load_defaults_max_time(fallback)
```

_Внутренняя функция._

Читает лимит записи из NSUserDefaults.

### `_save_defaults_max_time`

```python
_save_defaults_max_time(value)
```

_Внутренняя функция._

Сохраняет лимит записи в NSUserDefaults.

### `_load_defaults_input_device_index`

```python
_load_defaults_input_device_index()
```

_Внутренняя функция._

Читает индекс сохранённого микрофона из NSUserDefaults.

### `_save_defaults_input_device_index`

```python
_save_defaults_input_device_index(value)
```

_Внутренняя функция._

Сохраняет индекс выбранного микрофона в NSUserDefaults.

### `_remove_defaults_key`

```python
_remove_defaults_key(key)
```

_Внутренняя функция._

Удаляет ключ из NSUserDefaults.

### `_performance_mode_label`

```python
_performance_mode_label(performance_mode)
```

_Внутренняя функция._

Возвращает человекочитаемое имя режима работы.

### `_normalize_performance_mode`

```python
_normalize_performance_mode(performance_mode)
```

_Внутренняя функция._

Нормализует идентификатор режима работы.
