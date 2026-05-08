"""Единый runtime-сервис загруженных MLX-моделей."""

from __future__ import annotations

import gc
import importlib
import logging
import threading
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, cast

if TYPE_CHECKING:
    from collections.abc import Callable

LOGGER = logging.getLogger(__name__)

BACKEND_LM = "lm"
BACKEND_VLM = "vlm"
BACKEND_QWEN_ASR = "qwen-asr"
BACKEND_MLX_TTS = "mlx-tts"
BACKEND_WHISPER = "whisper"

_VLM_MODEL_INDICATORS = ("gemma-4", "gemma4", "-vlm", "vision")


def is_vlm_model(model_name: str) -> bool:
    """Определяет, нужен ли mlx_vlm для данной LLM-модели."""
    lower = model_name.lower()
    return any(indicator in lower for indicator in _VLM_MODEL_INDICATORS)


def is_qwen_asr_model_name(model_name: str) -> bool:
    """Определяет, что ASR-модель должна идти через mlx-audio Qwen backend."""
    normalized = model_name.rsplit("/", maxsplit=1)[-1].lower()
    return normalized.startswith("qwen3-asr")


@dataclass(frozen=True, slots=True)
class ModelRuntimeKey:
    """Ключ runtime-экземпляра модели: backend плюс исходный model_id."""

    backend: str
    model_id: str


@dataclass(slots=True)
class _InflightLoad:
    """Состояние single-flight загрузки модели."""

    event: threading.Event
    generation: int
    value: Any | None = None
    error: BaseException | None = None


def _default_memory_cleanup() -> None:
    """Очищает Python и MLX cache после выгрузки runtime-моделей."""
    gc.collect()
    try:
        import mlx.core as mx  # noqa: PLC0415
    except ImportError:
        return
    clear_cache = getattr(mx, "clear_cache", None)
    if callable(clear_cache):
        clear_cache()


def _default_lm_loader(model_name: str) -> tuple[Any, Any]:
    """Загружает MLX LM-модель напрямую через mlx-lm."""
    from mlx_lm import load  # noqa: PLC0415

    loaded = load(model_name)
    return loaded[0], loaded[1]


def _default_vlm_loader(model_name: str) -> tuple[Any, Any]:
    """Загружает VLM-модель напрямую через mlx-vlm."""
    from mlx_vlm import load  # noqa: PLC0415

    model, processor = load(model_name)
    return model, processor


def _default_qwen_asr_loader(model_name: str) -> Any:
    """Загружает Qwen3-ASR модель напрямую через mlx-audio."""
    try:
        from mlx_audio.stt import load as load_mlx_audio_stt_model  # noqa: PLC0415
    except ImportError as exc:
        raise RuntimeError("Для модели Qwen3-ASR нужна зависимость mlx-audio. Выполните `uv sync --dev`.") from exc
    return load_mlx_audio_stt_model(model_name)


def _default_mlx_tts_loader(model_name: str) -> Any:
    """Загружает streaming MLX TTS-модель напрямую через mlx-audio."""
    try:
        from mlx_audio.tts import load as load_mlx_audio_tts_model  # noqa: PLC0415
    except ImportError as exc:
        raise RuntimeError("Для MLX TTS нужна зависимость mlx-audio. Выполните uv sync --dev.") from exc
    return load_mlx_audio_tts_model(model_name)


def _set_whisper_model_holder(model_path: str, model: Any) -> None:
    """Заполняет singleton ModelHolder библиотеки mlx_whisper."""
    transcribe_module = importlib.import_module("mlx_whisper.transcribe")
    model_holder = transcribe_module.ModelHolder
    model_holder.model = model
    model_holder.model_path = model_path


def _default_whisper_loader(model_name: str) -> Any:
    """Загружает Whisper-модель и регистрирует её в ModelHolder."""
    import mlx.core as mx  # noqa: PLC0415
    from mlx_whisper.load_models import load_model  # noqa: PLC0415

    model = load_model(model_name, dtype=mx.float16)
    _set_whisper_model_holder(model_name, model)
    return model


class ModelRuntimeService:
    """Хранит загруженные MLX runtime-объекты и объединяет параллельные загрузки."""

    def __init__(
        self,
        *,
        lm_loader: Callable[[str], tuple[Any, Any]] | None = None,
        vlm_loader: Callable[[str], tuple[Any, Any]] | None = None,
        qwen_asr_loader: Callable[[str], Any] | None = None,
        mlx_tts_loader: Callable[[str], Any] | None = None,
        whisper_loader: Callable[[str], Any] | None = None,
        memory_cleanup: Callable[[], None] | None = None,
    ) -> None:
        self._lm_loader = lm_loader or _default_lm_loader
        self._vlm_loader = vlm_loader or _default_vlm_loader
        self._qwen_asr_loader = qwen_asr_loader or _default_qwen_asr_loader
        self._mlx_tts_loader = mlx_tts_loader or _default_mlx_tts_loader
        self._whisper_loader = whisper_loader or _default_whisper_loader
        self._memory_cleanup = memory_cleanup or _default_memory_cleanup
        self._models: dict[ModelRuntimeKey, Any] = {}
        self._inflight: dict[ModelRuntimeKey, _InflightLoad] = {}
        self._model_generations: dict[str, int] = {}
        self._lock = threading.RLock()
        self._loader_lock = threading.Lock()

    def get_lm(self, model_id: str) -> tuple[Any, Any]:
        """Возвращает загруженную LM-модель и tokenizer через общий cache."""
        return cast("tuple[Any, Any]", self._get_or_load(ModelRuntimeKey(BACKEND_LM, model_id), self._lm_loader))

    def get_vlm(self, model_id: str) -> tuple[Any, Any]:
        """Возвращает загруженную VLM-модель и processor через общий cache."""
        return cast("tuple[Any, Any]", self._get_or_load(ModelRuntimeKey(BACKEND_VLM, model_id), self._vlm_loader))

    def get_qwen_asr(self, model_id: str) -> Any:
        """Возвращает загруженную Qwen3-ASR модель через общий cache."""
        return self._get_or_load(ModelRuntimeKey(BACKEND_QWEN_ASR, model_id), self._qwen_asr_loader)

    def get_mlx_tts(self, model_id: str) -> Any:
        """Возвращает загруженную MLX TTS-модель через общий cache."""
        return self._get_or_load(ModelRuntimeKey(BACKEND_MLX_TTS, model_id), self._mlx_tts_loader)

    def get_whisper(self, model_id: str) -> Any:
        """Возвращает загруженную Whisper-модель и подготавливает ModelHolder."""
        return self._get_or_load(ModelRuntimeKey(BACKEND_WHISPER, model_id), self._whisper_loader)

    def preload_selected_models(
        self,
        *,
        asr_model: str | None = None,
        llm_model: str | None = None,
        tts_model: str | None = None,
        wait: bool = False,
    ) -> list[threading.Thread]:
        """Запускает прогрев выбранных ASR, LLM/VLM и MLX TTS моделей."""
        threads: list[threading.Thread] = []
        if asr_model:
            target = self.get_qwen_asr if is_qwen_asr_model_name(asr_model) else self.get_whisper
            threads.append(self.preload_model(asr_model, label="ASR-модель", loader=target))
        if llm_model:
            target = self.get_vlm if is_vlm_model(llm_model) else self.get_lm
            threads.append(self.preload_model(llm_model, label="VLM-модель" if is_vlm_model(llm_model) else "LLM-модель", loader=target))
        if tts_model:
            threads.append(self.preload_model(tts_model, label="TTS-модель", loader=self.get_mlx_tts))
        if wait:
            for thread in threads:
                thread.join()
        return threads

    def preload_model(self, model_id: str, *, label: str, loader: Callable[[str], Any]) -> threading.Thread:
        """Запускает фоновый прогрев одной модели и не пробрасывает ошибку в UI-поток."""

        def run() -> None:
            try:
                loader(model_id)
            except Exception:
                LOGGER.exception("⚠️ Не удалось прогреть модель: label=%s, model=%s", label, model_id)
            else:
                LOGGER.info("🧠 Модель прогрета: label=%s, model=%s", label, model_id)

        thread = threading.Thread(target=run, name=f"model-preload-{label}", daemon=True)
        thread.start()
        return thread

    def preload_asr_model(self, model_id: str) -> threading.Thread:
        """Запускает фоновый прогрев выбранной ASR-модели."""
        loader = self.get_qwen_asr if is_qwen_asr_model_name(model_id) else self.get_whisper
        return self.preload_model(model_id, label="ASR-модель", loader=loader)

    def preload_llm_model(self, model_id: str) -> threading.Thread:
        """Запускает фоновый прогрев выбранной LLM/VLM-модели."""
        label = "VLM-модель" if is_vlm_model(model_id) else "LLM-модель"
        loader = self.get_vlm if is_vlm_model(model_id) else self.get_lm
        return self.preload_model(model_id, label=label, loader=loader)

    def preload_tts_model(self, model_id: str) -> threading.Thread:
        """Запускает фоновый прогрев выбранной MLX TTS-модели."""
        return self.preload_model(model_id, label="TTS-модель", loader=self.get_mlx_tts)

    def release_model(self, model_id: str) -> None:
        """Освобождает все runtime-экземпляры указанного model_id."""
        with self._lock:
            self._model_generations[model_id] = self._model_generations.get(model_id, 0) + 1
            keys = [key for key in self._models if key.model_id == model_id]
            has_inflight = any(key.model_id == model_id for key in self._inflight)
            for key in keys:
                self._models.pop(key, None)
        if not keys and not has_inflight:
            return
        if keys:
            self._memory_cleanup()
        LOGGER.info("🧠 Модель освобождена из runtime-cache: model=%s, backends=%s", model_id, [key.backend for key in keys])

    def shutdown(self) -> None:
        """Очищает runtime-cache всех моделей при завершении приложения."""
        with self._lock:
            had_models = bool(self._models)
            model_ids = {key.model_id for key in self._models} | {key.model_id for key in self._inflight}
            for model_id in model_ids:
                self._model_generations[model_id] = self._model_generations.get(model_id, 0) + 1
            self._models.clear()
        if had_models:
            self._memory_cleanup()
        LOGGER.info("🧠 Runtime-cache моделей очищен")

    def _get_or_load(self, key: ModelRuntimeKey, loader: Callable[[str], Any]) -> Any:
        """Возвращает модель из cache или ждёт единственную текущую загрузку."""
        with self._lock:
            cached_model = self._models.get(key)
            if cached_model is not None:
                LOGGER.info("🧠 Использую уже загруженную модель: backend=%s, model=%s", key.backend, key.model_id)
                return cached_model

            inflight = self._inflight.get(key)
            if inflight is None:
                inflight = _InflightLoad(
                    event=threading.Event(),
                    generation=self._model_generations.get(key.model_id, 0),
                )
                self._inflight[key] = inflight
                should_load = True
            else:
                should_load = False
                LOGGER.info("🧠 Ожидаю текущую загрузку модели: backend=%s, model=%s", key.backend, key.model_id)

        if not should_load:
            inflight.event.wait()
            if inflight.error is not None:
                raise inflight.error
            return inflight.value

        try:
            LOGGER.info("🧠 Загружаю модель в общий runtime-cache: backend=%s, model=%s", key.backend, key.model_id)
            with self._loader_lock:
                value = loader(key.model_id)
        except BaseException as error:
            with self._lock:
                inflight.error = error
                self._inflight.pop(key, None)
                inflight.event.set()
            raise

        with self._lock:
            if inflight.generation == self._model_generations.get(key.model_id, 0):
                self._models[key] = value
            inflight.value = value
            self._inflight.pop(key, None)
            inflight.event.set()
        LOGGER.info("🧠 Модель прогрета: backend=%s, model=%s", key.backend, key.model_id)
        return value
