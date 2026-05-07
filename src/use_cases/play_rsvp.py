"""Use case запуска RSVP-чтения текста из буфера обмена."""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import TYPE_CHECKING

from ..domain.reader_constants import estimate_rsvp_duration_seconds
from ..domain.reader_types import OutputMode, ReaderClipboardPort, RSVPConfig, RSVPDisplayPort, build_rsvp_frames
from .reader_source import read_reader_source

if TYPE_CHECKING:
    from .preprocess_text import PreprocessTextUseCase

LOGGER = logging.getLogger(__name__)

Notify = Callable[[str, str], None]


class PlayRSVPUseCase:
    """Оркестрирует сценарий буфер обмена → LLM → RSVP overlay."""

    def __init__(
        self,
        *,
        clipboard: ReaderClipboardPort,
        preprocessor: PreprocessTextUseCase,
        display: RSVPDisplayPort,
        notify: Notify,
    ) -> None:
        self.clipboard = clipboard
        self.preprocessor = preprocessor
        self.display = display
        self.notify = notify

    def toggle(self, config: RSVPConfig, *, preprocess_enabled: bool) -> None:
        """Запускает RSVP или закрывает уже открытый overlay повторным хоткеем."""
        if self.display.is_running():
            LOGGER.info("📖 RSVP уже открыт, закрываю overlay")
            self.display.close()
            return
        self.play(config, preprocess_enabled=preprocess_enabled)

    def play(self, config: RSVPConfig, *, preprocess_enabled: bool) -> None:
        """Запускает полный RSVP-сценарий для текущего текста в буфере."""
        source = read_reader_source(self.clipboard, self.notify)
        if source is None:
            return

        processed = self.preprocessor.execute(
            source.text,
            OutputMode.RSVP,
            enabled=preprocess_enabled,
        )
        frames = build_rsvp_frames(processed.text, config.chunk_size)
        if not frames:
            self.notify("MLX Whisper Dictation", "Буфер пуст.")
            return

        word_count = sum(frame.word_count for frame in frames)
        duration = estimate_rsvp_duration_seconds(word_count, config.wpm)
        LOGGER.info(
            "📖 Запускаю RSVP: words=%d, frames=%d, wpm=%d, chunk=%d, duration=%.1f, fallback=%s",
            word_count,
            len(frames),
            config.wpm,
            config.chunk_size,
            duration,
            processed.used_fallback,
        )
        self.display.show_frames(frames, config)
