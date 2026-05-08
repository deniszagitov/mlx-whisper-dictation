"""Централизованный менеджер локальных MLX-моделей."""

from __future__ import annotations

import logging
import threading
import time
from collections import deque
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING, Any, Protocol

from ..domain.constants import Config
from ..domain.model_downloads import ModelDownloadProgress, format_model_download_metrics

if TYPE_CHECKING:
    import numpy as np
    import numpy.typing as npt

ProgressCallback = Callable[[ModelDownloadProgress], None]
LegacyProgressCallback = Callable[..., None]

LOGGER = logging.getLogger(__name__)
DOWNLOAD_SPEED_WINDOW_SECONDS = 8.0
DOWNLOAD_MIN_SPEED_WINDOW_SECONDS = 1.0
DOWNLOAD_MIN_SPEED_SAMPLES = 2
DOWNLOAD_TQDM_MIN_INTERVAL_SECONDS = 0.5
DOWNLOAD_TQDM_SMOOTHING = 0.05


class ModelDownloaderProtocol(Protocol):
    """Минимальный контракт downloader-а для ModelManager."""

    def is_model_cached(self, model_name: str) -> bool:
        """Проверяет наличие модели в локальном cache."""
        ...

    def ensure_downloaded(
        self,
        model_name: str,
        *,
        label: str,
        progress_callback: ProgressCallback | None = None,
    ) -> None:
        """Скачивает модель при необходимости."""
        ...


def _is_local_model_path(model_name: str) -> bool:
    """Проверяет, похож ли идентификатор модели на локальный путь."""
    path = Path(model_name).expanduser()
    return path.exists()


def _coerce_total(value: object) -> int:
    """Преобразует total progress bar в неотрицательное число байт."""
    if isinstance(value, bool) or value is None:
        return 0
    if isinstance(value, int):
        return max(value, 0)
    if isinstance(value, float):
        return max(int(value), 0)
    return 0


def _emit_legacy_progress(callback: LegacyProgressCallback | None, progress: ModelDownloadProgress) -> None:
    """Пробрасывает новое событие в старый callback загрузки LLM."""
    if callback is None:
        return
    try:
        callback(
            progress.stage,
            progress.percent,
            progress.total_bytes,
            progress.speed_bytes_per_second,
            progress.eta_seconds,
        )
    except TypeError:
        callback(progress.stage, progress.percent, progress.total_bytes)


class HuggingFaceModelDownloader:
    """Единый downloader Hugging Face моделей с консольным и UI-прогрессом."""

    def __init__(
        self,
        *,
        snapshot_downloader: Callable[..., str] | None = None,
        cache_checker: Callable[[str, str], Any] | None = None,
        clock: Callable[[], float] | None = None,
        min_emit_interval_seconds: float = 0.25,
    ) -> None:
        self._snapshot_downloader = snapshot_downloader
        self._cache_checker = cache_checker
        self._clock = clock or time.monotonic
        self._min_emit_interval_seconds = min_emit_interval_seconds

    def is_model_cached(self, model_name: str) -> bool:
        """Проверяет, есть ли модель в локальном cache Hugging Face."""
        if _is_local_model_path(model_name):
            return True
        try:
            checker = self._cache_checker
            if checker is None:
                from huggingface_hub import try_to_load_from_cache  # noqa: PLC0415

                checker = try_to_load_from_cache
            result = checker(model_name, "config.json")
            return result is not None and not isinstance(result, type)
        except Exception:
            return False

    def ensure_downloaded(
        self,
        model_name: str,
        *,
        label: str,
        progress_callback: ProgressCallback | None = None,
    ) -> None:
        """Скачивает модель через общий механизм с progress bar и событиями."""
        LOGGER.info("📥 Проверяю загрузку модели: label=%s, model=%s", label, model_name)
        if _is_local_model_path(model_name):
            self._emit(
                progress_callback,
                ModelDownloadProgress(
                    label=label,
                    model_name=model_name,
                    stage="локальный путь",
                    percent=Config.DOWNLOAD_COMPLETE_PCT,
                    complete=True,
                ),
            )
            return

        self._emit(
            progress_callback,
            ModelDownloadProgress(label=label, model_name=model_name, stage="Подготовка…"),
        )

        try:
            snapshot_downloader = self._snapshot_downloader
            if snapshot_downloader is None:
                from huggingface_hub import snapshot_download  # noqa: PLC0415

                snapshot_downloader = snapshot_download
            LOGGER.info("📥 Скачиваю модель через Hugging Face: label=%s, model=%s", label, model_name)
            snapshot_downloader(model_name, tqdm_class=self._build_tqdm_class(label, model_name, progress_callback))
        except Exception:
            self._emit(
                progress_callback,
                ModelDownloadProgress(label=label, model_name=model_name, stage="ошибка", failed=True),
            )
            raise

        self._emit(
            progress_callback,
            ModelDownloadProgress(
                label=label,
                model_name=model_name,
                stage="",
                percent=Config.DOWNLOAD_COMPLETE_PCT,
                complete=True,
            ),
        )

    def _build_tqdm_class(
        self,
        label: str,
        model_name: str,
        progress_callback: ProgressCallback | None,
    ) -> type[Any]:
        """Создаёт tqdm-класс, который одновременно пишет в консоль и callback."""
        from tqdm.auto import tqdm as base_tqdm  # noqa: PLC0415

        clock = self._clock
        emit = self._emit
        min_emit_interval_seconds = self._min_emit_interval_seconds

        class _ModelDownloadTqdm(base_tqdm):  # type: ignore[misc]
            """tqdm с пробросом скорости и ETA в меню."""

            _lock: Any = None

            def __init__(self, *args: Any, **kwargs: Any) -> None:
                progress_name = str(kwargs.pop("name", "") or "")
                self._download_progress_tracked = kwargs.get("unit") == "B" or progress_name == "huggingface_hub.snapshot_download"
                self._download_started_at = clock()
                self._download_last_emit_at = 0.0
                self._download_samples: deque[tuple[float, int]] = deque()
                self._download_last_speed: float | None = None
                kwargs["disable"] = False
                kwargs["mininterval"] = DOWNLOAD_TQDM_MIN_INTERVAL_SECONDS
                kwargs["smoothing"] = DOWNLOAD_TQDM_SMOOTHING
                if self._download_progress_tracked:
                    kwargs["bar_format"] = "{l_bar}{bar}| {n_fmt}/{total_fmt} [{elapsed}] {postfix}"
                super().__init__(*args, **kwargs)
                if self._download_progress_tracked:
                    self._emit_download_progress(force=True)

            def update(self, n: int | float | None = 1) -> bool | None:
                """Обновляет progress bar и отдаёт событие наружу."""
                result = super().update(n)
                if self._download_progress_tracked:
                    self._emit_download_progress()
                return result if isinstance(result, bool) or result is None else bool(result)

            def refresh(self, *args: Any, **kwargs: Any) -> bool | None:
                """Публикует изменение total, когда Hugging Face уточняет размер."""
                result = super().refresh(*args, **kwargs)
                if getattr(self, "_download_progress_tracked", False):
                    self._emit_download_progress()
                return result if isinstance(result, bool) or result is None else bool(result)

            def close(self) -> None:
                """Фиксирует финальный прогресс перед закрытием progress bar."""
                if getattr(self, "_download_progress_tracked", False):
                    self._emit_download_progress(force=True)
                super().close()

            def _emit_download_progress(self, *, force: bool = False) -> None:
                now = clock()
                if not force and now - self._download_last_emit_at < min_emit_interval_seconds:
                    return
                self._download_last_emit_at = now
                total = _coerce_total(getattr(self, "total", 0))
                downloaded = _coerce_total(getattr(self, "n", 0))
                speed = self._download_speed(now, downloaded)
                eta = (total - downloaded) / speed if speed and total > downloaded else None
                percent = min(downloaded / total * Config.DOWNLOAD_COMPLETE_PCT, Config.DOWNLOAD_COMPLETE_PCT) if total else 0.0
                self.postfix = format_model_download_metrics(speed, eta)
                emit(
                    progress_callback,
                    ModelDownloadProgress(
                        label=label,
                        model_name=model_name,
                        stage=str(getattr(self, "desc", "") or "Загрузка…"),
                        downloaded_bytes=downloaded,
                        total_bytes=total,
                        percent=percent,
                        speed_bytes_per_second=speed,
                        eta_seconds=eta,
                    ),
                )

            def _download_speed(self, now: float, downloaded: int) -> float | None:
                """Считает сглаженную скорость по скользящему окну байтов."""
                samples = self._download_samples
                if not samples or downloaded >= samples[-1][1]:
                    samples.append((now, downloaded))
                else:
                    samples.clear()
                    samples.append((now, downloaded))
                    self._download_last_speed = None
                while len(samples) > 1 and now - samples[0][0] > DOWNLOAD_SPEED_WINDOW_SECONDS:
                    samples.popleft()
                if len(samples) < DOWNLOAD_MIN_SPEED_SAMPLES:
                    return self._download_last_speed
                start_time, start_downloaded = samples[0]
                elapsed = now - start_time
                delta = downloaded - start_downloaded
                if elapsed < DOWNLOAD_MIN_SPEED_WINDOW_SECONDS or delta <= 0:
                    return self._download_last_speed
                self._download_last_speed = delta / elapsed
                return self._download_last_speed

            @classmethod
            def get_lock(cls) -> Any:
                """Возвращает lock для tqdm.contrib.concurrent.ensure_lock."""
                if getattr(cls, "_lock", None) is None:
                    cls._lock = threading.Lock()
                return cls._lock

            @classmethod
            def set_lock(cls, lock: Any) -> None:
                """Устанавливает lock для tqdm.contrib.concurrent.ensure_lock."""
                cls._lock = lock

        return _ModelDownloadTqdm

    def _emit(self, progress_callback: ProgressCallback | None, progress: ModelDownloadProgress) -> None:
        """Отправляет событие прогресса, изолируя ошибки подписчика."""
        if progress_callback is None:
            return
        try:
            progress_callback(progress)
        except Exception:
            LOGGER.exception("⚠️ Ошибка callback прогресса загрузки модели")


class ModelManager:
    """Единая точка скачивания и загрузки ASR, LLM/VLM и MLX TTS моделей."""

    def __init__(
        self,
        *,
        downloader: ModelDownloaderProtocol | None = None,
        progress_callback: ProgressCallback | None = None,
        lm_loader: Callable[[str], tuple[Any, Any]] | None = None,
        vlm_loader: Callable[[str], tuple[Any, Any]] | None = None,
        qwen_asr_loader: Callable[[str], Any] | None = None,
        tts_loader: Callable[[str], Any] | None = None,
    ) -> None:
        self._downloader = downloader or HuggingFaceModelDownloader()
        self._progress_callback = progress_callback
        self._lm_loader = lm_loader
        self._vlm_loader = vlm_loader
        self._qwen_asr_loader = qwen_asr_loader
        self._tts_loader = tts_loader

    def set_progress_callback(self, callback: ProgressCallback | None) -> None:
        """Назначает callback для публикации прогресса в приложение."""
        self._progress_callback = callback

    def is_model_cached(self, model_name: str) -> bool:
        """Проверяет, доступна ли модель локально."""
        return self._downloader.is_model_cached(model_name)

    def ensure_model_downloaded(
        self,
        model_name: str,
        *,
        label: str,
        progress_callback: LegacyProgressCallback | None = None,
    ) -> None:
        """Скачивает модель через общий downloader и старый LLM callback."""

        def emit(progress: ModelDownloadProgress) -> None:
            if self._progress_callback is not None:
                self._progress_callback(progress)
            _emit_legacy_progress(progress_callback, progress)

        self._downloader.ensure_downloaded(model_name, label=label, progress_callback=emit)

    def ensure_llm_model_downloaded(
        self,
        model_name: str,
        progress_callback: LegacyProgressCallback | None = None,
    ) -> None:
        """Скачивает LLM-модель через общий менеджер."""
        self.ensure_model_downloaded(model_name, label="LLM-модель", progress_callback=progress_callback)

    def load_llm_runtime_objects(self, model_name: str) -> tuple[Any, Any]:
        """Скачивает и загружает MLX LLM-модель."""
        self.ensure_model_downloaded(model_name, label="LLM-модель")
        if self._lm_loader is None:
            from mlx_lm import load  # noqa: PLC0415

            loaded = load(model_name)
        else:
            loaded = self._lm_loader(model_name)
        return loaded[0], loaded[1]

    def load_vlm_runtime_objects(self, model_name: str) -> tuple[Any, Any]:
        """Скачивает и загружает MLX VLM-модель."""
        self.ensure_model_downloaded(model_name, label="VLM-модель")
        loader = self._vlm_loader
        if loader is None:
            from mlx_vlm import load  # noqa: PLC0415

            loader = load
        model, processor = loader(model_name)
        return model, processor

    def load_qwen_asr_model(self, model_name: str) -> Any:
        """Скачивает и загружает Qwen3-ASR модель через mlx-audio."""
        self.ensure_model_downloaded(model_name, label="ASR-модель")
        loader = self._qwen_asr_loader
        if loader is None:
            try:
                from mlx_audio.stt import load as load_mlx_audio_stt_model  # noqa: PLC0415
            except ImportError as exc:
                raise RuntimeError("Для модели Qwen3-ASR нужна зависимость mlx-audio. Выполните `uv sync --dev`.") from exc
            loader = load_mlx_audio_stt_model
        return loader(model_name)

    def load_tts_model(self, model_name: str) -> Any:
        """Скачивает и загружает streaming MLX TTS-модель."""
        self.ensure_model_downloaded(model_name, label="TTS-модель")
        loader = self._tts_loader
        if loader is None:
            try:
                from mlx_audio.tts import load as load_mlx_audio_tts_model  # noqa: PLC0415
            except ImportError as exc:
                raise RuntimeError("Для MLX TTS нужна зависимость mlx-audio. Выполните uv sync --dev.") from exc
            loader = load_mlx_audio_tts_model
        return loader(model_name)

    def run_asr_transcription(
        self,
        audio_data: npt.NDArray[np.float32],
        model_name: str,
        language: str | None,
    ) -> dict[str, Any]:
        """Скачивает ASR-модель и запускает подходящий backend."""
        from . import asr_runtime  # noqa: PLC0415

        if asr_runtime.is_qwen_asr_model(model_name):
            return asr_runtime.run_qwen_transcription(
                audio_data,
                model_name,
                language,
                model_loader=self.load_qwen_asr_model,
            )
        self.ensure_model_downloaded(model_name, label="ASR-модель")
        return asr_runtime.run_whisper_transcription(audio_data, model_name, language)


_DEFAULT_MODEL_MANAGER: ModelManager | None = None


def default_model_manager() -> ModelManager:
    """Возвращает общий менеджер моделей для legacy runtime-функций."""
    global _DEFAULT_MODEL_MANAGER  # noqa: PLW0603
    if _DEFAULT_MODEL_MANAGER is None:
        _DEFAULT_MODEL_MANAGER = ModelManager()
    return _DEFAULT_MODEL_MANAGER
