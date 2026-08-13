"""Юнит-тесты общего ASR runtime для Whisper, Qwen3-ASR и GigaAM."""

from types import SimpleNamespace

import numpy as np
from src.domain.constants import Config
from src.infrastructure import asr_runtime as asr_runtime_module


def make_audio(seconds=1.0, amplitude=0.01):
    """Создает искусственный аудиосигнал заданной длины и амплитуды."""
    samples = int(16000 * seconds)
    return np.full(samples, amplitude, dtype=np.float32)


def test_run_asr_transcription_dispatches_to_qwen_backend(monkeypatch):
    """Qwen3-ASR-модели должны идти через mlx-audio backend."""
    calls: list[tuple[object, str, str | None]] = []

    def fake_qwen_transcription(audio_data, model_name, language):
        calls.append((audio_data, model_name, language))
        return {"text": "qwen"}

    monkeypatch.setattr(
        asr_runtime_module,
        "run_qwen_transcription",
        fake_qwen_transcription,
    )

    result = asr_runtime_module.run_asr_transcription(make_audio(), "mlx-community/Qwen3-ASR-1.7B-8bit", "ru")

    assert result == {"text": "qwen"}
    assert calls
    assert calls[0][1] == "mlx-community/Qwen3-ASR-1.7B-8bit"
    assert calls[0][2] == "ru"


def test_run_asr_transcription_dispatches_to_gigaam_backend(monkeypatch):
    """Пресет GigaAM должен идти через transcribe.cpp backend."""
    calls: list[tuple[object, str, str | None]] = []

    def fake_gigaam_transcription(audio_data, model_name, language):
        calls.append((audio_data, model_name, language))
        return {"text": "gigaam"}

    monkeypatch.setattr(asr_runtime_module, "run_gigaam_transcription", fake_gigaam_transcription)

    result = asr_runtime_module.run_asr_transcription(
        make_audio(),
        "handy-computer/gigaam-v3-e2e-rnnt-gguf",
        "ru",
    )

    assert result == {"text": "gigaam"}
    assert calls[0][1] == "handy-computer/gigaam-v3-e2e-rnnt-gguf"
    assert calls[0][2] == "ru"


def test_run_asr_transcription_dispatches_to_gigaam_multilingual_large_ctc(monkeypatch):
    """Официальный large_ctc checkpoint должен идти через PyTorch runtime."""
    calls = []

    def fake_multilingual(audio_data, model_name, language):
        calls.append((audio_data, model_name, language))
        return {"text": "multilingual"}

    monkeypatch.setattr(asr_runtime_module, "run_gigaam_multilingual_transcription", fake_multilingual)

    result = asr_runtime_module.run_asr_transcription(
        make_audio(),
        Config.GIGAAM_MULTILINGUAL_LARGE_CTC_MODEL,
        "uz",
    )

    assert result == {"text": "multilingual"}
    assert calls[0][1:] == (Config.GIGAAM_MULTILINGUAL_LARGE_CTC_MODEL, "uz")


def test_run_asr_transcription_dispatches_to_whisper_backend(monkeypatch):
    """Whisper-модели должны сохранять текущий mlx_whisper backend."""
    calls: list[tuple[object, str, str | None]] = []

    def fake_whisper_transcription(audio_data, model_name, language):
        calls.append((audio_data, model_name, language))
        return {"text": "whisper"}

    monkeypatch.setattr(
        asr_runtime_module,
        "run_whisper_transcription",
        fake_whisper_transcription,
    )

    result = asr_runtime_module.run_asr_transcription(make_audio(), "mlx-community/whisper-large-v3-turbo", "ru")

    assert result == {"text": "whisper"}
    assert calls
    assert calls[0][1] == "mlx-community/whisper-large-v3-turbo"
    assert calls[0][2] == "ru"


def test_run_qwen_transcription_passes_audio_from_memory(monkeypatch):
    """Qwen backend должен получать аудио напрямую из памяти, а не путь к WAV."""
    captured = {}

    class FakeResult:
        def __init__(self) -> None:
            self.text = "Привет"
            self.language = "Russian"
            self.segments: list[dict[str, float | str]] = [{"text": "Привет", "start": 0.0, "end": 0.5}]
            self.prompt_tokens = 3
            self.generation_tokens = 4
            self.total_tokens = 7

    class FakeModel:
        def generate(self, audio, **kwargs):
            captured["audio"] = audio
            captured["language"] = kwargs.get("language")
            return FakeResult()

    monkeypatch.setattr(asr_runtime_module, "_get_cached_qwen_model", lambda _model_name: FakeModel())

    result = asr_runtime_module.run_qwen_transcription(make_audio(), "mlx-community/Qwen3-ASR-1.7B-8bit", "ru")

    assert captured["language"] == "Russian"
    assert not isinstance(captured["audio"], str)
    assert getattr(captured["audio"], "shape", None) == (16000,)
    assert result["text"] == "Привет"
    assert result["language"] == "Russian"
    assert result["segments"] == [{"text": "Привет", "start": 0.0, "end": 0.5}]
    assert result["total_tokens"] == 7


def test_run_qwen_transcription_falls_back_to_auto_language(monkeypatch):
    """Неподдержанный языковой код не должен ломать вызов Qwen backend-а."""
    captured = {}

    class FakeResult:
        def __init__(self) -> None:
            self.text = "Hello"
            self.language = "English"
            self.segments: list[dict[str, float | str]] = []
            self.prompt_tokens = 0
            self.generation_tokens = 2
            self.total_tokens = 2

    class FakeModel:
        def generate(self, audio, **kwargs):
            captured["audio"] = audio
            captured["language"] = kwargs.get("language")
            return FakeResult()

    monkeypatch.setattr(asr_runtime_module, "_get_cached_qwen_model", lambda _model_name: FakeModel())

    result = asr_runtime_module.run_qwen_transcription(make_audio(), "mlx-community/Qwen3-ASR-1.7B-8bit", "xx")

    assert captured["language"] is None
    assert not isinstance(captured["audio"], str)
    assert result["language"] == "English"
    assert result["total_tokens"] == 2


def test_resolve_gigaam_model_downloads_exact_fp16_file(monkeypatch):
    """Hugging Face-пресет должен скачивать только выбранный F16 GGUF."""
    calls = []

    def fake_download(**kwargs):
        calls.append(kwargs)
        return "/tmp/gigaam-v3-e2e-rnnt-F16.gguf"

    monkeypatch.setattr(asr_runtime_module, "hf_hub_download", fake_download)

    path = asr_runtime_module._resolve_gigaam_model_path("handy-computer/gigaam-v3-e2e-rnnt-gguf")

    assert str(path) == "/tmp/gigaam-v3-e2e-rnnt-F16.gguf"
    assert calls == [
        {
            "repo_id": "handy-computer/gigaam-v3-e2e-rnnt-gguf",
            "filename": "gigaam-v3-e2e-rnnt-F16.gguf",
        }
    ]


def test_run_gigaam_transcription_normalizes_result_and_ignores_language(monkeypatch):
    """GigaAM получает float32 PCM, а результат возвращается в общем формате ASR."""
    captured = {}

    class FakeSession:
        limits = SimpleNamespace(effective_max_audio_ms=25_000)

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def run(self, audio, **kwargs):
            captured["audio"] = audio
            captured["kwargs"] = kwargs
            return SimpleNamespace(
                text="Привет, мир!",
                segments=(SimpleNamespace(text="Привет, мир!", t0_ms=100, t1_ms=900, n_tokens=3),),
                tokens=(object(), object(), object()),
            )

    class FakeModel:
        def session(self):
            return FakeSession()

    monkeypatch.setattr(asr_runtime_module, "_get_cached_gigaam_model", lambda _model_name: FakeModel())

    result = asr_runtime_module.run_gigaam_transcription(
        np.ones(16_000, dtype=np.float64),
        "handy-computer/gigaam-v3-e2e-rnnt-gguf",
        "en",
    )

    assert captured["audio"].dtype == np.float32
    assert captured["audio"].flags.c_contiguous is True
    assert captured["kwargs"] == {"language": None, "timestamps": "auto"}
    assert result == {
        "text": "Привет, мир!",
        "language": "ru",
        "segments": [{"text": "Привет, мир!", "start": 0.1, "end": 0.9, "tokens": 3}],
        "total_tokens": 3,
    }


def test_run_gigaam_transcription_splits_long_audio_without_losing_tail(monkeypatch):
    """Запись длиннее лимита GigaAM разбивается, а все части попадают в ответ."""
    chunks = []

    class FakeSession:
        limits = SimpleNamespace(effective_max_audio_ms=25_000)

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def run(self, audio, **_kwargs):
            chunks.append(audio.copy())
            index = len(chunks)
            return SimpleNamespace(text=f"часть {index}", segments=(), tokens=())

    class FakeModel:
        def session(self):
            return FakeSession()

    monkeypatch.setattr(asr_runtime_module, "_get_cached_gigaam_model", lambda _model_name: FakeModel())
    audio = np.arange(400_123, dtype=np.float32)

    result = asr_runtime_module.run_gigaam_transcription(audio, "handy-computer/gigaam-v3-e2e-rnnt-gguf", "ru")

    assert [len(chunk) for chunk in chunks] == [400_000, 123]
    np.testing.assert_array_equal(np.concatenate(chunks), audio)
    assert result["text"] == "часть 1 часть 2"
    assert result["segments"][1]["start"] == 25.0
    assert result["segments"][1]["end"] == 25.0 + 123 / 16_000


def test_gigaam_model_is_loaded_once(monkeypatch, tmp_path):
    """GGUF-модель должна оставаться загруженной между диктовками."""
    model_path = tmp_path / "gigaam-v3-e2e-rnnt-F16.gguf"
    model_path.touch()
    loaded_models = []
    fake_model = object()

    def fake_load_model(path):
        loaded_models.append(path)
        return fake_model

    monkeypatch.setattr(asr_runtime_module, "_resolve_gigaam_model_path", lambda _model_name: model_path)
    monkeypatch.setattr(asr_runtime_module, "_load_gigaam_model", fake_load_model)
    monkeypatch.setattr(asr_runtime_module, "_GIGAAM_MODEL_CACHE", {})

    first = asr_runtime_module._get_cached_gigaam_model("gigaam-v3-e2e-rnnt-F16.gguf")
    second = asr_runtime_module._get_cached_gigaam_model("gigaam-v3-e2e-rnnt-F16.gguf")

    assert first is fake_model
    assert second is fake_model
    assert loaded_models == [model_path]
