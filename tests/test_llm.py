"""Тесты управления памятью и кэшированием в LLMProcessor."""

import sys
from types import SimpleNamespace

import llm


class FakeTokenizer:
    """Простой токенизатор для тестов LLMProcessor."""

    def apply_chat_template(self, messages, tokenize=False, add_generation_prompt=True, enable_thinking=False):
        """Формирует простой строковый prompt из сообщений."""
        del tokenize, add_generation_prompt, enable_thinking
        return " | ".join(message["content"] for message in messages)

    def encode(self, text):
        """Возвращает псевдотокены как список слов."""
        return text.split()


def test_fast_mode_reuses_loaded_model(monkeypatch):
    """Быстрый режим должен повторно использовать уже загруженную модель."""
    load_calls = []
    gc_calls = []

    def fake_load(model_name):
        load_calls.append(model_name)
        return object(), FakeTokenizer()

    monkeypatch.setattr(llm.gc, "collect", lambda: gc_calls.append(True))
    monkeypatch.setitem(sys.modules, "mlx_lm", SimpleNamespace(load=fake_load, generate=lambda *_args, **_kwargs: "готово"))

    processor = llm.LLMProcessor("fake-model")
    processor.set_performance_mode("fast")

    assert processor.process_text("первый", "система") == "готово"
    assert processor.process_text("второй", "система") == "готово"
    assert load_calls == ["fake-model"]
    assert processor._cached_model is not None
    assert gc_calls == []


def test_normal_mode_unloads_model_after_generation(monkeypatch):
    """Обычный режим должен выгружать модель после каждого ответа."""
    load_calls = []
    gc_calls = []

    def fake_load(model_name):
        load_calls.append(model_name)
        return object(), FakeTokenizer()

    monkeypatch.setattr(llm.gc, "collect", lambda: gc_calls.append(True))
    monkeypatch.setitem(sys.modules, "mlx_lm", SimpleNamespace(load=fake_load, generate=lambda *_args, **_kwargs: "готово"))

    processor = llm.LLMProcessor("fake-model")

    assert processor.process_text("текст", "система") == "готово"
    assert load_calls == ["fake-model"]
    assert processor._cached_model is None
    assert gc_calls == [True]


def test_strip_think_blocks_removes_reasoning_tags():
    """think-блоки должны полностью вырезаться из ответа."""
    assert llm.strip_think_blocks("<think>скрыто</think>готово") == "готово"


def test_sanitize_llm_response_extracts_final_answer_after_marker():
    """Если модель вывела служебный блок и маркер ответа, должен остаться только итог."""
    raw = (
        "1. Analyze the Request:\n"
        "* Context: пример\n"
        "* Query: пример\n"
        "* Constraints: one sentence\n\n"
        "Final answer: Слышу тебя, напиши ещё раз короче."
    )

    assert llm.sanitize_llm_response(raw) == "Слышу тебя, напиши ещё раз короче."


def test_sanitize_llm_response_hides_structured_response_without_explicit_answer():
    """Structured-ответ без явного маркера финала не должен попадать в UI."""
    raw = (
        "1. Analyze the Request:\n"
        "* Context: фрагмент текста\n"
        "* Query: ты меня слышишь\n"
        "* Constraints: no markdown\n"
        "Слышу тебя, но фраза сбивчивая, повтори спокойнее."
    )

    assert llm.sanitize_llm_response(raw) == ""


def test_process_text_sanitizes_reasoning_response(monkeypatch):
    """process_text должен возвращать итоговый ответ без reasoning-пролога."""

    def fake_load(_model_name):
        return object(), FakeTokenizer()

    def fake_generate(*_args, **_kwargs):
        return "1. Analyze the Request:\n* Context: пример\n* Query: пример\n* Constraints: short answer\n\nОтвет: Готово."

    monkeypatch.setitem(sys.modules, "mlx_lm", SimpleNamespace(load=fake_load, generate=fake_generate))

    processor = llm.LLMProcessor("fake-model")

    assert processor.process_text("текст", "система") == "Готово."


def test_sanitize_llm_response_extracts_russian_draft_section():
    """Русские секции анализа должны схлопываться до содержимого черновика."""
    raw = (
        '1. **Анализ запроса:** Пользователь спрашивает "Кто ты такой?".\n'
        "2. **Определение ответа:** Я — языковая модель.\n"
        "3. **Ограничения:** Одно предложение.\n"
        "4. **Черновик:** Я — ИИ-помощник, который помогает с текстом и вопросами 🙂"
    )

    assert llm.sanitize_llm_response(raw) == "Я — ИИ-помощник, который помогает с текстом и вопросами 🙂"


def test_sanitize_llm_response_keeps_plain_text_answer():
    """Обычный однострочный ответ без служебной структуры должен сохраняться."""
    raw = "Привет! Всё готово 🙂"

    assert llm.sanitize_llm_response(raw) == "Привет! Всё готово 🙂"


def test_sanitize_llm_response_truncates_to_limit():
    """Слишком длинный ответ должен аккуратно обрезаться до лимита символов."""
    raw = "Очень длинный ответ " * 20

    result = llm.sanitize_llm_response(raw)

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

    assert llm.sanitize_llm_response(raw) == ""


def test_process_text_returns_empty_for_truncated_reasoning(monkeypatch):
    """process_text должен отдавать пустой результат, если модель вернула только reasoning-обрывок."""

    def fake_load(_model_name):
        return object(), FakeTokenizer()

    def fake_generate(*_args, **_kwargs):
        return (
            "1.  **Analyze the Request:**\n"
            "    *   **Context:** пример\n"
            "    *   **Question:** кто ты такой\n"
            "    *   **Constraints:** no analysis\n\n"
            "2.  **Drafting the Content:**\n"
            "    *   I"
        )

    monkeypatch.setitem(sys.modules, "mlx_lm", SimpleNamespace(load=fake_load, generate=fake_generate))

    processor = llm.LLMProcessor("fake-model")

    assert processor.process_text("текст", "система") == ""


def test_process_text_logs_raw_model_response(monkeypatch, caplog):
    """Сырой ответ модели должен явно попадать в лог даже если UI его скрывает."""

    def fake_load(_model_name):
        return object(), FakeTokenizer()

    raw_response = "1. **Анализ запроса:** Пользователь просит рассказать анекдот.\n2. **Анализ ограничений:** Одно предложение."

    def fake_generate(*_args, **_kwargs):
        return raw_response

    monkeypatch.setitem(sys.modules, "mlx_lm", SimpleNamespace(load=fake_load, generate=fake_generate))

    processor = llm.LLMProcessor("fake-model")

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

    assert llm.sanitize_llm_response(raw) == ""


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

    assert llm.sanitize_llm_response(raw) == ""
