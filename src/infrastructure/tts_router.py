"""Выбор локального TTS backend-а для reader Speaker."""

from __future__ import annotations

from typing import TYPE_CHECKING

from ..domain.reader_constants import TTS_ENGINE_MLX

if TYPE_CHECKING:
    from ..domain.reader_types import TTSConfig, TTSPort, TTSVoice


class ReaderTTSRouter:
    """Маршрутизирует TTS между Apple AVSpeech и MLX TTS."""

    def __init__(self, *, apple_speaker: TTSPort, mlx_speaker: TTSPort) -> None:
        self._apple_speaker = apple_speaker
        self._mlx_speaker = mlx_speaker

    def speak(self, text: str, config: TTSConfig) -> None:
        """Запускает выбранный TTS backend."""
        self._speaker_for_config(config).speak(text, config)

    def stop(self) -> None:
        """Останавливает оба backend-а, чтобы повторный хоткей был надёжным."""
        self._apple_speaker.stop()
        self._mlx_speaker.stop()

    def is_speaking(self) -> bool:
        """Сообщает, воспроизводит ли речь любой backend."""
        return self._apple_speaker.is_speaking() or self._mlx_speaker.is_speaking()

    def available_voices(self) -> list[TTSVoice]:
        """Возвращает системные Apple-голоса для Apple backend-а."""
        return self._apple_speaker.available_voices()

    def set_keep_model_loaded(self, enabled: bool) -> None:
        """Прокидывает режим удержания модели в backend-и."""
        self._apple_speaker.set_keep_model_loaded(enabled)
        self._mlx_speaker.set_keep_model_loaded(enabled)

    def _speaker_for_config(self, config: TTSConfig) -> TTSPort:
        """Выбирает speaker по TTSConfig."""
        if config.engine == TTS_ENGINE_MLX:
            return self._mlx_speaker
        return self._apple_speaker
