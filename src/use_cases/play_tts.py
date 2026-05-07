"""Use case запуска ускоренного TTS из буфера обмена."""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import TYPE_CHECKING

from ..domain.reader_types import OutputMode, ReaderClipboardPort, TTSConfig, TTSPort
from .reader_source import read_reader_source

if TYPE_CHECKING:
    from .preprocess_text import PreprocessTextUseCase

LOGGER = logging.getLogger(__name__)

Notify = Callable[[str, str], None]


class PlayTTSUseCase:
    """Оркестрирует сценарий буфер обмена → LLM → локальное озвучивание."""

    def __init__(
        self,
        *,
        clipboard: ReaderClipboardPort,
        preprocessor: PreprocessTextUseCase,
        speaker: TTSPort,
        notify: Notify,
    ) -> None:
        self.clipboard = clipboard
        self.preprocessor = preprocessor
        self.speaker = speaker
        self.notify = notify

    def toggle(self, config: TTSConfig, *, preprocess_enabled: bool) -> None:
        """Запускает TTS или останавливает воспроизведение повторным хоткеем."""
        if self.speaker.is_speaking():
            LOGGER.info("🔈 TTS уже воспроизводится, останавливаю")
            self.speaker.stop()
            return
        self.play(config, preprocess_enabled=preprocess_enabled)

    def play(self, config: TTSConfig, *, preprocess_enabled: bool) -> None:
        """Запускает полный TTS-сценарий для текущего текста в буфере."""
        source = read_reader_source(self.clipboard, self.notify)
        if source is None:
            return

        processed = self.preprocessor.execute(
            source.text,
            OutputMode.TTS,
            enabled=preprocess_enabled,
            tts_config=config,
        )
        if not processed.text.strip():
            self.notify("MLX Whisper Dictation", "Буфер пуст.")
            return

        LOGGER.info(
            "🔈 Запускаю TTS: chars=%d, backend=%s, rate=%.2f, voice=%s, fallback=%s",
            len(processed.text),
            config.engine,
            config.rate_multiplier,
            config.voice_id or "auto",
            processed.used_fallback,
        )
        self.speaker.speak(processed.text, config)

    def stop(self) -> None:
        """Останавливает TTS, если оно активно."""
        if self.speaker.is_speaking():
            self.speaker.stop()
