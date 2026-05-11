"""SQLite-журнал диктовок: текст, исходное аудио, метаданные.

База — единый файл `~/Library/Application Support/Dictator/journal.db`.
Источник правды для будущих часовых/дневных саммари: каждое событие
содержит финальный текст, длительность, и сырое аудио в PCM16 mono.

Аудио хранится как BLOB прямо в таблице `events`. Для журнала размером
порядка часов суммарной речи это ок: SQLite справляется с гигабайтами
блобов, а Time Machine аккуратно бэкапит один файл.
"""

from __future__ import annotations

import json
import logging
import sqlite3
import threading
from contextlib import contextmanager
from pathlib import Path
from typing import TYPE_CHECKING

from ...domain.constants import Config
from ...domain.digest import DailyDigest, HourlyDigest

if TYPE_CHECKING:
    from collections.abc import Iterator

    from ...domain.dictation_log import DictationEvent

LOGGER = logging.getLogger(__name__)


_SCHEMA_VERSION = 2


_INIT_STATEMENTS: tuple[str, ...] = (
    """
    CREATE TABLE IF NOT EXISTS schema_meta (
        key TEXT PRIMARY KEY,
        value TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS events (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        started_at REAL NOT NULL,
        ended_at REAL NOT NULL,
        text TEXT NOT NULL,
        language TEXT,
        model TEXT NOT NULL,
        source TEXT NOT NULL,
        audio_pcm16 BLOB NOT NULL,
        sample_rate INTEGER NOT NULL,
        duration_seconds REAL NOT NULL,
        rms_energy REAL NOT NULL,
        audio_bytes INTEGER NOT NULL
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_events_started_at ON events(started_at)",
    "CREATE INDEX IF NOT EXISTS idx_events_source ON events(source)",
    """
    CREATE TABLE IF NOT EXISTS hourly_digests (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        date TEXT NOT NULL,
        hour INTEGER NOT NULL,
        summary TEXT NOT NULL,
        source_event_ids TEXT NOT NULL,
        duration_seconds REAL NOT NULL,
        event_count INTEGER NOT NULL,
        generated_at REAL NOT NULL,
        UNIQUE(date, hour)
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_hourly_digests_date ON hourly_digests(date)",
    """
    CREATE TABLE IF NOT EXISTS daily_digests (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        date TEXT NOT NULL UNIQUE,
        summary TEXT NOT NULL,
        hourly_digest_ids TEXT NOT NULL,
        generated_at REAL NOT NULL
    )
    """,
)


class JournalDb:
    """SQLite-хранилище журнала диктовок.

    Один файл базы на пользователя. Соединения создаются на каждый вызов,
    чтобы корректно работать из разных потоков (использование sqlite3
    в multi-thread окружении требует либо одного потока, либо новой
    connection на поток).
    """

    def __init__(self, db_path: str | Path | None = None) -> None:
        """Создаёт журнал и инициализирует схему БД."""
        self._db_path = Path(db_path) if db_path is not None else Config.JOURNAL_DB_PATH
        self._init_lock = threading.Lock()
        self._initialized = False
        self._ensure_initialized()

    @property
    def db_path(self) -> Path:
        """Возвращает путь к файлу БД."""
        return self._db_path

    def _ensure_parent_dir(self) -> None:
        """Создаёт родительскую директорию для файла БД."""
        self._db_path.parent.mkdir(parents=True, exist_ok=True)

    def _ensure_initialized(self) -> None:
        """Создаёт схему БД при первом обращении."""
        if self._initialized:
            return
        with self._init_lock:
            if self._initialized:
                return
            self._ensure_parent_dir()
            with self._connect() as conn:
                for statement in _INIT_STATEMENTS:
                    conn.execute(statement)
                conn.execute(
                    "INSERT OR REPLACE INTO schema_meta(key, value) VALUES(?, ?)",
                    ("schema_version", str(_SCHEMA_VERSION)),
                )
            self._initialized = True
            LOGGER.info("📒 Журнал диктовок готов: %s", self._db_path)

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        """Открывает соединение и гарантирует commit/rollback и close."""
        conn = sqlite3.connect(self._db_path)
        try:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA synchronous=NORMAL")
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def record_event(self, event: DictationEvent) -> int:
        """Сохраняет событие журнала и возвращает его id."""
        with self._connect() as conn:
            cursor = conn.execute(
                """
                INSERT INTO events(
                    started_at, ended_at, text, language, model, source,
                    audio_pcm16, sample_rate, duration_seconds, rms_energy, audio_bytes
                )
                VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    float(event.started_at),
                    float(event.ended_at),
                    event.text,
                    event.language,
                    event.model,
                    event.source,
                    event.audio_pcm16,
                    int(event.sample_rate),
                    float(event.duration_seconds),
                    float(event.rms_energy),
                    len(event.audio_pcm16),
                ),
            )
            event_id = int(cursor.lastrowid or 0)
        LOGGER.debug(
            "📒 Событие журнала записано: id=%d, длительность=%.2f с, аудио=%d байт, источник=%s",
            event_id,
            event.duration_seconds,
            len(event.audio_pcm16),
            event.source,
        )
        return event_id

    def count_events(self) -> int:
        """Возвращает общее число событий в журнале."""
        with self._connect() as conn:
            row = conn.execute("SELECT COUNT(*) FROM events").fetchone()
        return int(row[0]) if row else 0

    def events_in_range(self, start_unix: float, end_unix: float) -> list[dict[str, object]]:
        """Возвращает события в полу-открытом диапазоне `[start, end)`.

        Используется scheduler-ом для часовых/дневных саммари.
        Аудио-блоб не возвращается, чтобы не тащить десятки мегабайт без нужды.
        """
        with self._connect() as conn:
            cursor = conn.execute(
                """
                SELECT id, started_at, ended_at, text, language, model, source,
                       sample_rate, duration_seconds, rms_energy, audio_bytes
                FROM events
                WHERE started_at >= ? AND started_at < ?
                ORDER BY started_at ASC
                """,
                (float(start_unix), float(end_unix)),
            )
            columns = [description[0] for description in cursor.description]
            rows = cursor.fetchall()
        return [dict(zip(columns, row, strict=True)) for row in rows]

    def upsert_hourly_digest(self, digest: HourlyDigest) -> int:
        """Сохраняет часовое резюме (insert или replace по `(date, hour)`).

        Возвращает id записи. Делает full-replace вместо append-only внутри часа,
        чтобы повторная генерация (например, после ручного «перегенерировать сегодня»)
        не плодила дубликаты.
        """
        encoded_event_ids = json.dumps(list(digest.source_event_ids))
        with self._connect() as conn:
            cursor = conn.execute(
                """
                INSERT INTO hourly_digests(
                    date, hour, summary, source_event_ids,
                    duration_seconds, event_count, generated_at
                )
                VALUES(?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(date, hour) DO UPDATE SET
                    summary = excluded.summary,
                    source_event_ids = excluded.source_event_ids,
                    duration_seconds = excluded.duration_seconds,
                    event_count = excluded.event_count,
                    generated_at = excluded.generated_at
                RETURNING id
                """,
                (
                    digest.date,
                    int(digest.hour),
                    digest.summary,
                    encoded_event_ids,
                    float(digest.duration_seconds),
                    int(digest.event_count),
                    float(digest.generated_at),
                ),
            )
            row = cursor.fetchone()
            digest_id = int(row[0])
        LOGGER.debug(
            "📒 Часовое резюме сохранено: %s %02d:00, событий=%d, длительность=%.1f с",
            digest.date,
            digest.hour,
            digest.event_count,
            digest.duration_seconds,
        )
        return digest_id

    def hourly_digests_for_date(self, date: str) -> list[HourlyDigest]:
        """Возвращает часовые резюме за дату в порядке возрастания часа."""
        with self._connect() as conn:
            cursor = conn.execute(
                """
                SELECT id, date, hour, summary, source_event_ids,
                       duration_seconds, event_count, generated_at
                FROM hourly_digests
                WHERE date = ?
                ORDER BY hour ASC
                """,
                (date,),
            )
            rows = cursor.fetchall()
        digests: list[HourlyDigest] = []
        for row in rows:
            (_id, row_date, hour, summary, source_event_ids,
             duration_seconds, event_count, generated_at) = row
            digests.append(
                HourlyDigest(
                    date=str(row_date),
                    hour=int(hour),
                    summary=str(summary),
                    source_event_ids=tuple(json.loads(source_event_ids)),
                    duration_seconds=float(duration_seconds),
                    event_count=int(event_count),
                    generated_at=float(generated_at),
                ),
            )
        return digests

    def upsert_daily_digest(self, digest: DailyDigest) -> int:
        """Сохраняет дневное резюме (insert или replace по `date`)."""
        encoded_hourly_ids = json.dumps(list(digest.hourly_digest_ids))
        with self._connect() as conn:
            cursor = conn.execute(
                """
                INSERT INTO daily_digests(date, summary, hourly_digest_ids, generated_at)
                VALUES(?, ?, ?, ?)
                ON CONFLICT(date) DO UPDATE SET
                    summary = excluded.summary,
                    hourly_digest_ids = excluded.hourly_digest_ids,
                    generated_at = excluded.generated_at
                RETURNING id
                """,
                (
                    digest.date,
                    digest.summary,
                    encoded_hourly_ids,
                    float(digest.generated_at),
                ),
            )
            row = cursor.fetchone()
            digest_id = int(row[0])
        LOGGER.debug("📒 Дневное резюме сохранено: %s", digest.date)
        return digest_id

    def daily_digest_for_date(self, date: str) -> DailyDigest | None:
        """Возвращает дневное резюме или None, если его ещё нет."""
        with self._connect() as conn:
            cursor = conn.execute(
                """
                SELECT date, summary, hourly_digest_ids, generated_at
                FROM daily_digests
                WHERE date = ?
                """,
                (date,),
            )
            row = cursor.fetchone()
        if row is None:
            return None
        return DailyDigest(
            date=str(row[0]),
            summary=str(row[1]),
            hourly_digest_ids=tuple(json.loads(row[2])),
            generated_at=float(row[3]),
        )

    def delete_hourly_digests_for_date(self, date: str) -> int:
        """Удаляет все часовые резюме за дату. Возвращает число удалённых."""
        with self._connect() as conn:
            cursor = conn.execute("DELETE FROM hourly_digests WHERE date = ?", (date,))
            deleted = cursor.rowcount or 0
        return int(deleted)
