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


def test_sanitize_llm_response_extracts_last_content_line_without_marker():
    """Если маркера нет, должен остаться последний содержательный ответ."""
    raw = (
        "1. Analyze the Request:\n"
        "* Context: фрагмент текста\n"
        "* Query: ты меня слышишь\n"
        "* Constraints: no markdown\n"
        "Слышу тебя, но фраза сбивчивая, повтори спокойнее."
    )

    assert llm.sanitize_llm_response(raw) == "Слышу тебя, но фраза сбивчивая, повтори спокойнее."


def test_process_text_sanitizes_reasoning_response(monkeypatch):
    """process_text должен возвращать итоговый ответ без reasoning-пролога."""

    def fake_load(_model_name):
        return object(), FakeTokenizer()

    def fake_generate(*_args, **_kwargs):
        return "1. Analyze the Request:\n* Context: пример\n* Query: пример\n* Constraints: short answer\n\nОтвет: Готово."

    monkeypatch.setitem(sys.modules, "mlx_lm", SimpleNamespace(load=fake_load, generate=fake_generate))

    processor = llm.LLMProcessor("fake-model")

    assert processor.process_text("текст", "система") == "Готово."
