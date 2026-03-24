"""Тесты изолированного диагностического блока приложения."""

import json

import numpy as np


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


def test_diagnostics_retention_keeps_only_latest_stems(app_module, tmp_path):
    """DiagnosticsStore должен удалять старые группы файлов сверх лимита."""
    diagnostics_store = app_module.DiagnosticsStore(root_dir=tmp_path, enabled=True, max_artifacts=2)

    for index in range(3):
        stem = f"sample-{index}"
        diagnostics = {"index": index}
        diagnostics_store.save_transcription_artifacts(stem, diagnostics, text=str(index))

    remaining = sorted(path.stem for path in (tmp_path / "transcriptions").glob("*.json"))

    assert remaining == ["sample-1", "sample-2"]


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
