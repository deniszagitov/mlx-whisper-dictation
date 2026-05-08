# Reader preprocessing

Исходный файл: `src/use_cases/preprocess_text.py`

Use case предобработки текста reader-модуля через локальную LLM.

## Константы

- `LOGGER` = `logging.getLogger(__name__)`
- `RSVP_SYSTEM_PROMPT` = `'Ты локальный редактор текста для RSVP-чтения. Удали вступления вроде «Конечно», «Отличный вопрос», «Давай разберём». Удали заключения вроде «Если есть ещё вопросы…», «Надеюсь, помог». Сохрани структуру: TL;DR одной фразой, затем 2-3 ключевых пункта, затем детали. Дроби длинные предложения на короткие, целевая длина до 12 слов. Термины, имена, числа и факты сохраняй без изменений. Не добавляй сведения, которых не было в исходном тексте. Верни только готовый текст без пояснений.'`
- `TTS_SYSTEM_PROMPT` = `'Ты локальный редактор текста для ускоренного голосового чтения. Удали markdown-разметку: звёздочки, решётки, маркеры списков и тройные бэктики. Ссылки замени словом «ссылка», длинные идентификаторы словом «идентификатор». Кодовые блоки замени короткой фразой «дальше блок кода» или убери, если они не важны. Однозначные аббревиатуры раскрывай в произносимую форму: API как эй-пи-ай, DWH как ди-дабл-ю-эйч. Сохрани структуру повествования и не добавляй новых фактов. Если текст слишком большой, сократи его без потери главной мысли. Верни только текст для озвучивания без пояснений.'`
- `_RSVP_LEADING_PATTERNS` = `('^\\s*(конечно|отличный вопрос|давай разбер[её]м|давайте разбер[её]м)[\\s,!.:;-]*',)`
- `_RSVP_TRAILING_PATTERNS` = `('[\\s.!?]*(если есть ещё вопросы.*|если есть еще вопросы.*|надеюсь,?\\s+помог.*)\\s*$',)`
- `_FENCED_CODE_PATTERN` = `re.compile('```.*?```', flags=re.DOTALL)`
- `_INLINE_CODE_PATTERN` = `re.compile('`[^`\\n]+`')`
- `_URL_PATTERN` = `re.compile('\\b(?:[a-z][a-z0-9+.-]*://|www\\.)\\S+', flags=re.IGNORECASE)`
- `_LONG_IDENTIFIER_PATTERN` = `re.compile('\\b[a-zA-Z0-9_-]{24,}\\b')`
- `_MARKDOWN_MARKER_PATTERN` = `re.compile('(^|\\n)\\s{0,3}(?:#{1,6}\\s+|[-*+]\\s+|\\d+[.)]\\s+|>\\s*)')`
- `_MARKDOWN_SYMBOL_PATTERN` = `re.compile('[*_~]{1,3}')`
- `_WHITESPACE_PATTERN` = `re.compile('[ \\t]+')`
- `_BLANK_LINES_PATTERN` = `re.compile('\\n{3,}')`

## Классы

## `ReaderSourceText`

Проверенный исходный текст из буфера обмена.

## `PreprocessTextUseCase`

Готовит текст для RSVP или TTS, используя LLM и локальные fallback-правила.

### Методы

#### `__init__`

```python
__init__(llm_processor: LLMReformatterPort | None) -> None
```

Конструктор класса.

#### `execute`

```python
execute(raw_text: str, mode: OutputMode, *, enabled: bool, tts_config: TTSConfig | None = None) -> ProcessedText
```

Возвращает подготовленный текст для выбранного reader-режима.

#### `_run_llm`

```python
_run_llm(text: str, mode: OutputMode) -> str
```

_Внутренняя функция._

Вызывает LLM с системным prompt для выбранного режима.

## Публичные функции

### `prepare_reader_source_text`

```python
prepare_reader_source_text(text: str) -> ReaderSourceText
```

Обрезает слишком длинный текст reader-сценария по безопасному лимиту.

### `cleanup_rsvp_text`

```python
cleanup_rsvp_text(text: str) -> str
```

Локально убирает типовые LLM-преамбулы и хвосты для RSVP.

### `normalize_tts_text`

```python
normalize_tts_text(text: str) -> str
```

Локально чистит текст перед озвучиванием через системный TTS.

### `limit_tts_text`

```python
limit_tts_text(text: str, config: TTSConfig) -> str
```

Ограничивает TTS-текст примерной длительностью из настроек Speaker.
