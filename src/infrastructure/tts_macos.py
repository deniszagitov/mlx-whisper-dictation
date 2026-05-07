"""Локальное TTS-воспроизведение через AVSpeechSynthesizer."""

from __future__ import annotations

import logging
from typing import Any

from ..domain.reader_types import TTSConfig, TTSVoice

LOGGER = logging.getLogger(__name__)


class MacOSTTSController:
    """Обёртка над AVSpeechSynthesizer для ускоренного локального TTS."""

    def __init__(self, synthesizer: Any | None = None, avfoundation: Any | None = None) -> None:
        """Создаёт TTS controller и лениво подключает AVFoundation."""
        if avfoundation is None:
            try:
                import AVFoundation  # noqa: PLC0415
            except ModuleNotFoundError:
                LOGGER.exception("🔈 PyObjC AVFoundation не установлен, TTS будет недоступен")
                self._avfoundation = None
                self._synthesizer = None
                return

            avfoundation = AVFoundation
        self._avfoundation = avfoundation
        self._synthesizer = synthesizer or avfoundation.AVSpeechSynthesizer.alloc().init()

    def available_voices(self) -> list[TTSVoice]:
        """Возвращает системные голоса AVSpeech."""
        if self._avfoundation is None:
            return []
        voice_class = self._avfoundation.AVSpeechSynthesisVoice
        return [
            TTSVoice(
                identifier=str(voice.identifier()),
                name=str(voice.name()),
                language=str(voice.language()),
            )
            for voice in voice_class.speechVoices()
        ]

    def set_keep_model_loaded(self, _enabled: bool) -> None:
        """Игнорирует режим удержания MLX TTS-модели."""
        return None

    def speak(self, text: str, config: TTSConfig) -> None:
        """Начинает озвучивание текста с заданным множителем скорости."""
        if not text.strip():
            return
        if self._avfoundation is None or self._synthesizer is None:
            raise RuntimeError("AVFoundation недоступен. Выполните uv sync --dev и пересоберите Dictator.app.")
        if self.is_speaking():
            self.stop()

        utterance = self._avfoundation.AVSpeechUtterance.speechUtteranceWithString_(text)
        utterance.setRate_(self._speech_rate(config.rate_multiplier))
        voice = self._resolve_voice(config.voice_id)
        if voice is not None:
            utterance.setVoice_(voice)

        LOGGER.info(
            "🔈 AVSpeech запускает озвучивание: chars=%d, rate_multiplier=%.2f, voice=%s",
            len(text),
            config.rate_multiplier,
            config.voice_id or "auto",
        )
        self._synthesizer.speakUtterance_(utterance)

    def stop(self) -> None:
        """Останавливает текущее воспроизведение немедленно."""
        if self._avfoundation is None or self._synthesizer is None:
            return
        boundary = getattr(self._avfoundation, "AVSpeechBoundaryImmediate", 0)
        self._synthesizer.stopSpeakingAtBoundary_(boundary)
        LOGGER.info("🔈 AVSpeech остановлен")

    def is_speaking(self) -> bool:
        """Сообщает, воспроизводится ли сейчас речь."""
        if self._synthesizer is None:
            return False
        return bool(self._synthesizer.isSpeaking())

    def _speech_rate(self, rate_multiplier: float) -> float:
        """Считает безопасную скорость AVSpeechUtterance."""
        avfoundation = self._avfoundation
        if avfoundation is None:
            return 0.5
        default_rate = float(getattr(avfoundation, "AVSpeechUtteranceDefaultSpeechRate", 0.5))
        minimum_rate = float(getattr(avfoundation, "AVSpeechUtteranceMinimumSpeechRate", 0.0))
        maximum_rate = float(getattr(avfoundation, "AVSpeechUtteranceMaximumSpeechRate", 1.0))
        desired_rate = default_rate * max(rate_multiplier, 0.1)
        return min(max(desired_rate, minimum_rate), maximum_rate)

    def _resolve_voice(self, voice_id: str | None) -> Any | None:
        """Выбирает заданный голос или русский системный голос по умолчанию."""
        avfoundation = self._avfoundation
        if avfoundation is None:
            return None
        voice_class = avfoundation.AVSpeechSynthesisVoice
        if voice_id:
            voice = voice_class.voiceWithIdentifier_(voice_id)
            if voice is not None:
                return voice

        voices = list(voice_class.speechVoices())
        russian_voice = next((voice for voice in voices if str(voice.language()).lower().startswith("ru")), None)
        if russian_voice is not None:
            return russian_voice
        english_voice = next((voice for voice in voices if str(voice.language()).lower().startswith("en")), None)
        return english_voice
