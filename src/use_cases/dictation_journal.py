"""Use case часовых и дневных резюме журнала диктовок.

Логика разбита на два шага, чтобы держать нагрузку на LLM маленькой и
избегать «прыжков» в итоговой заметке:

1. `summarize_hour(date, hour)` — вызывается по завершении часа. Если в
   часу было достаточно речи (см. порог значимости в `Config`), события
   склеиваются в один LLM-вызов и результат пишется в `hourly_digests`.
2. `summarize_day(date)` — вызывается в начале следующего дня (или
   вручную из меню). Берёт все часовые резюме за дату, собирает их в
   один LLM-вызов и пишет результат в `daily_digests`. Здесь же
   опциональный экспорт в Obsidian / папку с дайджестами.
"""

from __future__ import annotations

import logging
import time as _time
from datetime import datetime, time, timedelta
from typing import TYPE_CHECKING, Protocol

from ..domain.constants import Config
from ..domain.digest import DailyDigest, HourlyDigest

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence

    from ..domain.ports import LlmGatewayProtocol

LOGGER = logging.getLogger(__name__)


class JournalReadWritePort(Protocol):
    """Порт журнала, нужный use case-у. Подмножество `JournalDb`."""

    def events_in_range(self, start_unix: float, end_unix: float) -> list[dict[str, object]]:
        """Возвращает события в полу-открытом интервале `[start, end)`."""
        ...

    def upsert_hourly_digest(self, digest: HourlyDigest) -> int:
        """Сохраняет часовое резюме."""
        ...

    def hourly_digests_for_date(self, date: str) -> list[HourlyDigest]:
        """Возвращает часовые резюме за дату."""
        ...

    def upsert_daily_digest(self, digest: DailyDigest) -> int:
        """Сохраняет дневное резюме."""
        ...

    def delete_hourly_digests_for_date(self, date: str) -> int:
        """Удаляет часовые резюме за дату."""
        ...


class DigestExporterPort(Protocol):
    """Порт экспорта дневного резюме во внешний файл (например, Obsidian)."""

    def export_daily(self, daily: DailyDigest, hourly: Sequence[HourlyDigest]) -> None:
        """Записывает дневной дайджест в файл, если экспорт включён."""
        ...


def _hour_window_unix(date: str, hour: int) -> tuple[float, float]:
    """Возвращает unix-границы локального часа `[start, end)`."""
    start_dt = datetime.combine(datetime.strptime(date, "%Y-%m-%d").date(), time(hour=hour))
    end_dt = start_dt + timedelta(hours=1)
    return start_dt.timestamp(), end_dt.timestamp()


def _day_bounds_for_date(date: str) -> tuple[float, float]:
    """Возвращает unix-границы локального дня `[start, end)`."""
    start_dt = datetime.combine(datetime.strptime(date, "%Y-%m-%d").date(), time(hour=0))
    end_dt = start_dt + timedelta(days=1)
    return start_dt.timestamp(), end_dt.timestamp()


def _coerce_float(value: object, fallback: float = 0.0) -> float:
    """Безопасно приводит значение из dict-события к float."""
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            return fallback
    return fallback


def _coerce_int(value: object, fallback: int = 0) -> int:
    """Безопасно приводит значение из dict-события к int."""
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, (int, float)):
        return int(value)
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError:
            return fallback
    return fallback


def _event_duration(event: dict[str, object]) -> float:
    """Возвращает длительность события в секундах."""
    return _coerce_float(event.get("duration_seconds", 0.0))


def _is_hour_significant(events: Sequence[dict[str, object]]) -> bool:
    """Проверяет, что в часу достаточно речи, чтобы запускать LLM-резюме."""
    if len(events) < Config.DIGEST_HOURLY_MIN_EVENT_COUNT:
        return False
    total_duration = sum(_event_duration(event) for event in events)
    return total_duration >= Config.DIGEST_HOURLY_MIN_DURATION_SECONDS


def _hour_input_text(events: Sequence[dict[str, object]]) -> str:
    """Готовит вход для LLM: тексты событий часа, отсортированные по времени."""
    parts: list[str] = []
    for event in events:
        text = str(event.get("text", "")).strip()
        if not text:
            continue
        started_at = _coerce_float(event.get("started_at", 0.0))
        marker = datetime.fromtimestamp(started_at).strftime("%H:%M") if started_at else "??:??"
        parts.append(f"[{marker}] {text}")
    return "\n".join(parts)


def _day_input_text(hourly: Sequence[HourlyDigest]) -> str:
    """Готовит вход для дневного LLM-вызова из часовых резюме."""
    parts: list[str] = []
    for digest in hourly:
        if not digest.summary.strip():
            continue
        parts.append(f"[{digest.hour:02d}:00] {digest.summary.strip()}")
    return "\n".join(parts)


class DictationJournalUseCases:
    """Часовые и дневные резюме журнала диктовок через локальную LLM."""

    def __init__(
        self,
        journal: JournalReadWritePort,
        llm_processor: LlmGatewayProtocol | None,
        *,
        digest_exporter: DigestExporterPort | None = None,
        clock: Callable[[], float] | None = None,
        on_progress: Callable[[str], None] | None = None,
    ) -> None:
        """Создаёт use case.

        Args:
            journal: Порт журнала (записи + резюме).
            llm_processor: Локальная LLM. Если None, генерация резюме невозможна.
            digest_exporter: Необязательный экспорт в файл (Obsidian / fallback).
            clock: Источник времени (по умолчанию `time.time`).
            on_progress: Опциональный callback статусов для UI/логов.
        """
        self._journal = journal
        self._llm = llm_processor
        self._exporter = digest_exporter
        self._clock = clock or _time.time
        self._on_progress = on_progress or (lambda _msg: None)

    def summarize_hour(self, date: str, hour: int) -> HourlyDigest | None:
        """Генерирует часовое резюме, если в часу было достаточно речи.

        Возвращает резюме или None, если час пустой/не значимый или LLM недоступна.
        """
        if self._llm is None:
            LOGGER.debug("⏭️ LLM недоступна — пропускаю часовое резюме %s %02d:00", date, hour)
            return None

        start_unix, end_unix = _hour_window_unix(date, hour)
        events = self._journal.events_in_range(start_unix, end_unix)
        if not _is_hour_significant(events):
            LOGGER.debug(
                "⏭️ Час %s %02d:00 не значимый: событий=%d", date, hour, len(events),
            )
            return None

        input_text = _hour_input_text(events)
        if not input_text:
            return None

        self._on_progress(f"📒 Часовое резюме {date} {hour:02d}:00")
        try:
            summary = self._llm.process_text(
                input_text,
                Config.DIGEST_HOURLY_PROMPT,
                max_tokens=Config.DIGEST_HOURLY_MAX_TOKENS,
            )
        except Exception:
            LOGGER.exception("❌ Ошибка LLM при часовом резюме %s %02d:00", date, hour)
            return None

        cleaned_summary = (summary or "").strip()
        if not cleaned_summary:
            LOGGER.warning("⚠️ Пустое часовое резюме %s %02d:00", date, hour)
            return None

        digest = HourlyDigest(
            date=date,
            hour=hour,
            summary=cleaned_summary,
            source_event_ids=tuple(_coerce_int(event.get("id")) for event in events),
            duration_seconds=sum(_event_duration(event) for event in events),
            event_count=len(events),
            generated_at=self._clock(),
        )
        self._journal.upsert_hourly_digest(digest)
        return digest

    def summarize_day(self, date: str) -> DailyDigest | None:
        """Генерирует дневное резюме на основе уже готовых часовых.

        Если для дня нет ни одного часового резюме — возвращает None.
        После записи резюме делает экспорт в файл (если экспортер задан).
        """
        if self._llm is None:
            LOGGER.debug("⏭️ LLM недоступна — пропускаю дневное резюме %s", date)
            return None

        hourly = self._journal.hourly_digests_for_date(date)
        if not hourly:
            LOGGER.info("ℹ️ Нет часовых резюме за %s — пропускаю дневное резюме", date)
            return None

        input_text = _day_input_text(hourly)
        if not input_text:
            return None

        self._on_progress(f"📒 Дневное резюме {date}")
        try:
            summary = self._llm.process_text(
                input_text,
                Config.DIGEST_DAILY_PROMPT,
                max_tokens=Config.DIGEST_DAILY_MAX_TOKENS,
            )
        except Exception:
            LOGGER.exception("❌ Ошибка LLM при дневном резюме %s", date)
            return None

        cleaned_summary = (summary or "").strip()
        if not cleaned_summary:
            LOGGER.warning("⚠️ Пустое дневное резюме %s", date)
            return None

        digest = DailyDigest(
            date=date,
            summary=cleaned_summary,
            hourly_digest_ids=(),
            generated_at=self._clock(),
        )
        self._journal.upsert_daily_digest(digest)

        if self._exporter is not None:
            try:
                self._exporter.export_daily(digest, hourly)
            except Exception:
                LOGGER.exception("⚠️ Не удалось экспортировать дневное резюме %s", date)

        return digest

    def regenerate_today(self, today: str | None = None) -> DailyDigest | None:
        """Полностью пересобирает резюме для текущего дня.

        Используется кнопкой «Перегенерировать сегодня» в меню. Удаляет
        накопленные часовые резюме за день, прогоняет генерацию по всем
        часам, в которых были события, и финализирует дневным резюме.
        """
        date = today or datetime.fromtimestamp(self._clock()).strftime("%Y-%m-%d")
        self._journal.delete_hourly_digests_for_date(date)

        day_start, day_end = _day_bounds_for_date(date)
        events = self._journal.events_in_range(day_start, day_end)
        hours_with_events: set[int] = {
            datetime.fromtimestamp(_coerce_float(event.get("started_at", 0.0))).hour for event in events
        }
        for hour in sorted(hours_with_events):
            self.summarize_hour(date, hour)

        return self.summarize_day(date)


__all__ = [
    "DictationJournalUseCases",
    "DigestExporterPort",
    "JournalReadWritePort",
]
