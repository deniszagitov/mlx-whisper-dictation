"""Тесты runtime-адаптеров MLX LLM."""

from __future__ import annotations

from src.infrastructure import llm_runtime


def test_progress_tqdm_compatible_with_ensure_lock(monkeypatch):
    """Downloader должен отдавать tqdm-класс, совместимый с ensure_lock и итерацией."""
    from tqdm.contrib.concurrent import ensure_lock

    tqdm_cls_holder = []
    progress_events = []

    def fake_snapshot_download(_model_name, tqdm_class=None):
        tqdm_cls_holder.append(tqdm_class)

    monkeypatch.setattr("huggingface_hub.snapshot_download", fake_snapshot_download)

    llm_runtime.ensure_llm_model_downloaded(
        "fake-model",
        progress_callback=lambda desc, pct, total: progress_events.append((desc, pct, total)),
    )
    assert progress_events == [("Подготовка…", 0, 0), ("", 100, 0)]

    tqdm_cls = tqdm_cls_holder[0]

    with ensure_lock(tqdm_cls) as lock:
        assert lock is not None

    items = list(tqdm_cls([1, 2, 3], total=3, desc="files"))
    assert items == [1, 2, 3]

    assert list(tqdm_cls()) == []
    assert ("files", 100.0, 3) in progress_events


def test_cleanup_llm_runtime_memory_calls_gc(monkeypatch):
    """Cleanup runtime должен прокидывать освобождение памяти в gc.collect()."""
    gc_calls = []

    monkeypatch.setattr(llm_runtime.gc, "collect", lambda: gc_calls.append(True))

    llm_runtime.cleanup_llm_runtime_memory()

    assert gc_calls == [True]
