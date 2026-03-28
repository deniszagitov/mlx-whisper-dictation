"""Тесты изолированного диагностического блока приложения."""

import json
import logging
import os

import numpy as np
import pytest
from src import diagnostics


def make_audio(seconds=1.0, amplitude=0.01):
    """Создает искусственный аудиосигнал заданной длины и амплитуды."""
    samples = int(16000 * seconds)
    return np.full(samples, amplitude, dtype=np.float32)


def test_build_audio_diagnostics_contains_expected_fields(app_module):
    """DiagnosticsStore должен собирать компактную сводку по аудио."""
    diagnostics_store = app_module.DiagnosticsStore(enabled=False)

    diagnostics = diagnostics_store.build_audio_diagnostics(make_audio(seconds=2.0, amplitude=0.02), "ru")

    assert diagnostics["language"] == "ru"
    assert diagnostics["duration_seconds"] == 2.0
    assert diagnostics["sample_rate"] == 16000
    assert diagnostics["samples"] == 32000


def test_disabled_diagnostics_do_not_write_files(app_module, tmp_path):
    """При disabled=False диагностический блок не должен писать файлы."""
    diagnostics_store = app_module.DiagnosticsStore(root_dir=tmp_path, enabled=False)

    wav_path = diagnostics_store.save_audio_recording("sample", make_audio(), {"ok": True})
    result_path = diagnostics_store.save_transcription_artifacts("sample", {"ok": True}, text="Привет")

    assert wav_path is None
    assert result_path is None
    assert not (tmp_path / "recordings").exists()
    assert not (tmp_path / "transcriptions").exists()


def test_enabled_diagnostics_write_audio_and_transcription_files(app_module, tmp_path):
    """При включенной диагностике должны сохраняться аудио и результаты распознавания."""
    diagnostics_store = app_module.DiagnosticsStore(root_dir=tmp_path, enabled=True)
    diagnostics = diagnostics_store.build_audio_diagnostics(make_audio(), "ru")

    wav_path = diagnostics_store.save_audio_recording("sample", make_audio(), diagnostics)
    result_path = diagnostics_store.save_transcription_artifacts(
        "sample",
        diagnostics,
        result={"text": "Привет"},
        text="Привет",
    )

    assert wav_path == tmp_path / "recordings" / "sample.wav"
    assert result_path == tmp_path / "transcriptions" / "sample.json"
    assert (tmp_path / "recordings" / "sample.json").exists()
    assert (tmp_path / "transcriptions" / "sample.txt").read_text(encoding="utf-8") == "Привет"


def test_diagnostics_retention_removes_files_older_than_24_hours(app_module, tmp_path):
    """DiagnosticsStore должен удалять артефакты старше 24 часов."""
    diagnostics_store = app_module.DiagnosticsStore(root_dir=tmp_path, enabled=True, retention_seconds=24 * 60 * 60)
    transcriptions_dir = tmp_path / "transcriptions"
    transcriptions_dir.mkdir(parents=True)
    old_json = transcriptions_dir / "old.json"
    old_txt = transcriptions_dir / "old.txt"
    old_json.write_text("{}", encoding="utf-8")
    old_txt.write_text("old", encoding="utf-8")

    stale_time = 2_000_000.0
    current_time = stale_time + (24 * 60 * 60) + 10
    fresh_time = current_time - 5
    os.utime(old_json, (stale_time, stale_time))
    os.utime(old_txt, (stale_time, stale_time))

    diagnostics_store.save_transcription_artifacts("fresh", {"ok": True}, text="fresh")
    fresh_json = transcriptions_dir / "fresh.json"
    fresh_txt = transcriptions_dir / "fresh.txt"
    os.utime(fresh_json, (fresh_time, fresh_time))
    os.utime(fresh_txt, (fresh_time, fresh_time))

    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(diagnostics.logging, "time", __import__("time"))
    monkeypatch.setattr(diagnostics.time, "time", lambda: current_time)
    diagnostics_store._cleanup_directory(transcriptions_dir)
    monkeypatch.undo()

    assert not old_json.exists()
    assert not old_txt.exists()
    assert fresh_json.exists()
    assert fresh_txt.exists()


def test_diagnostics_payload_serializes_result(app_module, tmp_path):
    """JSON-представление диагностики должно включать текст и result payload."""
    diagnostics_store = app_module.DiagnosticsStore(root_dir=tmp_path, enabled=True)

    result_path = diagnostics_store.save_transcription_artifacts(
        "sample",
        {"language": "ru"},
        result={"text": "Готово", "segments": []},
        text="Готово",
    )

    payload = json.loads(result_path.read_text(encoding="utf-8"))

    assert payload["text"] == "Готово"
    assert payload["result"]["segments"] == []


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("thank you", True),
        (" Thank You. ", True),
        ("Продолжение следует...", True),
        ("обычный текст", False),
    ],
)
def test_looks_like_hallucination_detects_known_phrases(text, expected):
    """Фильтр галлюцинаций должен распознавать известные шаблоны."""
    assert diagnostics.looks_like_hallucination(text) is expected


def test_max_level_filter_blocks_records_at_and_above_limit():
    """MaxLevelFilter должен пропускать только записи ниже указанного уровня."""
    filter_instance = diagnostics.MaxLevelFilter(logging.ERROR)
    debug_record = logging.LogRecord("test", logging.DEBUG, __file__, 1, "debug", (), None)
    error_record = logging.LogRecord("test", logging.ERROR, __file__, 1, "error", (), None)

    assert filter_instance.filter(debug_record) is True
    assert filter_instance.filter(error_record) is False


def test_setup_logging_creates_stdout_and_stderr_handlers(tmp_path, monkeypatch):
    """setup_logging должен настроить консоль и раздельные файловые хендлеры."""
    root_logger = logging.getLogger()
    original_handlers = list(root_logger.handlers)

    monkeypatch.setattr(diagnostics, "LOG_DIR", tmp_path)

    diagnostics.setup_logging()

    try:
        logger = logging.getLogger("diagnostics-test")
        logger.info("info message")
        logger.error("error message")

        for handler in root_logger.handlers:
            if hasattr(handler, "flush"):
                handler.flush()

        assert len(root_logger.handlers) == 3
        assert (tmp_path / "stdout.log").exists()
        assert (tmp_path / "stderr.log").exists()

        stdout_text = (tmp_path / "stdout.log").read_text(encoding="utf-8")
        stderr_text = (tmp_path / "stderr.log").read_text(encoding="utf-8")

        assert "info message" in stdout_text
        assert "error message" not in stdout_text
        assert "error message" in stderr_text
    finally:
        for handler in root_logger.handlers:
            handler.close()
        root_logger.handlers.clear()
        root_logger.handlers.extend(original_handlers)
