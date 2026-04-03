"""Юнит-тесты общего ASR runtime для Whisper и Qwen3-ASR."""

import numpy as np
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
