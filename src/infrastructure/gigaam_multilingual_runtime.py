"""Runtime GigaAM Multilingual large_ctc через PyTorch MPS/CPU."""

from __future__ import annotations

import logging
import threading
from importlib import import_module
from typing import Any

import numpy as np

from ..domain.constants import Config

LOGGER = logging.getLogger(__name__)

_MODEL_CACHE: dict[str, object] = {}
_MODEL_CACHE_LOCK = threading.Lock()
_RUN_LOCK = threading.Lock()
_MAX_AUDIO_SECONDS = 25


def is_gigaam_multilingual_large_ctc_model(model_name: str) -> bool:
    """Определяет официальный 600M large_ctc checkpoint."""
    return model_name.strip().lower() == Config.GIGAAM_MULTILINGUAL_LARGE_CTC_MODEL.lower()


def load_gigaam_multilingual_large_ctc() -> object:
    """Загружает официальный large_ctc checkpoint на MPS или CPU."""
    try:
        torch = import_module("torch")
        transformers = import_module("transformers")
    except ImportError as error:
        raise RuntimeError(
            "Для GigaAM Multilingual large_ctc нужны torch, torchaudio, transformers, hydra-core и omegaconf. "
            "Выполните `uv sync --dev`."
        ) from error

    model = transformers.AutoModel.from_pretrained(
        Config.GIGAAM_MULTILINGUAL_REPO,
        revision=Config.GIGAAM_MULTILINGUAL_LARGE_CTC_REVISION,
        trust_remote_code=True,
    )
    device = "mps" if torch.backends.mps.is_available() else "cpu"
    model.eval()
    model.to(device)
    LOGGER.info("🧠 GigaAM Multilingual large_ctc загружена: device=%s", device)
    return model


def get_cached_gigaam_multilingual_model(model_name: str) -> Any:
    """Возвращает один кэшированный экземпляр large_ctc."""
    with _MODEL_CACHE_LOCK:
        cached_model = _MODEL_CACHE.get(model_name)
        if cached_model is not None:
            return cached_model

        model = load_gigaam_multilingual_large_ctc()
        _MODEL_CACHE[model_name] = model
        return model


def _model_device_and_dtype(model: object) -> tuple[object, object]:
    """Возвращает устройство и dtype первого параметра PyTorch-модели."""
    parameter = next(model.parameters())  # type: ignore[attr-defined]
    return parameter.device, parameter.dtype


def _normalize_language(language: str | None) -> str | None:
    """Оставляет только языки, заявленные для Multilingual checkpoint."""
    if language is None:
        return None
    normalized = language.strip().lower().replace("_", "-").split("-", maxsplit=1)[0]
    if normalized in Config.GIGAAM_MULTILINGUAL_LANGUAGES:
        return normalized
    LOGGER.warning(
        "🧠 GigaAM Multilingual не заявляет язык %s; декодирование остаётся автоматическим",
        language,
    )
    return None


def run_gigaam_multilingual_transcription(
    audio_data: Any,
    model_name: str,
    language: str | None,
) -> dict[str, Any]:
    """Распознаёт речь large_ctc из float32 mono 16 kHz PCM."""
    torch = import_module("torch")
    audio = np.ascontiguousarray(np.asarray(audio_data, dtype=np.float32).reshape(-1))
    normalized_language = _normalize_language(language)
    if not audio.size:
        return {
            "text": "",
            "language": normalized_language,
            "segments": [],
            "total_tokens": 0,
        }

    model = get_cached_gigaam_multilingual_model(model_name)
    inner_model = model.model
    device, dtype = _model_device_and_dtype(model)
    chunk_samples = Config.AUDIO_SAMPLE_RATE * _MAX_AUDIO_SECONDS
    text_parts: list[str] = []
    segments: list[dict[str, Any]] = []
    total_tokens = 0

    with _RUN_LOCK, torch.inference_mode():
        for chunk_start in range(0, len(audio), chunk_samples):
            chunk = audio[chunk_start : chunk_start + chunk_samples]
            wav = torch.from_numpy(chunk).to(device=device, dtype=dtype).unsqueeze(0)
            wav_length = torch.full(
                [1],
                wav.shape[-1],
                device=device,
                dtype=torch.long,
            )
            encoded, encoded_length = inner_model(wav, wav_length)
            text, token_ids, _token_frames = inner_model.decoding.decode(
                inner_model.head,
                encoded,
                encoded_length,
            )[0]
            normalized_text = str(text).strip()
            if normalized_text:
                text_parts.append(normalized_text)

            token_count = len(token_ids)
            total_tokens += token_count
            offset_s = chunk_start / Config.AUDIO_SAMPLE_RATE
            segments.append(
                {
                    "text": normalized_text,
                    "start": offset_s,
                    "end": offset_s + len(chunk) / Config.AUDIO_SAMPLE_RATE,
                    "tokens": token_count,
                }
            )

    return {
        "text": " ".join(text_parts),
        "language": normalized_language,
        "segments": segments,
        "total_tokens": total_tokens,
    }
