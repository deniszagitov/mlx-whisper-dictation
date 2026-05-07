"""Тесты предобработки текста reader-модуля."""

from src.domain.reader_constants import READER_CLIPBOARD_CHAR_LIMIT
from src.domain.reader_types import OutputMode, TTSConfig
from src.use_cases.preprocess_text import PreprocessTextUseCase, cleanup_rsvp_text, normalize_tts_text, prepare_reader_source_text


class FakeLLM:
    """Фейковая LLM для reader-предобработки."""

    def __init__(self, response="готовый текст", *, cached=True, error=None):
        self.response = response
        self.cached = cached
        self.error = error
        self.calls = []
        self.last_token_usage = 0

    def is_model_cached(self):
        return self.cached

    def process_text(self, text, system_prompt, *, context=None, max_tokens=None):
        self.calls.append((text, system_prompt, context, max_tokens))
        if self.error is not None:
            raise self.error
        return self.response


def test_cleanup_rsvp_text_removes_common_preamble_and_tail():
    text = "Конечно, давай разберём. Главная мысль. Если есть ещё вопросы, спрашивай."

    assert cleanup_rsvp_text(text) == "Главная мысль"


def test_normalize_tts_text_removes_markdown_code_urls_and_expands_known_abbreviations():
    raw = "# Заголовок\n- **API** доступен по www.example.test\n```python\nprint(1)\n```"

    result = normalize_tts_text(raw)

    assert "#" not in result
    assert "**" not in result
    assert "эй-пи-ай" in result
    assert "ссылка" in result
    assert "дальше блок кода" in result


def test_prepare_reader_source_text_truncates_boundary_length():
    raw = "а" * (READER_CLIPBOARD_CHAR_LIMIT + 5)

    source = prepare_reader_source_text(raw)

    assert source.truncated is True
    assert source.source_char_count == READER_CLIPBOARD_CHAR_LIMIT + 5
    assert len(source.text) == READER_CLIPBOARD_CHAR_LIMIT


def test_preprocess_uses_llm_for_rsvp_and_applies_local_cleanup():
    llm = FakeLLM("Конечно, важная мысль. Надеюсь, помог.")
    use_case = PreprocessTextUseCase(llm)

    result = use_case.execute("сырой текст", OutputMode.RSVP, enabled=True)

    assert result.text == "важная мысль"
    assert result.used_fallback is False
    assert llm.calls
    assert "RSVP" in llm.calls[0][1]


def test_preprocess_uses_raw_text_when_llm_fails():
    llm = FakeLLM(error=RuntimeError("boom"))
    use_case = PreprocessTextUseCase(llm)

    result = use_case.execute("**API**", OutputMode.TTS, enabled=True, tts_config=TTSConfig())

    assert result.text == "эй-пи-ай"
    assert result.used_fallback is True


def test_tts_preprocess_limits_large_audio_by_config():
    words = " ".join(f"слово{i}" for i in range(600))
    llm = FakeLLM(words)
    use_case = PreprocessTextUseCase(llm)

    result = use_case.execute(
        words,
        OutputMode.TTS,
        enabled=True,
        tts_config=TTSConfig(rate_multiplier=1.5, max_minutes=2),
    )

    assert len(result.text.split()) <= 510
