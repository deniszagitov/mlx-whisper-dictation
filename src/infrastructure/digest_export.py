"""Экспорт дневных дайджестов в файловую систему.

Источник пути для записи (в порядке убывания приоритета):

1. Переменная окружения ``DICTATOR_OBSIDIAN_VAULT`` — корень Obsidian-vault
   пользователя. При наличии файлы пишутся в ``<vault>/Daily/YYYY-MM-DD.md``.
2. Сохранённое значение ``obsidian_vault_path`` из NSUserDefaults
   (см. ``Config.DEFAULTS_KEY_OBSIDIAN_VAULT``) — настройка из меню.
3. Fallback ``~/Library/Application Support/Dictator/digests/YYYY-MM-DD.md`` —
   используется только если в настройках/окружении явно включён режим
   локального fallback-а (флаг ``allow_fallback=True``).

Если ничего не настроено и fallback не включён, экспорт превращается в no-op,
чтобы пользователи без Obsidian не получали неожиданно созданные файлы.
"""

from __future__ import annotations

import logging
import os
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

from ..domain.constants import Config

if TYPE_CHECKING:
    from collections.abc import Sequence

    from ..domain.digest import DailyDigest, HourlyDigest

LOGGER = logging.getLogger(__name__)


def _format_daily_markdown(daily: DailyDigest, hourly: Sequence[HourlyDigest]) -> str:
    """Формирует markdown-файл дайджеста за день.

    Структура:

        # YYYY-MM-DD
        ## Резюме дня
        <текст>

        ## HH:00–HH:00
        <часовое резюме>

    Daily-блок всегда сверху. Часовые резюме идут в хронологическом порядке.
    """
    generated = datetime.fromtimestamp(daily.generated_at).strftime("%Y-%m-%d %H:%M:%S")

    lines: list[str] = []
    lines.append(f"# {daily.date}\n")
    lines.append("## Резюме дня")
    lines.append(f"_сгенерировано {generated}_\n")
    lines.append(daily.summary.strip())
    lines.append("")

    sorted_hourly = sorted(hourly, key=lambda digest: digest.hour)
    last_hour_index = 23
    for digest in sorted_hourly:
        next_hour = digest.hour + 1 if digest.hour < last_hour_index else 0
        lines.append(f"## {digest.hour:02d}:00–{next_hour:02d}:00")
        lines.append(digest.summary.strip())
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


class DigestExporter:
    """Пишет дневные дайджесты в Obsidian vault или в local fallback."""

    def __init__(
        self,
        *,
        configured_vault_path: str | None = None,
        allow_fallback: bool = False,
    ) -> None:
        """Создаёт экспортер.

        Args:
            configured_vault_path: Путь к Obsidian vault из пользовательских
                настроек. Может быть None или пустой строкой.
            allow_fallback: Если True и vault не задан, пишем дайджесты
                в `Config.DIGEST_FALLBACK_DIR` (Application Support/Dictator).
                По умолчанию False — без vault экспорт выключен полностью.
        """
        self._configured_vault_path = configured_vault_path
        self._allow_fallback = bool(allow_fallback)

    def is_configured(self) -> bool:
        """Сообщает, настроен ли реальный путь для экспорта."""
        return self._resolve_target_dir() is not None

    def export_daily(self, daily: DailyDigest, hourly: Sequence[HourlyDigest]) -> None:
        """Пишет markdown-файл с дневным дайджестом, если экспорт настроен."""
        target_dir = self._resolve_target_dir()
        if target_dir is None:
            LOGGER.debug("⏭️ Экспорт дайджестов не настроен — пропускаю запись для %s", daily.date)
            return

        target_dir.mkdir(parents=True, exist_ok=True)
        target_file = target_dir / f"{daily.date}.md"
        target_file.write_text(_format_daily_markdown(daily, hourly), encoding="utf-8")
        LOGGER.info("📒 Дневной дайджест записан: %s", target_file)

    def _resolve_target_dir(self) -> Path | None:
        """Возвращает целевую директорию для дайджестов или None."""
        env_disabled = bool(os.environ.get(Config.DIGEST_DISABLED_ENV))
        if env_disabled:
            return None

        env_vault = os.environ.get(Config.OBSIDIAN_VAULT_ENV, "").strip()
        if env_vault:
            return Path(env_vault).expanduser() / Config.DIGEST_OBSIDIAN_DAILY_SUBDIR

        if self._configured_vault_path:
            normalized = self._configured_vault_path.strip()
            if normalized:
                return Path(normalized).expanduser() / Config.DIGEST_OBSIDIAN_DAILY_SUBDIR

        if self._allow_fallback:
            return Config.DIGEST_FALLBACK_DIR

        return None
