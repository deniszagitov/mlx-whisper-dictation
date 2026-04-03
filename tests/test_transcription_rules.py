"""Юнит-тесты object-based правил постобработки транскрипции."""

from src.domain.transcription import (
    CapitalizeFirstLetterRule,
    RemoveTrailingPeriodForSingleSentenceRule,
    TranscriptionPostprocessor,
)


def test_capitalize_first_letter_skips_leading_spaces_and_quotes() -> None:
    """Правило заглавной буквы должно находить первый буквенный символ дальше префиксов."""
    rule = CapitalizeFirstLetterRule()

    assert rule.apply('   "привет"') == '   "Привет"'


def test_capitalize_first_letter_keeps_text_without_letters() -> None:
    """Если букв нет, правило не должно менять строку."""
    rule = CapitalizeFirstLetterRule()

    assert rule.apply(" 123...") == " 123..."


def test_remove_trailing_period_for_single_sentence_basic_case() -> None:
    """Обычная финальная точка у одного предложения должна удаляться."""
    rule = RemoveTrailingPeriodForSingleSentenceRule()

    assert rule.apply("Привет.") == "Привет"


def test_remove_trailing_period_preserves_trailing_whitespace() -> None:
    """После удаления точки завершающие пробелы должны сохраняться."""
    rule = RemoveTrailingPeriodForSingleSentenceRule()

    assert rule.apply("Привет.  ") == "Привет  "


def test_remove_trailing_period_keeps_multiple_sentences() -> None:
    """Если предложений больше одного, финальная точка должна остаться."""
    rule = RemoveTrailingPeriodForSingleSentenceRule()

    assert rule.apply("Привет. Как дела.") == "Привет. Как дела."


def test_remove_trailing_period_keeps_ellipsis() -> None:
    """Многоточие не должно восприниматься как финальная одиночная точка."""
    rule = RemoveTrailingPeriodForSingleSentenceRule()

    assert rule.apply("Привет...") == "Привет..."


def test_remove_trailing_period_handles_closing_quotes() -> None:
    """Точка перед закрывающей кавычкой должна убираться корректно."""
    rule = RemoveTrailingPeriodForSingleSentenceRule()

    assert rule.apply('"Привет."') == '"Привет"'


def test_remove_trailing_period_handles_closing_parenthesis() -> None:
    """Точка перед закрывающей скобкой должна убираться корректно."""
    rule = RemoveTrailingPeriodForSingleSentenceRule()

    assert rule.apply("(Привет.)") == "(Привет)"


def test_remove_trailing_period_keeps_abbreviation_like_text() -> None:
    """Аббревиатуры с несколькими точками не должны терять финальную точку."""
    rule = RemoveTrailingPeriodForSingleSentenceRule()

    assert rule.apply("т.д.") == "т.д."


def test_postprocessor_applies_rules_in_order() -> None:
    """Пайплайн правил должен применять преобразования последовательно."""
    postprocessor = TranscriptionPostprocessor(
        rules=(
            CapitalizeFirstLetterRule(),
            RemoveTrailingPeriodForSingleSentenceRule(),
        )
    )

    assert postprocessor.apply("привет.") == "Привет"
