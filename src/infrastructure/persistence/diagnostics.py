"""Логирование и сохранение диагностических артефактов приложения."""

from __future__ import annotations

import json
import logging
import logging.handlers
import sys
import time
import wave
from pathlib import Path
from typing import TYPE_CHECKING, Any

import numpy as np
import numpy.typing as npt

from ...domain.constants import Config
from ...domain.logging import DICTATION_LOGGER_NAME
from ...domain.types import RecordedAudio

if TYPE_CHECKING:
    from ...domain.types import AudioDiagnostics, PreprocessedAudio


class MaxLevelFilter(logging.Filter):
    """Пропускает записи не выше заданного уровня логирования."""

    def __init__(self, level: int) -> None:
        """Сохраняет максимальный уровень логов для фильтрации."""
        super().__init__()
        self.level = level

    def filter(self, record: logging.LogRecord) -> bool:
        """Возвращает True, если запись не превышает допустимый уровень."""
        return record.levelno < self.level


def _cleanup_expired_files(directory: Path, pattern: str, retention_seconds: float, *, include_current_file: bool = False) -> None:
    """Удаляет файлы старше retention_seconds."""
    threshold = time.time() - retention_seconds
    for path in directory.glob(pattern):
        if not path.is_file():
            continue
        if not include_current_file and path.name in {"stdout.log", "stderr.log"}:
            continue
        if path.stat().st_mtime <= threshold:
            path.unlink(missing_ok=True)


class DailyRetentionFileHandler(logging.handlers.TimedRotatingFileHandler):
    """Ротирует лог-файл раз в 24 часа и удаляет старые файлы."""

    def __init__(self, filename: str | Path, *, retention_seconds: float = Config.ARTIFACT_TTL_SECONDS, **kwargs: Any) -> None:
        self.retention_seconds = retention_seconds
        super().__init__(filename, when="H", interval=24, backupCount=0, **kwargs)
        self._cleanup_expired_log_family()

    def doRollover(self) -> None:
        """Создает новый суточный лог-файл и чистит просроченные ротации."""
        super().doRollover()
        self._cleanup_expired_log_family()

    def _cleanup_expired_log_family(self) -> None:
        """Удаляет старые файлы текущего лог-семейства."""
        base_path = Path(self.baseFilename)
        _cleanup_expired_files(base_path.parent, f"{base_path.name}*", self.retention_seconds)


def _replace_logger_handlers(logger: logging.Logger) -> None:
    """Закрывает старые handler-ы и очищает конфигурацию логгера."""
    for handler in logger.handlers:
        handler.close()
    logger.handlers.clear()


def setup_logging() -> None:
    """Настраивает консольное и файловое логирование приложения."""
    Config.LOG_DIR.mkdir(parents=True, exist_ok=True)
    _cleanup_expired_files(Config.LOG_DIR, "*.log*", Config.ARTIFACT_TTL_SECONDS, include_current_file=True)

    formatter = logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
    root_logger = logging.getLogger()
    dictation_logger = logging.getLogger(DICTATION_LOGGER_NAME)
    root_logger.setLevel(logging.INFO)
    dictation_logger.setLevel(logging.INFO)
    dictation_logger.propagate = False
    _replace_logger_handlers(root_logger)
    _replace_logger_handlers(dictation_logger)

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(formatter)

    stdout_handler = DailyRetentionFileHandler(
        Config.LOG_DIR / "stdout.log",
        encoding="utf-8",
    )
    stdout_handler.setLevel(logging.INFO)
    stdout_handler.addFilter(MaxLevelFilter(logging.ERROR))
    stdout_handler.setFormatter(formatter)

    stderr_handler = DailyRetentionFileHandler(
        Config.LOG_DIR / "stderr.log",
        encoding="utf-8",
    )
    stderr_handler.setLevel(logging.ERROR)
    stderr_handler.setFormatter(formatter)

    dictation_handler = DailyRetentionFileHandler(
        Config.LOG_DIR / "dictation.log",
        encoding="utf-8",
    )
    dictation_handler.setLevel(logging.INFO)
    dictation_handler.setFormatter(formatter)

    root_logger.addHandler(console_handler)
    root_logger.addHandler(stdout_handler)
    root_logger.addHandler(stderr_handler)
    dictation_logger.addHandler(dictation_handler)


class DiagnosticsStore:
    """Изолирует сохранение диагностических артефактов от основного runtime-кода."""

    def __init__(
        self,
        root_dir: str | Path = Config.LOG_DIR,
        enabled: bool = True,
        max_artifacts: int = Config.MAX_DEBUG_ARTIFACTS,
        retention_seconds: float = Config.ARTIFACT_TTL_SECONDS,
        recording_artifact_cleanup_enabled: bool = False,
    ) -> None:
        """Создает хранилище диагностических файлов.

        Args:
            root_dir: Корневая директория логов и артефактов.
            enabled: Нужно ли сохранять диагностические файлы.
            max_artifacts: Устаревший аргумент, сохранён только для совместимости.
            retention_seconds: Время жизни диагностических артефактов в секундах.
            recording_artifact_cleanup_enabled: Нужно ли удалять старые raw/final WAV-артефакты.
        """
        self.root_dir = Path(root_dir)
        self.enabled = enabled
        self.max_artifacts = max_artifacts
        self.retention_seconds = retention_seconds
        self.recording_artifact_cleanup_enabled = recording_artifact_cleanup_enabled

    @property
    def recordings_dir(self) -> Path:
        """Возвращает путь к папке с диагностическими аудиозаписями."""
        return self.root_dir / "recordings"

    @property
    def transcriptions_dir(self) -> Path:
        """Возвращает путь к папке с диагностическими транскрипциями."""
        return self.root_dir / "transcriptions"

    def artifact_stem(self) -> str:
        """Возвращает уникальное имя группы диагностических файлов."""
        timestamp = time.strftime("%Y%m%d-%H%M%S")
        milliseconds = int((time.time() % 1) * 1000)
        return f"{timestamp}-{milliseconds:03d}"

    def _cleanup_directory(self, directory: Path) -> None:
        """Удаляет диагностические файлы старше retention_seconds."""
        _cleanup_expired_files(directory, "*", self.retention_seconds, include_current_file=True)

    def set_recording_artifact_cleanup_enabled(self, enabled: object) -> None:
        """Переключает автоочистку WAV-артефактов записи."""
        self.recording_artifact_cleanup_enabled = bool(enabled)

    def _cleanup_recordings_directory(self) -> None:
        """Удаляет старые WAV/JSON записи только если автоочистка включена."""
        if self.recording_artifact_cleanup_enabled:
            self._cleanup_directory(self.recordings_dir)

    def build_audio_diagnostics(self, audio_data: npt.NDArray[np.float32], language: str | None) -> AudioDiagnostics:
        """Собирает компактную диагностику входного аудиосигнала."""
        audio_duration_seconds = len(audio_data) / Config.AUDIO_SAMPLE_RATE
        rms_energy = float(np.sqrt(np.mean(audio_data**2)))
        peak_amplitude = float(np.max(np.abs(audio_data))) if len(audio_data) else 0.0
        return {
            "language": language,
            "duration_seconds": audio_duration_seconds,
            "rms_energy": rms_energy,
            "peak_amplitude": peak_amplitude,
            "silence_threshold": Config.SILENCE_RMS_THRESHOLD,
            "hallucination_threshold": Config.HALLUCINATION_RMS_THRESHOLD,
            "sample_rate": Config.AUDIO_SAMPLE_RATE,
            "samples": len(audio_data),
            "first_samples": audio_data[:16].tolist(),
        }

    def _write_pcm16_wav(self, wav_path: Path, audio_data: npt.NDArray[np.float32], sample_rate: int) -> None:
        """Пишет float32 waveform как PCM16 WAV."""
        with wave.open(str(wav_path), "wb") as wav_file:
            wav_file.setnchannels(1)
            wav_file.setsampwidth(2)
            wav_file.setframerate(sample_rate)
            pcm_data = np.clip(audio_data * 32768.0, -32768, 32767).astype(np.int16)
            wav_file.writeframes(pcm_data.tobytes())

    def _recorded_audio_to_float32(self, recorded_audio: RecordedAudio) -> npt.NDArray[np.float32]:
        """Готовит сырую запись к diagnostic WAV без resampling."""
        samples = np.asarray(recorded_audio.samples)
        channels = max(int(recorded_audio.channels), 1)
        if channels > 1:
            usable_length = (len(samples) // channels) * channels
            samples = samples[:usable_length].reshape(-1, channels).mean(axis=1)
        if recorded_audio.sample_format == "int16" or samples.dtype == np.int16:
            return (samples.astype(np.float32) / 32768.0).astype(np.float32, copy=False)
        return np.clip(samples.astype(np.float32, copy=False), -1.0, 1.0)

    def save_audio_recording(
        self,
        stem: str,
        audio_data: npt.NDArray[np.float32],
        diagnostics: AudioDiagnostics | dict[str, Any],
    ) -> Path | None:
        """Сохраняет финальную аудиозапись и метаданные, если диагностика включена."""
        if not self.enabled:
            return None

        self.recordings_dir.mkdir(parents=True, exist_ok=True)
        wav_path = self.recordings_dir / f"{stem}.wav"
        self._write_pcm16_wav(wav_path, audio_data, Config.AUDIO_SAMPLE_RATE)

        metadata_path = self.recordings_dir / f"{stem}.json"
        metadata_path.write_text(json.dumps(diagnostics, ensure_ascii=False, indent=2), encoding="utf-8")
        self._cleanup_recordings_directory()
        return wav_path

    def save_recording_artifacts(
        self,
        stem: str,
        raw_audio: RecordedAudio | object,
        preprocessed_audio: PreprocessedAudio,
        diagnostics: dict[str, Any],
    ) -> dict[str, str] | None:
        """Сохраняет raw/final WAV и общие metadata для завершённой записи."""
        if not self.enabled:
            return None

        self.recordings_dir.mkdir(parents=True, exist_ok=True)

        if isinstance(raw_audio, RecordedAudio):
            raw_sample_rate = int(raw_audio.sample_rate)
            raw_audio_data = self._recorded_audio_to_float32(raw_audio)
        else:
            raw_sample_rate = Config.AUDIO_SAMPLE_RATE
            raw_audio_data = np.asarray(raw_audio, dtype=np.float32)

        raw_wav_path = self.recordings_dir / f"{stem}.raw.wav"
        final_wav_path = self.recordings_dir / f"{stem}.final.wav"
        metadata_path = self.recordings_dir / f"{stem}.json"

        self._write_pcm16_wav(raw_wav_path, raw_audio_data, raw_sample_rate)
        self._write_pcm16_wav(final_wav_path, preprocessed_audio.audio, preprocessed_audio.sample_rate)
        metadata_path.write_text(json.dumps(diagnostics, ensure_ascii=False, indent=2, default=str), encoding="utf-8")

        self._cleanup_recordings_directory()
        return {
            "raw_wav": str(raw_wav_path),
            "final_wav": str(final_wav_path),
            "metadata": str(metadata_path),
        }

    def save_transcription_artifacts(
        self,
        stem: str,
        diagnostics: AudioDiagnostics,
        result: Any = None,
        text: str = "",
        error_message: str | None = None,
    ) -> Path | None:
        """Сохраняет результат распознавания и метаданные, если диагностика включена."""
        if not self.enabled:
            return None

        self.transcriptions_dir.mkdir(parents=True, exist_ok=True)
        payload = {"diagnostics": diagnostics, "text": text, "error": error_message, "result": result}
        json_path = self.transcriptions_dir / f"{stem}.json"
        json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8")

        text_path = self.transcriptions_dir / f"{stem}.txt"
        text_path.write_text(text, encoding="utf-8")

        self._cleanup_directory(self.transcriptions_dir)
        return json_path
