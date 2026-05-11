"""Тесты SQLite-журнала диктовок."""

from __future__ import annotations

import struct

import pytest
from src.domain.constants import Config
from src.domain.dictation_log import DictationEvent
from src.domain.digest import DailyDigest, HourlyDigest
from src.infrastructure.persistence.journal_db import JournalDb


def _sample_pcm16(num_samples: int = 16) -> bytes:
    """Возвращает простой PCM16 буфер фиксированной длины."""
    return struct.pack("<" + "h" * num_samples, *range(num_samples))


@pytest.fixture
def journal(tmp_path):
    """Журнал поверх временной БД."""
    return JournalDb(tmp_path / "journal.db")


def make_event(
    *,
    started_at: float = 1_700_000_000.0,
    ended_at: float = 1_700_000_002.5,
    text: str = "привет",
    language: str | None = "ru",
    source: str = Config.JOURNAL_SOURCE_DICTATION,
    audio: bytes | None = None,
    sample_rate: int = 16000,
    duration_seconds: float = 2.5,
    rms_energy: float = 0.012,
    model: str = "mlx-community/whisper-large-v3-turbo",
) -> DictationEvent:
    """Готовит DictationEvent с предсказуемыми значениями для тестов."""
    return DictationEvent(
        started_at=started_at,
        ended_at=ended_at,
        text=text,
        language=language,
        model=model,
        source=source,
        audio_pcm16=audio if audio is not None else _sample_pcm16(),
        sample_rate=sample_rate,
        duration_seconds=duration_seconds,
        rms_energy=rms_energy,
    )


class TestJournalDbSchema:
    """Создание и базовый контракт схемы БД."""

    def test_creates_database_file(self, tmp_path):
        """Журнал должен создавать файл БД и родительскую директорию."""
        db_path = tmp_path / "nested" / "journal.db"

        JournalDb(db_path)

        assert db_path.exists()
        assert db_path.parent.is_dir()

    def test_schema_version_is_recorded(self, journal):
        """В schema_meta должна быть записана текущая версия схемы."""
        with journal._connect() as conn:
            row = conn.execute("SELECT value FROM schema_meta WHERE key = 'schema_version'").fetchone()
        assert row is not None
        assert row[0] == "2"

    def test_initialize_is_idempotent(self, tmp_path):
        """Повторное открытие не должно ронять схему и не дублирует данные."""
        db_path = tmp_path / "journal.db"

        first = JournalDb(db_path)
        first.record_event(make_event())

        second = JournalDb(db_path)
        assert second.count_events() == 1


class TestRecordEvent:
    """Запись событий и доступ к ним."""

    def test_record_event_returns_id_and_persists_payload(self, journal):
        """Сохранение события должно возвращать id и сохранять все поля."""
        event = make_event()

        event_id = journal.record_event(event)

        assert event_id > 0
        with journal._connect() as conn:
            row = conn.execute(
                "SELECT text, language, source, sample_rate, duration_seconds, rms_energy, "
                "audio_pcm16, audio_bytes, model FROM events WHERE id = ?",
                (event_id,),
            ).fetchone()
        assert row is not None
        assert row[0] == event.text
        assert row[1] == event.language
        assert row[2] == event.source
        assert row[3] == event.sample_rate
        assert row[4] == pytest.approx(event.duration_seconds)
        assert row[5] == pytest.approx(event.rms_energy)
        assert bytes(row[6]) == event.audio_pcm16
        assert row[7] == len(event.audio_pcm16)
        assert row[8] == event.model

    def test_count_events_reflects_records(self, journal):
        """count_events должен учитывать только реальные вставки."""
        assert journal.count_events() == 0
        journal.record_event(make_event())
        journal.record_event(make_event(text="второе"))
        assert journal.count_events() == 2

    def test_events_in_range_filters_by_started_at(self, journal):
        """events_in_range возвращает только события в полу-открытом интервале."""
        journal.record_event(make_event(started_at=100.0, text="до"))
        journal.record_event(make_event(started_at=200.0, text="внутри"))
        journal.record_event(make_event(started_at=300.0, text="после"))

        events = journal.events_in_range(150.0, 250.0)

        assert [event["text"] for event in events] == ["внутри"]

    def test_events_in_range_does_not_return_audio_blob(self, journal):
        """events_in_range — лёгкий запрос, без BLOB-поля audio_pcm16."""
        journal.record_event(make_event(started_at=100.0))

        events = journal.events_in_range(0.0, 1_000.0)

        assert events
        assert "audio_pcm16" not in events[0]
        assert events[0]["audio_bytes"] == len(_sample_pcm16())

    def test_events_in_range_orders_ascending(self, journal):
        """События должны возвращаться в хронологическом порядке."""
        journal.record_event(make_event(started_at=300.0, text="третий"))
        journal.record_event(make_event(started_at=100.0, text="первый"))
        journal.record_event(make_event(started_at=200.0, text="второй"))

        events = journal.events_in_range(0.0, 1_000.0)

        assert [event["text"] for event in events] == ["первый", "второй", "третий"]


def make_hourly(
    *,
    date: str = "2026-05-10",
    hour: int = 9,
    summary: str = "коротко за час",
    source_event_ids: tuple[int, ...] = (1, 2, 3),
    duration_seconds: float = 12.5,
    event_count: int = 3,
    generated_at: float = 1_700_000_000.0,
) -> HourlyDigest:
    """Готовит HourlyDigest для тестов."""
    return HourlyDigest(
        date=date,
        hour=hour,
        summary=summary,
        source_event_ids=source_event_ids,
        duration_seconds=duration_seconds,
        event_count=event_count,
        generated_at=generated_at,
    )


class TestHourlyDigests:
    """Хранилище часовых резюме."""

    def test_upsert_inserts_then_replaces_by_date_hour(self, journal):
        """Конфликт по `(date, hour)` обновляет запись, а не плодит дубль."""
        first_id = journal.upsert_hourly_digest(make_hourly(summary="первое"))
        second_id = journal.upsert_hourly_digest(make_hourly(summary="обновлено"))

        digests = journal.hourly_digests_for_date("2026-05-10")
        assert len(digests) == 1
        assert first_id == second_id
        assert digests[0].summary == "обновлено"

    def test_hourly_digests_for_date_orders_by_hour(self, journal):
        """Резюме за дату возвращаются в порядке возрастания часа."""
        journal.upsert_hourly_digest(make_hourly(hour=15, summary="день"))
        journal.upsert_hourly_digest(make_hourly(hour=9, summary="утро"))
        journal.upsert_hourly_digest(make_hourly(hour=21, summary="вечер"))

        digests = journal.hourly_digests_for_date("2026-05-10")

        assert [digest.hour for digest in digests] == [9, 15, 21]
        assert [digest.summary for digest in digests] == ["утро", "день", "вечер"]

    def test_delete_hourly_digests_for_date_only_removes_target_day(self, journal):
        """Удаление часовых резюме затрагивает только указанный день."""
        journal.upsert_hourly_digest(make_hourly(date="2026-05-10", hour=9))
        journal.upsert_hourly_digest(make_hourly(date="2026-05-10", hour=10))
        journal.upsert_hourly_digest(make_hourly(date="2026-05-11", hour=9))

        deleted = journal.delete_hourly_digests_for_date("2026-05-10")

        assert deleted == 2
        assert journal.hourly_digests_for_date("2026-05-10") == []
        assert len(journal.hourly_digests_for_date("2026-05-11")) == 1


class TestDailyDigests:
    """Хранилище дневных резюме."""

    def test_upsert_replaces_existing_daily(self, journal):
        """Повторный вызов upsert обновляет резюме того же дня."""
        first = DailyDigest(
            date="2026-05-10",
            summary="первое",
            hourly_digest_ids=(1, 2),
            generated_at=1_700_000_000.0,
        )
        updated = DailyDigest(
            date="2026-05-10",
            summary="обновлено",
            hourly_digest_ids=(1, 2, 3),
            generated_at=1_700_000_500.0,
        )
        first_id = journal.upsert_daily_digest(first)
        second_id = journal.upsert_daily_digest(updated)

        loaded = journal.daily_digest_for_date("2026-05-10")

        assert first_id == second_id
        assert loaded is not None
        assert loaded.summary == "обновлено"
        assert loaded.hourly_digest_ids == (1, 2, 3)

    def test_daily_digest_for_date_returns_none_when_missing(self, journal):
        """Если резюме не сохранялось, метод возвращает None."""
        assert journal.daily_digest_for_date("2099-01-01") is None
