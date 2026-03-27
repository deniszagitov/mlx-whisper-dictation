"""Обработка текста через LLM-модели приложения Dictator.

Содержит LLMProcessor для генерации ответов через MLX LLM
с загрузкой модели по требованию и выгрузкой после использования.
"""

import gc
import logging
import re

from config import DEFAULT_LLM_MODEL_NAME, DOWNLOAD_COMPLETE_PCT, LLM_MAX_TOKENS

LOGGER = logging.getLogger(__name__)

_THINK_BLOCK_RE = re.compile(r"<think>.*?</think>", re.DOTALL)
_THINK_TAIL_RE = re.compile(r"^.*?</think>", re.DOTALL)
_FINAL_ANSWER_MARKER_RE = re.compile(r"(?:^|\n)\s*(?:final answer|answer|ответ)\s*[:：]\s*", re.IGNORECASE)
_REASONING_HEADER_RE = re.compile(
    r"^\s*(?:\d+\.\s*)?(?:\*\*)?"
    r"(?:analyze the request|analysis|reasoning|thought process|"
    r"анализ запроса|разбор запроса|рассуждение|рассуждения)"
    r"(?:\*\*)?\s*:?[ \t]*$",
    re.IGNORECASE,
)
_REASONING_FIELD_RE = re.compile(
    r"^\s*(?:[*-]\s*)?(?:\*\*)?(?:context|query|constraints|контекст|запрос|ограничения)(?:\*\*)?\s*:",
    re.IGNORECASE,
)
_MIN_REASONING_FIELDS = 2
PERFORMANCE_MODE_NORMAL = "normal"
PERFORMANCE_MODE_FAST = "fast"


def strip_think_blocks(text):
    """Удаляет блоки рассуждений из ответа LLM.

    Некоторые модели (Qwen, DeepSeek) генерируют блок рассуждений
    внутри тегов <think>...</think>. Обрабатывает три случая:
    - Полный блок: <think>рассуждения</think>ответ
    - Без открывающего тега: рассуждения</think>ответ
    - Незакрытый блок: <think>рассуждения (без </think>)

    Args:
        text: Строка с ответом модели.

    Returns:
        Текст без блоков рассуждений.
    """
    cleaned = _THINK_BLOCK_RE.sub("", text)
    cleaned = _THINK_TAIL_RE.sub("", cleaned)
    if "<think>" in cleaned:
        cleaned = ""
    return cleaned.strip()


def _extract_final_answer_segment(text):
    """Возвращает хвост после последнего маркера финального ответа."""
    matches = list(_FINAL_ANSWER_MARKER_RE.finditer(text))
    if not matches:
        return ""
    return text[matches[-1].end() :].strip()


def _looks_like_reasoning_response(text):
    """Определяет ответы, где модель вывела служебные шаги вместо результата."""
    if not text:
        return False

    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if not lines:
        return False

    if _REASONING_HEADER_RE.match(lines[0]):
        return True

    reasoning_fields = sum(1 for line in lines if _REASONING_FIELD_RE.match(line))
    return reasoning_fields >= _MIN_REASONING_FIELDS


def _extract_last_content_line(text):
    """Ищет последнюю содержательную строку, пропуская служебную разметку."""
    for raw_line in reversed(text.splitlines()):
        line = raw_line.strip()
        if not line:
            continue
        if _REASONING_HEADER_RE.match(line) or _REASONING_FIELD_RE.match(line):
            continue
        if re.match(r"^\s*(?:[*-]|\d+\.)\s+", line):
            continue
        return line
    return ""


def sanitize_llm_response(text):
    """Очищает ответ модели от рассуждений и служебных секций."""
    cleaned = strip_think_blocks(text)
    if not cleaned:
        return ""

    final_segment = _extract_final_answer_segment(cleaned)
    if final_segment:
        return final_segment

    if _looks_like_reasoning_response(cleaned):
        last_line = _extract_last_content_line(cleaned)
        if last_line:
            return last_line

    return cleaned.strip()


class LLMProcessor:
    """Обрабатывает текст через LLM-модель с загрузкой по требованию.

    Загружает модель при первом вызове, генерирует ответ и выгружает
    модель из памяти для экономии ресурсов.

    Attributes:
        model_name: Имя или путь к модели MLX LLM.
        download_progress_callback: Callback для обновления UI прогресса загрузки.
    """

    def __init__(self, model_name=DEFAULT_LLM_MODEL_NAME):
        """Создаёт LLM-процессор.

        Args:
            model_name: Имя модели Hugging Face или локальный путь.
        """
        self.model_name = model_name
        self.last_token_usage = 0
        self.download_progress_callback = None
        self.performance_mode = PERFORMANCE_MODE_NORMAL
        self._cached_model = None
        self._cached_tokenizer = None

    def set_performance_mode(self, performance_mode):
        """Переключает стратегию управления памятью для LLM."""
        normalized_mode = performance_mode if performance_mode == PERFORMANCE_MODE_FAST else PERFORMANCE_MODE_NORMAL
        self.performance_mode = normalized_mode
        if normalized_mode != PERFORMANCE_MODE_FAST:
            self._unload_cached_model()

    def _load_runtime_objects(self):
        """Возвращает модель и токенизатор, используя кэш в быстром режиме."""
        from mlx_lm import load  # noqa: PLC0415

        if self._cached_model is not None and self._cached_tokenizer is not None:
            LOGGER.info("🤖 Использую уже загруженную LLM-модель")
            return self._cached_model, self._cached_tokenizer

        LOGGER.info("🤖 Загрузка LLM: %s", self.model_name)
        model, tokenizer = load(self.model_name)
        self._cached_model = model
        self._cached_tokenizer = tokenizer
        return model, tokenizer

    def _unload_cached_model(self):
        """Выгружает LLM-модель и токенизатор из памяти."""
        model = self._cached_model
        tokenizer = self._cached_tokenizer
        self._cached_model = None
        self._cached_tokenizer = None
        if model is None and tokenizer is None:
            return

        del model
        del tokenizer
        gc.collect()
        LOGGER.info("🤖 LLM выгружена из памяти")

    def is_model_cached(self):
        """Проверяет, скачана ли модель в кэш Hugging Face.

        Returns:
            True, если модель уже доступна локально.
        """
        try:
            from huggingface_hub import try_to_load_from_cache  # noqa: PLC0415

            result = try_to_load_from_cache(self.model_name, "config.json")
            return result is not None and not isinstance(result, type)
        except Exception:
            return False

    def ensure_model_downloaded(self):
        """Скачивает модель в стандартный кэш HuggingFace с отслеживанием прогресса.

        Использует ``~/.cache/huggingface/hub/`` — общая директория с Ollama,
        transformers и другими библиотеками. Если модель уже скачана,
        повторная загрузка не происходит.
        """
        from huggingface_hub import snapshot_download  # noqa: PLC0415

        callback = self.download_progress_callback

        class _ProgressTqdm:
            """Обёртка tqdm, которая пробрасывает прогресс в callback."""

            def __init__(self, *args, **kwargs):
                self.total = kwargs.get("total", 0)
                self.desc = str(kwargs.get("desc", ""))
                self.n = 0

            def update(self, n=1):
                """Обновляет позицию прогресса."""
                self.n += n
                if callback is not None and self.total and self.total > 0:
                    pct = min(self.n / self.total * DOWNLOAD_COMPLETE_PCT, DOWNLOAD_COMPLETE_PCT)
                    callback(self.desc, pct, self.total)

            def close(self):
                """Вызывается при завершении файла."""

            def __enter__(self):
                """Context manager вход."""
                return self

            def __exit__(self, *args):
                """Context manager выход."""

        LOGGER.info("📥 Начинаю загрузку модели: %s", self.model_name)
        if callback is not None:
            callback("Подготовка…", 0, 0)

        snapshot_download(
            self.model_name,
            tqdm_class=_ProgressTqdm,
        )

        LOGGER.info("✅ Модель загружена: %s", self.model_name)
        if callback is not None:
            callback("", DOWNLOAD_COMPLETE_PCT, 0)

    def _count_tokens(self, tokenizer, text):
        """Возвращает количество токенов для текста через tokenizer.encode."""
        if not text:
            return 0

        encoded = tokenizer.encode(text)
        if isinstance(encoded, dict):
            input_ids = encoded.get("input_ids")
            return len(input_ids) if input_ids is not None else 0
        if hasattr(encoded, "ids"):
            return len(encoded.ids)
        if hasattr(encoded, "input_ids"):
            return len(encoded.input_ids)
        if isinstance(encoded, (list, tuple)):
            return len(encoded)
        return 0

    def process_text(self, text, system_prompt, *, context=None):
        """Отправляет текст в LLM и возвращает ответ.

        Загружает модель, генерирует ответ и выгружает модель из памяти.

        Args:
            text: Пользовательский текст (транскрипция).
            system_prompt: Системный промпт для модели.
            context: Необязательный контекст из буфера обмена.

        Returns:
            Строка с ответом модели.

        Raises:
            Exception: Если модель не удалось загрузить или произошла ошибка генерации.
        """
        from mlx_lm import generate  # noqa: PLC0415

        self.last_token_usage = 0
        model, tokenizer = self._load_runtime_objects()
        try:
            if hasattr(tokenizer, "apply_chat_template"):
                user_content = f"Контекст из буфера обмена:\n{context}\n\nЗапрос:\n{text}" if context else text
                messages = [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_content},
                ]
                try:
                    prompt = tokenizer.apply_chat_template(
                        messages,
                        tokenize=False,
                        add_generation_prompt=True,
                        enable_thinking=False,
                    )
                except TypeError:
                    prompt = tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
            elif context:
                prompt = f"{system_prompt}\n\nКонтекст:\n{context}\n\nПользователь: {text}\nОтвет:"
            else:
                prompt = f"{system_prompt}\n\nПользователь: {text}\nОтвет:"

            prompt_tokens = self._count_tokens(tokenizer, prompt)
            LOGGER.info("🤖 Генерация ответа LLM (max_tokens=%d)", LLM_MAX_TOKENS)
            response = generate(model, tokenizer, prompt=prompt, max_tokens=LLM_MAX_TOKENS)
            response = sanitize_llm_response(response)
            response_tokens = self._count_tokens(tokenizer, response)
            self.last_token_usage = prompt_tokens + response_tokens
            LOGGER.info("🤖 LLM ответил, длина=%d символов", len(response))
            return response.strip()
        finally:
            if self.performance_mode == PERFORMANCE_MODE_FAST:
                LOGGER.info("🤖 LLM остаётся в памяти для быстрого режима")
            else:
                self._unload_cached_model()
