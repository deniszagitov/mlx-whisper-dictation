"""Доменные типы журнала диктовок.

Журнал хранит каждое успешное распознавание с привязкой к исходному
аудио (PCM16 mono 16 kHz) и текстовому результату. На этих данных
строятся часовые и дневные саммари.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True, slots=True)
class DictationEvent:
    """Одно событие диктовки: текст + исходное аудио + метаданные.

    Attributes:
        started_at: Unix-time старта записи.
        ended_at: Unix-time момента, когда транскрипция готова.
        text: Финальный текст после постобработки.
        language: Код языка распознавания (если задан).
        model: Имя ASR-модели, выполнившей распознавание.
        source: Источник события — обычная диктовка или LLM-пайплайн
            (значения см. в `Config.JOURNAL_SOURCE_*`).
        audio_pcm16: Сырые байты аудио в формате PCM16 mono.
        sample_rate: Частота дискретизации аудио (обычно 16 000 Гц).
        duration_seconds: Длительность аудио после препроцессинга.
        rms_energy: RMS-энергия аудио, посчитанная на этапе препроцессинга.
    """

    started_at: float
    ended_at: float
    text: str
    language: str | None
    model: str
    source: str
    audio_pcm16: bytes
    sample_rate: int
    duration_seconds: float
    rms_energy: float


class JournalWriterProtocol(Protocol):
    """Протокол записи событий журнала диктовок."""

    def record_event(self, event: DictationEvent) -> int:
        """Сохраняет событие журнала и возвращает его id."""
        ...
