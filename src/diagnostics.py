"""Логирование и диагностика приложения Dictator.

Содержит настройку логирования, фильтры, хранилище диагностических
артефактов и функцию проверки галлюцинаций Whisper.
"""

import json
import logging
import logging.handlers
import sys
import time
import wave
from pathlib import Path

import numpy as np

from config import (
    HALLUCINATION_RMS_THRESHOLD,
    KNOWN_HALLUCINATIONS,
    LOG_DIR,
    MAX_DEBUG_ARTIFACTS,
    SILENCE_RMS_THRESHOLD,
)


class MaxLevelFilter(logging.Filter):
    """Пропускает записи не выше заданного уровня логирования."""

    def __init__(self, level):
        """Сохраняет максимальный уровень логов для фильтрации."""
        super().__init__()
        self.level = level

    def filter(self, record):
        """Возвращает True, если запись не превышает допустимый уровень."""
        return record.levelno < self.level


def setup_logging():
    """Настраивает консольное и файловое логирование приложения."""
    LOG_DIR.mkdir(parents=True, exist_ok=True)

    formatter = logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)
    root_logger.handlers.clear()

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(formatter)

    stdout_handler = logging.handlers.RotatingFileHandler(
        LOG_DIR / "stdout.log",
        maxBytes=5_000_000,
        backupCount=3,
        encoding="utf-8",
    )
    stdout_handler.setLevel(logging.INFO)
    stdout_handler.addFilter(MaxLevelFilter(logging.ERROR))
    stdout_handler.setFormatter(formatter)

    stderr_handler = logging.handlers.RotatingFileHandler(
        LOG_DIR / "stderr.log",
        maxBytes=5_000_000,
        backupCount=3,
        encoding="utf-8",
    )
    stderr_handler.setLevel(logging.ERROR)
    stderr_handler.setFormatter(formatter)

    root_logger.addHandler(console_handler)
    root_logger.addHandler(stdout_handler)
    root_logger.addHandler(stderr_handler)


def looks_like_hallucination(text):
    """Проверяет, похож ли результат на типичную галлюцинацию Whisper."""
    return text.strip().lower() in KNOWN_HALLUCINATIONS


class DiagnosticsStore:
    """Изолирует сохранение диагностических артефактов от основного runtime-кода."""

    def __init__(self, root_dir=LOG_DIR, enabled=True, max_artifacts=MAX_DEBUG_ARTIFACTS):
        """Создает хранилище диагностических файлов.

        Args:
            root_dir: Корневая директория логов и артефактов.
            enabled: Нужно ли сохранять диагностические файлы.
            max_artifacts: Сколько последних наборов артефактов хранить.
        """
        self.root_dir = Path(root_dir)
        self.enabled = enabled
        self.max_artifacts = max_artifacts

    @property
    def recordings_dir(self):
        """Возвращает путь к папке с диагностическими аудиозаписями."""
        return self.root_dir / "recordings"

    @property
    def transcriptions_dir(self):
        """Возвращает путь к папке с диагностическими транскрипциями."""
        return self.root_dir / "transcriptions"

    def artifact_stem(self):
        """Возвращает уникальное имя группы диагностических файлов."""
        timestamp = time.strftime("%Y%m%d-%H%M%S")
        milliseconds = int((time.time() % 1) * 1000)
        return f"{timestamp}-{milliseconds:03d}"

    def _cleanup_directory(self, directory):
        """Оставляет только последние диагностические файлы в указанной директории."""
        stems_to_mtime = {}
        for path in directory.iterdir():
            if path.is_file():
                stems_to_mtime[path.stem] = max(stems_to_mtime.get(path.stem, 0.0), path.stat().st_mtime)

        sorted_stems = sorted(stems_to_mtime.items(), key=lambda item: item[1], reverse=True)
        stems_to_keep = {stem for stem, _mtime in sorted_stems[: self.max_artifacts]}

        for old_file in directory.iterdir():
            if old_file.is_file() and old_file.stem not in stems_to_keep:
                old_file.unlink(missing_ok=True)

    def build_audio_diagnostics(self, audio_data, language):
        """Собирает компактную диагностику входного аудиосигнала."""
        audio_duration_seconds = len(audio_data) / 16000
        rms_energy = float(np.sqrt(np.mean(audio_data**2)))
        peak_amplitude = float(np.max(np.abs(audio_data))) if len(audio_data) else 0.0
        return {
            "language": language,
            "duration_seconds": audio_duration_seconds,
            "rms_energy": rms_energy,
            "peak_amplitude": peak_amplitude,
            "silence_threshold": SILENCE_RMS_THRESHOLD,
            "hallucination_threshold": HALLUCINATION_RMS_THRESHOLD,
            "sample_rate": 16000,
            "samples": len(audio_data),
            "first_samples": audio_data[:16].tolist(),
        }

    def save_audio_recording(self, stem, audio_data, diagnostics):
        """Сохраняет аудиозапись и метаданные, если диагностика включена."""
        if not self.enabled:
            return None

        self.recordings_dir.mkdir(parents=True, exist_ok=True)
        wav_path = self.recordings_dir / f"{stem}.wav"
        with wave.open(str(wav_path), "wb") as wav_file:
            wav_file.setnchannels(1)
            wav_file.setsampwidth(2)
            wav_file.setframerate(16000)
            pcm_data = np.clip(audio_data * 32768.0, -32768, 32767).astype(np.int16)
            wav_file.writeframes(pcm_data.tobytes())

        metadata_path = self.recordings_dir / f"{stem}.json"
        metadata_path.write_text(json.dumps(diagnostics, ensure_ascii=False, indent=2), encoding="utf-8")
        self._cleanup_directory(self.recordings_dir)
        return wav_path

    def save_transcription_artifacts(self, stem, diagnostics, result=None, text="", error_message=None):
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
