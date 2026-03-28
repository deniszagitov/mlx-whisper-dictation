"""Чистые правила подготовки и очистки ответов LLM."""

from __future__ import annotations

import logging
import re

from .constants import Config

LOGGER = logging.getLogger(__name__)

_THINK_BLOCK_RE = re.compile(r"<think>.*?</think>", re.DOTALL)
_THINK_TAIL_RE = re.compile(r"^.*?</think>", re.DOTALL)
_FINAL_ANSWER_MARKER_RE = re.compile(r"(?:^|\n)\s*(?:final answer|answer|ответ)\s*[:：]\s*", re.IGNORECASE)
_SECTION_LINE_RE = re.compile(
    r"^\s*(?:\d+\.\s*)?(?:[*-]\s*)?(?P<label>[^:\n]{1,80}?)\s*[:：]\s*(?P<value>.+?)\s*$",
    re.IGNORECASE,
)
_ANSWER_SECTION_LABELS = frozenset(
    {
        "draft",
        "final answer",
        "answer",
        "response",
        "черновик",
        "определение ответа",
        "ответ",
    }
)
_STRUCTURED_PREFIX_RE = re.compile(r"^\s*(?:\d+\.|[*#>-]|[-*]\s)")

_CLIPBOARD_CONTEXT_HINT_RE = re.compile(
    r"(этот|это|здесь|выше|ниже|буфер|clipboard|text|текст|сообщени|документ|"
    r"перевед|исправ|отредакт|сократ|резюм|перескаж|перефраз|объясни|о чем|"
    r"what is this|about this|translate|rewrite|fix|summari[sz]e|proofread)",
    re.IGNORECASE,
)


def should_use_clipboard_context(request_text: object, clipboard_text: object) -> bool:
    """Решает, нужно ли передавать буфер обмена как контекст для LLM."""
    if not clipboard_text:
        return False

    normalized_request = str(request_text or "").strip()
    if not normalized_request:
        return False

    return _CLIPBOARD_CONTEXT_HINT_RE.search(normalized_request) is not None


def strip_think_blocks(text: str) -> str:
    """Удаляет блоки рассуждений из ответа LLM."""
    cleaned = _THINK_BLOCK_RE.sub("", text)
    cleaned = _THINK_TAIL_RE.sub("", cleaned)
    if "<think>" in cleaned:
        cleaned = ""
    return cleaned.strip()


def _extract_final_answer_segment(text: str) -> str:
    """Возвращает хвост после последнего маркера финального ответа."""
    matches = list(_FINAL_ANSWER_MARKER_RE.finditer(text))
    if not matches:
        return ""
    return text[matches[-1].end() :].strip()


def _strip_markdown_emphasis(text: str) -> str:
    """Убирает markdown-обрамление, мешающее распознаванию служебных секций."""
    return text.replace("**", "").replace("__", "")


def _extract_answer_section(text: str) -> str:
    """Достаёт payload из строк вида «Черновик: ...» или «Ответ: ...»."""
    candidate = ""
    for raw_line in text.splitlines():
        match = _SECTION_LINE_RE.match(_strip_markdown_emphasis(raw_line.strip()))
        if not match:
            continue
        label = match.group("label").strip().casefold()
        value = match.group("value").strip()
        if label in _ANSWER_SECTION_LABELS and value:
            candidate = value
    return candidate


def _is_answer_section_label(label: str) -> bool:
    """Определяет, что метка секции содержит финальный ответ."""
    return label.strip().casefold() in _ANSWER_SECTION_LABELS


def _is_plain_text_response(text: str) -> bool:
    """Пропускает в UI только простой финальный текст без структурных маркеров."""
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if not lines:
        return False

    for line in lines:
        normalized = _strip_markdown_emphasis(line)
        if _STRUCTURED_PREFIX_RE.match(normalized):
            return False
        section_match = _SECTION_LINE_RE.match(normalized)
        if section_match and not _is_answer_section_label(section_match.group("label")):
            return False

    return True


def _normalize_response_whitespace(text: str) -> str:
    """Сводит ответ к одной аккуратной строке без лишних пробелов."""
    collapsed = re.sub(r"\s+", " ", text).strip()
    collapsed = re.sub(r"^(?:\*\*|__|[*#>-]\s*)+", "", collapsed)
    collapsed = re.sub(r"(?:\*\*|__)+$", "", collapsed)
    return collapsed.strip("'\" ")


def _truncate_response(text: str, limit: int = Config.LLM_RESPONSE_CHAR_LIMIT) -> str:
    """Обрезает ответ до лимита, стараясь сохранить целое предложение."""
    if len(text) <= limit:
        return text

    truncated = text[: limit - 1].rstrip(" ,;:-")
    sentence_break = max(truncated.rfind(symbol) for symbol in ".!?…")
    if sentence_break >= max(limit // 2, 40):
        return truncated[: sentence_break + 1].strip()

    word_break = truncated.rfind(" ")
    if word_break >= max(limit // 2, 40):
        truncated = truncated[:word_break]

    return truncated.rstrip(" ,;:-") + "…"


def sanitize_llm_response(text: str) -> str:
    """Возвращает только безопасный финальный текст для UI и вставки."""
    cleaned = strip_think_blocks(text)
    if not cleaned:
        return ""

    section_answer = _extract_answer_section(cleaned)
    if section_answer:
        cleaned = section_answer

    final_segment = _extract_final_answer_segment(cleaned)
    if final_segment:
        cleaned = final_segment
    elif not _is_plain_text_response(cleaned):
        LOGGER.warning("⚠️ Скрываю structured-ответ LLM из UI; смотрите сырой лог модели")
        return ""

    cleaned = _normalize_response_whitespace(cleaned)
    return _truncate_response(cleaned)
