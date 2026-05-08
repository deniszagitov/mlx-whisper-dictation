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
from ..domain.model_downloads import ModelDownloadProgress, ModelRequiredError, format_model_download_metrics

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
DOWNLOAD_MAX_WORKERS = 4
DOWNLOAD_MIN_SPEED_BYTES_PER_SECOND = 2 * 1024 * 1024
DOWNLOAD_SLOW_SPEED_GRACE_SECONDS = 30.0
DOWNLOAD_STALL_TIMEOUT_SECONDS = 60.0
DOWNLOAD_HEALTH_MONITOR_INTERVAL_SECONDS = 5.0


class ModelDownloadHealthError(RuntimeError):
    """Ошибка здоровья загрузки модели."""


class ModelDownloadTooSlowError(ModelDownloadHealthError):
    """Загрузка слишком долго идёт ниже минимальной скорости."""


class ModelDownloadStalledError(ModelDownloadHealthError):
    """Загрузка слишком долго не получает новые байты."""


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
            progress.warning,
        )
    except TypeError:
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
        max_workers: int = DOWNLOAD_MAX_WORKERS,
        min_speed_bytes_per_second: float = DOWNLOAD_MIN_SPEED_BYTES_PER_SECOND,
        slow_speed_grace_seconds: float = DOWNLOAD_SLOW_SPEED_GRACE_SECONDS,
        stall_timeout_seconds: float = DOWNLOAD_STALL_TIMEOUT_SECONDS,
        health_monitor_interval_seconds: float = DOWNLOAD_HEALTH_MONITOR_INTERVAL_SECONDS,
    ) -> None:
        self._snapshot_downloader = snapshot_downloader
        self._cache_checker = cache_checker
        self._clock = clock or time.monotonic
        self._min_emit_interval_seconds = min_emit_interval_seconds
        self._max_workers = max(max_workers, 1)
        self._min_speed_bytes_per_second = max(min_speed_bytes_per_second, 0.0)
        self._slow_speed_grace_seconds = max(slow_speed_grace_seconds, 0.0)
        self._stall_timeout_seconds = max(stall_timeout_seconds, 0.0)
        self._health_monitor_interval_seconds = max(health_monitor_interval_seconds, 0.0)
        self._completed_models: set[str] = set()
        self._local_model_paths: dict[str, str] = {}
        self._completed_models_lock = threading.Lock()

    def is_model_cached(self, model_name: str) -> bool:
        """Проверяет, есть ли модель в локальном cache Hugging Face."""
        return self.get_local_model_path(model_name) is not None

    def get_local_model_path(self, model_name: str) -> str | None:
        """Возвращает локальный snapshot модели Hugging Face без обращения к сети."""
        if _is_local_model_path(model_name):
            return str(Path(model_name).expanduser())
        with self._completed_models_lock:
            cached_path = self._local_model_paths.get(model_name)
        if cached_path is not None:
            return cached_path
        try:
            snapshot_downloader = self._snapshot_downloader
            if snapshot_downloader is None:
                from huggingface_hub import snapshot_download  # noqa: PLC0415

                snapshot_downloader = snapshot_download
            local_path = snapshot_downloader(model_name, local_files_only=True)
        except TypeError:
            return self._local_path_from_cached_config(model_name)
        except Exception:
            return None
        if isinstance(local_path, str) and local_path:
            self._remember_local_model_path(model_name, local_path)
            return local_path
        return None

    def _local_path_from_cached_config(self, model_name: str) -> str | None:
        """Проверяет cache старым способом, не запуская сетевую загрузку."""
        try:
            checker = self._cache_checker
            if checker is None:
                from huggingface_hub import try_to_load_from_cache  # noqa: PLC0415

                checker = try_to_load_from_cache
            result = checker(model_name, "config.json")
        except Exception:
            return None
        if isinstance(result, str) and result:
            local_path = str(Path(result).parent)
            self._remember_local_model_path(model_name, local_path)
            return local_path
        return None

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
        if self._is_completed_in_process(model_name):
            LOGGER.info("📦 Модель уже проверена в этом запуске: label=%s, model=%s", label, model_name)
            self._emit(
                progress_callback,
                ModelDownloadProgress(
                    label=label,
                    model_name=model_name,
                    stage="уже загружена",
                    percent=Config.DOWNLOAD_COMPLETE_PCT,
                    complete=True,
                ),
            )
            return

        cached_path = self.get_local_model_path(model_name)
        if cached_path is not None:
            LOGGER.info(
                "📦 Модель найдена в локальном cache Hugging Face: label=%s, model=%s, path=%s",
                label,
                model_name,
                cached_path,
            )
            self._mark_completed_in_process(model_name)
            self._emit(
                progress_callback,
                ModelDownloadProgress(
                    label=label,
                    model_name=model_name,
                    stage="уже в cache",
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
            LOGGER.info(
                "📥 Скачиваю модель через Hugging Face: label=%s, model=%s, workers=%s",
                label,
                model_name,
                self._max_workers,
            )
            downloaded_path = snapshot_downloader(
                model_name,
                max_workers=self._max_workers,
                tqdm_class=self._build_tqdm_class(label, model_name, progress_callback),
            )
            if isinstance(downloaded_path, str) and downloaded_path:
                self._remember_local_model_path(model_name, downloaded_path)
        except ModelDownloadHealthError as exc:
            self._emit(
                progress_callback,
                ModelDownloadProgress(label=label, model_name=model_name, stage="ошибка", warning=str(exc), failed=True),
            )
            raise
        except Exception:
            self._emit(
                progress_callback,
                ModelDownloadProgress(label=label, model_name=model_name, stage="ошибка", failed=True),
            )
            raise

        self._mark_completed_in_process(model_name)
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
        min_speed_bytes_per_second = self._min_speed_bytes_per_second
        slow_speed_grace_seconds = self._slow_speed_grace_seconds
        stall_timeout_seconds = self._stall_timeout_seconds
        health_monitor_interval_seconds = self._health_monitor_interval_seconds

        class _ModelDownloadTqdm(base_tqdm):  # type: ignore[misc]
            """tqdm с пробросом скорости и ETA в меню."""

            _lock: Any = None

            def __init__(self, *args: Any, **kwargs: Any) -> None:
                progress_name = str(kwargs.pop("name", "") or "")
                self._download_progress_tracked = kwargs.get("unit") == "B" or progress_name == "huggingface_hub.snapshot_download"
                self._download_started_at = clock()
                self._download_last_progress_at = self._download_started_at
                self._download_last_emit_at = 0.0
                self._download_samples: deque[tuple[float, int]] = deque()
                self._download_last_speed: float | None = None
                self._download_slow_since: float | None = None
                self._download_health_error: ModelDownloadHealthError | None = None
                self._download_health_warning: str | None = None
                self._download_state_lock = threading.RLock()
                self._download_monitor_stop = threading.Event()
                self._download_monitor_thread: threading.Thread | None = None
                kwargs["disable"] = False
                kwargs["mininterval"] = DOWNLOAD_TQDM_MIN_INTERVAL_SECONDS
                kwargs["smoothing"] = DOWNLOAD_TQDM_SMOOTHING
                if self._download_progress_tracked:
                    kwargs["bar_format"] = "{l_bar}{bar}| {n_fmt}/{total_fmt} [{elapsed}] {postfix}"
                super().__init__(*args, **kwargs)
                if self._download_progress_tracked:
                    self._download_last_progress_at = self._download_started_at if _coerce_total(getattr(self, "n", 0)) <= 0 else clock()
                    self._start_health_monitor()
                    self._emit_download_progress(force=True)

            def update(self, n: int | float | None = 1) -> bool | None:
                """Обновляет progress bar и отдаёт событие наружу."""
                self._raise_download_health_error()
                result = super().update(n)
                if self._download_progress_tracked:
                    if n is not None and n > 0:
                        with self._download_state_lock:
                            self._download_last_progress_at = clock()
                    self._emit_download_progress()
                    self._raise_download_health_error()
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
                    self._download_monitor_stop.set()
                    monitor = self._download_monitor_thread
                    if monitor is not None and monitor.is_alive():
                        monitor.join(timeout=1.0)
                super().close()

            def _emit_download_progress(self, *, force: bool = False) -> None:
                now = clock()
                if not force and now - self._download_last_emit_at < min_emit_interval_seconds:
                    return
                self._download_last_emit_at = now
                total = _coerce_total(getattr(self, "total", 0))
                downloaded = _coerce_total(getattr(self, "n", 0))
                speed = self._download_speed(now, downloaded)
                warning = self._download_health_check(now, downloaded, total, speed)
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
                        warning=warning,
                    ),
                )

            def _download_speed(self, now: float, downloaded: int) -> float | None:
                """Считает сглаженную скорость по скользящему окну байтов."""
                with self._download_state_lock:
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

            def _download_health_check(
                self,
                now: float,
                downloaded: int,
                total: int,
                speed: float | None,
            ) -> str | None:
                """Следит за зависанием и устойчиво низкой скоростью."""
                if not total or downloaded >= total:
                    with self._download_state_lock:
                        self._download_slow_since = None
                        self._download_health_warning = None
                    return None

                warning: str | None = None
                with self._download_state_lock:
                    idle_seconds = now - self._download_last_progress_at
                    if stall_timeout_seconds and downloaded > 0 and idle_seconds >= stall_timeout_seconds:
                        warning = f"загрузка приостановилась на {idle_seconds:.0f} с"
                        if self._download_health_error is None:
                            self._download_health_error = ModelDownloadStalledError(warning)
                            LOGGER.warning(
                                "📥 Загрузка модели приостановилась: label=%s, model=%s, idle_seconds=%.1f",
                                label,
                                model_name,
                                idle_seconds,
                            )
                    elif min_speed_bytes_per_second and speed is not None and speed < min_speed_bytes_per_second:
                        if self._download_slow_since is None:
                            self._download_slow_since = now
                        slow_seconds = now - self._download_slow_since
                        warning = (
                            f"скорость ниже {format_model_download_metrics(min_speed_bytes_per_second, None)}"
                            if slow_seconds < slow_speed_grace_seconds
                            else f"слишком медленно: ниже {format_model_download_metrics(min_speed_bytes_per_second, None)}"
                        )
                        if slow_seconds >= slow_speed_grace_seconds and self._download_health_error is None:
                            self._download_health_error = ModelDownloadTooSlowError(warning)
                            LOGGER.warning(
                                "📥 Загрузка модели слишком медленная: label=%s, model=%s, speed=%.1f B/s, threshold=%.1f B/s",
                                label,
                                model_name,
                                speed,
                                min_speed_bytes_per_second,
                            )
                    else:
                        self._download_slow_since = None

                    if warning is not None:
                        self._download_health_warning = warning
                    elif self._download_health_error is None:
                        self._download_health_warning = None
                    return self._download_health_warning

            def _start_health_monitor(self) -> None:
                """Запускает лёгкий монитор зависания между progress update-ами."""
                if not health_monitor_interval_seconds or not stall_timeout_seconds:
                    return

                def monitor() -> None:
                    while not self._download_monitor_stop.wait(health_monitor_interval_seconds):
                        if not getattr(self, "_download_progress_tracked", False):
                            return
                        self._emit_download_progress(force=True)

                self._download_monitor_thread = threading.Thread(target=monitor, daemon=True)
                self._download_monitor_thread.start()

            def _raise_download_health_error(self) -> None:
                error = getattr(self, "_download_health_error", None)
                if error is not None:
                    raise error

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

    def _is_completed_in_process(self, model_name: str) -> bool:
        """Проверяет, была ли модель уже успешно скачана в текущем запуске."""
        with self._completed_models_lock:
            return model_name in self._completed_models

    def _mark_completed_in_process(self, model_name: str) -> None:
        """Запоминает успешную проверку модели до завершения процесса."""
        with self._completed_models_lock:
            self._completed_models.add(model_name)

    def _remember_local_model_path(self, model_name: str, local_path: str) -> None:
        """Запоминает локальный snapshot path для runtime-loader-ов."""
        with self._completed_models_lock:
            self._local_model_paths[model_name] = local_path

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
        self._verified_models: set[str] = set()
        self._verified_models_lock = threading.Lock()

    def set_progress_callback(self, callback: ProgressCallback | None) -> None:
        """Назначает callback для публикации прогресса в приложение."""
        self._progress_callback = callback

    def is_model_cached(self, model_name: str) -> bool:
        """Проверяет, доступна ли модель локально."""
        return self.is_model_ready(model_name) or self._downloader.is_model_cached(model_name)

    def is_model_ready(self, model_name: str) -> bool:
        """Проверяет, была ли модель подтверждена для runtime в текущем запуске."""
        if _is_local_model_path(model_name):
            return True
        with self._verified_models_lock:
            return model_name in self._verified_models

    def require_model_ready(self, model_name: str, *, label: str) -> None:
        """Прерывает runtime-загрузку, если модель ещё не проверена общим downloader-ом."""
        if self.is_model_ready(model_name):
            return
        raise ModelRequiredError(model_name, label=label)

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
        self._mark_model_ready(model_name)

    def ensure_llm_model_downloaded(
        self,
        model_name: str,
        progress_callback: LegacyProgressCallback | None = None,
    ) -> None:
        """Скачивает LLM-модель через общий менеджер."""
        self.ensure_model_downloaded(model_name, label="LLM-модель", progress_callback=progress_callback)

    def load_llm_runtime_objects(self, model_name: str) -> tuple[Any, Any]:
        """Загружает MLX LLM-модель после проверки общим downloader-ом."""
        self.require_model_ready(model_name, label="LLM-модель")
        runtime_model_name = self._runtime_model_name(model_name)
        if self._lm_loader is None:
            from mlx_lm import load  # noqa: PLC0415

            loaded = load(runtime_model_name)
        else:
            loaded = self._lm_loader(runtime_model_name)
        return loaded[0], loaded[1]

    def load_vlm_runtime_objects(self, model_name: str) -> tuple[Any, Any]:
        """Загружает MLX VLM-модель после проверки общим downloader-ом."""
        self.require_model_ready(model_name, label="VLM-модель")
        runtime_model_name = self._runtime_model_name(model_name)
        loader = self._vlm_loader
        if loader is None:
            from mlx_vlm import load  # noqa: PLC0415

            loader = load
        model, processor = loader(runtime_model_name)
        return model, processor

    def load_qwen_asr_model(self, model_name: str) -> Any:
        """Скачивает и загружает Qwen3-ASR модель через mlx-audio."""
        self.ensure_model_downloaded(model_name, label="ASR-модель")
        runtime_model_name = self._runtime_model_name(model_name)
        loader = self._qwen_asr_loader
        if loader is None:
            try:
                from mlx_audio.stt import load as load_mlx_audio_stt_model  # noqa: PLC0415
            except ImportError as exc:
                raise RuntimeError("Для модели Qwen3-ASR нужна зависимость mlx-audio. Выполните `uv sync --dev`.") from exc
            loader = load_mlx_audio_stt_model
        return loader(runtime_model_name)

    def load_tts_model(self, model_name: str) -> Any:
        """Загружает streaming MLX TTS-модель после проверки общим downloader-ом."""
        self.require_model_ready(model_name, label="TTS-модель")
        runtime_model_name = self._runtime_model_name(model_name)
        loader = self._tts_loader
        if loader is None:
            try:
                from mlx_audio.tts import load as load_mlx_audio_tts_model  # noqa: PLC0415
            except ImportError as exc:
                raise RuntimeError("Для MLX TTS нужна зависимость mlx-audio. Выполните uv sync --dev.") from exc
            loader = load_mlx_audio_tts_model
        return loader(runtime_model_name)

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
        return asr_runtime.run_whisper_transcription(audio_data, self._runtime_model_name(model_name), language)

    def _mark_model_ready(self, model_name: str) -> None:
        """Запоминает успешную проверку модели для последующих runtime-load вызовов."""
        with self._verified_models_lock:
            self._verified_models.add(model_name)

    def _runtime_model_name(self, model_name: str) -> str:
        """Подменяет HF repo id на локальный snapshot path, если он уже есть в cache."""
        if _is_local_model_path(model_name):
            return str(Path(model_name).expanduser())
        resolver = getattr(self._downloader, "get_local_model_path", None)
        if not callable(resolver):
            return model_name
        local_path = resolver(model_name)
        return local_path or model_name


_DEFAULT_MODEL_MANAGER: ModelManager | None = None


def default_model_manager() -> ModelManager:
    """Возвращает общий менеджер моделей для legacy runtime-функций."""
    global _DEFAULT_MODEL_MANAGER  # noqa: PLW0603
    if _DEFAULT_MODEL_MANAGER is None:
        _DEFAULT_MODEL_MANAGER = ModelManager()
    return _DEFAULT_MODEL_MANAGER
