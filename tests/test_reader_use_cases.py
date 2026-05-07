"""Тесты RSVP/TTS use case-ов reader-модуля."""

from src.domain.reader_types import ClipboardContent, RSVPConfig, TTSConfig
from src.use_cases.play_rsvp import PlayRSVPUseCase
from src.use_cases.play_tts import PlayTTSUseCase
from src.use_cases.preprocess_text import PreprocessTextUseCase


class FakeClipboard:
    """Фейковый read-only буфер."""

    def __init__(self, content):
        self.content = content

    def read_content(self):
        return self.content


class FakeLLM:
    """Фейковая LLM."""

    last_token_usage = 0

    def __init__(self, response="один два три четыре"):
        self.response = response
        self.calls = []

    def is_model_cached(self):
        return True

    def process_text(self, text, system_prompt, *, context=None, max_tokens=None):
        self.calls.append((text, system_prompt, context, max_tokens))
        return self.response


class FakeRSVPDisplay:
    """Фейковый RSVP overlay."""

    def __init__(self):
        self.frames = []
        self.configs = []
        self.closed = 0
        self.running = False

    def show_frames(self, frames, config):
        self.frames = frames
        self.configs.append(config)
        self.running = True

    def close(self):
        self.closed += 1
        self.running = False

    def is_running(self):
        return self.running

    def handle_key(self, _key_name):
        return False


class FakeSpeaker:
    """Фейковый TTS speaker."""

    def __init__(self):
        self.spoken = []
        self.stopped = 0
        self.speaking = False

    def speak(self, text, config):
        self.spoken.append((text, config))
        self.speaking = True

    def stop(self):
        self.stopped += 1
        self.speaking = False

    def is_speaking(self):
        return self.speaking

    def available_voices(self):
        return []

    def set_keep_model_loaded(self, _enabled):
        return None


def test_rsvp_use_case_reads_clipboard_preprocesses_and_shows_frames():
    notifications = []
    display = FakeRSVPDisplay()
    llm = FakeLLM("один два три")
    use_case = PlayRSVPUseCase(
        clipboard=FakeClipboard(ClipboardContent("сырой текст", has_text_type=True)),
        preprocessor=PreprocessTextUseCase(llm),
        display=display,
        notify=lambda title, message: notifications.append((title, message)),
    )

    use_case.play(RSVPConfig(chunk_size=2), preprocess_enabled=True)

    assert [frame.text for frame in display.frames] == ["один два", "три"]
    assert llm.calls
    assert notifications == []


def test_rsvp_repeated_toggle_closes_overlay_without_reading_clipboard():
    display = FakeRSVPDisplay()
    display.running = True
    use_case = PlayRSVPUseCase(
        clipboard=FakeClipboard(ClipboardContent("текст", has_text_type=True)),
        preprocessor=PreprocessTextUseCase(None),
        display=display,
        notify=lambda _title, _message: None,
    )

    use_case.toggle(RSVPConfig(), preprocess_enabled=False)

    assert display.closed == 1


def test_tts_use_case_normalizes_text_and_speaks():
    speaker = FakeSpeaker()
    use_case = PlayTTSUseCase(
        clipboard=FakeClipboard(ClipboardContent("**API**: www.example.test", has_text_type=True)),
        preprocessor=PreprocessTextUseCase(None),
        speaker=speaker,
        notify=lambda _title, _message: None,
    )

    use_case.play(TTSConfig(rate_multiplier=2.5), preprocess_enabled=False)

    assert speaker.spoken
    assert "эй-пи-ай" in speaker.spoken[0][0]
    assert "ссылка" in speaker.spoken[0][0]


def test_tts_repeated_toggle_stops_active_speaker():
    speaker = FakeSpeaker()
    speaker.speaking = True
    use_case = PlayTTSUseCase(
        clipboard=FakeClipboard(ClipboardContent("текст", has_text_type=True)),
        preprocessor=PreprocessTextUseCase(None),
        speaker=speaker,
        notify=lambda _title, _message: None,
    )

    use_case.toggle(TTSConfig(), preprocess_enabled=False)

    assert speaker.stopped == 1


def test_reader_use_case_notifies_empty_and_non_text_clipboard():
    notifications = []
    speaker = FakeSpeaker()
    use_case = PlayTTSUseCase(
        clipboard=FakeClipboard(ClipboardContent(None, has_text_type=False)),
        preprocessor=PreprocessTextUseCase(None),
        speaker=speaker,
        notify=lambda title, message: notifications.append((title, message)),
    )

    use_case.play(TTSConfig(), preprocess_enabled=False)

    assert notifications == [("MLX Whisper Dictation", "В буфере не текст.")]
    assert speaker.spoken == []
