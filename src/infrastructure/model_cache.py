"""Runtime-операции с локальным Hugging Face cache для скачиваемых моделей."""

from __future__ import annotations

import logging
import threading
from pathlib import Path
from typing import TYPE_CHECKING, Any

from huggingface_hub import constants, scan_cache_dir, snapshot_download

from ..domain.constants import Config

if TYPE_CHECKING:
    from collections.abc import Callable

LOGGER = logging.getLogger(__name__)


def is_huggingface_model_id(model_id: str) -> bool:
    """Сообщает, похожа ли строка на Hugging Face repo id, а не на локальный путь."""
    normalized = str(model_id or "").strip()
    if not normalized or "://" in normalized:
        return False
    expanded_path = Path(normalized).expanduser()
    if expanded_path.is_absolute() or normalized.startswith((".", "~")):
        return False
    return normalized.count("/") == 1 and all(part.strip() for part in normalized.split("/", maxsplit=1))


def is_model_cached(model_id: str) -> bool:
    """Проверяет, доступна ли модель локально: как путь или как Hugging Face snapshot."""
    normalized = str(model_id or "").strip()
    if not normalized:
        return False
    local_path = Path(normalized).expanduser()
    if local_path.exists():
        return True
    if not is_huggingface_model_id(normalized):
        return False

    repo_cache_path = _repo_cache_path(normalized)
    snapshots_dir = repo_cache_path / "snapshots"
    if not snapshots_dir.is_dir():
        return False
    return any(path.is_dir() and any(path.iterdir()) for path in snapshots_dir.iterdir())


def ensure_model_downloaded(
    model_id: str,
    progress_callback: Callable[[str, float, int], None] | None = None,
) -> None:
    """Скачивает Hugging Face модель в локальный cache с прогрессом для UI."""
    if not is_huggingface_model_id(model_id):
        raise RuntimeError(f"Модель нельзя скачать автоматически: {model_id}")

    class _ProgressTqdm:
        """Минимальная tqdm-совместимая обёртка для snapshot_download."""

        _lock = None

        def __init__(self, iterable: Any = None, *args: Any, **kwargs: Any) -> None:
            self._iterable = iterable
            self.total: int | float = int(kwargs.get("total", 0) or 0)
            self.desc = str(kwargs.get("desc", ""))
            self.n = 0

        def __iter__(self) -> Any:
            """Проксирует итерацию и обновляет прогресс."""
            if self._iterable is None:
                return
            for item in self._iterable:
                yield item
                self.update(1)

        def update(self, n: int = 1) -> None:
            """Передаёт приблизительный процент загрузки во внешний callback."""
            self.n += n
            if progress_callback is not None and self.total and self.total > 0:
                pct = min(self.n / self.total * Config.DOWNLOAD_COMPLETE_PCT, Config.DOWNLOAD_COMPLETE_PCT)
                progress_callback(self.desc, pct, int(self.total))

        def close(self) -> None:
            """Совместимость с tqdm API."""

        def __enter__(self) -> _ProgressTqdm:
            """Context manager вход."""
            return self

        def __exit__(self, *args: object) -> None:
            """Context manager выход."""

        @classmethod
        def get_lock(cls) -> Any:
            """Возвращает lock для tqdm.contrib.concurrent.ensure_lock."""
            if cls._lock is None:
                cls._lock = threading.Lock()
            return cls._lock

        @classmethod
        def set_lock(cls, lock: Any) -> None:
            """Устанавливает lock для tqdm.contrib.concurrent.ensure_lock."""
            cls._lock = lock

    if progress_callback is not None:
        progress_callback("Подготовка…", 0, 0)

    snapshot_download(model_id, tqdm_class=_ProgressTqdm)

    if progress_callback is not None:
        progress_callback("", Config.DOWNLOAD_COMPLETE_PCT, 0)


def delete_cached_model(model_id: str) -> bool:
    """Удаляет все cached revisions указанной Hugging Face модели."""
    if not is_huggingface_model_id(model_id):
        return False

    cache_info = scan_cache_dir()
    repo_info = next((repo for repo in cache_info.repos if repo.repo_id == model_id and repo.repo_type == "model"), None)
    if repo_info is None:
        return False

    revision_hashes = [revision.commit_hash for revision in repo_info.revisions]
    if not revision_hashes:
        return False

    LOGGER.info("🧹 Удаляю cached модель Hugging Face: %s", model_id)
    delete_strategy = cache_info.delete_revisions(*revision_hashes)
    delete_strategy.execute()
    return True


def _repo_cache_path(model_id: str) -> Path:
    """Возвращает стандартный путь repo в Hugging Face cache."""
    return Path(constants.HF_HUB_CACHE) / f"models--{model_id.replace('/', '--')}"
