# Распознавание и вставка

Исходный файл: `src/use_cases/transcription.py`

Use case распознавания речи, вставки текста и истории.

## Константы

- `LOGGER` = `logging.getLogger(__name__)`

## Классы

## `_DisabledDiagnosticsStore`

Null-object для сценариев, где сохранение диагностических файлов отключено.

### Методы

#### `artifact_stem`

```python
artifact_stem() -> str
```

Возвращает псевдо-имя диагностической группы.

#### `save_audio_recording`

```python
save_audio_recording(stem: str, audio_data: npt.NDArray[np.float32], diagnostics: AudioDiagnostics | dict[str, Any]) -> None
```

Игнорирует сохранение WAV-артефактов.

#### `save_transcription_artifacts`

```python
save_transcription_artifacts(stem: str, diagnostics: AudioDiagnostics | dict[str, Any], result: Any = None, text: str = '', error_message: str | None = None) -> None
```

Игнорирует сохранение диагностических результатов.

## `_InMemorySettingsStore`

Простейшее in-memory хранилище настроек для fallback-сценариев.

### Методы

#### `__init__`

```python
__init__() -> None
```

Конструктор класса.

## `TranscriptionUseCases`

Распознаёт аудио, вставляет результат и ведёт историю.

Attributes:
    diagnostics_store: Adapter сохранения диагностических артефактов.
    model_name: Имя или путь к модели MLX Whisper.
    paste_cgevent_enabled: Включён ли метод прямого ввода через CGEvent Unicode.
    paste_ax_enabled: Включён ли метод ввода через Accessibility API.
    paste_clipboard_enabled: Включён ли метод ввода через буфер обмена (Cmd+V).
    history: Список ранее распознанных текстов.
    history_callback: Callback для уведомления UI об изменении истории.

### Свойства

#### `paste_cgevent_enabled`

```python
paste_cgevent_enabled() -> bool
```

Возвращает флаг метода вставки через CGEvent.

#### `paste_ax_enabled`

```python
paste_ax_enabled() -> bool
```

Возвращает флаг метода вставки через Accessibility API.

#### `paste_clipboard_enabled`

```python
paste_clipboard_enabled() -> bool
```

Возвращает флаг метода вставки через буфер обмена.

#### `capitalize_first_letter_enabled`

```python
capitalize_first_letter_enabled() -> bool
```

Возвращает флаг правила заглавной буквы после распознавания.

#### `remove_trailing_period_for_single_sentence_enabled`

```python
remove_trailing_period_for_single_sentence_enabled() -> bool
```

Возвращает флаг удаления точки в конце одного предложения.

#### `restore_trailing_period_on_next_dictation_enabled`

```python
restore_trailing_period_on_next_dictation_enabled() -> bool
```

Возвращает флаг автоточки перед следующей диктовкой.

#### `gain_normalization_enabled`

```python
gain_normalization_enabled() -> bool
```

Возвращает флаг бережной нормализации аудио.

#### `audio_artifact_cleanup_enabled`

```python
audio_artifact_cleanup_enabled() -> bool
```

Возвращает флаг автоочистки WAV-артефактов записи.

#### `llm_clipboard_enabled`

```python
llm_clipboard_enabled() -> bool
```

Возвращает флаг использования буфера обмена для LLM.

#### `private_mode_enabled`

```python
private_mode_enabled() -> bool
```

Возвращает флаг private mode.

#### `total_tokens`

```python
total_tokens() -> int
```

Возвращает общий счётчик токенов.

### Методы

#### `__init__`

```python
__init__(model_name: str, settings_store: SettingsStoreProtocol | None = None, preferences: TranscriberPreferences | None = None, diagnostics_store: Any | None = None, audio_preprocessor: Callable[..., PreprocessedAudio] | None = None, transcription_runner: Callable[[npt.NDArray[np.float32], str, str | None], dict[str, Any]] | None = None, type_text_via_cgevent: Callable[[str], None] | None = None, insert_text_via_ax: Callable[[str], None] | None = None, send_cmd_v: Callable[[], None] | None = None, clipboard_reader: Callable[[], str | None] | None = None, clipboard_writer: Callable[[str], None] | None = None, history_item_loader: Callable[[], list[Any]] | None = None, history_record_saver: Callable[[list[HistoryRecord]], None] | None = None, notify_user: Callable[[str, str], None] | None = None, is_accessibility_trusted: Callable[[], bool] | None = None, get_input_monitoring_status: Callable[[], bool | None] | None = None, request_accessibility_permission: Callable[[], bool] | None = None, request_input_monitoring_permission: Callable[[], bool | None] | None = None, warn_missing_accessibility_permission: Callable[[], None] | None = None, warn_missing_input_monitoring_permission: Callable[[], None] | None = None, frontmost_application_info: Callable[[], dict[str, str | int] | None] | None = None) -> None
```

Создаёт use case распознавания и вставки.

Args:
    model_name: Имя модели Hugging Face или локальный путь к модели.
    settings_store: Хранилище пользовательских настроек и флагов runtime.
    preferences: Нормализованные настройки методов вставки и private mode.
    diagnostics_store: Необязательный adapter сохранения диагностических файлов.
    audio_preprocessor: Необязательный runtime-preprocessor записанного аудио.
    transcription_runner: Необязательный runtime-вызов Whisper.
    type_text_via_cgevent: Необязательный runtime-ввод через CGEvent.
    insert_text_via_ax: Необязательный runtime-ввод через Accessibility API.
    send_cmd_v: Необязательный runtime для Cmd+V.
    clipboard_reader: Необязательное чтение системного буфера обмена.
    clipboard_writer: Необязательная запись в системный буфер обмена.
    history_item_loader: Необязательное чтение сырых записей истории.
    history_record_saver: Необязательное сохранение нормализованной истории.
    notify_user: Необязательное системное уведомление для ошибок и fallback.
    is_accessibility_trusted: Необязательная проверка права Accessibility.
    get_input_monitoring_status: Необязательная проверка права Input Monitoring.
    request_accessibility_permission: Необязательный повторный запрос права Accessibility.
    request_input_monitoring_permission: Необязательный повторный запрос права Input Monitoring.
    warn_missing_accessibility_permission: Необязательное предупреждение о недостающем Accessibility.
    warn_missing_input_monitoring_permission: Необязательное предупреждение о недостающем Input Monitoring.
    frontmost_application_info: Необязательное чтение текущего активного приложения.

#### `_sync_diagnostics_cleanup_setting`

```python
_sync_diagnostics_cleanup_setting() -> None
```

_Внутренняя функция._

Синхронизирует настройку автоочистки с diagnostics store.

#### `set_private_mode`

```python
set_private_mode(enabled: object) -> None
```

Переключает private mode для истории текста.

В private mode история не загружается из persistence-адаптера и не
сохраняется между перезапусками. Уже сохранённая история остаётся
в defaults, но скрывается до выхода из private mode.

Args:
    enabled: Нужно ли включить private mode.

#### `_current_time`

```python
_current_time() -> float
```

_Внутренняя функция._

Возвращает текущее время в Unix timestamp.

#### `_sync_history_state`

```python
_sync_history_state() -> None
```

_Внутренняя функция._

Синхронизирует публичный список истории с внутренними записями.

#### `_sync_internal_history_from_public_list`

```python
_sync_internal_history_from_public_list() -> None
```

_Внутренняя функция._

Подхватывает прямые изменения self.history, используемые в тестах.

#### `_prune_expired_history`

```python
_prune_expired_history() -> bool
```

_Внутренняя функция._

Удаляет записи истории старше 24 часов.

#### `_reload_persisted_history`

```python
_reload_persisted_history() -> None
```

_Внутренняя функция._

Перечитывает историю из persistence-адаптера и сразу удаляет просроченные записи.

#### `prune_expired_history`

```python
prune_expired_history() -> bool
```

Публично очищает историю старше 24 часов и сохраняет результат.

#### `_notify_token_usage_changed`

```python
_notify_token_usage_changed() -> None
```

_Внутренняя функция._

Вызывает callback обновления UI после изменения счётчика токенов.

#### `add_token_usage`

```python
add_token_usage(token_count: int) -> None
```

Добавляет подтверждённое количество токенов к общему счётчику.

#### `_normalize_frontmost_application_signature`

```python
_normalize_frontmost_application_signature(app_info: dict[str, str | int] | None) -> tuple[str, int, str] | None
```

_Внутренняя функция._

Нормализует краткую информацию об активном приложении для сравнения.

#### `_frontmost_application_signature`

```python
_frontmost_application_signature() -> tuple[str, int, str] | None
```

_Внутренняя функция._

Возвращает сигнатуру активного приложения через runtime-hook.

#### `_reset_pending_period_prefix_for_next_dictation`

```python
_reset_pending_period_prefix_for_next_dictation() -> None
```

_Внутренняя функция._

Сбрасывает состояние автоматической цепочки предложений.

#### `_remember_period_prefix_for_next_dictation`

```python
_remember_period_prefix_for_next_dictation(*, established: bool) -> None
```

_Внутренняя функция._

Запоминает или продлевает цепочку автоматического связывания предложений.

#### `_trailing_period_was_removed`

```python
_trailing_period_was_removed(text: str) -> bool
```

_Внутренняя функция._

Проверяет, сняла ли постобработка финальную точку у текущего текста.

#### `_text_ends_with_terminal_punctuation`

```python
_text_ends_with_terminal_punctuation(text: str) -> bool
```

_Внутренняя функция._

Проверяет, заканчивается ли текст завершающим знаком препинания.

#### `_ensure_terminal_punctuation`

```python
_ensure_terminal_punctuation(text: str) -> str
```

_Внутренняя функция._

Добавляет завершающую точку, если фрагмент её не содержит.

#### `_apply_pending_period_prefix`

```python
_apply_pending_period_prefix(text: str) -> str
```

_Внутренняя функция._

Форматирует продолжение цепочки предложений между диктовками.

#### `handle_keyboard_activity`

```python
handle_keyboard_activity() -> None
```

Сбрасывает продолжение фразы после любого ручного ввода с клавиатуры.

#### `handle_frontmost_application_change`

```python
handle_frontmost_application_change(app_info: dict[str, str | int] | None) -> None
```

Сбрасывает продолжение фразы, если пользователь ушёл в другое приложение.

#### `_type_text_via_cgevent`

```python
_type_text_via_cgevent(text: str) -> None
```

_Внутренняя функция._

Вставляет текст через отправку Unicode-символов посредством CGEvent.

Разбивает текст на пакеты и отправляет каждый пакет как пару
keyDown/keyUp событий с прикреплённой Unicode-строкой.
Не трогает буфер обмена.

Args:
    text: Текст для ввода.

Raises:
    RuntimeError: Если не удалось создать источник событий.

#### `_insert_text_via_ax`

```python
_insert_text_via_ax(text: str) -> None
```

_Внутренняя функция._

Вставляет текст через macOS Accessibility API.

Находит сфокусированный элемент UI и записывает текст
через атрибут kAXSelectedTextAttribute, что вставляет текст
в позицию курсора или заменяет выделение.
Не трогает буфер обмена.

Args:
    text: Текст для вставки.

Raises:
    RuntimeError: Если не удалось получить сфокусированный элемент
        или записать текст через Accessibility API.

#### `_read_clipboard`

```python
_read_clipboard() -> str | None
```

_Внутренняя функция._

Читает текст из системного буфера обмена через runtime-адаптер.

#### `_copy_to_clipboard`

```python
_copy_to_clipboard(text: str) -> None
```

_Внутренняя функция._

Копирует текст в системный буфер обмена через runtime-адаптер.

#### `_load_history_items`

```python
_load_history_items() -> list[Any]
```

_Внутренняя функция._

Читает сырые записи истории через runtime-адаптер.

#### `_save_history_records`

```python
_save_history_records(records: list[HistoryRecord]) -> None
```

_Внутренняя функция._

Сохраняет нормализованные записи истории через runtime-адаптер.

#### `_notify_user`

```python
_notify_user(title: str, message: str) -> None
```

_Внутренняя функция._

Показывает системное уведомление через injected runtime-hook.

#### `_is_accessibility_trusted`

```python
_is_accessibility_trusted() -> bool
```

_Внутренняя функция._

Проверяет право Accessibility через injected runtime-hook.

#### `_get_input_monitoring_status`

```python
_get_input_monitoring_status() -> bool | None
```

_Внутренняя функция._

Проверяет право Input Monitoring через injected runtime-hook.

#### `_request_accessibility_permission`

```python
_request_accessibility_permission() -> bool
```

_Внутренняя функция._

Повторно запрашивает право Accessibility через runtime-hook.

#### `_request_input_monitoring_permission`

```python
_request_input_monitoring_permission() -> bool | None
```

_Внутренняя функция._

Повторно запрашивает право Input Monitoring через runtime-hook.

#### `_warn_missing_accessibility_permission`

```python
_warn_missing_accessibility_permission() -> None
```

_Внутренняя функция._

Вызывает предупреждение о недостающем Accessibility.

#### `_warn_missing_input_monitoring_permission`

```python
_warn_missing_input_monitoring_permission() -> None
```

_Внутренняя функция._

Вызывает предупреждение о недостающем Input Monitoring.

#### `_copy_result_to_clipboard_fallback`

```python
_copy_result_to_clipboard_fallback(text: str) -> bool
```

_Внутренняя функция._

Пытается сохранить результат в буфер обмена для ручной вставки.

#### `_fallback_storage_message`

```python
_fallback_storage_message(*, clipboard_saved: bool) -> str
```

_Внутренняя функция._

Формирует хвост пользовательского сообщения о сохранённом результате.

#### `_paste_via_clipboard`

```python
_paste_via_clipboard(text: str) -> None
```

_Внутренняя функция._

Вставляет текст через буфер обмена с последующим восстановлением.

Сохраняет текущее содержимое буфера обмена, записывает новый текст,
отправляет Cmd+V, а затем восстанавливает предыдущее содержимое.

Args:
    text: Текст для вставки.

Raises:
    RuntimeError: Если не удалось создать keyboard events.

#### `_send_cmd_v`

```python
_send_cmd_v() -> None
```

_Внутренняя функция._

Отправляет системные keyboard events для Cmd+V.

#### `add_to_history`

```python
add_to_history(text: str) -> None
```

Добавляет распознанный текст в историю.

Вставляет текст в начало списка, удаляет записи старше 24 часов,
сохраняет через persistence-адаптер и вызывает callback для обновления UI.

Args:
    text: Распознанный текст.

#### `_run_transcription`

```python
_run_transcription(audio_data: npt.NDArray[np.float32], language: str | None) -> dict[str, Any]
```

_Внутренняя функция._

Запускает один проход распознавания с заданными параметрами языка.

#### `_asr_backend_name`

```python
_asr_backend_name() -> str
```

_Внутренняя функция._

Возвращает короткое имя ASR backend-а по текущей модели.

#### `_preprocess_audio`

```python
_preprocess_audio(audio_data: Any, language: str | None) -> PreprocessedAudio
```

_Внутренняя функция._

Приводит записанное аудио к контракту ASR-модели.

#### `_save_recording_artifacts`

```python
_save_recording_artifacts(stem: str, raw_audio: Any, preprocessed_audio: PreprocessedAudio, diagnostics: dict[str, Any]) -> Any
```

_Внутренняя функция._

Сохраняет raw/final WAV-артефакты, если store это поддерживает.

#### `_build_text_postprocessor`

```python
_build_text_postprocessor() -> TranscriptionPostprocessor
```

_Внутренняя функция._

Собирает цепочку включённых правил постобработки распознанного текста.

#### `_postprocess_transcribed_text`

```python
_postprocess_transcribed_text(text: str) -> str
```

_Внутренняя функция._

Применяет постобработку к непустому результату распознавания.

#### `transcribe`

```python
transcribe(audio_data: Any, language: str | None = None) -> None
```

Распознает аудио и вставляет результат в активное приложение.

Args:
    audio_data: Записанное аудио или legacy-массив float32.
    language: Необязательный код языка для улучшения распознавания.

#### `transcribe_to_text`

```python
transcribe_to_text(audio_data: Any, language: str | None = None) -> str | None
```

Распознаёт аудио через Whisper и возвращает текст без вставки.

Выполняет диагностику аудио, один проход Whisper, учёт токенов
и проверку на галлюцинации. Не вставляет текст и не работает с LLM.

Args:
    audio_data: Записанное аудио или legacy-массив float32.
    language: Необязательный код языка для улучшения распознавания.

Returns:
    Распознанный текст или None, если речь не обнаружена
    или результат отброшен как галлюцинация.

## Внутренние функции

### `_legacy_preprocess_audio`

```python
_legacy_preprocess_audio(audio_input: Any, language: str | None, *, enable_gain_normalization: bool = True) -> PreprocessedAudio
```

_Внутренняя функция._

Поддерживает старый ndarray-контракт без infrastructure-preprocessor.

### `_noop_notify_user`

```python
_noop_notify_user(_title: str, _message: str) -> None
```

_Внутренняя функция._

Игнорирует системные уведомления в тестовых и headless-сценариях.

### `_default_accessibility_status`

```python
_default_accessibility_status() -> bool
```

_Внутренняя функция._

Считает Accessibility доступным, если integration-hook не подключён.

### `_default_input_monitoring_status`

```python
_default_input_monitoring_status() -> bool | None
```

_Внутренняя функция._

Считает Input Monitoring доступным, если integration-hook не подключён.

### `_default_accessibility_request`

```python
_default_accessibility_request() -> bool
```

_Внутренняя функция._

Возвращает успешный результат для request-hook по умолчанию.

### `_default_input_monitoring_request`

```python
_default_input_monitoring_request() -> bool | None
```

_Внутренняя функция._

Возвращает успешный результат для request-hook по умолчанию.

### `_noop_permission_warning`

```python
_noop_permission_warning() -> None
```

_Внутренняя функция._

Игнорирует предупреждение о недостающих правах.
