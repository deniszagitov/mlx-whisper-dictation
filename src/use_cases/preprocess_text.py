"""Use case предобработки текста reader-модуля через локальную LLM."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass

from ..domain.reader_constants import (
    READER_CLIPBOARD_CHAR_LIMIT,
    RSVP_PREPROCESS_MAX_TOKENS,
    TTS_PREPROCESS_MAX_TOKENS,
    tts_max_words,
)
from ..domain.reader_types import LLMReformatterPort, OutputMode, ProcessedText, TTSConfig

LOGGER = logging.getLogger(__name__)

RSVP_SYSTEM_PROMPT = (
    "Ты локальный редактор текста для RSVP-чтения. "
    "Удали вступления вроде «Конечно», «Отличный вопрос», «Давай разберём». "
    "Удали заключения вроде «Если есть ещё вопросы…», «Надеюсь, помог». "
    "Сохрани структуру: TL;DR одной фразой, затем 2-3 ключевых пункта, затем детали. "
    "Дроби длинные предложения на короткие, целевая длина до 12 слов. "
    "Термины, имена, числа и факты сохраняй без изменений. "
    "Не добавляй сведения, которых не было в исходном тексте. "
    "Верни только готовый текст без пояснений."
)

TTS_SYSTEM_PROMPT = (
    "Ты локальный редактор текста для ускоренного голосового чтения. "
    "Удали markdown-разметку: звёздочки, решётки, маркеры списков и тройные бэктики. "
    "Ссылки замени словом «ссылка», длинные идентификаторы словом «идентификатор». "
    "Кодовые блоки замени короткой фразой «дальше блок кода» или убери, если они не важны. "
    "Однозначные аббревиатуры раскрывай в произносимую форму: API как эй-пи-ай, DWH как ди-дабл-ю-эйч. "
    "Сохрани структуру повествования и не добавляй новых фактов. "
    "Если текст слишком большой, сократи его без потери главной мысли. "
    "Верни только текст для озвучивания без пояснений."
)

_RSVP_LEADING_PATTERNS = (
    r"^\s*(конечно|отличный вопрос|давай разбер[её]м|давайте разбер[её]м)[\s,!.:;-]*",
)
_RSVP_TRAILING_PATTERNS = (
    r"[\s.!?]*(если есть ещё вопросы.*|если есть еще вопросы.*|надеюсь,?\s+помог.*)\s*$",
)
_FENCED_CODE_PATTERN = re.compile(r"```.*?```", flags=re.DOTALL)
_INLINE_CODE_PATTERN = re.compile(r"`[^`\n]+`")
_URL_PATTERN = re.compile(r"\b(?:[a-z][a-z0-9+.-]*://|www\.)\S+", flags=re.IGNORECASE)
_LONG_IDENTIFIER_PATTERN = re.compile(r"\b[a-zA-Z0-9_-]{24,}\b")
_MARKDOWN_MARKER_PATTERN = re.compile(r"(^|\n)\s{0,3}(?:#{1,6}\s+|[-*+]\s+|\d+[.)]\s+|>\s*)")
_MARKDOWN_SYMBOL_PATTERN = re.compile(r"[*_~]{1,3}")
_WHITESPACE_PATTERN = re.compile(r"[ \t]+")
_BLANK_LINES_PATTERN = re.compile(r"\n{3,}")


@dataclass(frozen=True, slots=True)
class ReaderSourceText:
    """Проверенный исходный текст из буфера обмена."""

    text: str
    source_char_count: int
    truncated: bool


def prepare_reader_source_text(text: str) -> ReaderSourceText:
    """Обрезает слишком длинный текст reader-сценария по безопасному лимиту."""
    source_char_count = len(text)
    if source_char_count <= READER_CLIPBOARD_CHAR_LIMIT:
        return ReaderSourceText(text=text, source_char_count=source_char_count, truncated=False)
    return ReaderSourceText(
        text=text[:READER_CLIPBOARD_CHAR_LIMIT],
        source_char_count=source_char_count,
        truncated=True,
    )


def cleanup_rsvp_text(text: str) -> str:
    """Локально убирает типовые LLM-преамбулы и хвосты для RSVP."""
    cleaned = text.strip()
    for pattern in _RSVP_LEADING_PATTERNS:
        while True:
            next_cleaned = re.sub(pattern, "", cleaned, flags=re.IGNORECASE)
            if next_cleaned == cleaned:
                break
            cleaned = next_cleaned
    for pattern in _RSVP_TRAILING_PATTERNS:
        cleaned = re.sub(pattern, "", cleaned, flags=re.IGNORECASE | re.DOTALL)
    cleaned = _WHITESPACE_PATTERN.sub(" ", cleaned)
    cleaned = _BLANK_LINES_PATTERN.sub("\n\n", cleaned)
    return cleaned.strip()


def normalize_tts_text(text: str) -> str:
    """Локально чистит текст перед озвучиванием через системный TTS."""
    cleaned = _FENCED_CODE_PATTERN.sub(" дальше блок кода ", text)
    cleaned = _INLINE_CODE_PATTERN.sub(" идентификатор ", cleaned)
    cleaned = _URL_PATTERN.sub(" ссылка ", cleaned)
    cleaned = _LONG_IDENTIFIER_PATTERN.sub(" идентификатор ", cleaned)
    cleaned = _MARKDOWN_MARKER_PATTERN.sub(r"\1", cleaned)
    cleaned = _MARKDOWN_SYMBOL_PATTERN.sub("", cleaned)
    cleaned = re.sub(r"\bAPI\b", "эй-пи-ай", cleaned)
    cleaned = re.sub(r"\bDWH\b", "ди-дабл-ю-эйч", cleaned)
    cleaned = _WHITESPACE_PATTERN.sub(" ", cleaned)
    cleaned = _BLANK_LINES_PATTERN.sub("\n\n", cleaned)
    return cleaned.strip()


def limit_tts_text(text: str, config: TTSConfig) -> str:
    """Ограничивает TTS-текст примерной длительностью из настроек Speaker."""
    max_words = tts_max_words(config.max_minutes, config.rate_multiplier)
    if max_words is None:
        return text
    words = text.split()
    if len(words) <= max_words:
        return text
    return " ".join(words[:max_words]).rstrip(" .,;:") + "."


class PreprocessTextUseCase:
    """Готовит текст для RSVP или TTS, используя LLM и локальные fallback-правила."""

    def __init__(self, llm_processor: LLMReformatterPort | None) -> None:
        self.llm_processor = llm_processor

    def execute(
        self,
        raw_text: str,
        mode: OutputMode,
        *,
        enabled: bool,
        tts_config: TTSConfig | None = None,
    ) -> ProcessedText:
        """Возвращает подготовленный текст для выбранного reader-режима."""
        source = prepare_reader_source_text(raw_text)
        text_for_model = source.text
        used_fallback = False

        if enabled and self.llm_processor is not None and self.llm_processor.is_model_cached():
            try:
                text_for_model = self._run_llm(text_for_model, mode)
            except Exception:
                LOGGER.warning("⚠️ LLM-предобработка reader упала, использую исходный текст", exc_info=True)
                used_fallback = True
                text_for_model = source.text
        elif enabled and self.llm_processor is not None:
            LOGGER.warning("⚠️ LLM-модель reader не найдена в локальном кэше, использую исходный текст")
            used_fallback = True

        if mode is OutputMode.RSVP:
            final_text = cleanup_rsvp_text(text_for_model)
        else:
            final_text = normalize_tts_text(text_for_model)
            if tts_config is not None:
                final_text = limit_tts_text(final_text, tts_config)

        return ProcessedText(
            text=final_text or source.text.strip(),
            mode=mode,
            source_char_count=source.source_char_count,
            truncated=source.truncated,
            used_fallback=used_fallback,
        )

    def _run_llm(self, text: str, mode: OutputMode) -> str:
        """Вызывает LLM с системным prompt для выбранного режима."""
        if self.llm_processor is None:
            return text
        if mode is OutputMode.RSVP:
            return self.llm_processor.process_text(text, RSVP_SYSTEM_PROMPT, max_tokens=RSVP_PREPROCESS_MAX_TOKENS)
        return self.llm_processor.process_text(text, TTS_SYSTEM_PROMPT, max_tokens=TTS_PREPROCESS_MAX_TOKENS)
