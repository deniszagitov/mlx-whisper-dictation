# Zipper TTS

Исходный файл: `src/domain/zipper_tts.py`

Правила подготовки голосовых ответов Zipper для локального TTS.

## Константы

- `_FENCED_CODE_PATTERN` = `re.compile('```.*?```', flags=re.DOTALL)`
- `_INLINE_CODE_PATTERN` = `re.compile('`[^`\\n]+`')`
- `_URL_PATTERN` = `re.compile('\\b(?:[a-z][a-z0-9+.-]*://|www\\.)\\S+', flags=re.IGNORECASE)`
- `_LONG_IDENTIFIER_PATTERN` = `re.compile('\\b[a-zA-Z0-9_-]{24,}\\b')`
- `_MARKDOWN_MARKER_PATTERN` = `re.compile('(^|\\n)\\s{0,3}(?:#{1,6}\\s+|[-*+]\\s+|\\d+[.)]\\s+|>\\s*)')`
- `_MARKDOWN_SYMBOL_PATTERN` = `re.compile('[*_~]{1,3}')`
- `_NUMBER_PATTERN` = `re.compile('\\d+')`
- `_WHITESPACE_PATTERN` = `re.compile('[ \\t]+')`
- `_PAUSE_PUNCTUATION` = `'.,?!:;'`
- `_SIMPLE_NUMBER_MAX_DIGITS` = `6`
- `_SIMPLE_NUMBER_MAX_VALUE` = `999999`
- `_TEEN_MIN` = `10`
- `_TEEN_MAX` = `19`
- `_PLURAL_TEEN_MIN` = `11`
- `_PLURAL_TEEN_MAX` = `14`
- `_PLURAL_FEW_MIN` = `2`
- `_PLURAL_FEW_MAX` = `4`
- `_DIGIT_WORDS` = `{0: 'ноль', 1: 'один', 2: 'два', 3: 'три', 4: 'четыре', 5: 'пять', 6: 'шесть', 7: 'семь', 8: 'восемь', 9: 'девять'}`
- `_UNITS_MASCULINE` = `{1: 'один', 2: 'два', 3: 'три', 4: 'четыре', 5: 'пять', 6: 'шесть', 7: 'семь', 8: 'восемь', 9: 'девять'}`
- `_UNITS_FEMININE` = `{**_UNITS_MASCULINE, 1: 'одна', 2: 'две'}`
- `_TEENS` = `{10: 'десять', 11: 'одиннадцать', 12: 'двенадцать', 13: 'тринадцать', 14: 'четырнадцать', 15: 'пятнадцать', 16: 'шестнадцать', 17: 'семнадцать', 18: 'восемнадцать', 19: 'девятнадцать'}`
- `_TENS` = `{20: 'двадцать', 30: 'тридцать', 40: 'сорок', 50: 'пятьдесят', 60: 'шестьдесят', 70: 'семьдесят', 80: 'восемьдесят', 90: 'девяносто'}`
- `_HUNDREDS` = `{100: 'сто', 200: 'двести', 300: 'триста', 400: 'четыреста', 500: 'пятьсот', 600: 'шестьсот', 700: 'семьсот', 800: 'восемьсот', 900: 'девятьсот'}`

## Публичные функции

### `normalize_zipper_voice_text`

```python
normalize_zipper_voice_text(text: str) -> str
```

Возвращает безопасный текст для голосового TTS Zipper без цифр и технической разметки.

## Внутренние функции

### `_number_to_russian_words`

```python
_number_to_russian_words(raw_number: str) -> str
```

_Внутренняя функция._

Переводит простые числа в слова, а неоднозначные формы проговаривает по цифрам.
