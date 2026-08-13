"""Тесты PyTorch runtime GigaAM Multilingual large_ctc."""

from __future__ import annotations

from contextlib import nullcontext
from types import SimpleNamespace

import numpy as np
from src.domain.constants import Config
from src.infrastructure import gigaam_multilingual_runtime as runtime


class FakeTensor:
    """Минимальный tensor-double для проверки wiring без PyTorch."""

    def __init__(self, values):
        self.values = np.asarray(values)
        self.shape = self.values.shape
        self.device = "mps"
        self.dtype = "float32"

    def to(self, *, device=None, dtype=None):
        self.device = device or self.device
        self.dtype = dtype or self.dtype
        return self

    def unsqueeze(self, _axis):
        self.values = np.expand_dims(self.values, 0)
        self.shape = self.values.shape
        return self


class FakeTorch:
    """PyTorch-double только для используемого runtime API."""

    long = "int64"

    @staticmethod
    def from_numpy(values):
        return FakeTensor(values)

    @staticmethod
    def full(shape, value, *, device, dtype):
        return FakeTensor(np.full(shape, value)).to(device=device, dtype=dtype)

    @staticmethod
    def inference_mode():
        return nullcontext()


def test_large_ctc_model_identifier_is_exact():
    """Диспетчер не должен путать ctc с непригодным для ASR large_ssl."""
    assert runtime.is_gigaam_multilingual_large_ctc_model(Config.GIGAAM_MULTILINGUAL_LARGE_CTC_MODEL) is True
    assert runtime.is_gigaam_multilingual_large_ctc_model("ai-sage/GigaAM-Multilingual@large_ssl") is False


def test_loader_uses_official_large_ctc_revision_and_mps(monkeypatch):
    """Загрузчик выбирает официальный 600M checkpoint и MPS."""
    calls: list[object] = []

    class FakeModel:
        def eval(self):
            calls.append("eval")

        def to(self, device):
            calls.append(("to", device))

    fake_model = FakeModel()
    def fake_from_pretrained(*args, **kwargs):
        calls.append((args, kwargs))
        return fake_model

    fake_transformers = SimpleNamespace(AutoModel=SimpleNamespace(from_pretrained=fake_from_pretrained))
    fake_torch = SimpleNamespace(backends=SimpleNamespace(mps=SimpleNamespace(is_available=lambda: True)))
    monkeypatch.setattr(
        runtime,
        "import_module",
        lambda name: fake_torch if name == "torch" else fake_transformers,
    )

    result = runtime.load_gigaam_multilingual_large_ctc()

    assert result is fake_model
    assert calls[0] == (
        ("ai-sage/GigaAM-Multilingual",),
        {"revision": "large_ctc", "trust_remote_code": True},
    )
    assert calls[1:] == ["eval", ("to", "mps")]


def test_transcription_splits_long_audio_and_keeps_all_text(monkeypatch):
    """large_ctc получает все 25-секундные части и возвращает общий формат ASR."""
    decode_calls: list[int] = []

    class FakeDecoding:
        def decode(self, _head, _encoded, _encoded_length):
            index = len(decode_calls) + 1
            decode_calls.append(index)
            return [(f"часть {index}", [index, index + 10], [0, 1])]

    class FakeInnerModel:
        head = object()
        decoding = FakeDecoding()

        def __call__(self, wav, wav_length):
            assert wav.shape[0] == 1
            assert wav_length.device == "mps"
            return object(), object()

    fake_model = SimpleNamespace(model=FakeInnerModel())
    monkeypatch.setattr(runtime, "import_module", lambda _name: FakeTorch)
    monkeypatch.setattr(runtime, "get_cached_gigaam_multilingual_model", lambda _model_name: fake_model)
    monkeypatch.setattr(runtime, "_model_device_and_dtype", lambda _model: ("mps", "float32"))
    audio = np.arange(400_123, dtype=np.float32)

    result = runtime.run_gigaam_multilingual_transcription(
        audio,
        Config.GIGAAM_MULTILINGUAL_LARGE_CTC_MODEL,
        "kk-KZ",
    )

    assert result["text"] == "часть 1 часть 2"
    assert result["language"] == "kk"
    assert result["total_tokens"] == 4
    assert result["segments"][0]["start"] == 0.0
    assert result["segments"][0]["end"] == 25.0
    assert result["segments"][1]["start"] == 25.0
    assert result["segments"][1]["end"] == 25.0 + 123 / 16_000


def test_model_cache_loads_large_checkpoint_once(monkeypatch):
    """600M checkpoint не должен повторно загружаться между диктовками."""
    loaded = []
    fake_model = object()

    def fake_load_model():
        loaded.append(True)
        return fake_model

    monkeypatch.setattr(runtime, "_MODEL_CACHE", {})
    monkeypatch.setattr(runtime, "load_gigaam_multilingual_large_ctc", fake_load_model)

    first = runtime.get_cached_gigaam_multilingual_model(Config.GIGAAM_MULTILINGUAL_LARGE_CTC_MODEL)
    second = runtime.get_cached_gigaam_multilingual_model(Config.GIGAAM_MULTILINGUAL_LARGE_CTC_MODEL)

    assert first is fake_model
    assert second is fake_model
    assert loaded == [True]
