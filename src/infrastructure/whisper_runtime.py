"""Runtime-обёртка над mlx_whisper для локальной транскрибации."""

from __future__ import annotations

from typing import Any

import mlx_whisper


def run_whisper_transcription(audio_data: object, model_name: str, language: str | None) -> dict[str, Any]:
    """Запускает один проход mlx_whisper с фиксированными runtime-параметрами."""
    result: dict[str, Any] = mlx_whisper.transcribe(
        audio_data,
        language=language,
        path_or_hf_repo=model_name,
        condition_on_previous_text=False,
        hallucination_silence_threshold=2.0,
    )
    return result
