"""Runtime-адаптеры для загрузки, генерации и выгрузки MLX LLM."""

from __future__ import annotations

import gc
import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Callable

from ..domain.constants import Config
from ..domain.llm_processing import sanitize_llm_response

LOGGER = logging.getLogger(__name__)

PERFORMANCE_MODE_NORMAL = "normal"
PERFORMANCE_MODE_FAST = "fast"

_VLM_MODEL_INDICATORS = ("gemma-4", "gemma4", "-vlm", "vision")


def _is_vlm_model(model_name: str) -> bool:
    """Определяет, нужен ли mlx_vlm для данной модели."""
    lower = model_name.lower()
    return any(indicator in lower for indicator in _VLM_MODEL_INDICATORS)


def load_llm_runtime_objects(model_name: str) -> tuple[Any, Any]:
    """Загружает MLX LLM-модель и токенизатор по имени модели."""
    from mlx_lm import load

    loaded = load(model_name)
    return loaded[0], loaded[1]


def generate_llm_text(model: Any, tokenizer: Any, prompt: str, max_tokens: int = Config.LLM_MAX_TOKENS) -> str:
    """Генерирует текст через загруженные runtime-объекты MLX LLM."""
    from mlx_lm import generate

    return generate(model, tokenizer, prompt=prompt, max_tokens=max_tokens)


def load_vlm_runtime_objects(model_name: str) -> tuple[Any, Any]:
    """Загружает VLM-модель и процессор по имени модели."""
    from mlx_vlm import load

    model, processor = load(model_name)
    return model, processor


def generate_vlm_text(model: Any, processor: Any, prompt: str, max_tokens: int = Config.LLM_MAX_TOKENS) -> str:
    """Генерирует текст через загруженные runtime-объекты MLX VLM."""
    from mlx_vlm import generate

    return str(generate(model, processor, prompt, max_tokens=max_tokens))


def cleanup_llm_runtime_memory() -> None:
    """Освобождает память после выгрузки LLM-модели."""
    gc.collect()


def is_llm_model_cached(model_name: str) -> bool:
    """Проверяет, скачана ли модель в кэш Hugging Face."""
    try:
        from huggingface_hub import try_to_load_from_cache

        result = try_to_load_from_cache(model_name, "config.json")
        return result is not None and not isinstance(result, type)
    except Exception:
        return False


def ensure_llm_model_downloaded(
    model_name: str,
    progress_callback: Callable[[str, float, int], None] | None = None,
) -> None:
    """Скачивает модель в кэш Hugging Face с пробросом прогресса в callback."""
    from huggingface_hub import snapshot_download

    class _ProgressTqdm:
        """Обёртка tqdm, совместимая с snapshot_download и ensure_lock."""

        _lock = None

        def __init__(self, iterable: Any = None, *args: Any, **kwargs: Any) -> None:
            self._iterable = iterable
            self.total: int | float = int(kwargs.get("total", 0) or 0)
            self.desc = str(kwargs.get("desc", ""))
            self.n = 0

        def __iter__(self) -> Any:
            """Проксирует итерацию и обновляет прогресс по каждому элементу."""
            if self._iterable is None:
                return
            for item in self._iterable:
                yield item
                self.update(1)

        def update(self, n: int = 1) -> None:
            """Увеличивает прогресс и сообщает его во внешний callback."""
            self.n += n
            if progress_callback is not None and self.total and self.total > 0:
                pct = min(self.n / self.total * Config.DOWNLOAD_COMPLETE_PCT, Config.DOWNLOAD_COMPLETE_PCT)
                progress_callback(self.desc, pct, int(self.total))

        def close(self) -> None:
            """Вызывается snapshot_download при завершении шага."""

        def __enter__(self) -> _ProgressTqdm:
            """Context manager вход."""
            return self

        def __exit__(self, *args: object) -> None:
            """Context manager выход."""

        @classmethod
        def get_lock(cls) -> Any:
            """Возвращает lock для tqdm.contrib.concurrent.ensure_lock."""
            import threading

            if cls._lock is None:
                cls._lock = threading.Lock()
            return cls._lock

        @classmethod
        def set_lock(cls, lock: Any) -> None:
            """Устанавливает lock для tqdm.contrib.concurrent.ensure_lock."""
            cls._lock = lock

    if progress_callback is not None:
        progress_callback("Подготовка…", 0, 0)

    snapshot_download(model_name, tqdm_class=_ProgressTqdm)

    if progress_callback is not None:
        progress_callback("", Config.DOWNLOAD_COMPLETE_PCT, 0)


class LlmGateway:
    """Concrete gateway для обработки текста через MLX LLM."""

    def __init__(
        self,
        model_name: str = Config.DEFAULT_LLM_MODEL_NAME,
        runtime_loader: Callable[[str], tuple[Any, Any]] | None = None,
        generation_runner: Callable[[Any, Any, str, int], str] | None = None,
        model_cache_checker: Callable[[str], bool] | None = None,
        model_downloader: Callable[[str, Callable[[str, float, int], None] | None], None] | None = None,
        memory_cleanup: Callable[[], None] | None = None,
        vlm_runtime_loader: Callable[[str], tuple[Any, Any]] | None = None,
        vlm_generation_runner: Callable[[Any, Any, str, int], str] | None = None,
    ) -> None:
        """Создаёт gateway к LLM runtime."""
        self.model_name = model_name
        self.last_token_usage: int = 0
        self.download_progress_callback: Callable[[str, float, int], None] | None = None
        self.performance_mode: str = PERFORMANCE_MODE_NORMAL
        self._cached_model: Any | None = None
        self._cached_tokenizer: Any | None = None
        self._lm_runtime_loader = runtime_loader
        self._lm_generation_runner = generation_runner
        self._vlm_runtime_loader = vlm_runtime_loader
        self._vlm_generation_runner = vlm_generation_runner
        self._model_cache_checker = model_cache_checker
        self._model_downloader = model_downloader
        self._memory_cleanup = memory_cleanup
        self._apply_backend_for_model(model_name)

    def _apply_backend_for_model(self, model_name: str) -> None:
        """Выбирает правильный backend (LM или VLM) для модели."""
        if _is_vlm_model(model_name):
            self._runtime_loader = self._vlm_runtime_loader
            self._generation_runner = self._vlm_generation_runner
        else:
            self._runtime_loader = self._lm_runtime_loader
            self._generation_runner = self._lm_generation_runner

    def set_performance_mode(self, performance_mode: str) -> None:
        """Переключает стратегию управления памятью для LLM."""
        normalized_mode = performance_mode if performance_mode == PERFORMANCE_MODE_FAST else PERFORMANCE_MODE_NORMAL
        self.performance_mode = normalized_mode
        if normalized_mode != PERFORMANCE_MODE_FAST:
            self._unload_cached_model()

    def _load_runtime_objects(self) -> tuple[Any, Any]:
        """Возвращает модель и токенизатор, используя кэш в быстром режиме."""
        if self._cached_model is not None and self._cached_tokenizer is not None:
            LOGGER.info("🤖 Использую уже загруженную LLM-модель")
            return self._cached_model, self._cached_tokenizer

        if self._runtime_loader is None:
            raise RuntimeError("LLM runtime не настроен")

        LOGGER.info("🤖 Загрузка LLM: %s", self.model_name)
        model, tokenizer = self._runtime_loader(self.model_name)
        self._cached_model = model
        self._cached_tokenizer = tokenizer
        return model, tokenizer

    def change_model(self, model_name: str) -> None:
        """Переключает LLM-модель и автоматически выбирает backend."""
        if model_name == self.model_name:
            return
        self._unload_cached_model()
        self.model_name = model_name
        self._apply_backend_for_model(model_name)
        LOGGER.info("🤖 LLM-модель переключена: %s", model_name)

    def _unload_cached_model(self) -> None:
        """Выгружает LLM-модель и токенизатор из памяти."""
        had_cached_objects = self._cached_model is not None or self._cached_tokenizer is not None
        self._cached_model = None
        self._cached_tokenizer = None
        if not had_cached_objects:
            return
        if self._memory_cleanup is None:
            raise RuntimeError("LLM cleanup runtime не настроен")
        self._memory_cleanup()
        LOGGER.info("🤖 LLM выгружена из памяти")

    def is_model_cached(self) -> bool:
        """Проверяет, скачана ли модель в локальный кэш."""
        if self._model_cache_checker is None:
            return False
        return self._model_cache_checker(self.model_name)

    def ensure_model_downloaded(self) -> None:
        """Скачивает модель в кэш Hugging Face с отслеживанием прогресса."""
        if self._model_downloader is None:
            raise RuntimeError("LLM download runtime не настроен")
        LOGGER.info("📥 Начинаю загрузку модели: %s", self.model_name)
        self._model_downloader(self.model_name, self.download_progress_callback)
        LOGGER.info("✅ Модель загружена: %s", self.model_name)

    def _count_tokens(self, tokenizer: Any, text: str) -> int:
        """Возвращает количество токенов для текста через tokenizer.encode."""
        if not text:
            return 0

        actual_tokenizer = getattr(tokenizer, "tokenizer", tokenizer)
        encoded = actual_tokenizer.encode(text)
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

    def process_text(self, text: str, system_prompt: str, *, context: str | None = None, max_tokens: int | None = None) -> str:
        """Отправляет текст в LLM и возвращает очищенный ответ."""
        effective_max_tokens = max_tokens if max_tokens is not None else Config.LLM_MAX_TOKENS
        self.last_token_usage = 0
        model, tokenizer = self._load_runtime_objects()
        if self._generation_runner is None:
            raise RuntimeError("LLM generation runtime не настроен")
        try:
            actual_tokenizer = getattr(tokenizer, "tokenizer", tokenizer)
            if hasattr(actual_tokenizer, "apply_chat_template"):
                user_content = f"Контекст из буфера обмена:\n{context}\n\nЗапрос:\n{text}" if context else text
                messages = [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_content},
                ]
                try:
                    prompt = actual_tokenizer.apply_chat_template(
                        messages,
                        tokenize=False,
                        add_generation_prompt=True,
                        enable_thinking=False,
                    )
                except TypeError:
                    prompt = actual_tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
            elif context:
                prompt = f"{system_prompt}\n\nКонтекст:\n{context}\n\nПользователь: {text}\nОтвет:"
            else:
                prompt = f"{system_prompt}\n\nПользователь: {text}\nОтвет:"

            prompt_tokens = self._count_tokens(tokenizer, prompt)
            LOGGER.info("🤖 Генерация ответа LLM (max_tokens=%d)", effective_max_tokens)
            raw_response = self._generation_runner(model, tokenizer, prompt, effective_max_tokens)
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
