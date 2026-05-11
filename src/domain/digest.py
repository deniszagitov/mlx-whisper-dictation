"""Доменные типы часовых и дневных резюме журнала диктовок."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class HourlyDigest:
    """Краткое резюме одного часа диктовок.

    Attributes:
        date: Локальная дата в формате `YYYY-MM-DD`.
        hour: Локальный час суток (0..23).
        summary: Текст резюме, сгенерированный LLM.
        source_event_ids: Идентификаторы событий журнала, попавших в этот час.
        duration_seconds: Сумма длительностей исходных аудиозаписей.
        event_count: Количество исходных событий.
        generated_at: Unix-time момента генерации резюме.
    """

    date: str
    hour: int
    summary: str
    source_event_ids: tuple[int, ...]
    duration_seconds: float
    event_count: int
    generated_at: float


@dataclass(frozen=True, slots=True)
class DailyDigest:
    """Цельное резюме одного дня, собранное из часовых резюме.

    Attributes:
        date: Локальная дата в формате `YYYY-MM-DD`.
        summary: Связный абзац-резюме за день.
        hourly_digest_ids: Идентификаторы часовых резюме, попавших в день.
        generated_at: Unix-time момента генерации резюме.
    """

    date: str
    summary: str
    hourly_digest_ids: tuple[int, ...]
    generated_at: float
