"""Чистые правила обработки транскрипции и истории."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from .constants import Config

if TYPE_CHECKING:
    import numpy as np
    import numpy.typing as npt

    from .types import AudioDiagnostics, HistoryRecord


def looks_like_hallucination(text: str) -> bool:
    """Проверяет, похож ли результат на типичную галлюцинацию Whisper."""
    return text.strip().lower() in Config.KNOWN_HALLUCINATIONS


class TranscriptionPostprocessingRule:
    """Протокол поведения отдельного правила постобработки транскрипции."""

    def apply(self, text: str) -> str:
        """Возвращает текст после применения одного правила."""
        raise NotImplementedError


@dataclass(frozen=True, slots=True)
class CapitalizeFirstLetterRule(TranscriptionPostprocessingRule):
    """Делает первый буквенный символ текста заглавным."""

    def apply(self, text: str) -> str:
        """Возвращает текст с первой заглавной буквой без изменения остальной строки."""
        for index, character in enumerate(text):
            if character.isalpha():
                return text[:index] + character.upper() + text[index + 1 :]
        return text


@dataclass(frozen=True, slots=True)
class RemoveTrailingPeriodForSingleSentenceRule(TranscriptionPostprocessingRule):
    """Убирает точку в конце, если текст выглядит как одно предложение."""

    _closing_symbols: tuple[str, ...] = ('"', "'", ")", "]", "}", "»")
    _sentence_boundary_re = re.compile(r"(?<!\.)\.(?!\.)")

    def apply(self, text: str) -> str:
        """Удаляет завершающую точку только у текста, похожего на одно предложение."""
        stripped_text = text.rstrip()
        if not stripped_text:
            return text

        trimmed_suffix_length = 0
        while stripped_text and stripped_text[-1] in self._closing_symbols:
            stripped_text = stripped_text[:-1]
            trimmed_suffix_length += 1

        if not stripped_text.endswith("."):
            return text

        if stripped_text.endswith(".."):
            return text

        sentence_period_count = len(self._sentence_boundary_re.findall(stripped_text))
        if sentence_period_count != 1:
            return text

        base_text = stripped_text[:-1]
        closing_suffix = text[len(text.rstrip()) - trimmed_suffix_length : len(text.rstrip())]
        trailing_whitespace = text[len(text.rstrip()) :]
        return base_text + closing_suffix + trailing_whitespace


@dataclass(frozen=True, slots=True)
class TranscriptionPostprocessor:
    """Применяет включённую цепочку правил постобработки к распознанному тексту."""

    rules: tuple[TranscriptionPostprocessingRule, ...]

    def apply(self, text: str) -> str:
        """Прогоняет текст через все настроенные правила по порядку."""
        processed_text = text
        for rule in self.rules:
            processed_text = rule.apply(processed_text)
        return processed_text


def build_audio_diagnostics(
    audio_data: npt.NDArray[np.float32],
    language: str | None,
) -> AudioDiagnostics:
    """Собирает компактную диагностику входного аудиосигнала."""
    audio_duration_seconds = len(audio_data) / 16000
    rms_energy = float(((audio_data**2).mean()) ** 0.5) if len(audio_data) else 0.0
    peak_amplitude = float(abs(audio_data).max()) if len(audio_data) else 0.0
    return {
        "language": language,
        "duration_seconds": audio_duration_seconds,
        "rms_energy": rms_energy,
        "peak_amplitude": peak_amplitude,
        "silence_threshold": Config.SILENCE_RMS_THRESHOLD,
        "hallucination_threshold": Config.HALLUCINATION_RMS_THRESHOLD,
        "sample_rate": 16000,
        "samples": len(audio_data),
        "first_samples": audio_data[:16].tolist(),
    }


def is_mapping(obj: object) -> bool:
    """Проверяет, является ли объект словарём или NSDictionary-подобным объектом."""
    return isinstance(obj, dict) or hasattr(obj, "objectForKey_")


def normalize_history_record(item: Any, now: float) -> HistoryRecord | None:
    """Приводит запись истории к внутреннему формату с TTL."""
    if is_mapping(item):
        text = item.get("text", "")
        created_at = item.get("created_at", now)
    else:
        text = item
        created_at = now

    if is_mapping(text):
        return None

    text = str(text)

    try:
        created_at = float(created_at)
    except (TypeError, ValueError):
        created_at = now

    created_at = min(created_at, now)

    if now - created_at > Config.ARTIFACT_TTL_SECONDS:
        return None

    return {"text": text, "created_at": created_at}


def extract_transcription_token_count(result: object) -> int:
    """Извлекает количество токенов из результата ASR backend-а."""
    if not isinstance(result, dict):
        return 0

    explicit_total = result.get("total_tokens")
    if isinstance(explicit_total, int):
        return max(explicit_total, 0)

    prompt_tokens = result.get("prompt_tokens")
    generation_tokens = result.get("generation_tokens")
    if isinstance(prompt_tokens, int) or isinstance(generation_tokens, int):
        return max(int(prompt_tokens or 0), 0) + max(int(generation_tokens or 0), 0)

    token_count = 0
    segments = result.get("segments", [])
    for segment in segments:
        if not isinstance(segment, dict):
            continue
        tokens = segment.get("tokens")
        if isinstance(tokens, (list, tuple)):
            token_count += len(tokens)
        elif isinstance(tokens, int):
            token_count += tokens
    return token_count
