"""Runtime-обёртка над mlx_whisper для локальной транскрибации."""

from __future__ import annotations

import inspect
from typing import Any

import mlx_whisper


def run_whisper_transcription(audio_data: object, model_name: str, language: str | None) -> dict[str, Any]:
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
