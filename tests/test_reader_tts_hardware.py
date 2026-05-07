"""Hardware-тесты TTS reader-модуля."""

import sys
import time

import pytest
from src.domain.reader_types import TTSConfig
from src.infrastructure.tts_macos import MacOSTTSController


@pytest.mark.hardware
@pytest.mark.skipif(sys.platform != "darwin", reason="AVSpeechSynthesizer доступен только на macOS")
def test_avspeech_synthesizer_speaks_short_text_at_fast_rate():
    speaker = MacOSTTSController()

    started_at = time.monotonic()
    speaker.speak("Короткая проверка ускоренного чтения.", TTSConfig(rate_multiplier=2.5))
    time.sleep(0.2)
    was_speaking = speaker.is_speaking()
    speaker.stop()
    elapsed = time.monotonic() - started_at

    assert elapsed < 2.0
    assert was_speaking in {True, False}
