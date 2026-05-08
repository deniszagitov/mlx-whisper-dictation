"""Тесты единого runtime-cache MLX-моделей."""

from __future__ import annotations

import importlib
import threading
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace

import pytest
from src.infrastructure import model_runtime_service as runtime_module
from src.infrastructure.llm_runtime import LlmGateway
from src.infrastructure.model_runtime_service import ModelRuntimeService


class FakeTokenizer:
    """Минимальный tokenizer для LlmGateway."""

    def apply_chat_template(self, messages, tokenize=False, add_generation_prompt=True, enable_thinking=False):
        """Собирает prompt из сообщений."""
        del tokenize, add_generation_prompt, enable_thinking
        return "\n".join(message["content"] for message in messages)

    def encode(self, text):
        """Считает токены словами."""
        return text.split()


@pytest.mark.parametrize(
    ("method_name", "loader_name"),
    [
        ("get_lm", "lm_loader"),
        ("get_mlx_tts", "mlx_tts_loader"),
        ("get_qwen_asr", "qwen_asr_loader"),
    ],
)
def test_concurrent_runtime_requests_share_single_load(method_name: str, loader_name: str) -> None:
    """Параллельные запросы одной модели должны ждать один loader."""
    load_calls: list[str] = []
    release_loader = threading.Event()
    loader_started = threading.Event()
    model = object()

    def loader(model_name: str):
        load_calls.append(model_name)
        loader_started.set()
        release_loader.wait(timeout=2)
        if method_name == "get_lm":
            return model, FakeTokenizer()
        return model

    if loader_name == "lm_loader":
        service = ModelRuntimeService(lm_loader=loader)
    elif loader_name == "mlx_tts_loader":
        service = ModelRuntimeService(mlx_tts_loader=loader)
    else:
        service = ModelRuntimeService(qwen_asr_loader=loader)
    runtime_getter = getattr(service, method_name)

    with ThreadPoolExecutor(max_workers=4) as executor:
        futures = [executor.submit(runtime_getter, "model-a") for _ in range(4)]
        assert loader_started.wait(timeout=1)
        release_loader.set()
        results = [future.result(timeout=2) for future in futures]

    assert load_calls == ["model-a"]
    if method_name == "get_lm":
        assert [result[0] for result in results] == [model, model, model, model]
    else:
        assert results == [model, model, model, model]


def test_lm_gateway_reader_and_zipper_share_runtime_loader() -> None:
    """Последовательные вызовы одного gateway не должны повторно грузить LLM."""
    load_calls: list[str] = []

    def load_model(model_name: str):
        load_calls.append(model_name)
        return object(), FakeTokenizer()

    service = ModelRuntimeService(lm_loader=load_model)
    gateway = LlmGateway(
        "shared-llm",
        runtime_loader=service.get_lm,
        generation_runner=lambda _model, _tokenizer, _prompt, _max_tokens: "готово",
    )

    assert gateway.process_text("команда Zipper", "система") == "готово"
    assert gateway.process_text("текст reader", "система") == "готово"
    assert load_calls == ["shared-llm"]


def test_release_model_removes_only_selected_model() -> None:
    """release_model должен очищать только указанный model_id."""
    load_calls: list[str] = []
    cleanup_calls: list[bool] = []

    def load_model(model_name: str):
        load_calls.append(model_name)
        return object(), FakeTokenizer()

    service = ModelRuntimeService(lm_loader=load_model, memory_cleanup=lambda: cleanup_calls.append(True))

    service.get_lm("model-a")
    service.get_lm("model-b")
    service.release_model("model-a")
    service.get_lm("model-b")
    service.get_lm("model-a")

    assert load_calls == ["model-a", "model-b", "model-a"]
    assert cleanup_calls == [True]


def test_release_model_during_inflight_load_prevents_stale_cache() -> None:
    """Если модель сменили во время загрузки, завершившийся load не должен остаться в cache."""
    load_calls: list[str] = []
    loader_started = threading.Event()
    release_loader = threading.Event()

    def load_model(model_name: str):
        load_calls.append(model_name)
        loader_started.set()
        release_loader.wait(timeout=2)
        return object(), FakeTokenizer()

    service = ModelRuntimeService(lm_loader=load_model)
    worker = threading.Thread(target=lambda: service.get_lm("model-a"))
    worker.start()
    assert loader_started.wait(timeout=1)

    service.release_model("model-a")
    release_loader.set()
    worker.join(timeout=2)
    service.get_lm("model-a")

    assert load_calls == ["model-a", "model-a"]


def test_different_backend_loaders_are_serialized_to_avoid_import_deadlocks() -> None:
    """Параллельный preload разных backend-ов не должен запускать тяжёлые import/load одновременно."""
    active_loaders = 0
    max_active_loaders = 0
    counter_lock = threading.Lock()
    release_first_loader = threading.Event()
    first_loader_started = threading.Event()

    def tracked_loader(model_name: str) -> object:
        nonlocal active_loaders, max_active_loaders
        with counter_lock:
            active_loaders += 1
            max_active_loaders = max(max_active_loaders, active_loaders)
        if model_name == "model-a":
            first_loader_started.set()
            release_first_loader.wait(timeout=2)
        try:
            return object()
        finally:
            with counter_lock:
                active_loaders -= 1

    service = ModelRuntimeService(qwen_asr_loader=tracked_loader, mlx_tts_loader=tracked_loader)
    with ThreadPoolExecutor(max_workers=2) as executor:
        first = executor.submit(service.get_qwen_asr, "model-a")
        assert first_loader_started.wait(timeout=1)
        second = executor.submit(service.get_mlx_tts, "model-b")
        release_first_loader.set()
        first.result(timeout=2)
        second.result(timeout=2)

    assert max_active_loaders == 1


def test_whisper_preload_fills_model_holder_and_transcribe_reuses_it(monkeypatch) -> None:
    """Whisper preload должен заполнить ModelHolder без повторной загрузки при том же path."""
    transcribe_module = importlib.import_module("mlx_whisper.transcribe")
    load_calls: list[tuple[str, str]] = []
    model = SimpleNamespace(name="whisper")

    def preload_model(model_name: str, dtype=None):
        del dtype
        load_calls.append(("preload", model_name))
        return model

    def holder_load_model(model_name: str, dtype=None):
        del dtype
        load_calls.append(("holder", model_name))
        return SimpleNamespace(name="unexpected")

    monkeypatch.setattr("mlx_whisper.load_models.load_model", preload_model)
    monkeypatch.setattr(transcribe_module, "load_model", holder_load_model)
    transcribe_module.ModelHolder.model = None
    transcribe_module.ModelHolder.model_path = None

    service = ModelRuntimeService()
    service.get_whisper("/tmp/whisper-model")
    reused_model = transcribe_module.ModelHolder.get_model("/tmp/whisper-model", dtype=object())

    assert reused_model is model
    assert transcribe_module.ModelHolder.model_path == "/tmp/whisper-model"
    assert load_calls == [("preload", "/tmp/whisper-model")]


def test_shutdown_clears_runtime_cache() -> None:
    """shutdown должен очищать cache один раз и позволять процессу завершиться чисто."""
    load_calls: list[str] = []
    cleanup_calls: list[bool] = []

    def load_model(model_name: str):
        load_calls.append(model_name)
        return object(), FakeTokenizer()

    service = ModelRuntimeService(lm_loader=load_model, memory_cleanup=lambda: cleanup_calls.append(True))

    service.get_lm("model-a")
    service.shutdown()
    service.get_lm("model-a")

    assert load_calls == ["model-a", "model-a"]
    assert cleanup_calls == [True]


def test_preload_selected_models_routes_backends(monkeypatch) -> None:
    """preload_selected_models должен выбрать ASR, VLM и TTS backends."""
    calls: list[tuple[str, str]] = []
    threads: list[threading.Thread] = []

    class ImmediateThread:
        def __init__(self, *, target, name=None, daemon=None):
            del name, daemon
            self._target = target

        def start(self):
            self._target()

        def join(self):
            return None

    monkeypatch.setattr(runtime_module.threading, "Thread", ImmediateThread)
    def load_whisper(model_name: str) -> object:
        calls.append(("whisper", model_name))
        return object()

    def load_vlm(model_name: str) -> tuple[object, object]:
        calls.append(("vlm", model_name))
        return object(), object()

    def load_tts(model_name: str) -> object:
        calls.append(("tts", model_name))
        return object()

    service = ModelRuntimeService(
        whisper_loader=load_whisper,
        vlm_loader=load_vlm,
        mlx_tts_loader=load_tts,
    )

    threads = service.preload_selected_models(
        asr_model="mlx-community/whisper-large-v3-turbo",
        llm_model="mlx-community/gemma-4-26b-a4b-it-4bit",
        tts_model="mlx-community/Qwen3-TTS",
        wait=True,
    )

    assert len(threads) == 3
    assert calls == [
        ("whisper", "mlx-community/whisper-large-v3-turbo"),
        ("vlm", "mlx-community/gemma-4-26b-a4b-it-4bit"),
        ("tts", "mlx-community/Qwen3-TTS"),
    ]
