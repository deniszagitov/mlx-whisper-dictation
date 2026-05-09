"""Безопасные helper-функции для логирования без утечки пользовательских данных."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import TYPE_CHECKING

from .constants import Config

if TYPE_CHECKING:
    from collections.abc import Mapping

DICTATION_LOGGER_NAME = "dictation"


def summarize_text_for_logging(text: object) -> str:
    """Возвращает безопасную сводку текста без публикации содержимого."""
    normalized = str(text or "")
    digest = hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:12] if normalized else "empty"
    return f"chars={len(normalized)}, words={len(normalized.split())}, sha256={digest}"


def sanitize_path_for_logging(path: str | Path, *, root_dir: str | Path = Config.LOG_DIR) -> str:
    """Сводит абсолютный путь к относительному пути внутри каталога логов."""
    normalized_path = Path(path)
    normalized_root = Path(root_dir)
    try:
        return str(normalized_path.relative_to(normalized_root))
    except ValueError:
        return normalized_path.name or str(normalized_path)


def sanitize_mapping_for_logging(
    values: Mapping[str, str] | None,
    *,
    root_dir: str | Path = Config.LOG_DIR,
) -> dict[str, str] | None:
    """Маскирует абсолютные пути внутри словаря логируемых артефактов."""
    if values is None:
        return None
    return {
        str(key): sanitize_path_for_logging(str(value), root_dir=root_dir)
        for key, value in values.items()
    }
