"""Тесты централизованного менеджера моделей."""

from __future__ import annotations

from types import SimpleNamespace
from typing import TYPE_CHECKING, Any

import numpy as np
import pytest
from src.infrastructure import asr_runtime
from src.infrastructure.model_manager import HuggingFaceModelDownloader, ModelManager

if TYPE_CHECKING:
    from src.domain.model_downloads import ModelDownloadProgress


def test_huggingface_downloader_emits_speed_and_eta() -> None:
    """Общий downloader должен считать скорость и прогноз времени."""
    now = 0.0
    progress_events: list[ModelDownloadProgress] = []

    def clock() -> float:
        return now

    def fake_snapshot_download(_model_name: str, *, tqdm_class: type[Any]) -> str:
        nonlocal now
        progress_bar = tqdm_class(total=100, unit="B", name="huggingface_hub.snapshot_download")
        now = 2.0
        progress_bar.update(50)
        progress_bar.close()
        return "/tmp/model"

    downloader = HuggingFaceModelDownloader(
        snapshot_downloader=fake_snapshot_download,
        clock=clock,
        min_emit_interval_seconds=0,
    )

    downloader.ensure_downloaded("mlx-community/test-model", label="ASR-модель", progress_callback=progress_events.append)

    mid_progress = next(event for event in progress_events if event.downloaded_bytes == 50)
    assert mid_progress.total_bytes == 100
    assert mid_progress.percent == 50.0
    assert mid_progress.speed_bytes_per_second == 25.0
    assert mid_progress.eta_seconds == 2.0
    assert progress_events[-1].complete is True


def test_huggingface_downloader_smooths_short_speed_spikes() -> None:
    """Скорость не должна прыгать от коротких стартовых updates."""
    now = 0.0
    progress_events: list[ModelDownloadProgress] = []

    def clock() -> float:
        return now

    def fake_snapshot_download(_model_name: str, *, tqdm_class: type[Any]) -> str:
        nonlocal now
        progress_bar = tqdm_class(total=100_000, unit="B", name="huggingface_hub.snapshot_download")
        now = 0.1
        progress_bar.update(20_000)
        now = 1.1
        progress_bar.update(20_000)
        progress_bar.close()
        return "/tmp/model"

    downloader = HuggingFaceModelDownloader(
        snapshot_downloader=fake_snapshot_download,
        clock=clock,
        min_emit_interval_seconds=0,
    )

    downloader.ensure_downloaded("mlx-community/test-model", label="LLM-модель", progress_callback=progress_events.append)

    first_real_progress = next(event for event in progress_events if event.downloaded_bytes == 20_000)
    smoothed_progress = next(event for event in progress_events if event.downloaded_bytes == 40_000)
    assert first_real_progress.speed_bytes_per_second is None
    assert smoothed_progress.speed_bytes_per_second == pytest.approx(36_363.64, rel=0.01)
    assert smoothed_progress.eta_seconds == pytest.approx(1.65, rel=0.01)


def test_console_progress_bar_uses_smoothed_speed_text() -> None:
    """Консольный progress bar должен показывать наш сглаженный speed/ETA."""
    now = 0.0
    progress_bars: list[Any] = []

    def clock() -> float:
        return now

    def fake_snapshot_download(_model_name: str, *, tqdm_class: type[Any]) -> str:
        nonlocal now
        progress_bar = tqdm_class(total=100_000, unit="B", name="huggingface_hub.snapshot_download")
        progress_bars.append(progress_bar)
        now = 1.0
        progress_bar.update(50_000)
        progress_bar.close()
        return "/tmp/model"

    downloader = HuggingFaceModelDownloader(
        snapshot_downloader=fake_snapshot_download,
        clock=clock,
        min_emit_interval_seconds=0,
    )

    downloader.ensure_downloaded("mlx-community/test-model", label="LLM-модель")

    progress_bar = progress_bars[0]
    assert "{rate_fmt}" not in progress_bar.bar_format
    assert "{remaining}" not in progress_bar.bar_format
    assert "КБ/с" in progress_bar.postfix
    assert "осталось" in progress_bar.postfix


def test_model_manager_routes_loads_through_single_downloader(monkeypatch) -> None:
    """LLM, TTS и Whisper-ASR должны идти через один downloader."""
    download_calls: list[tuple[str, str]] = []
    load_calls: list[tuple[str, str]] = []

    class FakeDownloader:
        def is_model_cached(self, _model_name: str) -> bool:
            return False

        def ensure_downloaded(self, model_name: str, *, label: str, progress_callback: Any = None) -> None:
            del progress_callback
            download_calls.append((label, model_name))

    def fake_lm_loader(model_name: str) -> tuple[object, object]:
        load_calls.append(("llm", model_name))
        return object(), object()

    def fake_tts_loader(model_name: str) -> object:
        load_calls.append(("tts", model_name))
        return object()

    def fake_whisper(audio_data: object, model_name: str, language: str | None) -> dict[str, str | None]:
        del audio_data
        load_calls.append(("asr", model_name))
        return {"text": language}

    monkeypatch.setattr(asr_runtime, "run_whisper_transcription", fake_whisper)
    manager = ModelManager(downloader=FakeDownloader(), lm_loader=fake_lm_loader, tts_loader=fake_tts_loader)

    manager.load_llm_runtime_objects("mlx-community/llm")
    manager.load_tts_model("mlx-community/tts")
    result = manager.run_asr_transcription(np.zeros(16000, dtype=np.float32), "mlx-community/whisper-turbo", "ru")

    assert result == {"text": "ru"}
    assert download_calls == [
        ("LLM-модель", "mlx-community/llm"),
        ("TTS-модель", "mlx-community/tts"),
        ("ASR-модель", "mlx-community/whisper-turbo"),
    ]
    assert load_calls == [
        ("llm", "mlx-community/llm"),
        ("tts", "mlx-community/tts"),
        ("asr", "mlx-community/whisper-turbo"),
    ]


def test_model_manager_passes_qwen_asr_loader_through_downloader(monkeypatch) -> None:
    """Qwen3-ASR должен получать модель через loader менеджера."""
    download_calls: list[tuple[str, str]] = []
    load_calls: list[str] = []

    class FakeDownloader:
        def is_model_cached(self, _model_name: str) -> bool:
            return False

        def ensure_downloaded(self, model_name: str, *, label: str, progress_callback: Any = None) -> None:
            del progress_callback
            download_calls.append((label, model_name))

    def fake_qwen_loader(model_name: str) -> SimpleNamespace:
        load_calls.append(model_name)
        return SimpleNamespace()

    def fake_qwen_transcription(
        _audio_data: object,
        _model_name: str,
        _language: str | None,
        *,
        model_loader: Any,
    ) -> dict[str, str]:
        model_loader("mlx-community/Qwen3-ASR-1.7B-8bit")
        return {"text": "qwen"}

    monkeypatch.setattr(asr_runtime, "run_qwen_transcription", fake_qwen_transcription)
    manager = ModelManager(downloader=FakeDownloader(), qwen_asr_loader=fake_qwen_loader)

    result = manager.run_asr_transcription(np.zeros(16000, dtype=np.float32), "mlx-community/Qwen3-ASR-1.7B-8bit", "ru")

    assert result == {"text": "qwen"}
    assert download_calls == [("ASR-модель", "mlx-community/Qwen3-ASR-1.7B-8bit")]
    assert load_calls == ["mlx-community/Qwen3-ASR-1.7B-8bit"]
