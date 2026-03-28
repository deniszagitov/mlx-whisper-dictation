"""Медленные интеграционные тесты слоя транскрибации через mlx_whisper."""

import numpy as np
import pytest
import src.infrastructure.whisper_runtime as whisper_runtime_module
from src.domain.constants import Config


def make_audio(seconds=1.0, amplitude=0.01):
    """Создает простой тестовый аудиосигнал."""
    samples = int(16000 * seconds)
    return np.full(samples, amplitude, dtype=np.float32)


@pytest.mark.slow
class TestTranscriptionIntegration:
    """Проверяет базовый контракт интеграции с mlx_whisper."""

    def test_run_transcription_returns_expected_shape(self, app_module):
        """Интеграция с моделью должна возвращать словарь с text/language/segments."""
        diagnostics_store = app_module.DiagnosticsStore(enabled=False)
        transcriber = app_module.SpeechTranscriber(
            Config.DEFAULT_MODEL_NAME,
            diagnostics_store=diagnostics_store,
            transcription_runner=whisper_runtime_module.run_whisper_transcription,
        )

        result = transcriber._run_transcription(make_audio(seconds=1.0, amplitude=0.0), "ru")

        assert isinstance(result, dict)
        assert "text" in result
        assert "language" in result
        assert "segments" in result

    def test_run_transcription_accepts_language_override(self, app_module, monkeypatch):
        """Transcriber должен прокидывать language в mlx_whisper без искажений."""
        calls = []
        diagnostics_store = app_module.DiagnosticsStore(enabled=False)
        transcriber = app_module.SpeechTranscriber(
            "dummy-model",
            diagnostics_store=diagnostics_store,
            transcription_runner=whisper_runtime_module.run_whisper_transcription,
        )

        def fake_transcribe(audio_data, **kwargs):
            calls.append(kwargs)
            return {"text": "ok", "language": kwargs["language"], "segments": []}

        monkeypatch.setattr(whisper_runtime_module.mlx_whisper, "transcribe", fake_transcribe)  # type: ignore[attr-defined]

        result = transcriber._run_transcription(make_audio(), "ru")

        assert result["language"] == "ru"
        assert calls[0]["language"] == "ru"
        assert calls[0]["condition_on_previous_text"] is False
        assert calls[0]["hallucination_silence_threshold"] == 2.0
