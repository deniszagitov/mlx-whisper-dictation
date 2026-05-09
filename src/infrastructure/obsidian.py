"""Инфраструктурный адаптер для работы с Obsidian vault и архивом истории."""

from __future__ import annotations

import logging
import os
import re
from datetime import date, datetime
from pathlib import Path

from ..domain.constants import Config

LOGGER = logging.getLogger(__name__)

_UNSAFE_FILENAME_RE = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
_HISTORY_HEADER_RE = re.compile(r"^## (?P<time>\d{2}:\d{2}:\d{2}) \| (?P<kind>[^\n]+)\n", re.MULTILINE)
_HISTORY_TOPICS_LINE_RE = re.compile(r"^Темы:\s*(?P<topics>.+)\n", re.MULTILINE)
_HISTORY_BLOCK_ID_RE = re.compile(r"\n\^(?P<block_id>[a-z0-9\-]+)\s*$", re.MULTILINE)
_WIKI_LINK_RE = re.compile(r"\[\[(?P<target>[^\]]+)\]\]")

_DEFAULT_VAULT_DIRNAME = "obsidian-vault"
_HISTORY_SUBPATH = Path("05 📅 Daily Notes") / "Dictator"
_TOPICS_DIRNAME = "Темы"
_MIN_QUERY_WORD_LENGTH = 2
_TOPIC_MAX_LENGTH = 64
_TOPIC_MAX_COUNT = 3
_TOPIC_PREVIEW_LENGTH = 120


def get_default_vault_path() -> Path:
    """Возвращает путь к основному Obsidian vault по умолчанию."""
    return Path.home() / "Repositories" / _DEFAULT_VAULT_DIRNAME


def resolve_obsidian_vault_path(configured_path: str | Path | None = None) -> Path:
    """Возвращает эффективный путь к vault с учётом переменной окружения.

    Приоритет:
    1. `DICTATOR_OBSIDIAN_VAULT_PATH`
    2. сохранённый путь из настроек
    3. проектный путь по умолчанию
    """
    env_value = os.getenv(Config.OBSIDIAN_VAULT_PATH_ENV, "").strip()
    if env_value:
        return Path(env_value).expanduser()

    if configured_path is not None:
        normalized = str(configured_path).strip()
        if normalized:
            return Path(normalized).expanduser()

    return get_default_vault_path()


def get_obsidian_history_directory(vault_path: str | Path) -> Path:
    """Возвращает директорию дневного архива диктовок внутри vault."""
    return Path(vault_path) / _HISTORY_SUBPATH


def get_obsidian_topics_directory(vault_path: str | Path) -> Path:
    """Возвращает директорию topic notes для графа смыслов."""
    return get_obsidian_history_directory(vault_path) / _TOPICS_DIRNAME


def append_obsidian_history_entry(
    vault_path: str | Path,
    text: str,
    *,
    kind: str = "диктовка",
    created_at: datetime | None = None,
    semantic_topics: list[str] | None = None,
) -> Path:
    """Добавляет запись в дневной markdown-файл истории."""
    normalized_text = str(text).strip()
    if not normalized_text:
        raise ValueError("Нельзя сохранить пустую запись истории в Obsidian")

    timestamp = created_at or datetime.now()
    history_dir = get_obsidian_history_directory(vault_path)
    history_dir.mkdir(parents=True, exist_ok=True)

    file_path = _daily_history_file_path(vault_path, timestamp.date())
    if not file_path.exists():
        file_path.write_text(f"# Dictator · {timestamp:%Y-%m-%d}\n\n", encoding="utf-8")

    topics = _normalize_semantic_topics(semantic_topics or [])
    block_id = _history_block_id(timestamp=timestamp, kind=kind)
    topic_links = _topic_links(topics)

    with file_path.open("a", encoding="utf-8") as handle:
        handle.write(f"## {timestamp:%H:%M:%S} | {kind}\n")
        if topic_links:
            handle.write(f"Темы: {', '.join(topic_links)}\n")
        handle.write(f"{normalized_text}\n^{block_id}\n\n")

    for topic in topics:
        _update_obsidian_topic_note(
            vault_path=vault_path,
            topic=topic,
            daily_note_path=file_path,
            timestamp=timestamp,
            kind=kind,
            block_id=block_id,
            preview=normalized_text,
        )

    LOGGER.info("🗂️ Запись добавлена в историю Obsidian: %s", file_path)
    return file_path


def load_obsidian_history_items(vault_path: str | Path, *, max_items: int = 500) -> list[dict[str, object]]:
    """Читает архивированные записи истории из дневных markdown-файлов."""
    history_dir = get_obsidian_history_directory(vault_path)
    if not history_dir.is_dir():
        return []

    records: list[dict[str, object]] = []
    for md_file in sorted(history_dir.glob("*.md"), reverse=True):
        try:
            content = md_file.read_text(encoding="utf-8")
        except Exception:
            LOGGER.exception("⚠️ Не удалось прочитать файл истории Obsidian: %s", md_file)
            continue
        records.extend(_parse_history_entries(md_file, content))
        if len(records) >= max_items:
            break

    records.sort(key=_history_created_at, reverse=True)
    return records[:max_items]


def load_obsidian_daily_topics(
    vault_path: str | Path,
    *,
    target_day: date | datetime | None = None,
    max_topics: int = 8,
) -> list[tuple[str, int]]:
    """Возвращает темы текущего дня с количеством упоминаний для UI."""
    normalized_day = _normalize_target_day(target_day)
    file_path = _daily_history_file_path(vault_path, normalized_day)
    if not file_path.is_file():
        return []

    try:
        content = file_path.read_text(encoding="utf-8")
    except Exception:
        LOGGER.exception("⚠️ Не удалось прочитать дневную заметку Dictator: %s", file_path)
        return []

    topic_labels: dict[str, str] = {}
    topic_counts: dict[str, int] = {}
    for match in _HISTORY_TOPICS_LINE_RE.finditer(content):
        for topic in _extract_topics_from_line(match.group("topics")):
            key = topic.casefold()
            topic_labels.setdefault(key, topic)
            topic_counts[key] = topic_counts.get(key, 0) + 1

    ranked_topics = sorted(
        ((topic_labels[key], mentions) for key, mentions in topic_counts.items()),
        key=lambda item: (-item[1], item[0].casefold()),
    )
    return ranked_topics[:max_topics]


def _sanitize_filename(name: str) -> str:
    """Удаляет небезопасные символы из имени файла."""
    cleaned = _UNSAFE_FILENAME_RE.sub("", name).strip()
    return cleaned[:100] if cleaned else "заметка"


def write_obsidian_note(vault_path: str | Path, content: str) -> Path:
    """Записывает заметку в Obsidian vault и возвращает путь к файлу.

    Имя файла формируется из даты и первой строки содержимого.
    """
    vault = Path(vault_path)
    vault.mkdir(parents=True, exist_ok=True)

    now = datetime.now()
    first_line = content.split("\n", maxsplit=1)[0].strip()
    title = first_line.lstrip("# ").strip() if first_line else "заметка"
    safe_title = _sanitize_filename(title)

    filename = f"{now:%Y-%m-%d} {safe_title}.md"
    file_path = vault / filename

    suffix = 0
    while file_path.exists():
        suffix += 1
        filename = f"{now:%Y-%m-%d} {safe_title} ({suffix}).md"
        file_path = vault / filename

    file_path.write_text(content, encoding="utf-8")
    LOGGER.info("📝 Заметка сохранена: %s", file_path)
    return file_path


def search_obsidian_notes(
    vault_path: str | Path,
    query: str,
    *,
    history_only: bool = False,
    max_notes: int = 5,
    max_chars: int = 3000,
) -> str:
    """Ищет релевантные заметки в vault по ключевым словам.

    Возвращает объединённое содержимое найденных заметок (до max_chars символов).
    """
    vault = Path(vault_path)
    if not vault.is_dir():
        return ""

    query_words = [w.lower() for w in re.findall(r"\w+", query, flags=re.UNICODE) if len(w) > _MIN_QUERY_WORD_LENGTH]
    if not query_words:
        return ""

    search_root = get_obsidian_history_directory(vault) if history_only else vault
    if not search_root.is_dir():
        return ""

    history_dir = get_obsidian_history_directory(vault)
    scored: list[tuple[int, str, str]] = []
    for md_file in search_root.rglob("*.md"):
        if history_only and md_file.is_relative_to(get_obsidian_topics_directory(vault)):
            continue
        try:
            text = md_file.read_text(encoding="utf-8")
        except Exception:
            continue
        relative_path = str(md_file.relative_to(vault))
        if _is_daily_history_file(md_file, history_dir):
            for entry in _iter_history_search_chunks(md_file, text):
                score = _score_query_match(f"{entry[0]}\n{entry[1]}", query_words)
                if score > 0:
                    scored.append((score, entry[0], entry[1]))
            continue

        score = _score_query_match(f"{relative_path}\n{text}", query_words)
        if score > 0:
            scored.append((score, relative_path, text))

    scored.sort(key=lambda item: item[0], reverse=True)
    top_chunks = scored[:max_notes]

    parts: list[str] = []
    total = 0
    for _score, label, text in top_chunks:
        header = f"--- {label} ---\n"
        chunk = header + text.strip()
        if total + len(chunk) > max_chars:
            remaining = max_chars - total
            if remaining > len(header) + 50:
                parts.append(header + text[: remaining - len(header)])
            break
        parts.append(chunk)
        total += len(chunk)

    return "\n\n".join(parts)


def _parse_history_entries(md_file: Path, content: str) -> list[dict[str, object]]:
    """Разбирает дневной markdown-файл истории на отдельные записи."""
    date_str = md_file.stem
    try:
        day = datetime.strptime(date_str, "%Y-%m-%d").date()
    except ValueError:
        return []

    matches = list(_HISTORY_HEADER_RE.finditer(content))
    if not matches:
        return []

    records: list[dict[str, object]] = []
    for index, match in enumerate(matches):
        start = match.end()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(content)
        body = _clean_history_entry_body(content[start:end])
        if not body:
            continue
        try:
            entry_time = datetime.strptime(match.group("time"), "%H:%M:%S").time()
        except ValueError:
            continue
        created_at = datetime.combine(day, entry_time).timestamp()
        records.append({"text": body, "created_at": created_at})
    return records


def _iter_history_search_chunks(md_file: Path, content: str) -> list[tuple[str, str]]:
    """Готовит отдельные поисковые чанки для дневного файла истории."""
    matches = list(_HISTORY_HEADER_RE.finditer(content))
    if not matches:
        return [(str(md_file.relative_to(md_file.parents[1])), content)]

    chunks: list[tuple[str, str]] = []
    relative_path = str(md_file.relative_to(md_file.parents[1]))
    for index, match in enumerate(matches):
        start = match.end()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(content)
        body = _clean_history_entry_body(content[start:end], preserve_topics=True)
        if not body:
            continue
        label = f"{relative_path} :: {match.group('time')} :: {match.group('kind').strip()}"
        chunks.append((label, body))
    return chunks


def _score_query_match(text: str, query_words: list[str]) -> int:
    """Оценивает релевантность текста запросу по простому lexical score."""
    lower_text = text.lower()
    return sum(lower_text.count(word) for word in query_words)


def _history_created_at(item: dict[str, object]) -> float:
    """Возвращает timestamp записи истории в удобном для сортировки виде."""
    value = item.get("created_at")
    if isinstance(value, int | float):
        return float(value)
    return 0.0


def _normalize_target_day(target_day: date | datetime | None) -> date:
    """Приводит дату выборки к объекту date."""
    if isinstance(target_day, datetime):
        return target_day.date()
    if isinstance(target_day, date):
        return target_day
    return datetime.now().date()


def _daily_history_file_path(vault_path: str | Path, target_day: date) -> Path:
    """Возвращает путь к дневной заметке Dictator."""
    return get_obsidian_history_directory(vault_path) / f"{target_day:%Y-%m-%d}.md"


def _normalize_semantic_topics(topics: list[str]) -> list[str]:
    """Очищает и дедуплицирует список семантических тем."""
    normalized: list[str] = []
    seen: set[str] = set()
    for topic in topics:
        cleaned = re.sub(r"\s+", " ", str(topic).strip(" -•\t\r\n"))
        if not cleaned:
            continue
        if len(cleaned) > _TOPIC_MAX_LENGTH:
            cleaned = cleaned[:_TOPIC_MAX_LENGTH].rstrip()
        key = cleaned.casefold()
        if key in seen:
            continue
        normalized.append(cleaned)
        seen.add(key)
        if len(normalized) >= _TOPIC_MAX_COUNT:
            break
    return normalized


def _extract_topics_from_line(raw_topics: str) -> list[str]:
    """Достаёт имена тем из wiki-links строки `Темы:`."""
    topics: list[str] = []
    for match in _WIKI_LINK_RE.finditer(raw_topics):
        target = match.group("target").strip()
        topic = Path(target.split("#", maxsplit=1)[0]).name.strip()
        if topic:
            topics.append(topic)
    return topics


def _history_block_id(*, timestamp: datetime, kind: str) -> str:
    """Формирует стабильный block id для backlink-ов Obsidian."""
    kind_slug = re.sub(r"[^a-z0-9]+", "-", str(kind).strip().lower()).strip("-") or "entry"
    return f"dictator-{timestamp:%Y%m%d-%H%M%S}-{kind_slug}"


def _topic_links(topics: list[str]) -> list[str]:
    """Преобразует темы в Obsidian wiki-links."""
    return [f"[[{_topic_note_path_string(topic)}]]" for topic in topics]


def _topic_note_path_string(topic: str) -> str:
    """Возвращает wiki-path заметки темы относительно корня vault."""
    return (_HISTORY_SUBPATH / _TOPICS_DIRNAME / _sanitize_filename(topic)).as_posix()


def _update_obsidian_topic_note(
    *,
    vault_path: str | Path,
    topic: str,
    daily_note_path: Path,
    timestamp: datetime,
    kind: str,
    block_id: str,
    preview: str,
) -> None:
    """Создаёт или обновляет topic note для Obsidian graph."""
    topics_dir = get_obsidian_topics_directory(vault_path)
    topics_dir.mkdir(parents=True, exist_ok=True)

    topic_note_path = topics_dir / f"{_sanitize_filename(topic)}.md"
    if not topic_note_path.exists():
        topic_note_path.write_text(f"# {topic}\n\n## Упоминания\n", encoding="utf-8")

    link_target = f"{_HISTORY_SUBPATH.as_posix()}/{daily_note_path.name}#^{block_id}"
    preview_text = preview.replace("\n", " ").strip()
    if len(preview_text) > _TOPIC_PREVIEW_LENGTH:
        preview_text = preview_text[:_TOPIC_PREVIEW_LENGTH].rstrip() + "…"
    backlink_line = f"- [[{link_target}]] · {timestamp:%H:%M:%S} · {kind} · {preview_text}"

    existing = topic_note_path.read_text(encoding="utf-8")
    if backlink_line not in existing:
        with topic_note_path.open("a", encoding="utf-8") as handle:
            handle.write(f"{backlink_line}\n")


def _clean_history_entry_body(body: str, *, preserve_topics: bool = False) -> str:
    """Убирает служебные строки из сохранённой записи истории."""
    cleaned = str(body).strip()
    if not preserve_topics:
        cleaned = _HISTORY_TOPICS_LINE_RE.sub("", cleaned)
    cleaned = _HISTORY_BLOCK_ID_RE.sub("", cleaned)
    return cleaned.strip()


def _is_daily_history_file(md_file: Path, history_dir: Path) -> bool:
    """Определяет, что markdown-файл является дневной записью Dictator."""
    return md_file.parent == history_dir and md_file.suffix == ".md"
