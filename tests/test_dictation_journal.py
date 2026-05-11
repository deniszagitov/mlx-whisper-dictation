"""Тесты use case часовых и дневных резюме журнала."""

from __future__ import annotations

from datetime import datetime, time
from typing import TYPE_CHECKING

import pytest
from src.domain.constants import Config
from src.domain.digest import DailyDigest, HourlyDigest
from src.use_cases.dictation_journal import DictationJournalUseCases

if TYPE_CHECKING:
    from collections.abc import Sequence


def _hour_unix(date: str, hour: int) -> float:
    """Возвращает unix-время начала локального часа."""
    return datetime.combine(datetime.strptime(date, "%Y-%m-%d").date(), time(hour=hour)).timestamp()


def _make_event(
    *,
    event_id: int,
    started_at: float,
    text: str = "пример текста",
    duration_seconds: float = 4.0,
) -> dict[str, object]:
    """Готовит dict-событие в формате `JournalDb.events_in_range()`."""
    return {
        "id": event_id,
        "started_at": started_at,
        "ended_at": started_at + duration_seconds,
        "text": text,
        "language": "ru",
        "model": "test-model",
        "source": Config.JOURNAL_SOURCE_DICTATION,
        "sample_rate": 16000,
        "duration_seconds": duration_seconds,
        "rms_energy": 0.012,
        "audio_bytes": int(duration_seconds * 32000),
    }


class FakeJournal:
    """In-memory заглушка журнала для тестирования use case-а."""

    def __init__(self) -> None:
        self.events: list[dict[str, object]] = []
        self.hourly_digests: list[HourlyDigest] = []
        self.daily_digests: list[DailyDigest] = []
        self.deleted_dates: list[str] = []

    def add_event(self, event: dict[str, object]) -> None:
        self.events.append(event)

    def events_in_range(self, start_unix: float, end_unix: float) -> list[dict[str, object]]:
        def _started_at(event: dict[str, object]) -> float:
            value = event["started_at"]
            return float(value) if isinstance(value, (int, float)) else 0.0

        return [event for event in self.events if start_unix <= _started_at(event) < end_unix]

    def upsert_hourly_digest(self, digest: HourlyDigest) -> int:
        existing = [
            (idx, item)
            for idx, item in enumerate(self.hourly_digests)
            if item.date == digest.date and item.hour == digest.hour
        ]
        if existing:
            idx, _ = existing[0]
            self.hourly_digests[idx] = digest
            return idx + 1
        self.hourly_digests.append(digest)
        return len(self.hourly_digests)

    def hourly_digests_for_date(self, date: str) -> list[HourlyDigest]:
        return sorted(
            (digest for digest in self.hourly_digests if digest.date == date),
            key=lambda digest: digest.hour,
        )

    def upsert_daily_digest(self, digest: DailyDigest) -> int:
        for idx, item in enumerate(self.daily_digests):
            if item.date == digest.date:
                self.daily_digests[idx] = digest
                return idx + 1
        self.daily_digests.append(digest)
        return len(self.daily_digests)

    def delete_hourly_digests_for_date(self, date: str) -> int:
        before = len(self.hourly_digests)
        self.hourly_digests = [digest for digest in self.hourly_digests if digest.date != date]
        self.deleted_dates.append(date)
        return before - len(self.hourly_digests)


class FakeLlm:
    """Заглушка LLM-процессора с управляемыми ответами."""

    def __init__(self, response: str = "сгенерированное резюме") -> None:
        self.response = response
        self.calls: list[dict[str, object]] = []
        self.last_token_usage = 0
        self.download_progress_callback = None

    def is_model_cached(self) -> bool:
        return True

    def set_performance_mode(self, _mode: str) -> None:
        return None

    def process_text(
        self,
        text: str,
        system_prompt: str,
        *,
        context: str | None = None,
        max_tokens: int | None = None,
    ) -> str:
        self.calls.append(
            {
                "text": text,
                "system_prompt": system_prompt,
                "context": context,
                "max_tokens": max_tokens,
            },
        )
        return self.response

    def ensure_model_downloaded(self) -> None:
        return None

    def change_model(self, _name: str) -> None:
        return None


class FailingLlm(FakeLlm):
    """LLM-заглушка, бросающая исключение в process_text."""

    def process_text(self, *args, **kwargs):
        raise RuntimeError("boom")


class FakeExporter:
    """Перехватывает вызовы export_daily."""

    def __init__(self, *, raise_error: bool = False) -> None:
        self.calls: list[tuple[DailyDigest, Sequence[HourlyDigest]]] = []
        self.raise_error = raise_error

    def export_daily(self, daily: DailyDigest, hourly: Sequence[HourlyDigest]) -> None:
        self.calls.append((daily, tuple(hourly)))
        if self.raise_error:
            raise RuntimeError("disk full")


@pytest.fixture
def fixed_clock():
    """Возвращает фиксированный clock для воспроизводимых тестов."""
    return lambda: 1_700_000_000.0


def _seed_significant_hour(journal: FakeJournal, date: str, hour: int) -> None:
    """Заполняет час двумя событиями выше порога значимости."""
    base = _hour_unix(date, hour)
    journal.add_event(_make_event(event_id=1, started_at=base + 10, text="первое", duration_seconds=4.0))
    journal.add_event(_make_event(event_id=2, started_at=base + 30, text="второе", duration_seconds=5.0))


class TestSummarizeHour:
    """Сценарии часового резюме."""

    def test_returns_none_when_hour_is_below_significance_threshold(self, fixed_clock):
        """Час с одной короткой записью не запускает LLM-вызов."""
        journal = FakeJournal()
        base = _hour_unix("2026-05-10", 9)
        journal.add_event(_make_event(event_id=1, started_at=base + 10, duration_seconds=2.0))
        llm = FakeLlm()
        use_case = DictationJournalUseCases(journal, llm, clock=fixed_clock)

        result = use_case.summarize_hour("2026-05-10", 9)

        assert result is None
        assert llm.calls == []
        assert journal.hourly_digests == []

    def test_returns_none_when_no_events_in_hour(self, fixed_clock):
        """Пустой час не запускает LLM."""
        journal = FakeJournal()
        llm = FakeLlm()
        use_case = DictationJournalUseCases(journal, llm, clock=fixed_clock)

        assert use_case.summarize_hour("2026-05-10", 9) is None
        assert llm.calls == []

    def test_persists_hourly_digest_when_significant(self, fixed_clock):
        """Час с достаточной длительностью пишется в журнал."""
        journal = FakeJournal()
        _seed_significant_hour(journal, "2026-05-10", 9)
        llm = FakeLlm(response="итог часа")
        use_case = DictationJournalUseCases(journal, llm, clock=fixed_clock)

        result = use_case.summarize_hour("2026-05-10", 9)

        assert result is not None
        assert result.summary == "итог часа"
        assert result.event_count == 2
        assert result.duration_seconds == pytest.approx(9.0)
        assert journal.hourly_digests == [result]
        assert len(llm.calls) == 1
        assert llm.calls[0]["max_tokens"] == Config.DIGEST_HOURLY_MAX_TOKENS
        assert "первое" in str(llm.calls[0]["text"])
        assert "второе" in str(llm.calls[0]["text"])

    def test_skips_when_llm_is_not_configured(self, fixed_clock):
        """Без LLM журнал не пишется."""
        journal = FakeJournal()
        _seed_significant_hour(journal, "2026-05-10", 9)
        use_case = DictationJournalUseCases(journal, llm_processor=None, clock=fixed_clock)

        assert use_case.summarize_hour("2026-05-10", 9) is None
        assert journal.hourly_digests == []

    def test_skips_when_llm_returns_blank(self, fixed_clock):
        """Пустой ответ LLM не должен попадать в журнал."""
        journal = FakeJournal()
        _seed_significant_hour(journal, "2026-05-10", 9)
        use_case = DictationJournalUseCases(journal, FakeLlm(response="   "), clock=fixed_clock)

        assert use_case.summarize_hour("2026-05-10", 9) is None
        assert journal.hourly_digests == []

    def test_swallows_llm_errors(self, fixed_clock):
        """Ошибка LLM не ломает планировщик и не пишет резюме."""
        journal = FakeJournal()
        _seed_significant_hour(journal, "2026-05-10", 9)
        use_case = DictationJournalUseCases(journal, FailingLlm(), clock=fixed_clock)

        assert use_case.summarize_hour("2026-05-10", 9) is None
        assert journal.hourly_digests == []


def _hourly(hour: int, summary: str) -> HourlyDigest:
    """Готовит часовое резюме с минимальными значимыми полями."""
    return HourlyDigest(
        date="2026-05-10",
        hour=hour,
        summary=summary,
        source_event_ids=(1,),
        duration_seconds=10.0,
        event_count=1,
        generated_at=0.0,
    )


class TestSummarizeDay:
    """Сценарии дневного резюме."""

    def test_returns_none_when_day_has_no_hourly_digests(self, fixed_clock):
        """Без часовых резюме дневной digest не создаётся."""
        journal = FakeJournal()
        use_case = DictationJournalUseCases(journal, FakeLlm(), clock=fixed_clock)

        assert use_case.summarize_day("2026-05-10") is None
        assert journal.daily_digests == []

    def test_persists_daily_digest_and_calls_exporter(self, fixed_clock):
        """Дневной digest пишется в журнал и отдаётся экспортеру."""
        journal = FakeJournal()
        journal.upsert_hourly_digest(_hourly(9, "утром погулял"))
        journal.upsert_hourly_digest(_hourly(15, "сделал созвон"))
        exporter = FakeExporter()
        llm = FakeLlm(response="день получился насыщенным")
        use_case = DictationJournalUseCases(journal, llm, digest_exporter=exporter, clock=fixed_clock)

        result = use_case.summarize_day("2026-05-10")

        assert result is not None
        assert result.summary == "день получился насыщенным"
        assert journal.daily_digests == [result]
        assert len(llm.calls) == 1
        assert llm.calls[0]["max_tokens"] == Config.DIGEST_DAILY_MAX_TOKENS
        assert "утром погулял" in str(llm.calls[0]["text"])
        assert "сделал созвон" in str(llm.calls[0]["text"])
        assert len(exporter.calls) == 1
        exported_daily, exported_hourly = exporter.calls[0]
        assert exported_daily is result
        assert [digest.hour for digest in exported_hourly] == [9, 15]

    def test_continues_when_exporter_fails(self, fixed_clock):
        """Ошибка экспорта не должна откатывать запись резюме в журнал."""
        journal = FakeJournal()
        journal.upsert_hourly_digest(_hourly(9, "пара мыслей"))
        exporter = FakeExporter(raise_error=True)
        use_case = DictationJournalUseCases(journal, FakeLlm(), digest_exporter=exporter, clock=fixed_clock)

        result = use_case.summarize_day("2026-05-10")

        assert result is not None
        assert journal.daily_digests == [result]


class TestRegenerateToday:
    """Сценарий ручной пересборки за сегодня."""

    def test_runs_summarize_for_each_hour_with_events_and_finalizes_day(self):
        """Пересборка очищает старое и проходит по всем часам с событиями."""
        date = "2026-05-10"
        clock_value = datetime.combine(
            datetime.strptime(date, "%Y-%m-%d").date(),
            time(hour=22),
        ).timestamp()
        journal = FakeJournal()
        # Часы 9 и 15 — значимые, час 11 — слишком короткий.
        _seed_significant_hour(journal, date, 9)
        _seed_significant_hour(journal, date, 15)
        base_short_hour = _hour_unix(date, 11)
        journal.add_event(
            _make_event(event_id=99, started_at=base_short_hour + 5, duration_seconds=1.5),
        )
        # Старый часовой digest, который должен быть удалён.
        journal.upsert_hourly_digest(_hourly(7, "вчерашняя выдумка"))

        llm = FakeLlm(response="сводка")
        use_case = DictationJournalUseCases(journal, llm, clock=lambda: clock_value)

        result = use_case.regenerate_today()

        assert journal.deleted_dates == [date]
        hours_in_journal = [digest.hour for digest in journal.hourly_digests_for_date(date)]
        assert hours_in_journal == [9, 15]
        assert result is not None
        assert result.date == date

    def test_uses_clock_to_derive_today(self):
        """Без явного аргумента берёт сегодняшнюю дату из часов."""
        clock_value = datetime(2026, 5, 11, 23, 0, 0).timestamp()
        journal = FakeJournal()
        use_case = DictationJournalUseCases(journal, FakeLlm(), clock=lambda: clock_value)

        # Должно работать даже без событий (просто вернуть None и почистить день).
        assert use_case.regenerate_today() is None
        assert journal.deleted_dates == ["2026-05-11"]


def test_significance_uses_min_duration_threshold():
    """Через границу длительности порог значимости меняет решение."""
    journal = FakeJournal()
    base = _hour_unix("2026-05-10", 9)
    short_event = _make_event(
        event_id=1, started_at=base + 10, duration_seconds=Config.DIGEST_HOURLY_MIN_DURATION_SECONDS - 0.1,
    )
    journal.add_event(short_event)
    use_case = DictationJournalUseCases(journal, FakeLlm(), clock=lambda: 0.0)

    assert use_case.summarize_hour("2026-05-10", 9) is None

    journal.events.clear()
    journal.add_event(
        _make_event(
            event_id=2,
            started_at=base + 10,
            duration_seconds=Config.DIGEST_HOURLY_MIN_DURATION_SECONDS,
        ),
    )

    result = use_case.summarize_hour("2026-05-10", 9)
    assert result is not None


def test_input_text_contains_hour_minute_markers(fixed_clock):
    """Вход в LLM содержит маркеры HH:MM, чтобы модель могла учесть тайминг."""
    journal = FakeJournal()
    base = _hour_unix("2026-05-10", 9)
    plus_minutes = base + 12 * 60 + 30  # 09:12:30
    journal.add_event(_make_event(event_id=1, started_at=base, duration_seconds=4.0))
    journal.add_event(_make_event(event_id=2, started_at=plus_minutes, duration_seconds=4.0))
    llm = FakeLlm()
    use_case = DictationJournalUseCases(journal, llm, clock=fixed_clock)

    use_case.summarize_hour("2026-05-10", 9)

    assert llm.calls
    rendered = str(llm.calls[0]["text"])
    assert "[09:00]" in rendered or "[09:12]" in rendered


def test_progress_callback_is_called(fixed_clock):
    """Внешний наблюдатель прогресса получает уведомления."""
    journal = FakeJournal()
    _seed_significant_hour(journal, "2026-05-10", 9)
    progress: list[str] = []
    use_case = DictationJournalUseCases(
        journal,
        FakeLlm(),
        clock=fixed_clock,
        on_progress=progress.append,
    )

    use_case.summarize_hour("2026-05-10", 9)

    assert any("Часовое резюме" in message for message in progress)
