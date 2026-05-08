"""Доменные типы и форматирование прогресса загрузки моделей."""

from __future__ import annotations

from dataclasses import dataclass

from .constants import Config

BYTES_PER_UNIT = 1024
COMPACT_DECIMAL_THRESHOLD = 10


@dataclass(frozen=True, slots=True)
class ModelDownloadProgress:
    """Снимок прогресса загрузки локальной MLX-модели."""

    label: str
    model_name: str
    stage: str
    downloaded_bytes: int = 0
    total_bytes: int = 0
    percent: float = 0.0
    speed_bytes_per_second: float | None = None
    eta_seconds: float | None = None
    warning: str | None = None
    complete: bool = False
    failed: bool = False


class ModelRequiredError(RuntimeError):
    """Сигнал runtime-слоя: модель нужно скачать вне текущего контекста."""

    def __init__(self, model_name: str, *, label: str) -> None:
        self.model_name = model_name
        self.label = label
        super().__init__(f"{label} не готова к локальному запуску: {model_name}")


def format_bytes(value: float | int) -> str:
    """Форматирует размер в компактную строку для меню."""
    size = float(max(value, 0))
    units = ("Б", "КБ", "МБ", "ГБ", "ТБ")
    unit_index = 0
    while size >= BYTES_PER_UNIT and unit_index < len(units) - 1:
        size /= BYTES_PER_UNIT
        unit_index += 1
    if unit_index == 0:
        return f"{size:.0f} {units[unit_index]}"
    if size >= COMPACT_DECIMAL_THRESHOLD or size.is_integer():
        return f"{size:.0f} {units[unit_index]}"
    return f"{size:.1f} {units[unit_index]}"


def format_duration(seconds: float | int | None) -> str:
    """Форматирует оставшееся время загрузки."""
    if seconds is None or seconds < 0:
        return "неизвестно"
    total_seconds = round(seconds)
    minutes, remainder = divmod(total_seconds, 60)
    hours, minutes = divmod(minutes, 60)
    if hours:
        return f"{hours} ч {minutes:02d} мин"
    if minutes:
        return f"{minutes} мин {remainder:02d} с"
    return f"{remainder} с"


def format_model_download_metrics(
    speed_bytes_per_second: float | None,
    eta_seconds: float | None,
) -> str:
    """Форматирует скорость и прогноз времени для строки прогресса."""
    parts: list[str] = []
    if speed_bytes_per_second is not None and speed_bytes_per_second > 0:
        parts.append(f"{format_bytes(speed_bytes_per_second)}/с")
    if eta_seconds is not None and eta_seconds >= 0:
        parts.append(f"осталось {format_duration(eta_seconds)}")
    return " · ".join(parts)


def format_model_download_title(progress: ModelDownloadProgress) -> str:
    """Возвращает пользовательскую строку прогресса загрузки модели."""
    if progress.failed:
        details = f": {progress.warning}" if progress.warning else " загрузки"
        return f"❌ {progress.label}: ошибка{details}"
    if progress.complete or progress.percent >= Config.DOWNLOAD_COMPLETE_PCT:
        return f"✅ {progress.label}: загружена"

    metrics = format_model_download_metrics(progress.speed_bytes_per_second, progress.eta_seconds)
    suffix = f" · {metrics}" if metrics else ""
    prefix = "⚠️" if progress.warning else "📥"
    warning = f" · {progress.warning}" if progress.warning else ""
    if progress.total_bytes > 0:
        loaded = format_bytes(progress.downloaded_bytes)
        total = format_bytes(progress.total_bytes)
        return f"{prefix} {progress.label}: {progress.percent:.0f}% ({loaded}/{total}){warning}{suffix}"
    stage = progress.stage.strip() or "подготовка"
    return f"{prefix} {progress.label}: {stage}{warning}{suffix}"
