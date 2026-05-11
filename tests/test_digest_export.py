"""Тесты экспорта дневных дайджестов в файловую систему."""

from __future__ import annotations

import pytest
from src.domain.constants import Config
from src.domain.digest import DailyDigest, HourlyDigest
from src.infrastructure.digest_export import DigestExporter


def make_daily(*, summary: str = "день в трёх предложениях") -> DailyDigest:
    """Готовит DailyDigest для тестов экспорта."""
    return DailyDigest(
        date="2026-05-10",
        summary=summary,
        hourly_digest_ids=(1, 2),
        generated_at=1_700_000_000.0,
    )


def make_hourly(*, hour: int, summary: str) -> HourlyDigest:
    """Готовит HourlyDigest для тестов экспорта."""
    return HourlyDigest(
        date="2026-05-10",
        hour=hour,
        summary=summary,
        source_event_ids=(1,),
        duration_seconds=10.0,
        event_count=1,
        generated_at=1_700_000_000.0,
    )


@pytest.fixture(autouse=True)
def isolated_env(monkeypatch: pytest.MonkeyPatch):
    """Гарантирует чистое окружение для тестов экспорта."""
    monkeypatch.delenv(Config.OBSIDIAN_VAULT_ENV, raising=False)
    monkeypatch.delenv(Config.DIGEST_DISABLED_ENV, raising=False)


class TestResolveTarget:
    """Логика выбора целевой папки для экспорта."""

    def test_no_export_when_nothing_configured(self):
        """Без vault и без fallback экспорт выключен."""
        exporter = DigestExporter()
        assert exporter.is_configured() is False

    def test_env_vault_takes_precedence(self, monkeypatch, tmp_path):
        """`DICTATOR_OBSIDIAN_VAULT` побеждает настроенный путь."""
        configured = tmp_path / "configured-vault"
        env_vault = tmp_path / "env-vault"
        monkeypatch.setenv(Config.OBSIDIAN_VAULT_ENV, str(env_vault))

        exporter = DigestExporter(configured_vault_path=str(configured))
        exporter.export_daily(make_daily(), [make_hourly(hour=9, summary="утро")])

        assert (env_vault / Config.DIGEST_OBSIDIAN_DAILY_SUBDIR / "2026-05-10.md").exists()
        assert not (configured / Config.DIGEST_OBSIDIAN_DAILY_SUBDIR / "2026-05-10.md").exists()

    def test_disable_env_blocks_export_even_with_vault(self, monkeypatch, tmp_path):
        """`DICTATOR_DIGEST_DISABLE_EXPORT=1` отключает запись."""
        env_vault = tmp_path / "env-vault"
        monkeypatch.setenv(Config.OBSIDIAN_VAULT_ENV, str(env_vault))
        monkeypatch.setenv(Config.DIGEST_DISABLED_ENV, "1")

        exporter = DigestExporter()
        exporter.export_daily(make_daily(), [make_hourly(hour=9, summary="утро")])

        assert not env_vault.exists()
        assert exporter.is_configured() is False

    def test_fallback_writes_to_app_support_when_allowed(self, monkeypatch, tmp_path):
        """Fallback используется только при `allow_fallback=True`."""
        fallback_dir = tmp_path / "Digests"
        monkeypatch.setattr(Config, "DIGEST_FALLBACK_DIR", fallback_dir)

        exporter = DigestExporter(allow_fallback=True)
        exporter.export_daily(make_daily(), [make_hourly(hour=9, summary="утро")])

        target_file = fallback_dir / "2026-05-10.md"
        assert target_file.exists()

    def test_configured_vault_used_when_no_env(self, tmp_path):
        """Если env пуст, используется путь из настроек приложения."""
        vault = tmp_path / "obsidian"
        exporter = DigestExporter(configured_vault_path=str(vault))

        exporter.export_daily(make_daily(), [make_hourly(hour=9, summary="утро")])

        assert (vault / Config.DIGEST_OBSIDIAN_DAILY_SUBDIR / "2026-05-10.md").exists()


class TestMarkdownFormatting:
    """Структура итогового markdown-файла."""

    def test_daily_summary_first_then_hourly_ascending(self, tmp_path):
        """Daily-блок сверху, часовые ниже в хронологическом порядке."""
        vault = tmp_path / "vault"
        exporter = DigestExporter(configured_vault_path=str(vault))
        hourly = [
            make_hourly(hour=21, summary="закрытие дня"),
            make_hourly(hour=9, summary="зарядка"),
            make_hourly(hour=15, summary="созвон"),
        ]

        exporter.export_daily(make_daily(summary="насыщенный день"), hourly)

        body = (vault / Config.DIGEST_OBSIDIAN_DAILY_SUBDIR / "2026-05-10.md").read_text(encoding="utf-8")
        assert body.startswith("# 2026-05-10")
        assert "## Резюме дня" in body
        assert body.index("насыщенный день") < body.index("зарядка")
        assert body.index("зарядка") < body.index("созвон")
        assert body.index("созвон") < body.index("закрытие дня")
        assert "## 09:00–10:00" in body
        assert "## 15:00–16:00" in body
        assert "## 21:00–22:00" in body
