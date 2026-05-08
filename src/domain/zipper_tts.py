"""Правила подготовки голосовых ответов Zipper для локального TTS."""

from __future__ import annotations

import re

_FENCED_CODE_PATTERN = re.compile(r"```.*?```", flags=re.DOTALL)
_INLINE_CODE_PATTERN = re.compile(r"`[^`\n]+`")
_URL_PATTERN = re.compile(r"\b(?:[a-z][a-z0-9+.-]*://|www\.)\S+", flags=re.IGNORECASE)
_LONG_IDENTIFIER_PATTERN = re.compile(r"\b[a-zA-Z0-9_-]{24,}\b")
_MARKDOWN_MARKER_PATTERN = re.compile(r"(^|\n)\s{0,3}(?:#{1,6}\s+|[-*+]\s+|\d+[.)]\s+|>\s*)")
_MARKDOWN_SYMBOL_PATTERN = re.compile(r"[*_~]{1,3}")
_NUMBER_PATTERN = re.compile(r"\d+")
_WHITESPACE_PATTERN = re.compile(r"[ \t]+")
_PAUSE_PUNCTUATION = ".,?!:;"
_SIMPLE_NUMBER_MAX_DIGITS = 6
_SIMPLE_NUMBER_MAX_VALUE = 999_999
_TEEN_MIN = 10
_TEEN_MAX = 19
_PLURAL_TEEN_MIN = 11
_PLURAL_TEEN_MAX = 14
_PLURAL_FEW_MIN = 2
_PLURAL_FEW_MAX = 4

_DIGIT_WORDS = {
    0: "ноль",
    1: "один",
    2: "два",
    3: "три",
    4: "четыре",
    5: "пять",
    6: "шесть",
    7: "семь",
    8: "восемь",
    9: "девять",
}
_UNITS_MASCULINE = {
    1: "один",
    2: "два",
    3: "три",
    4: "четыре",
    5: "пять",
    6: "шесть",
    7: "семь",
    8: "восемь",
    9: "девять",
}
_UNITS_FEMININE = {
    **_UNITS_MASCULINE,
    1: "одна",
    2: "две",
}
_TEENS = {
    10: "десять",
    11: "одиннадцать",
    12: "двенадцать",
    13: "тринадцать",
    14: "четырнадцать",
    15: "пятнадцать",
    16: "шестнадцать",
    17: "семнадцать",
    18: "восемнадцать",
    19: "девятнадцать",
}
_TENS = {
    20: "двадцать",
    30: "тридцать",
    40: "сорок",
    50: "пятьдесят",
    60: "шестьдесят",
    70: "семьдесят",
    80: "восемьдесят",
    90: "девяносто",
}
_HUNDREDS = {
    100: "сто",
    200: "двести",
    300: "триста",
    400: "четыреста",
    500: "пятьсот",
    600: "шестьсот",
    700: "семьсот",
    800: "восемьсот",
    900: "девятьсот",
}


def normalize_zipper_voice_text(text: str) -> str:
    """Возвращает безопасный текст для голосового TTS Zipper без цифр и технической разметки."""
    cleaned = _FENCED_CODE_PATTERN.sub(" дальше блок кода ", str(text or ""))
    cleaned = _INLINE_CODE_PATTERN.sub(" идентификатор ", cleaned)
    cleaned = _URL_PATTERN.sub(" ссылка ", cleaned)
    cleaned = _LONG_IDENTIFIER_PATTERN.sub(" идентификатор ", cleaned)
    cleaned = _MARKDOWN_MARKER_PATTERN.sub(r"\1", cleaned)
    cleaned = _MARKDOWN_SYMBOL_PATTERN.sub("", cleaned)
    cleaned = re.sub(r"\bAPI\b", "эй пи ай", cleaned)
    cleaned = re.sub(r"\bDWH\b", "ди дабл ю эйч", cleaned)
    cleaned = _NUMBER_PATTERN.sub(lambda match: _number_to_russian_words(match.group(0)), cleaned)
    cleaned = _keep_voice_chars(cleaned)
    cleaned = _WHITESPACE_PATTERN.sub(" ", cleaned)
    cleaned = re.sub(r"\s+([.,?!:;])", r"\1", cleaned)
    cleaned = re.sub(r"([.,?!:;])(?=\S)", r"\1 ", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned.strip()


def _number_to_russian_words(raw_number: str) -> str:
    """Переводит простые числа в слова, а неоднозначные формы проговаривает по цифрам."""
    if len(raw_number) > _SIMPLE_NUMBER_MAX_DIGITS or (len(raw_number) > 1 and raw_number.startswith("0")):
        return _digits_to_words(raw_number)
    try:
        value = int(raw_number)
    except ValueError:
        return _digits_to_words(raw_number)
    if value > _SIMPLE_NUMBER_MAX_VALUE:
        return _digits_to_words(raw_number)
    return _int_to_russian_words(value)


def _digits_to_words(raw_number: str) -> str:
    words: list[str] = []
    for character in raw_number:
        try:
            digit = int(character)
        except ValueError:
            continue
        words.append(_DIGIT_WORDS[digit])
    return " ".join(words)


def _int_to_russian_words(value: int) -> str:
    if value == 0:
        return _DIGIT_WORDS[0]
    parts: list[str] = []
    thousands, remainder = divmod(value, 1000)
    if thousands:
        parts.extend(_under_thousand_to_words(thousands, feminine=True))
        parts.append(_thousand_word(thousands))
    if remainder:
        parts.extend(_under_thousand_to_words(remainder, feminine=False))
    return " ".join(parts)


def _under_thousand_to_words(value: int, *, feminine: bool) -> list[str]:
    parts: list[str] = []
    hundreds, remainder = divmod(value, 100)
    if hundreds:
        parts.append(_HUNDREDS[hundreds * 100])
    if _TEEN_MIN <= remainder <= _TEEN_MAX:
        parts.append(_TEENS[remainder])
        return parts
    tens, units = divmod(remainder, 10)
    if tens:
        parts.append(_TENS[tens * 10])
    if units:
        units_words = _UNITS_FEMININE if feminine else _UNITS_MASCULINE
        parts.append(units_words[units])
    return parts


def _thousand_word(value: int) -> str:
    last_two = value % 100
    if _PLURAL_TEEN_MIN <= last_two <= _PLURAL_TEEN_MAX:
        return "тысяч"
    last = value % 10
    if last == 1:
        return "тысяча"
    if _PLURAL_FEW_MIN <= last <= _PLURAL_FEW_MAX:
        return "тысячи"
    return "тысяч"


def _keep_voice_chars(text: str) -> str:
    chars: list[str] = []
    for character in text:
        if character.isalpha() or character.isspace() or character in _PAUSE_PUNCTUATION:
            chars.append(character)
        else:
            chars.append(" ")
    return "".join(chars)
