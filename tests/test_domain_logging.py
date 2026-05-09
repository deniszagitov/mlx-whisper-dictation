"""Тесты безопасного маскирования и нормализации логов."""

from __future__ import annotations

from src.domain.constants import Config
from src.domain.logging import sanitize_mapping_for_logging, sanitize_path_for_logging, summarize_text_for_logging


def test_summarize_text_for_logging_hides_source_text():
    """Сводка текста не должна содержать исходную строку целиком."""
    text = "секретный текст 123"

    summary = summarize_text_for_logging(text)

    assert text not in summary
    assert f"chars={len(text)}" in summary
    assert "words=3" in summary
    assert "sha256=" in summary


def test_sanitize_path_for_logging_makes_log_paths_relative():
    """Абсолютные пути внутри каталога логов должны становиться относительными."""
    path = Config.LOG_DIR / "recordings" / "20260509-222229-996.raw.wav"

    sanitized = sanitize_path_for_logging(path)

    assert sanitized == "recordings/20260509-222229-996.raw.wav"


def test_sanitize_mapping_for_logging_masks_all_paths():
    """Словарь диагностических артефактов должен логироваться без домашней директории."""
    mapping = {
        "raw_wav": str(Config.LOG_DIR / "recordings" / "sample.raw.wav"),
        "metadata": str(Config.LOG_DIR / "recordings" / "sample.json"),
    }

    sanitized = sanitize_mapping_for_logging(mapping)

    assert sanitized == {
        "raw_wav": "recordings/sample.raw.wav",
        "metadata": "recordings/sample.json",
    }
