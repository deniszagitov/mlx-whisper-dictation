"""Инфраструктурный адаптер для работы с Obsidian vault."""

from __future__ import annotations

import logging
import re
from datetime import datetime
from pathlib import Path

LOGGER = logging.getLogger(__name__)

_UNSAFE_FILENAME_RE = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


_MIN_QUERY_WORD_LENGTH = 2


def get_default_vault_path() -> Path:
    """Возвращает путь к vault по умолчанию."""
    return Path.home() / "Repositories" / "obsidian-vault"


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


def search_obsidian_notes(vault_path: str | Path, query: str, *, max_notes: int = 5, max_chars: int = 3000) -> str:
    """Ищет релевантные заметки в vault по ключевым словам.

    Возвращает объединённое содержимое найденных заметок (до max_chars символов).
    """
    vault = Path(vault_path)
    if not vault.is_dir():
        return ""

    query_words = [w.lower() for w in query.split() if len(w) > _MIN_QUERY_WORD_LENGTH]
    if not query_words:
        return ""

    scored: list[tuple[int, Path]] = []
    for md_file in vault.glob("*.md"):
        try:
            text = md_file.read_text(encoding="utf-8")
        except Exception:
            continue
        lower_text = text.lower()
        score = sum(lower_text.count(word) for word in query_words)
        if score > 0:
            scored.append((score, md_file))

    scored.sort(key=lambda pair: pair[0], reverse=True)
    top_files = scored[:max_notes]

    parts: list[str] = []
    total = 0
    for _score, path in top_files:
        try:
            text = path.read_text(encoding="utf-8")
        except Exception:
            continue
        header = f"--- {path.name} ---\n"
        chunk = header + text
        if total + len(chunk) > max_chars:
            remaining = max_chars - total
            if remaining > len(header) + 50:
                parts.append(header + text[: remaining - len(header)])
            break
        parts.append(chunk)
        total += len(chunk)

    return "\n\n".join(parts)
