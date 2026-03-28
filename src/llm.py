"""Обработка текста через LLM-модели приложения Dictator.

Содержит LLMProcessor для генерации ответов через MLX LLM
с загрузкой модели по требованию и выгрузкой после использования.
"""

import gc
import logging
import re

from .config import Config

LOGGER = logging.getLogger(__name__)

_THINK_BLOCK_RE = re.compile(r"<think>.*?</think>", re.DOTALL)
_THINK_TAIL_RE = re.compile(r"^.*?</think>", re.DOTALL)
_FINAL_ANSWER_MARKER_RE = re.compile(r"(?:^|\n)\s*(?:final answer|answer|ответ)\s*[:：]\s*", re.IGNORECASE)
_SECTION_LINE_RE = re.compile(
    r"^\s*(?:\d+\.\s*)?(?:[*-]\s*)?(?P<label>[^:\n]{1,80}?)\s*[:：]\s*(?P<value>.+?)\s*$",
    re.IGNORECASE,
)
_ANSWER_SECTION_LABELS = frozenset(
    {
        "draft",
        "final answer",
        "answer",
        "response",
        "черновик",
        "определение ответа",
        "ответ",
    }
)
_STRUCTURED_PREFIX_RE = re.compile(r"^\s*(?:\d+\.|[*#>-]|[-*]\s)")
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


def _strip_markdown_emphasis(text):
    """Убирает markdown-обрамление, мешающее распознаванию служебных секций."""
    return text.replace("**", "").replace("__", "")


def _extract_answer_section(text):
    """Достаёт payload из строк вида «Черновик: ...» или «Ответ: ...»."""
    candidate = ""
    for raw_line in text.splitlines():
        match = _SECTION_LINE_RE.match(_strip_markdown_emphasis(raw_line.strip()))
        if not match:
            continue
        label = match.group("label").strip().casefold()
        value = match.group("value").strip()
        if label in _ANSWER_SECTION_LABELS and value:
            candidate = value
    return candidate


def _is_answer_section_label(label):
    """Определяет, что метка секции содержит финальный ответ."""
    return label.strip().casefold() in _ANSWER_SECTION_LABELS


def _is_plain_text_response(text):
    """Пропускает в UI только простой финальный текст без структурных маркеров."""
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if not lines:
        return False

    for line in lines:
        normalized = _strip_markdown_emphasis(line)
        if _STRUCTURED_PREFIX_RE.match(normalized):
            return False
        section_match = _SECTION_LINE_RE.match(normalized)
        if section_match and not _is_answer_section_label(section_match.group("label")):
            return False

    return True


def _normalize_response_whitespace(text):
    """Сводит ответ к одной аккуратной строке без лишних пробелов."""
    collapsed = re.sub(r"\s+", " ", text).strip()
    collapsed = re.sub(r"^(?:\*\*|__|[*#>-]\s*)+", "", collapsed)
    collapsed = re.sub(r"(?:\*\*|__)+$", "", collapsed)
    return collapsed.strip("'\" ")


def _truncate_response(text, limit=Config.LLM_RESPONSE_CHAR_LIMIT):
    """Обрезает ответ до лимита, стараясь сохранить целое предложение."""
    if len(text) <= limit:
        return text

    truncated = text[: limit - 1].rstrip(" ,;:-")
    sentence_break = max(truncated.rfind(symbol) for symbol in ".!?…")
    if sentence_break >= max(limit // 2, 40):
        return truncated[: sentence_break + 1].strip()

    word_break = truncated.rfind(" ")
    if word_break >= max(limit // 2, 40):
        truncated = truncated[:word_break]

    return truncated.rstrip(" ,;:-") + "…"


def sanitize_llm_response(text):
    """Возвращает только безопасный финальный текст для UI и вставки."""
    cleaned = strip_think_blocks(text)
    if not cleaned:
        return ""

    section_answer = _extract_answer_section(cleaned)
    if section_answer:
        cleaned = section_answer

    final_segment = _extract_final_answer_segment(cleaned)
    if final_segment:
        cleaned = final_segment
    elif not _is_plain_text_response(cleaned):
        LOGGER.warning("⚠️ Скрываю structured-ответ LLM из UI; смотрите сырой лог модели")
        return ""

    cleaned = _normalize_response_whitespace(cleaned)
    return _truncate_response(cleaned)


class LLMProcessor:
    """Обрабатывает текст через LLM-модель с загрузкой по требованию.

    Загружает модель при первом вызове, генерирует ответ и выгружает
    модель из памяти для экономии ресурсов.

    Attributes:
        model_name: Имя или путь к модели MLX LLM.
        download_progress_callback: Callback для обновления UI прогресса загрузки.
    """

    def __init__(self, model_name=Config.DEFAULT_LLM_MODEL_NAME):
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
        from mlx_lm import load

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
            from huggingface_hub import try_to_load_from_cache

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
        from huggingface_hub import snapshot_download

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
                    pct = min(self.n / self.total * Config.DOWNLOAD_COMPLETE_PCT, Config.DOWNLOAD_COMPLETE_PCT)
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
            callback("", Config.DOWNLOAD_COMPLETE_PCT, 0)

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
        from mlx_lm import generate

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
            LOGGER.info("🤖 Генерация ответа LLM (max_tokens=%d)", Config.LLM_MAX_TOKENS)
            raw_response = generate(model, tokenizer, prompt=prompt, max_tokens=Config.LLM_MAX_TOKENS)
            LOGGER.info("🤖 Сырой ответ LLM от модели: длина=%d, текст=%r", len(raw_response), raw_response)
            response = sanitize_llm_response(raw_response)
            response_tokens = self._count_tokens(tokenizer, response)
            self.last_token_usage = prompt_tokens + response_tokens
            LOGGER.info("🤖 Очищенный ответ LLM: длина=%d, текст=%r", len(response), response)
            return response.strip()
        finally:
            if self.performance_mode == PERFORMANCE_MODE_FAST:
                LOGGER.info("🤖 LLM остаётся в памяти для быстрого режима")
            else:
                self._unload_cached_model()
