"""Тесты чистой логики и orchestration в LLMProcessor."""

from __future__ import annotations

from typing import TYPE_CHECKING

from src.domain import llm_processing
from src.infrastructure import llm_runtime

if TYPE_CHECKING:
    from collections.abc import Callable


class FakeTokenizer:
    """Простой токенизатор для тестов LLMProcessor."""

    def apply_chat_template(self, messages, tokenize=False, add_generation_prompt=True, enable_thinking=False):
        """Формирует простой строковый prompt из сообщений."""
        del tokenize, add_generation_prompt, enable_thinking
        return " | ".join(message["content"] for message in messages)

    def encode(self, text):
        """Возвращает псевдотокены как список слов."""
        return text.split()


def make_processor(
    *,
    generated_response: str = "готово",
    load_calls: list[str] | None = None,
    cleanup_calls: list[bool] | None = None,
    generation_runner: Callable[[object, FakeTokenizer, str, int], str] | None = None,
) -> llm_runtime.LlmGateway:
    """Создаёт LLMProcessor с подменённым runtime-слоем."""
    actual_load_calls = load_calls if load_calls is not None else []
    actual_cleanup_calls = cleanup_calls if cleanup_calls is not None else []

    def fake_load(model_name: str):
        actual_load_calls.append(model_name)
        return object(), FakeTokenizer()

    def fake_generate(_model: object, _tokenizer: FakeTokenizer, _prompt: str, _max_tokens: int) -> str:
        return generated_response

    def fake_cleanup() -> None:
        actual_cleanup_calls.append(True)

    return llm_runtime.LlmGateway(
        "fake-model",
        runtime_loader=fake_load,
        generation_runner=generation_runner or fake_generate,
        model_cache_checker=lambda _model_name: False,
        model_downloader=lambda _model_name, _callback: None,
        memory_cleanup=fake_cleanup,
    )


def test_fast_mode_reuses_loaded_model():
    """Быстрый режим должен повторно использовать уже загруженную модель."""
    load_calls: list[str] = []
    cleanup_calls: list[bool] = []
    processor = make_processor(load_calls=load_calls, cleanup_calls=cleanup_calls)
    processor.set_performance_mode("fast")

    assert processor.process_text("первый", "система") == "готово"
    assert processor.process_text("второй", "система") == "готово"
    assert load_calls == ["fake-model"]
    assert processor._cached_model is not None
    assert cleanup_calls == []


def test_normal_mode_unloads_model_after_generation():
    """Обычный режим должен выгружать модель после каждого ответа."""
    load_calls: list[str] = []
    cleanup_calls: list[bool] = []
    processor = make_processor(load_calls=load_calls, cleanup_calls=cleanup_calls)

    assert processor.process_text("текст", "система") == "готово"
    assert load_calls == ["fake-model"]
    assert processor._cached_model is None
    assert cleanup_calls == [True]


def test_strip_think_blocks_removes_reasoning_tags():
    """think-блоки должны полностью вырезаться из ответа."""
    assert llm_processing.strip_think_blocks("<think>скрыто</think>готово") == "готово"


def test_sanitize_llm_response_extracts_final_answer_after_marker():
    """Если модель вывела служебный блок и маркер ответа, должен остаться только итог."""
    raw = (
        "1. Analyze the Request:\n"
        "* Context: пример\n"
        "* Query: пример\n"
        "* Constraints: one sentence\n\n"
        "Final answer: Слышу тебя, напиши ещё раз короче."
    )

    assert llm_processing.sanitize_llm_response(raw) == "Слышу тебя, напиши ещё раз короче."


def test_sanitize_llm_response_hides_structured_response_without_explicit_answer():
    """Structured-ответ без явного маркера финала не должен попадать в UI."""
    raw = (
        "1. Analyze the Request:\n"
        "* Context: фрагмент текста\n"
        "* Query: ты меня слышишь\n"
        "* Constraints: no markdown\n"
        "Слышу тебя, но фраза сбивчивая, повтори спокойнее."
    )

    assert llm_processing.sanitize_llm_response(raw) == ""


def test_process_text_sanitizes_reasoning_response():
    """process_text должен возвращать итоговый ответ без reasoning-пролога."""
    processor = make_processor(
        generated_response=(
            "1. Analyze the Request:\n* Context: пример\n* Query: пример\n* Constraints: short answer\n\nОтвет: Готово."
        )
    )

    assert processor.process_text("текст", "система") == "Готово."


def test_sanitize_llm_response_extracts_russian_draft_section():
    """Русские секции анализа должны схлопываться до содержимого черновика."""
    raw = (
        '1. **Анализ запроса:** Пользователь спрашивает "Кто ты такой?".\n'
        "2. **Определение ответа:** Я — языковая модель.\n"
        "3. **Ограничения:** Одно предложение.\n"
        "4. **Черновик:** Я — ИИ-помощник, который помогает с текстом и вопросами 🙂"
    )

    assert llm_processing.sanitize_llm_response(raw) == "Я — ИИ-помощник, который помогает с текстом и вопросами 🙂"


def test_sanitize_llm_response_keeps_plain_text_answer():
    """Обычный однострочный ответ без служебной структуры должен сохраняться."""
    raw = "Привет! Всё готово 🙂"

    assert llm_processing.sanitize_llm_response(raw) == "Привет! Всё готово 🙂"


def test_sanitize_llm_response_truncates_to_limit():
    """Слишком длинный ответ должен аккуратно обрезаться до лимита символов."""
    raw = "Очень длинный ответ " * 20

    result = llm_processing.sanitize_llm_response(raw)

    assert len(result) <= 180
    assert result.endswith("…")


def test_sanitize_llm_response_drops_truncated_reasoning_without_answer():
    """Обрезанный reasoning без финального ответа не должен просачиваться в UI."""
    raw = (
        "1.  **Analyze the Request:**\n"
        '    *   **Context:** "Second text"\n'
        '    *   **Question:** "Tell me, please, who are you?"\n'
        "    *   **Constraints:**\n"
        "        *   One single sentence.\n"
        "        *   No analysis.\n\n"
        "2.  **Drafting the Content:**\n"
        "    *   I"
    )

    assert llm_processing.sanitize_llm_response(raw) == ""


def test_process_text_returns_empty_for_truncated_reasoning():
    """process_text должен отдавать пустой результат, если модель вернула только reasoning-обрывок."""
    processor = make_processor(
        generated_response=(
            "1.  **Analyze the Request:**\n"
            "    *   **Context:** пример\n"
            "    *   **Question:** кто ты такой\n"
            "    *   **Constraints:** no analysis\n\n"
            "2.  **Drafting the Content:**\n"
            "    *   I"
        )
    )

    assert processor.process_text("текст", "система") == ""


def test_process_text_logs_raw_model_response(caplog):
    """Сырой ответ модели должен явно попадать в лог даже если UI его скрывает."""
    raw_response = "1. **Анализ запроса:** Пользователь просит рассказать анекдот.\n2. **Анализ ограничений:** Одно предложение."
    processor = make_processor(generated_response=raw_response)

    with caplog.at_level("INFO"):
        assert processor.process_text("текст", "система") == ""

    assert any(
        "Сырой ответ LLM от модели" in record.message and "Анализ запроса" in record.message and "Анализ ограничений" in record.message
        for record in caplog.records
    )


def test_sanitize_llm_response_drops_markdown_reasoning_block_without_answer():
    """Markdown reasoning с полями Input Text и Task не должен попадать в итоговый ответ."""
    raw = (
        "1.  **Analyze the Request:**\n"
        '    *   **Input Text:** "Здесь размещены русские народные сказки"\n'
        "    *   **Task:** Identify the topic of the text.\n"
        "    *   **Constraints:**\n"
        "        *   One single sentence.\n\n"
        "2."
    )

    assert llm_processing.sanitize_llm_response(raw) == ""


def test_sanitize_llm_response_drops_russian_numbered_reasoning_without_answer():
    """Русский reasoning-список без финального ответа не должен попадать в нотификацию."""
    raw = (
        "1.  **Анализ запроса:** Пользователь просит рассказать анекдот.\n"
        "2.  **Анализ ограничений:**\n"
        "    *   Одно предложение.\n"
        "    *   Максимум 180 символов.\n"
        "    *   Без markdown, списков, нумерации, заголовков.\n"
        "    *   Без анализа, рассуждений, черновика.\n"
        "    *   Plain text, можно 1 эмодзи.\n"
        "3.  **Выбор анекдота:** Нужен короткий, классический. Например, про кота и мышь или про учителя.\n"
        "    *   *Вариант 1:* — А что ты делаешь"
    )

    assert llm_processing.sanitize_llm_response(raw) == ""


def test_should_use_clipboard_context_with_keyword():
    """should_use_clipboard_context должен вернуть True при совпадении ключевого слова и непустом буфере."""
    assert llm_processing.should_use_clipboard_context("переведи это", "Hello world") is True
    assert llm_processing.should_use_clipboard_context("исправь этот текст", "some text") is True
    assert llm_processing.should_use_clipboard_context("перепиши это", "content") is True


def test_should_use_clipboard_context_without_keyword():
    """should_use_clipboard_context должен вернуть False без ключевых слов."""
    assert llm_processing.should_use_clipboard_context("расскажи анекдот", "some clipboard") is False
    assert llm_processing.should_use_clipboard_context("привет", "Hello") is False


def test_should_use_clipboard_context_empty_clipboard():
    """should_use_clipboard_context должен вернуть False при пустом буфере обмена."""
    assert llm_processing.should_use_clipboard_context("переведи это", None) is False
    assert llm_processing.should_use_clipboard_context("переведи это", "") is False
