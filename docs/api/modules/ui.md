# Menu bar UI

Исходный файл: `src/adapters/ui.py`

UI menu bar приложения Dictator.

Содержит StatusBarApp — адаптер menu bar UI к DictationApp, а также
вспомогательную функцию prompt_text для простых диалогов ввода.

## Константы

- `LOGGER` = `logging.getLogger(__name__)`
- `APPKIT_QUIT_DEFER_SECONDS` = `0.01`

## Классы

## `StatusBarApp`

Menu bar UI-адаптер для контроллера диктовки.

### Свойства

#### `state`

```python
state() -> str
```

Возвращает текущее состояние приложения.

#### `started`

```python
started() -> bool
```

Возвращает флаг активной записи.

#### `elapsed_time`

```python
elapsed_time() -> int
```

Возвращает длительность текущей записи.

#### `model_name`

```python
model_name() -> str
```

Возвращает краткое имя текущей модели.

#### `model_repo`

```python
model_repo() -> str
```

Возвращает полный идентификатор текущей модели.

#### `hotkey_status`

```python
hotkey_status() -> str
```

Возвращает display-строку основного хоткея.

#### `secondary_hotkey_status`

```python
secondary_hotkey_status() -> str
```

Возвращает display-строку дополнительного хоткея.

#### `llm_hotkey_status`

```python
llm_hotkey_status() -> str
```

Возвращает display-строку LLM-хоткея.

#### `zipper_hotkey_status`

```python
zipper_hotkey_status() -> str
```

Возвращает display-строку Zipper-хоткея.

#### `zipper_enabled`

```python
zipper_enabled() -> bool
```

Возвращает флаг включения Zipper.

#### `zipper_status`

```python
zipper_status() -> str
```

Возвращает статус Zipper.

#### `zipper_debug_panel_enabled`

```python
zipper_debug_panel_enabled() -> bool
```

Возвращает флаг debug-панели Zipper.

#### `rsvp_hotkey_status`

```python
rsvp_hotkey_status() -> str
```

Возвращает display-строку RSVP-хоткея.

#### `tts_hotkey_status`

```python
tts_hotkey_status() -> str
```

Возвращает display-строку TTS-хоткея.

#### `llm_prompt_name`

```python
llm_prompt_name() -> str
```

Возвращает имя активного LLM-промпта.

#### `llm_model_name`

```python
llm_model_name() -> str
```

Возвращает краткое имя текущей LLM-модели.

#### `llm_model_options`

```python
llm_model_options() -> list[str]
```

Возвращает список доступных LLM-моделей.

#### `reader_rsvp_wpm`

```python
reader_rsvp_wpm() -> int
```

Возвращает скорость RSVP.

#### `reader_rsvp_chunk_size`

```python
reader_rsvp_chunk_size() -> int
```

Возвращает размер RSVP chunk-а.

#### `reader_rsvp_font_size`

```python
reader_rsvp_font_size() -> int
```

Возвращает размер шрифта RSVP.

#### `reader_tts_rate_multiplier`

```python
reader_tts_rate_multiplier() -> float
```

Возвращает множитель скорости TTS.

#### `reader_tts_voice_id`

```python
reader_tts_voice_id() -> str | None
```

Возвращает идентификатор выбранного голоса TTS.

#### `reader_tts_max_minutes`

```python
reader_tts_max_minutes() -> int
```

Возвращает лимит длительности TTS.

#### `reader_tts_engine`

```python
reader_tts_engine() -> str
```

Возвращает выбранный backend TTS.

#### `reader_tts_mlx_model`

```python
reader_tts_mlx_model() -> str
```

Возвращает выбранную MLX TTS-модель.

#### `reader_tts_mlx_voice_description`

```python
reader_tts_mlx_voice_description() -> str
```

Возвращает описание MLX-голоса.

#### `reader_tts_tone_instruction`

```python
reader_tts_tone_instruction() -> str
```

Возвращает свободную инструкцию по интонации TTS.

#### `reader_preprocess_enabled`

```python
reader_preprocess_enabled() -> bool
```

Возвращает флаг LLM-предобработки reader.

#### `performance_mode`

```python
performance_mode() -> str
```

Возвращает текущий режим производительности.

#### `max_time`

```python
max_time() -> float | None
```

Возвращает лимит записи.

#### `max_time_options`

```python
max_time_options() -> list[float | None]
```

Возвращает доступные лимиты записи.

#### `model_options`

```python
model_options() -> list[str]
```

Возвращает список доступных моделей.

#### `languages`

```python
languages() -> list[str] | None
```

Возвращает список доступных языков.

#### `current_language`

```python
current_language() -> str | None
```

Возвращает текущий язык распознавания.

#### `input_devices`

```python
input_devices() -> list[Any]
```

Возвращает список доступных устройств ввода.

#### `current_input_device`

```python
current_input_device() -> Any
```

Возвращает текущее устройство ввода.

#### `audio_profile_name`

```python
audio_profile_name() -> str
```

Возвращает активный аудиопрофиль.

#### `high_quality_mac_builtin_enabled`

```python
high_quality_mac_builtin_enabled() -> bool
```

Возвращает флаг MacBook HQ-профиля.

#### `permission_status`

```python
permission_status() -> dict[str, bool | None]
```

Возвращает статусы системных разрешений.

#### `microphone_profiles`

```python
microphone_profiles() -> list[MicrophoneProfile]
```

Возвращает быстрые профили микрофона.

#### `show_recording_notification`

```python
show_recording_notification() -> bool
```

Возвращает флаг уведомления о старте записи.

#### `show_recording_overlay`

```python
show_recording_overlay() -> bool
```

Возвращает флаг показа overlay-индикатора.

#### `show_recording_time_in_menu_bar`

```python
show_recording_time_in_menu_bar() -> bool
```

Возвращает флаг отображения времени записи в menu bar.

#### `private_mode_enabled`

```python
private_mode_enabled() -> bool
```

Возвращает флаг приватного режима.

#### `paste_cgevent_enabled`

```python
paste_cgevent_enabled() -> bool
```

Возвращает флаг метода вставки через CGEvent.

#### `paste_ax_enabled`

```python
paste_ax_enabled() -> bool
```

Возвращает флаг метода вставки через AX API.

#### `paste_clipboard_enabled`

```python
paste_clipboard_enabled() -> bool
```

Возвращает флаг метода вставки через буфер обмена.

#### `llm_clipboard_enabled`

```python
llm_clipboard_enabled() -> bool
```

Возвращает флаг использования буфера обмена для LLM.

#### `capitalize_first_letter_enabled`

```python
capitalize_first_letter_enabled() -> bool
```

Возвращает флаг правила заглавной буквы.

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

Возвращает флаг автоочистки WAV-записей.

#### `history`

```python
history() -> list[str]
```

Возвращает историю распознанных текстов.

#### `total_tokens`

```python
total_tokens() -> int
```

Возвращает суммарный счётчик токенов.

#### `recording_overlay`

```python
recording_overlay() -> Any
```

Возвращает overlay-индикатор записи.

#### `key_listener`

```python
key_listener() -> Any
```

Возвращает runtime-listener основных хоткеев.

#### `start_time`

```python
start_time() -> float | None
```

Возвращает время старта текущей записи.

#### `_primary_key_combination`

```python
_primary_key_combination() -> str
```

_Внутренняя функция._

Возвращает основной хоткей во внутреннем формате.

#### `_secondary_key_combination`

```python
_secondary_key_combination() -> str
```

_Внутренняя функция._

Возвращает дополнительный хоткей во внутреннем формате.

#### `_llm_key_combination`

```python
_llm_key_combination() -> str
```

_Внутренняя функция._

Возвращает LLM-хоткей во внутреннем формате.

### Методы

#### `__init__`

```python
__init__(app: StatusBarControllerProtocol) -> None
```

Создаёт menu bar приложение, привязанное к контроллеру диктовки.

#### `_find_menu_item`

```python
_find_menu_item(container: Any, title: str) -> Any
```

_Внутренняя функция._

Рекурсивно ищет пункт меню по заголовку.

#### `_menu_item`

```python
_menu_item(title: str) -> Any
```

_Внутренняя функция._

Возвращает пункт меню по заголовку.

#### `_ensure_quit_item_available`

```python
_ensure_quit_item_available() -> None
```

_Внутренняя функция._

Оставляет пункт «Выход» активным во всех состояниях menu bar.

#### `_state_label`

```python
_state_label() -> str
```

_Внутренняя функция._

Возвращает человекочитаемое имя текущего состояния.

#### `_format_input_device`

```python
_format_input_device() -> str
```

_Внутренняя функция._

Возвращает строку текущего микрофона для меню.

#### `_format_language`

```python
_format_language() -> str
```

_Внутренняя функция._

Возвращает строку текущего языка для меню.

#### `_model_menu_title`

```python
_model_menu_title(model_repo: str) -> str
```

_Внутренняя функция._

Возвращает подпись пункта меню модели.

#### `_llm_model_menu_title`

```python
_llm_model_menu_title(model_repo: str) -> str
```

_Внутренняя функция._

Возвращает подпись пункта меню LLM-модели.

#### `_max_time_menu_title`

```python
_max_time_menu_title(max_time_value: float | None) -> str
```

_Внутренняя функция._

Возвращает подпись пункта меню лимита записи.

#### `_permission_title`

```python
_permission_title(permission_name: str, permission_status: bool | None) -> str
```

_Внутренняя функция._

Формирует строку статуса разрешения для меню.

#### `_permissions_menu_title`

```python
_permissions_menu_title() -> str
```

_Внутренняя функция._

Возвращает короткий итог по состоянию системных разрешений.

#### `_format_total_tokens`

```python
_format_total_tokens(token_count: int) -> str
```

_Внутренняя функция._

Форматирует число токенов для отображения в меню.

#### `_token_usage_title`

```python
_token_usage_title() -> str
```

_Внутренняя функция._

Возвращает заголовок пункта меню со счётчиком токенов.

#### `_format_tts_rate`

```python
_format_tts_rate(rate_multiplier: float) -> str
```

_Внутренняя функция._

Форматирует множитель скорости TTS.

#### `_format_tts_engine`

```python
_format_tts_engine(engine: str) -> str
```

_Внутренняя функция._

Форматирует backend TTS для меню.

#### `_short_model_name`

```python
_short_model_name(model_name: str) -> str
```

_Внутренняя функция._

Возвращает короткое имя модели для меню.

#### `_format_tts_max_minutes`

```python
_format_tts_max_minutes(max_minutes: int) -> str
```

_Внутренняя функция._

Форматирует лимит длительности TTS.

#### `_refresh_token_usage_item`

```python
_refresh_token_usage_item() -> None
```

_Внутренняя функция._

Обновляет пункт меню со счётчиком токенов.

#### `_refresh_permission_items`

```python
_refresh_permission_items() -> None
```

_Внутренняя функция._

Обновляет пункты меню со статусами разрешений.

#### `_refresh_hotkey_items`

```python
_refresh_hotkey_items() -> None
```

_Внутренняя функция._

Обновляет подписи хоткеев в меню.

#### `_refresh_reader_tts_voice_menu`

```python
_refresh_reader_tts_voice_menu() -> None
```

_Внутренняя функция._

Пересобирает подменю голосов TTS для текущего backend-а.

#### `_refresh_reader_items`

```python
_refresh_reader_items() -> None
```

_Внутренняя функция._

Обновляет пункты меню reader-настроек.

#### `_refresh_selection_states`

```python
_refresh_selection_states() -> None
```

_Внутренняя функция._

Обновляет отметки выбранных пунктов меню.

#### `_refresh_input_device_menu`

```python
_refresh_input_device_menu() -> None
```

_Внутренняя функция._

Пересобирает подменю выбора микрофона.

#### `_refresh_microphone_profiles_menu`

```python
_refresh_microphone_profiles_menu() -> None
```

_Внутренняя функция._

Пересобирает подменю быстрых профилей микрофона.

#### `_refresh_title_and_status`

```python
_refresh_title_and_status() -> None
```

_Внутренняя функция._

Обновляет иконку и строку статуса в menu bar.

#### `_format_history_title`

```python
_format_history_title(text: str) -> str
```

_Внутренняя функция._

Форматирует текст для отображения в подменю истории.

#### `_refresh_history_menu`

```python
_refresh_history_menu() -> None
```

_Внутренняя функция._

Обновляет подменю истории текста.

#### `_apply_snapshot`

```python
_apply_snapshot(snapshot: AppSnapshot) -> None
```

_Внутренняя функция._

Применяет новый snapshot DictationApp к меню.

#### `_apply_download_status_snapshot`

```python
_apply_download_status_snapshot(snapshot: AppSnapshot) -> bool
```

_Внутренняя функция._

Быстро применяет частые snapshot-ы прогресса загрузки без перестройки меню.

#### `_apply_snapshot_on_main_thread`

```python
_apply_snapshot_on_main_thread(snapshot: AppSnapshot) -> None
```

_Внутренняя функция._

Переводит применение snapshot на главный поток, если callback пришёл из background thread.

#### `set_state`

```python
set_state(state: str) -> None
```

Делегирует изменение состояния в DictationApp.

#### `set_permission_status`

```python
set_permission_status(permission_name: str, status: bool | None) -> None
```

Делегирует изменение статуса разрешения в DictationApp.

#### `change_input_device`

```python
change_input_device(sender: rumps.MenuItem) -> None
```

Переключает текущее устройство ввода.

#### `change_language`

```python
change_language(sender: rumps.MenuItem) -> None
```

Переключает текущий язык распознавания.

#### `change_model`

```python
change_model(sender: rumps.MenuItem) -> None
```

Переключает модель распознавания.

#### `change_max_time`

```python
change_max_time(sender: rumps.MenuItem) -> None
```

Переключает лимит записи.

#### `add_current_microphone_profile`

```python
add_current_microphone_profile(_: object) -> None
```

Открывает диалог и добавляет профиль текущего микрофона.

#### `apply_microphone_profile`

```python
apply_microphone_profile(sender: rumps.MenuItem) -> None
```

Применяет сохранённый профиль микрофона.

#### `delete_microphone_profile`

```python
delete_microphone_profile(sender: rumps.MenuItem) -> None
```

Удаляет сохранённый профиль микрофона.

#### `change_hotkey`

```python
change_hotkey(_: object) -> None
```

Изменяет основной хоткей через DictationApp.

#### `change_secondary_hotkey`

```python
change_secondary_hotkey(_: object) -> None
```

Изменяет дополнительный хоткей через DictationApp.

#### `change_llm_hotkey`

```python
change_llm_hotkey(_: object) -> None
```

Изменяет LLM-хоткей через DictationApp.

#### `change_zipper_hotkey`

```python
change_zipper_hotkey(_: object) -> None
```

Изменяет Zipper-хоткей через DictationApp.

#### `change_rsvp_hotkey`

```python
change_rsvp_hotkey(_: object) -> None
```

Изменяет RSVP-хоткей через DictationApp.

#### `change_tts_hotkey`

```python
change_tts_hotkey(_: object) -> None
```

Изменяет TTS-хоткей через DictationApp.

#### `request_accessibility_access`

```python
request_accessibility_access(_: object) -> None
```

Повторно запрашивает Accessibility.

#### `request_input_monitoring_access`

```python
request_input_monitoring_access(_: object) -> None
```

Повторно запрашивает Input Monitoring.

#### `toggle_recording_notification`

```python
toggle_recording_notification(_sender: rumps.MenuItem) -> None
```

Переключает системное уведомление о старте записи.

#### `toggle_recording_overlay`

```python
toggle_recording_overlay(_sender: rumps.MenuItem) -> None
```

Переключает индикатор записи у курсора.

#### `toggle_recording_time_in_menu_bar`

```python
toggle_recording_time_in_menu_bar(_sender: rumps.MenuItem) -> None
```

Переключает показ времени записи в строке меню.

#### `toggle_high_quality_mac_builtin`

```python
toggle_high_quality_mac_builtin(_sender: rumps.MenuItem) -> None
```

Переключает автоматический MacBook HQ-профиль.

#### `toggle_gain_normalization`

```python
toggle_gain_normalization(_sender: rumps.MenuItem) -> None
```

Переключает бережную нормализацию аудио.

#### `toggle_audio_artifact_cleanup`

```python
toggle_audio_artifact_cleanup(_sender: rumps.MenuItem) -> None
```

Переключает автоочистку диагностических WAV-записей.

#### `open_recordings_directory`

```python
open_recordings_directory(_sender: rumps.MenuItem) -> None
```

Открывает папку диагностических WAV-записей.

#### `change_performance_mode`

```python
change_performance_mode(sender: rumps.MenuItem) -> None
```

Переключает режим производительности.

#### `toggle_private_mode`

```python
toggle_private_mode(_sender: rumps.MenuItem) -> None
```

Переключает private mode.

#### `toggle_paste_cgevent`

```python
toggle_paste_cgevent(_sender: rumps.MenuItem) -> None
```

Переключает метод вставки CGEvent.

#### `toggle_paste_ax`

```python
toggle_paste_ax(_sender: rumps.MenuItem) -> None
```

Переключает метод вставки Accessibility API.

#### `toggle_paste_clipboard`

```python
toggle_paste_clipboard(_sender: rumps.MenuItem) -> None
```

Переключает метод вставки через буфер обмена.

#### `toggle_llm_clipboard`

```python
toggle_llm_clipboard(_sender: rumps.MenuItem) -> None
```

Переключает использование буфера обмена для LLM.

#### `start_rsvp`

```python
start_rsvp(_sender: rumps.MenuItem) -> None
```

Запускает RSVP из буфера обмена.

#### `start_tts`

```python
start_tts(_sender: rumps.MenuItem) -> None
```

Запускает TTS из буфера обмена.

#### `start_zipper`

```python
start_zipper(_sender: rumps.MenuItem) -> None
```

Запускает Zipper из меню.

#### `toggle_zipper_enabled`

```python
toggle_zipper_enabled(_sender: rumps.MenuItem) -> None
```

Включает или выключает Zipper.

#### `open_zipper_config`

```python
open_zipper_config(_sender: rumps.MenuItem) -> None
```

Открывает конфиг Zipper.

#### `reload_zipper_config`

```python
reload_zipper_config(_sender: rumps.MenuItem) -> None
```

Перечитывает конфиг Zipper.

#### `toggle_zipper_debug_panel`

```python
toggle_zipper_debug_panel(_sender: rumps.MenuItem) -> None
```

Переключает debug-панель Zipper.

#### `clear_zipper_context`

```python
clear_zipper_context(_sender: rumps.MenuItem) -> None
```

Очищает контекст Zipper.

#### `clear_zipper_memory`

```python
clear_zipper_memory(_sender: rumps.MenuItem) -> None
```

Очищает постоянную память Zipper.

#### `quit_application`

```python
quit_application(sender: rumps.MenuItem) -> None
```

Завершает приложение через управляемый shutdown.

#### `change_reader_rsvp_wpm`

```python
change_reader_rsvp_wpm(sender: rumps.MenuItem) -> None
```

Меняет скорость RSVP.

#### `change_reader_rsvp_chunk_size`

```python
change_reader_rsvp_chunk_size(sender: rumps.MenuItem) -> None
```

Меняет размер chunk-а RSVP.

#### `change_reader_rsvp_font_size`

```python
change_reader_rsvp_font_size(sender: rumps.MenuItem) -> None
```

Меняет размер шрифта RSVP.

#### `decrease_reader_tts_rate_multiplier`

```python
decrease_reader_tts_rate_multiplier(_sender: rumps.MenuItem) -> None
```

Уменьшает скорость TTS на один шаг.

#### `increase_reader_tts_rate_multiplier`

```python
increase_reader_tts_rate_multiplier(_sender: rumps.MenuItem) -> None
```

Увеличивает скорость TTS на один шаг.

#### `change_reader_tts_engine`

```python
change_reader_tts_engine(sender: rumps.MenuItem) -> None
```

Меняет backend TTS.

#### `change_reader_tts_mlx_model`

```python
change_reader_tts_mlx_model(sender: rumps.MenuItem) -> None
```

Меняет MLX TTS-модель.

#### `prompt_reader_tts_mlx_model`

```python
prompt_reader_tts_mlx_model(_sender: rumps.MenuItem) -> None
```

Открывает диалог точного имени MLX TTS-модели.

#### `prompt_reader_tts_mlx_voice_description`

```python
prompt_reader_tts_mlx_voice_description(_sender: rumps.MenuItem) -> None
```

Открывает диалог описания голоса MLX VoiceDesign.

#### `prompt_reader_tts_tone_instruction`

```python
prompt_reader_tts_tone_instruction(_sender: rumps.MenuItem) -> None
```

Открывает диалог свободной инструкции по интонации TTS.

#### `change_reader_tts_voice`

```python
change_reader_tts_voice(sender: rumps.MenuItem) -> None
```

Меняет системный голос TTS.

#### `change_reader_tts_max_minutes`

```python
change_reader_tts_max_minutes(sender: rumps.MenuItem) -> None
```

Меняет максимальную длительность TTS.

#### `toggle_reader_preprocess`

```python
toggle_reader_preprocess(_sender: rumps.MenuItem) -> None
```

Переключает LLM-предобработку reader.

#### `toggle_capitalize_first_letter`

```python
toggle_capitalize_first_letter(_sender: rumps.MenuItem) -> None
```

Переключает правило заглавной буквы после распознавания.

#### `toggle_remove_trailing_period_for_single_sentence`

```python
toggle_remove_trailing_period_for_single_sentence(_sender: rumps.MenuItem) -> None
```

Переключает удаление точки в конце одного предложения.

#### `toggle_restore_trailing_period_on_next_dictation`

```python
toggle_restore_trailing_period_on_next_dictation(_sender: rumps.MenuItem) -> None
```

Переключает автоточку перед следующей диктовкой.

#### `_copy_history_item`

```python
_copy_history_item(sender: rumps.MenuItem) -> None
```

_Внутренняя функция._

Копирует выбранный элемент истории в буфер обмена.

#### `start_app`

```python
start_app(_: object) -> None
```

Запускает запись.

#### `stop_app`

```python
stop_app(_: object) -> None
```

Останавливает запись.

#### `on_status_tick`

```python
on_status_tick(_: object) -> None
```

Обновляет индикатор времени записи в строке меню.

#### `toggle`

```python
toggle() -> None
```

Переключает обычный сценарий записи.

#### `toggle_llm`

```python
toggle_llm() -> None
```

Переключает LLM-сценарий записи.

#### `cancel_recording`

```python
cancel_recording() -> None
```

Отменяет активную запись без распознавания.

#### `_download_llm_model`

```python
_download_llm_model(_: object) -> None
```

_Внутренняя функция._

Запускает загрузку LLM-модели через DictationApp.

#### `_change_llm_prompt`

```python
_change_llm_prompt(sender: rumps.MenuItem) -> None
```

_Внутренняя функция._

Переключает текущий пресет системного промпта LLM.

#### `_change_llm_model`

```python
_change_llm_model(sender: rumps.MenuItem) -> None
```

_Внутренняя функция._

Переключает LLM-модель.

## Публичные функции

### `request_application_quit`

```python
request_application_quit(sender: object | None = None, *, emit_before_quit: bool = True) -> None
```

Запрашивает выход из AppKit на следующем проходе run loop.

### `prompt_text`

```python
prompt_text(title: str, message: str, default_text: str = '') -> str | None
```

Открывает простое AppKit-окно ввода текста и возвращает введённое значение.

## Внутренние функции

### `_call_on_main_thread`

```python
_call_on_main_thread(callback: Any, *args: Any) -> None
```

_Внутренняя функция._

Гарантирует, что обновление menu bar выполняется на главном потоке AppKit.
