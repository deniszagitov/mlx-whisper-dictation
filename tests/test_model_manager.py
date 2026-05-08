"""Тесты централизованного менеджера моделей."""

from __future__ import annotations

from types import SimpleNamespace
from typing import TYPE_CHECKING, Any

import numpy as np
import pytest
from src.domain.model_downloads import ModelRequiredError
from src.infrastructure import asr_runtime
from src.infrastructure.model_manager import (
    DOWNLOAD_MAX_WORKERS,
    HuggingFaceModelDownloader,
    ModelDownloadStalledError,
    ModelDownloadTooSlowError,
    ModelManager,
)

if TYPE_CHECKING:
    from src.domain.model_downloads import ModelDownloadProgress


def test_huggingface_downloader_emits_speed_and_eta() -> None:
    """Общий downloader должен считать скорость и прогноз времени."""
    now = 0.0
    progress_events: list[ModelDownloadProgress] = []

    def clock() -> float:
        return now

    def fake_snapshot_download(_model_name: str, *, max_workers: int, tqdm_class: type[Any]) -> str:
        nonlocal now
        assert max_workers == DOWNLOAD_MAX_WORKERS
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

    def fake_snapshot_download(_model_name: str, *, max_workers: int, tqdm_class: type[Any]) -> str:
        nonlocal now
        assert max_workers == DOWNLOAD_MAX_WORKERS
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

    def fake_snapshot_download(_model_name: str, *, max_workers: int, tqdm_class: type[Any]) -> str:
        nonlocal now
        assert max_workers == DOWNLOAD_MAX_WORKERS
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


def test_huggingface_downloader_fails_sustained_slow_download() -> None:
    """Downloader должен останавливать загрузку, которая устойчиво медленнее лимита."""
    now = 0.0
    progress_events: list[ModelDownloadProgress] = []

    def clock() -> float:
        return now

    def fake_snapshot_download(_model_name: str, *, max_workers: int, tqdm_class: type[Any]) -> str:
        nonlocal now
        assert max_workers == 4
        progress_bar = tqdm_class(total=100 * 1024 * 1024, unit="B", name="huggingface_hub.snapshot_download")
        now = 2.0
        progress_bar.update(1024 * 1024)
        now = 8.0
        progress_bar.update(1024 * 1024)
        return "/tmp/model"

    downloader = HuggingFaceModelDownloader(
        snapshot_downloader=fake_snapshot_download,
        clock=clock,
        min_emit_interval_seconds=0,
        min_speed_bytes_per_second=2 * 1024 * 1024,
        slow_speed_grace_seconds=5.0,
        health_monitor_interval_seconds=0,
    )

    with pytest.raises(ModelDownloadTooSlowError):
        downloader.ensure_downloaded("mlx-community/test-model", label="LLM-модель", progress_callback=progress_events.append)

    assert any(event.warning and "слишком медленно" in event.warning for event in progress_events)
    assert progress_events[-1].failed is True
    assert "ниже 2 МБ/с" in str(progress_events[-1].warning)


def test_huggingface_downloader_marks_stalled_download() -> None:
    """Downloader должен отличать паузу без новых байтов от нормального прогресса."""
    now = 0.0
    progress_events: list[ModelDownloadProgress] = []

    def clock() -> float:
        return now

    def fake_snapshot_download(_model_name: str, *, max_workers: int, tqdm_class: type[Any]) -> str:
        nonlocal now
        assert max_workers == 4
        progress_bar = tqdm_class(total=100, unit="B", name="huggingface_hub.snapshot_download")
        now = 1.0
        progress_bar.update(10)
        now = 7.0
        progress_bar.refresh()
        progress_bar.update(1)
        return "/tmp/model"

    downloader = HuggingFaceModelDownloader(
        snapshot_downloader=fake_snapshot_download,
        clock=clock,
        min_emit_interval_seconds=0,
        stall_timeout_seconds=5.0,
        health_monitor_interval_seconds=0,
    )

    with pytest.raises(ModelDownloadStalledError):
        downloader.ensure_downloaded("mlx-community/test-model", label="LLM-модель", progress_callback=progress_events.append)

    assert any(event.warning and "приостановилась" in event.warning for event in progress_events)
    assert progress_events[-1].failed is True
    assert "приостановилась" in str(progress_events[-1].warning)


def test_huggingface_downloader_skips_model_verified_in_current_process() -> None:
    """После успешной проверки в текущем запуске downloader не должен повторно ходить в сеть."""
    download_calls: list[str] = []
    progress_events: list[ModelDownloadProgress] = []

    def fake_snapshot_download(model_name: str, *, max_workers: int, tqdm_class: type[Any]) -> str:
        del max_workers, tqdm_class
        download_calls.append(model_name)
        return "/tmp/model"

    downloader = HuggingFaceModelDownloader(snapshot_downloader=fake_snapshot_download)

    downloader.ensure_downloaded("mlx-community/test-model", label="ASR-модель", progress_callback=progress_events.append)
    downloader.ensure_downloaded("mlx-community/test-model", label="ASR-модель", progress_callback=progress_events.append)

    assert download_calls == ["mlx-community/test-model"]
    assert progress_events[-1].complete is True


def test_huggingface_downloader_uses_local_snapshot_without_network() -> None:
    """Если snapshot уже есть в HF cache, downloader не должен обращаться к сети."""
    snapshot_calls: list[tuple[str, bool, int | None]] = []
    progress_events: list[ModelDownloadProgress] = []

    def fake_snapshot_download(
        model_name: str,
        *,
        local_files_only: bool = False,
        max_workers: int | None = None,
        tqdm_class: type[Any] | None = None,
    ) -> str:
        del tqdm_class
        snapshot_calls.append((model_name, local_files_only, max_workers))
        if local_files_only:
            return "/tmp/hf-cache/test-model"
        raise AssertionError("Сетевой snapshot_download не должен вызываться для готового cache")

    downloader = HuggingFaceModelDownloader(snapshot_downloader=fake_snapshot_download)

    downloader.ensure_downloaded("mlx-community/test-model", label="ASR-модель", progress_callback=progress_events.append)

    assert snapshot_calls == [("mlx-community/test-model", True, None)]
    assert progress_events[-1].stage == "уже в cache"
    assert progress_events[-1].complete is True
    assert downloader.get_local_model_path("mlx-community/test-model") == "/tmp/hf-cache/test-model"
    assert snapshot_calls == [("mlx-community/test-model", True, None)]


def test_model_manager_routes_downloads_through_single_downloader(monkeypatch) -> None:
    """LLM, TTS и Whisper-ASR должны проверяться через один downloader."""
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

    manager.ensure_model_downloaded("mlx-community/llm", label="LLM-модель")
    manager.load_llm_runtime_objects("mlx-community/llm")
    manager.ensure_model_downloaded("mlx-community/tts", label="TTS-модель")
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


def test_model_manager_passes_local_snapshot_paths_to_runtime_loaders(monkeypatch) -> None:
    """Runtime-loader-ы должны получать локальные snapshot paths вместо HF repo id."""
    download_calls: list[tuple[str, str]] = []
    load_calls: list[tuple[str, str]] = []

    class FakeDownloader:
        def is_model_cached(self, _model_name: str) -> bool:
            return True

        def get_local_model_path(self, model_name: str) -> str:
            return f"/tmp/hf-cache/{model_name.replace('/', '--')}"

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

    manager.ensure_model_downloaded("mlx-community/llm", label="LLM-модель")
    manager.load_llm_runtime_objects("mlx-community/llm")
    manager.ensure_model_downloaded("mlx-community/tts", label="TTS-модель")
    manager.load_tts_model("mlx-community/tts")
    result = manager.run_asr_transcription(np.zeros(16000, dtype=np.float32), "mlx-community/whisper-turbo", "ru")

    assert result == {"text": "ru"}
    assert download_calls == [
        ("LLM-модель", "mlx-community/llm"),
        ("TTS-модель", "mlx-community/tts"),
        ("ASR-модель", "mlx-community/whisper-turbo"),
    ]
    assert load_calls == [
        ("llm", "/tmp/hf-cache/mlx-community--llm"),
        ("tts", "/tmp/hf-cache/mlx-community--tts"),
        ("asr", "/tmp/hf-cache/mlx-community--whisper-turbo"),
    ]


def test_model_manager_runtime_load_uses_cached_hf_snapshot_without_download() -> None:
    """Runtime loader должен синхронно грузить модель из локального HF cache без сетевой загрузки."""
    download_calls: list[str] = []
    load_calls: list[str] = []

    class FakeDownloader:
        def is_model_cached(self, _model_name: str) -> bool:
            return True

        def get_local_model_path(self, model_name: str) -> str:
            return f"/tmp/hf-cache/{model_name.replace('/', '--')}"

        def ensure_downloaded(self, model_name: str, *, label: str, progress_callback: Any = None) -> None:
            del label, progress_callback
            download_calls.append(model_name)

    def fake_loader(model_name: str) -> tuple[object, object]:
        load_calls.append(model_name)
        return object(), object()

    manager = ModelManager(downloader=FakeDownloader(), lm_loader=fake_loader)

    manager.load_llm_runtime_objects("mlx-community/partial-llm")

    assert download_calls == []
    assert load_calls == ["/tmp/hf-cache/mlx-community--partial-llm"]


def test_model_manager_runtime_load_raises_model_required_when_hf_cache_missing() -> None:
    """Runtime loader не должен сам начинать сетевую загрузку модели, если HF cache пуст."""
    download_calls: list[str] = []

    class FakeDownloader:
        def is_model_cached(self, _model_name: str) -> bool:
            return False

        def ensure_downloaded(self, model_name: str, *, label: str, progress_callback: Any = None) -> None:
            del label, progress_callback
            download_calls.append(model_name)

    manager = ModelManager(downloader=FakeDownloader(), lm_loader=lambda _model_name: (object(), object()))

    with pytest.raises(ModelRequiredError) as error:
        manager.load_llm_runtime_objects("mlx-community/partial-llm")

    assert error.value.model_name == "mlx-community/partial-llm"
    assert error.value.label == "LLM-модель"
    assert download_calls == []


def test_model_manager_download_marks_model_ready_for_runtime_load() -> None:
    """После общей проверки модели runtime loader может загружать её без сети."""
    download_calls: list[str] = []
    load_calls: list[str] = []

    class FakeDownloader:
        def is_model_cached(self, _model_name: str) -> bool:
            return False

        def ensure_downloaded(self, model_name: str, *, label: str, progress_callback: Any = None) -> None:
            del label, progress_callback
            download_calls.append(model_name)

    def fake_loader(model_name: str) -> tuple[object, object]:
        load_calls.append(model_name)
        return object(), object()

    manager = ModelManager(downloader=FakeDownloader(), lm_loader=fake_loader)

    manager.ensure_model_downloaded("mlx-community/llm", label="LLM-модель")
    manager.load_llm_runtime_objects("mlx-community/llm")

    assert download_calls == ["mlx-community/llm"]
    assert load_calls == ["mlx-community/llm"]


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
