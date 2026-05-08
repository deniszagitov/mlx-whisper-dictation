"""Runtime-обёртки над локальными ASR backend-ами."""

from __future__ import annotations

import inspect
import logging
import threading
from typing import Any

try:
    import mlx.core as mx
except ImportError:
    mx = None  # type: ignore[assignment]

import mlx_whisper

LOGGER = logging.getLogger(__name__)

_QWEN_LANGUAGE_NAMES = {
    "ar": "Arabic",
    "arabic": "Arabic",
    "cs": "Czech",
    "czech": "Czech",
    "da": "Danish",
    "danish": "Danish",
    "de": "German",
    "german": "German",
    "el": "Greek",
    "greek": "Greek",
    "en": "English",
    "english": "English",
    "es": "Spanish",
    "spanish": "Spanish",
    "fa": "Persian",
    "persian": "Persian",
    "fi": "Finnish",
    "finnish": "Finnish",
    "fil": "Filipino",
    "filipino": "Filipino",
    "fr": "French",
    "french": "French",
    "hi": "Hindi",
    "hindi": "Hindi",
    "hu": "Hungarian",
    "hungarian": "Hungarian",
    "id": "Indonesian",
    "indonesian": "Indonesian",
    "it": "Italian",
    "italian": "Italian",
    "ja": "Japanese",
    "japanese": "Japanese",
    "ko": "Korean",
    "korean": "Korean",
    "mk": "Macedonian",
    "macedonian": "Macedonian",
    "ms": "Malay",
    "malay": "Malay",
    "nl": "Dutch",
    "dutch": "Dutch",
    "pl": "Polish",
    "polish": "Polish",
    "pt": "Portuguese",
    "portuguese": "Portuguese",
    "ro": "Romanian",
    "romanian": "Romanian",
    "ru": "Russian",
    "russian": "Russian",
    "sv": "Swedish",
    "swedish": "Swedish",
    "th": "Thai",
    "thai": "Thai",
    "tr": "Turkish",
    "turkish": "Turkish",
    "vi": "Vietnamese",
    "vietnamese": "Vietnamese",
    "yue": "Cantonese",
    "cantonese": "Cantonese",
    "zh": "Chinese",
    "zh-cn": "Chinese",
    "zh-hans": "Chinese",
    "zh-hant": "Chinese",
    "zh-tw": "Chinese",
    "chinese": "Chinese",
}
_QWEN_MODEL_CACHE: dict[str, object] = {}
_QWEN_MODEL_CACHE_LOCK = threading.Lock()


def _coerce_int(value: object) -> int:
    """Преобразует вход в неотрицательное целое число."""
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return max(value, 0)
    if isinstance(value, float):
        return max(int(value), 0)
    if isinstance(value, str):
        normalized = value.strip()
        if normalized.lstrip("-").isdigit():
            return max(int(normalized), 0)
    return 0


def _coerce_optional_text(value: object) -> str | None:
    """Преобразует произвольное значение в непустую строку."""
    if value is None:
        return None
    normalized = str(value).strip()
    return normalized or None


def is_qwen_asr_model(model_name: str) -> bool:
    """Определяет, что выбранная модель должна идти через mlx-audio."""
    normalized = model_name.rsplit("/", maxsplit=1)[-1].lower()
    return normalized.startswith("qwen3-asr")


def _map_qwen_language(language: str | None) -> str | None:
    """Преобразует языковой код приложения в имя языка для Qwen3-ASR."""
    normalized = _coerce_optional_text(language)
    if normalized is None:
        return None

    lookup_key = normalized.lower().replace("_", "-")
    mapped = _QWEN_LANGUAGE_NAMES.get(lookup_key)
    if mapped is None:
        LOGGER.info(
            "🧠 Для Qwen3-ASR язык %s не сопоставлен явно, использую автоопределение",
            normalized,
        )
    return mapped


def _load_qwen_model_from_mlx_audio(model_name: str) -> Any:
    """Загружает Qwen3-ASR модель через mlx-audio."""
    try:
        from mlx_audio.stt import load as load_mlx_audio_stt_model  # noqa: PLC0415
    except ImportError as exc:
        raise RuntimeError("Для модели Qwen3-ASR нужна зависимость mlx-audio. Выполните `uv sync --dev`.") from exc
    return load_mlx_audio_stt_model(model_name)


def _get_cached_qwen_model(model_name: str, model_loader: Any | None = None) -> Any:
    """Загружает и кэширует экземпляр Qwen3-ASR-модели."""
    with _QWEN_MODEL_CACHE_LOCK:
        cached_model = _QWEN_MODEL_CACHE.get(model_name)
        if cached_model is not None:
            return cached_model

    loader = model_loader or _load_qwen_model_from_mlx_audio
    model = loader(model_name)
    with _QWEN_MODEL_CACHE_LOCK:
        _QWEN_MODEL_CACHE[model_name] = model
    return model


def _normalize_qwen_segments(segments: object) -> list[dict[str, Any]]:
    """Приводит сегменты Qwen3-ASR к словарному формату приложения."""
    if not isinstance(segments, (list, tuple)):
        return []

    normalized_segments: list[dict[str, Any]] = []
    for segment in segments:
        if isinstance(segment, dict):
            normalized_segments.append(dict(segment))
            continue

        text = _coerce_optional_text(getattr(segment, "text", None))
        start = getattr(segment, "start", getattr(segment, "start_time", None))
        end = getattr(segment, "end", getattr(segment, "end_time", None))
        normalized_segment: dict[str, Any] = {}

        if text is not None:
            normalized_segment["text"] = text
        if isinstance(start, (int, float)):
            normalized_segment["start"] = float(start)
        if isinstance(end, (int, float)):
            normalized_segment["end"] = float(end)

        if normalized_segment:
            normalized_segments.append(normalized_segment)

    return normalized_segments


def run_whisper_transcription(audio_data: Any, model_name: str, language: str | None) -> dict[str, Any]:
    """Запускает один проход mlx_whisper с фиксированными runtime-параметрами."""
    kwargs: dict[str, Any] = {
        "language": language,
        "path_or_hf_repo": model_name,
        "condition_on_previous_text": False,
        "hallucination_silence_threshold": 2.0,
        "temperature": 0.0,
    }
    optional_kwargs = {
        "no_speech_threshold": 0.6,
        "compression_ratio_threshold": 2.4,
        "logprob_threshold": -1.0,
    }
    try:
        signature = inspect.signature(mlx_whisper.transcribe)
    except (TypeError, ValueError):
        signature = None
    accepts_kwargs = signature is None or any(
        parameter.kind is inspect.Parameter.VAR_KEYWORD for parameter in signature.parameters.values()
    )
    if accepts_kwargs:
        kwargs.update(optional_kwargs)
    elif signature is not None:
        kwargs.update({key: value for key, value in optional_kwargs.items() if key in signature.parameters})

    result: dict[str, Any] = mlx_whisper.transcribe(
        audio_data,
        **kwargs,
    )
    return result


def run_qwen_transcription(
    audio_data: Any,
    model_name: str,
    language: str | None,
    *,
    model_loader: Any | None = None,
) -> dict[str, Any]:
    """Запускает один проход Qwen3-ASR через mlx-audio без промежуточного WAV."""
    if mx is None:
        raise RuntimeError("Не удалось импортировать MLX runtime для Qwen3-ASR.")

    model = _get_cached_qwen_model(model_name, model_loader=model_loader)
    generate_kwargs: dict[str, object] = {}
    qwen_language = _map_qwen_language(language)
    if qwen_language is not None:
        generate_kwargs["language"] = qwen_language

    result = model.generate(mx.array(audio_data, dtype=mx.float32), **generate_kwargs)
    prompt_tokens = _coerce_int(getattr(result, "prompt_tokens", 0))
    generation_tokens = _coerce_int(getattr(result, "generation_tokens", 0))
    total_tokens = _coerce_int(getattr(result, "total_tokens", 0)) or (prompt_tokens + generation_tokens)
    detected_language = _coerce_optional_text(getattr(result, "language", None)) or qwen_language
    normalized_segments = _normalize_qwen_segments(getattr(result, "segments", []))

    return {
        "text": _coerce_optional_text(getattr(result, "text", "")) or "",
        "language": detected_language,
        "segments": normalized_segments,
        "prompt_tokens": prompt_tokens,
        "generation_tokens": generation_tokens,
        "total_tokens": total_tokens,
    }


def run_asr_transcription(audio_data: Any, model_name: str, language: str | None) -> dict[str, Any]:
    """Выбирает подходящий локальный ASR backend по имени модели."""
    if is_qwen_asr_model(model_name):
        return run_qwen_transcription(audio_data, model_name, language)
    return run_whisper_transcription(audio_data, model_name, language)
