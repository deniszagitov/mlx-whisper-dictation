"""Runtime-обёртки над локальными ASR backend-ами."""

from __future__ import annotations

import inspect
import logging
import threading
from importlib import import_module
from pathlib import Path
from typing import Any

import numpy as np
from huggingface_hub import hf_hub_download

try:
    import mlx.core as mx
except ImportError:
    mx = None  # type: ignore[assignment]

try:
    from mlx_audio.stt import load as load_mlx_audio_stt_model
except ImportError:
    load_mlx_audio_stt_model = None

import mlx_whisper

from ..domain.constants import Config
from .gigaam_multilingual_runtime import (
    is_gigaam_multilingual_large_ctc_model,
    run_gigaam_multilingual_transcription,
)

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
_GIGAAM_MODEL_CACHE: dict[str, object] = {}
_GIGAAM_MODEL_CACHE_LOCK = threading.Lock()
_GIGAAM_RUN_LOCK = threading.Lock()
_GIGAAM_MAX_AUDIO_MS = 25_000


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


def is_gigaam_asr_model(model_name: str) -> bool:
    """Определяет GigaAM-v3 e2e RNN-T в формате GGUF."""
    normalized = model_name.strip().lower()
    basename = normalized.rsplit("/", maxsplit=1)[-1]
    return normalized == Config.GIGAAM_MODEL_REPO.lower() or (
        basename.startswith("gigaam-v3-e2e-rnnt-") and basename.endswith(".gguf")
    )


def _resolve_gigaam_model_path(model_name: str) -> Path:
    """Возвращает локальный путь к выбранному GGUF, скачивая пресет при необходимости."""
    if model_name.strip().lower() == Config.GIGAAM_MODEL_REPO.lower():
        downloaded_path = hf_hub_download(
            repo_id=Config.GIGAAM_MODEL_REPO,
            filename=Config.GIGAAM_MODEL_FILENAME,
        )
        return Path(downloaded_path)

    local_path = Path(model_name).expanduser()
    if local_path.is_file():
        return local_path.resolve()
    raise FileNotFoundError(f"GGUF-модель GigaAM не найдена: {local_path}")


def _load_gigaam_model(model_path: Path) -> object:
    """Загружает GGUF-модель через официальный Python binding transcribe.cpp."""
    try:
        transcribe_cpp = import_module("transcribe_cpp")
    except ImportError as error:
        raise RuntimeError(
            "Для GigaAM GGUF нужна зависимость transcribe-cpp. Выполните `uv sync --dev`."
        ) from error

    return transcribe_cpp.Model(model_path, backend="auto")


def _get_cached_gigaam_model(model_name: str) -> Any:
    """Загружает и кэширует GigaAM, чтобы не перечитывать GGUF для каждой диктовки."""
    with _GIGAAM_MODEL_CACHE_LOCK:
        cached_model = _GIGAAM_MODEL_CACHE.get(model_name)
        if cached_model is not None:
            return cached_model

        model_path = _resolve_gigaam_model_path(model_name)
        model = _load_gigaam_model(model_path)
        _GIGAAM_MODEL_CACHE[model_name] = model

    LOGGER.info(
        "🧠 GigaAM загружена: %s, backend=%s",
        model_path,
        getattr(model, "backend", "неизвестно"),
    )
    return model


def _normalize_gigaam_segment(segment: object, *, offset_s: float) -> dict[str, Any]:
    """Приводит сегмент transcribe.cpp к формату диагностик приложения."""
    normalized: dict[str, Any] = {}
    text = _coerce_optional_text(getattr(segment, "text", None))
    if text is not None:
        normalized["text"] = text

    start_ms = getattr(segment, "t0_ms", None)
    end_ms = getattr(segment, "t1_ms", None)
    if isinstance(start_ms, (int, float)):
        normalized["start"] = offset_s + float(start_ms) / 1000.0
    if isinstance(end_ms, (int, float)):
        normalized["end"] = offset_s + float(end_ms) / 1000.0

    token_count = _coerce_int(getattr(segment, "n_tokens", 0))
    if token_count:
        normalized["tokens"] = token_count
    return normalized


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


def _get_cached_qwen_model(model_name: str) -> Any:
    """Загружает и кэширует экземпляр Qwen3-ASR-модели."""
    with _QWEN_MODEL_CACHE_LOCK:
        cached_model = _QWEN_MODEL_CACHE.get(model_name)
        if cached_model is not None:
            return cached_model

    if load_mlx_audio_stt_model is None:
        raise RuntimeError(
            "Для модели Qwen3-ASR нужна зависимость mlx-audio. Выполните `uv sync --dev`."
        )

    model = load_mlx_audio_stt_model(model_name)
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


def run_qwen_transcription(audio_data: Any, model_name: str, language: str | None) -> dict[str, Any]:
    """Запускает один проход Qwen3-ASR через mlx-audio без промежуточного WAV."""
    if mx is None:
        raise RuntimeError("Не удалось импортировать MLX runtime для Qwen3-ASR.")

    model = _get_cached_qwen_model(model_name)
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


def run_gigaam_transcription(audio_data: Any, model_name: str, language: str | None) -> dict[str, Any]:
    """Распознаёт русскую речь через GigaAM-v3 e2e RNN-T и transcribe.cpp."""
    if language is not None and language.lower().replace("_", "-") not in {"ru", "ru-ru", "russian"}:
        LOGGER.warning("🧠 GigaAM-v3 поддерживает только русский язык; настройка %s игнорируется", language)

    audio = np.ascontiguousarray(np.asarray(audio_data, dtype=np.float32).reshape(-1))
    if not audio.size:
        return {"text": "", "language": "ru", "segments": [], "total_tokens": 0}

    model = _get_cached_gigaam_model(model_name)
    text_parts: list[str] = []
    normalized_segments: list[dict[str, Any]] = []
    total_tokens = 0

    with _GIGAAM_RUN_LOCK, model.session() as session:
        session_limit_ms = _coerce_int(getattr(getattr(session, "limits", None), "effective_max_audio_ms", 0))
        max_audio_ms = min(session_limit_ms or _GIGAAM_MAX_AUDIO_MS, _GIGAAM_MAX_AUDIO_MS)
        chunk_samples = max(int(Config.AUDIO_SAMPLE_RATE * max_audio_ms / 1000), 1)

        for chunk_start in range(0, len(audio), chunk_samples):
            chunk = audio[chunk_start : chunk_start + chunk_samples]
            result = session.run(chunk, language=None, timestamps="auto")
            chunk_text = _coerce_optional_text(getattr(result, "text", ""))
            if chunk_text is not None:
                text_parts.append(chunk_text)

            offset_s = chunk_start / Config.AUDIO_SAMPLE_RATE
            result_segments = tuple(getattr(result, "segments", ()) or ())
            for segment in result_segments:
                normalized_segment = _normalize_gigaam_segment(segment, offset_s=offset_s)
                if normalized_segment:
                    normalized_segments.append(normalized_segment)

            result_tokens = tuple(getattr(result, "tokens", ()) or ())
            chunk_token_count = len(result_tokens)
            total_tokens += chunk_token_count
            if not result_segments and chunk_text is not None:
                normalized_segments.append(
                    {
                        "text": chunk_text,
                        "start": offset_s,
                        "end": offset_s + len(chunk) / Config.AUDIO_SAMPLE_RATE,
                        "tokens": chunk_token_count,
                    }
                )

    return {
        "text": " ".join(text_parts),
        "language": "ru",
        "segments": normalized_segments,
        "total_tokens": total_tokens,
    }


def run_asr_transcription(audio_data: Any, model_name: str, language: str | None) -> dict[str, Any]:
    """Выбирает подходящий локальный ASR backend по имени модели."""
    if is_gigaam_multilingual_large_ctc_model(model_name):
        return run_gigaam_multilingual_transcription(audio_data, model_name, language)
    if is_gigaam_asr_model(model_name):
        return run_gigaam_transcription(audio_data, model_name, language)
    if is_qwen_asr_model(model_name):
        return run_qwen_transcription(audio_data, model_name, language)
    return run_whisper_transcription(audio_data, model_name, language)
