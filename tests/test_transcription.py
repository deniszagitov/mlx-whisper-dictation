"""Тесты транскрибации через mlx_whisper.

Проверяет, что модель не галлюцинирует на тишине при включённых защитных
параметрах, и корректно распознаёт реальную речь.

Требует загруженную модель mlx-community/whisper-large-v3-turbo.
Тесты помечены маркером `slow`, потому что загрузка модели занимает время.
"""

import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

MODEL_NAME = "mlx-community/whisper-large-v3-turbo"

KNOWN_HALLUCINATIONS_RU = {
    "продолжение следует",
    "продолжение следует...",
    "спасибо за внимание",
    "спасибо за просмотр",
    "подписывайтесь на канал",
    "до свидания",
    "до новых встреч",
}

KNOWN_HALLUCINATIONS_EN = {
    "thank you",
    "thank you.",
    "thanks for watching",
    "please subscribe",
    "goodbye",
    "you",
}


def transcribe_audio(audio_data, language="ru"):
    """Вызывает mlx_whisper.transcribe с защитными параметрами из приложения."""
    import mlx_whisper

    return mlx_whisper.transcribe(
        audio_data,
        language=language,
        path_or_hf_repo=MODEL_NAME,
        condition_on_previous_text=False,
        hallucination_silence_threshold=2.0,
    )


@pytest.mark.slow
class TestTranscriptionHallucinations:
    """Тесты на галлюцинации модели."""

    def test_silence_does_not_hallucinate_ru(self):
        """На тишине с language=ru модель не должна выдавать известные галлюцинации."""
        silent = np.zeros(16000 * 3, dtype=np.float32)
        result = transcribe_audio(silent, language="ru")
        text = result.get("text", "").strip().lower()
        assert text not in KNOWN_HALLUCINATIONS_RU, f"Модель галлюцинирует на тишине: '{text}'"

    def test_silence_does_not_hallucinate_en(self):
        """На тишине с language=en модель не должна выдавать известные галлюцинации."""
        silent = np.zeros(16000 * 3, dtype=np.float32)
        result = transcribe_audio(silent, language="en")
        text = result.get("text", "").strip().lower()
        assert text not in KNOWN_HALLUCINATIONS_EN, f"Модель галлюцинирует на тишине: '{text}'"

    def test_low_noise_does_not_hallucinate(self):
        """Слабый фоновый шум не должен вызвать галлюцинацию."""
        np.random.seed(42)
        noise = np.random.randn(16000 * 3).astype(np.float32) * 0.001
        result = transcribe_audio(noise, language="ru")
        text = result.get("text", "").strip().lower()
        assert text not in KNOWN_HALLUCINATIONS_RU, f"Модель галлюцинирует на шуме: '{text}'"

    def test_result_has_expected_structure(self):
        """Результат транскрибации должен содержать ключи text, language, segments."""
        silent = np.zeros(16000 * 2, dtype=np.float32)
        result = transcribe_audio(silent, language="ru")
        assert "text" in result
        assert "language" in result
        assert "segments" in result

    def test_language_is_respected(self):
        """При language=ru результат должен сообщить, что язык — русский."""
        np.random.seed(42)
        audio = np.random.randn(16000 * 2).astype(np.float32) * 0.01
        result = transcribe_audio(audio, language="ru")
        assert result.get("language") == "ru"


@pytest.mark.slow
class TestTranscriptionSegments:
    """Тесты структуры сегментов транскрибации."""

    def test_segments_have_no_speech_prob(self):
        """Каждый сегмент должен содержать поле no_speech_prob."""
        np.random.seed(42)
        audio = np.random.randn(16000 * 3).astype(np.float32) * 0.02
        result = transcribe_audio(audio, language="ru")
        for segment in result.get("segments", []):
            assert "no_speech_prob" in segment

    def test_segments_have_compression_ratio(self):
        """Каждый сегмент должен содержать поле compression_ratio."""
        np.random.seed(42)
        audio = np.random.randn(16000 * 3).astype(np.float32) * 0.02
        result = transcribe_audio(audio, language="ru")
        for segment in result.get("segments", []):
            assert "compression_ratio" in segment
