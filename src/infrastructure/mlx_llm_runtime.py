"""Адаптер LLM gateway для reader-предобработки."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..domain.reader_types import LLMReformatterPort


@dataclass(slots=True)
class MlxLLMReformatter:
    """Тонкая обёртка над существующим LLM gateway приложения."""

    gateway: LLMReformatterPort

    @property
    def last_token_usage(self) -> int:
        """Возвращает число токенов последнего LLM-вызова."""
        return self.gateway.last_token_usage

    def is_model_cached(self) -> bool:
        """Проверяет, доступна ли текущая LLM-модель локально."""
        return self.gateway.is_model_cached()

    def process_text(
        self,
        text: str,
        system_prompt: str,
        *,
        context: str | None = None,
        max_tokens: int | None = None,
    ) -> str:
        """Делегирует предобработку в общий MLX LLM runtime."""
        return self.gateway.process_text(text, system_prompt, context=context, max_tokens=max_tokens)
