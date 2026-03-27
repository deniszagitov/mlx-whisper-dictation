# Распознавание и вставка

Исходный файл: `src/transcriber.py`

Распознавание речи и вставка текста в активное приложение.

Содержит класс SpeechTranscriber — ядро диктовки: транскрипция аудио
через MLX Whisper, автовставка через CGEvent/AX/Clipboard, история
распознанного текста и интеграция с LLM.

## Константы

- `LOGGER` = `logging.getLogger(__name__)`
- `_CLIPBOARD_CONTEXT_HINT_RE` = `re.compile('(этот|это|здесь|выше|ниже|буфер|clipboard|text|текст|сообщени|документ|перевед|исправ|отредакт|сократ|резюм|перескаж|перефраз|объясни|о чем|what is this|about this|translate|rewrite|fix|summari[sz]e|proofread)', re.IGNORECASE)`

## Классы

## `SpeechTranscriber`

Распознает аудио и вставляет текст в активное приложение.

Attributes:
    pykeyboard: Контроллер клавиатуры pynput для вставки текста.
    diagnostics_store: Изолированное хранилище диагностических артефактов.
    model_name: Имя или путь к модели MLX Whisper.
    paste_cgevent_enabled: Включён ли метод прямого ввода через CGEvent Unicode.
    paste_ax_enabled: Включён ли метод ввода через Accessibility API.
    paste_clipboard_enabled: Включён ли метод ввода через буфер обмена (Cmd+V).
    history: Список ранее распознанных текстов.
    history_callback: Callback для уведомления UI об изменении истории.

### Методы

#### `__init__`

```python
__init__(model_name, diagnostics_store = None)
```

Создает объект распознавания.

Args:
    model_name: Имя модели Hugging Face или локальный путь к модели.
    diagnostics_store: Необязательное хранилище диагностических файлов.

#### `set_private_mode`

```python
set_private_mode(enabled)
```

Переключает private mode для истории текста.

В private mode история не загружается из NSUserDefaults и не
сохраняется между перезапусками. Уже сохранённая история остаётся
в defaults, но скрывается до выхода из private mode.

Args:
    enabled: Нужно ли включить private mode.

#### `_notify_token_usage_changed`

```python
_notify_token_usage_changed()
```

_Внутренняя функция._

Вызывает callback обновления UI после изменения счётчика токенов.

#### `_add_token_usage`

```python
_add_token_usage(token_count)
```

_Внутренняя функция._

Добавляет подтверждённое количество токенов к общему счётчику.

#### `_extract_transcription_token_count`

```python
_extract_transcription_token_count(result)
```

_Внутренняя функция._

Извлекает количество Whisper-токенов из сегментов результата.

#### `_copy_text_to_clipboard`

```python
_copy_text_to_clipboard(text)
```

_Внутренняя функция._

Копирует текст в системный буфер обмена.

Args:
    text: Текст для сохранения в буфере обмена.

#### `_read_clipboard`

```python
_read_clipboard()
```

_Внутренняя функция._

Читает текстовое содержимое из системного буфера обмена.

Returns:
    Текст из буфера обмена или None, если буфер пуст.

#### `_should_use_clipboard_context`

```python
_should_use_clipboard_context(request_text, clipboard_text)
```

_Внутренняя функция._

Решает, нужно ли передавать буфер обмена как контекст для LLM.

#### `_can_deliver_llm_result`

```python
_can_deliver_llm_result(should_deliver_result)
```

_Внутренняя функция._

Проверяет, можно ли выводить ответ LLM в текущий момент.

#### `_type_text_via_cgevent`

```python
_type_text_via_cgevent(text)
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
_insert_text_via_ax(text)
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

#### `_paste_via_clipboard`

```python
_paste_via_clipboard(text)
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
_send_cmd_v()
```

_Внутренняя функция._

Отправляет системные keyboard events для Cmd+V.

#### `_add_to_history`

```python
_add_to_history(text)
```

_Внутренняя функция._

Добавляет распознанный текст в историю.

Вставляет текст в начало списка, обрезает до MAX_HISTORY_SIZE,
сохраняет в NSUserDefaults и вызывает callback для обновления UI.

Args:
    text: Распознанный текст.

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

#### `transcribe_for_llm`

```python
transcribe_for_llm(audio_data, language = None, *, llm_processor, system_prompt, on_llm_processing_started = None, should_deliver_result = None)
```

Распознаёт аудио через Whisper и отправляет результат в LLM.

После получения транскрипции передаёт текст в LLM-модель
с указанным системным промптом. Ответ LLM вставляется в активное
приложение через стандартную цепочку методов ввода.

Args:
    audio_data: Массив с аудио в формате float32.
    language: Необязательный код языка для распознавания.
    llm_processor: Экземпляр LLMProcessor для обработки текста.
    system_prompt: Системный промпт для LLM.
    on_llm_processing_started: Необязательный callback, вызываемый
        перед запуском LLM-обработки для обновления UI-статуса.
    should_deliver_result: Необязательный callback, который решает,
        можно ли показывать и копировать итоговый ответ LLM.
