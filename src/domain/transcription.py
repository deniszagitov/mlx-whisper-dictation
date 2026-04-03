"""Чистые правила обработки транскрипции и истории."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from .constants import Config

if TYPE_CHECKING:
    import numpy as np
    import numpy.typing as npt

    from .types import AudioDiagnostics, HistoryRecord


def looks_like_hallucination(text: str) -> bool:
    """Проверяет, похож ли результат на типичную галлюцинацию Whisper."""
    return text.strip().lower() in Config.KNOWN_HALLUCINATIONS


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
