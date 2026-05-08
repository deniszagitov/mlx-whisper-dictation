"""Чистые правила и дефолты модуля чтения буфера обмена."""

from __future__ import annotations

import math
import re
from typing import Final

READER_CLIPBOARD_CHAR_LIMIT: Final = 10_000

DEFAULT_RSVP_HOTKEY: Final = "cmd_l+alt+r"
DEFAULT_TTS_HOTKEY: Final = "cmd_l+alt+t"

DEFAULT_RSVP_WPM: Final = 400
DEFAULT_RSVP_CHUNK_SIZE: Final = 2
DEFAULT_RSVP_FONT_SIZE: Final = 64
DEFAULT_RSVP_BACKGROUND_COLOR: Final = "#111111"
DEFAULT_RSVP_TEXT_COLOR: Final = "#f5f5f5"
DEFAULT_RSVP_ORP_COLOR: Final = "#ffcc33"

RSVP_WPM_OPTIONS: Final = (300, 400, 500, 600, 700)
RSVP_CHUNK_SIZE_OPTIONS: Final = (1, 2, 3)
RSVP_FONT_SIZE_OPTIONS: Final = (48, 64, 80, 96)

DEFAULT_TTS_RATE_MULTIPLIER: Final = 1.0
DEFAULT_TTS_MAX_MINUTES: Final = 5
DEFAULT_TTS_ENGINE: Final = "apple"
DEFAULT_TTS_MLX_MODEL: Final = "mlx-community/Qwen3-TTS-12Hz-1.7B-VoiceDesign-4bit"
DEFAULT_TTS_MLX_VOICE_NAME: Final = "Русский быстрый ассистент-робот"
DEFAULT_TTS_MLX_VOICE_DESCRIPTION: Final = (
    "Быстрый русский голос ассистента-робота: чёткая дикция, собранная энергичная подача, "
    "уверенный техничный тембр, короткие паузы, высокая разборчивость, без эмоциональной драматизации. "
    "Всегда говорит по-русски."
)
DEFAULT_TTS_TONE_INSTRUCTION: Final = ""
TTS_RATE_MULTIPLIER_MIN: Final = 0.1
TTS_RATE_MULTIPLIER_MAX: Final = 3.0
TTS_RATE_MULTIPLIER_STEP: Final = 0.1
TTS_MAX_MINUTES_OPTIONS: Final = (2, 5, 10, 0)
TTS_ENGINE_APPLE: Final = "apple"
TTS_ENGINE_MLX: Final = "mlx"
TTS_ENGINE_OPTIONS: Final = (TTS_ENGINE_APPLE, TTS_ENGINE_MLX)
TTS_ENGINE_LABELS: Final = {
    TTS_ENGINE_APPLE: "Apple AVSpeech",
    TTS_ENGINE_MLX: "MLX Qwen3-TTS",
}
TTS_MLX_MODEL_OPTIONS: Final = (DEFAULT_TTS_MLX_MODEL,)
TTS_MLX_STREAMING_INTERVAL_SECONDS: Final = 0.32
TTS_MLX_LANGUAGE_CODE: Final = "russian"
TTS_MLX_GENERATION_SEED: Final = 42
TTS_MLX_GENERATION_TEMPERATURE: Final = 0.7
TTS_MLX_GENERATION_TOP_P: Final = 0.95
TTS_MLX_GENERATION_TOP_K: Final = 40
TTS_MLX_GENERATION_REPETITION_PENALTY: Final = 1.0
TTS_BASE_WORDS_PER_MINUTE: Final = 170

DEFAULT_READER_PREPROCESS_ENABLED: Final = True
RSVP_PREPROCESS_MAX_TOKENS: Final = 1_200
TTS_PREPROCESS_MAX_TOKENS: Final = 1_000

_WORD_PATTERN = re.compile(r"\S+", flags=re.UNICODE)


def reader_orp_index(word: str) -> int:
    """Возвращает индекс ORP-символа для слова по Spritz-подобному правилу."""
    if not word:
        return 0
    return min(math.floor((len(word) - 1) / 3), 4)


def reader_words(text: str) -> list[str]:
    """Разбивает текст на видимые слова для RSVP без изменения самих токенов."""
    return _WORD_PATTERN.findall(text)


def clamp_rsvp_wpm(value: object) -> int:
    """Возвращает ближайший допустимый темп RSVP."""
    parsed = _parse_int(value)
    if parsed is None:
        return DEFAULT_RSVP_WPM
    if parsed in RSVP_WPM_OPTIONS:
        return parsed
    return DEFAULT_RSVP_WPM


def clamp_rsvp_chunk_size(value: object) -> int:
    """Возвращает допустимый размер RSVP chunk-а."""
    parsed = _parse_int(value)
    if parsed is None:
        return DEFAULT_RSVP_CHUNK_SIZE
    if parsed in RSVP_CHUNK_SIZE_OPTIONS:
        return parsed
    return DEFAULT_RSVP_CHUNK_SIZE


def clamp_rsvp_font_size(value: object) -> int:
    """Возвращает допустимый размер шрифта RSVP."""
    parsed = _parse_int(value)
    if parsed is None:
        return DEFAULT_RSVP_FONT_SIZE
    if parsed in RSVP_FONT_SIZE_OPTIONS:
        return parsed
    return DEFAULT_RSVP_FONT_SIZE


def clamp_tts_rate_multiplier(value: object) -> float:
    """Возвращает допустимый множитель скорости TTS в непрерывном диапазоне."""
    parsed = _parse_float(value)
    if parsed is None or not math.isfinite(parsed):
        return DEFAULT_TTS_RATE_MULTIPLIER
    clamped = min(max(parsed, TTS_RATE_MULTIPLIER_MIN), TTS_RATE_MULTIPLIER_MAX)
    return round(clamped, 2)


def clamp_tts_max_minutes(value: object) -> int:
    """Возвращает допустимый лимит длительности TTS в минутах; 0 означает без лимита."""
    parsed = _parse_int(value)
    if parsed is None:
        return DEFAULT_TTS_MAX_MINUTES
    if parsed in TTS_MAX_MINUTES_OPTIONS:
        return parsed
    return DEFAULT_TTS_MAX_MINUTES


def clamp_tts_engine(value: object) -> str:
    """Возвращает допустимый backend TTS."""
    normalized = str(value or "").strip().lower()
    if normalized in TTS_ENGINE_OPTIONS:
        return normalized
    return DEFAULT_TTS_ENGINE


def normalize_tts_mlx_model(value: object) -> str:
    """Возвращает имя MLX TTS-модели."""
    normalized = str(value or "").strip()
    return normalized or DEFAULT_TTS_MLX_MODEL


def normalize_tts_mlx_voice_description(value: object, *, mlx_model: object = DEFAULT_TTS_MLX_MODEL) -> str:
    """Возвращает описание голоса для VoiceDesign TTS-модели."""
    if normalize_tts_mlx_model(mlx_model) == DEFAULT_TTS_MLX_MODEL:
        return DEFAULT_TTS_MLX_VOICE_DESCRIPTION
    normalized = str(value or "").strip()
    return normalized or DEFAULT_TTS_MLX_VOICE_DESCRIPTION


def normalize_tts_tone_instruction(value: object) -> str:
    """Возвращает свободную инструкцию по интонации TTS."""
    return " ".join(str(value or "").strip().split())


def build_tts_mlx_instruct(voice_description: object, tone_instruction: object) -> str:
    """Собирает итоговый VoiceDesign instruct для MLX TTS."""
    voice = str(voice_description or DEFAULT_TTS_MLX_VOICE_DESCRIPTION).strip() or DEFAULT_TTS_MLX_VOICE_DESCRIPTION
    tone = normalize_tts_tone_instruction(tone_instruction)
    if not tone:
        return voice
    return f"{voice}\nИнтонация TTS: {tone}."


def estimate_rsvp_duration_seconds(word_count: int, wpm: int) -> float:
    """Оценивает длительность RSVP-воспроизведения по количеству слов и wpm."""
    if word_count <= 0 or wpm <= 0:
        return 0.0
    return word_count / wpm * 60.0


def rsvp_frame_interval_seconds(chunk_size: int, wpm: int) -> float:
    """Возвращает интервал между RSVP-кадрами для сохранения заданного wpm."""
    safe_chunk_size = max(1, chunk_size)
    safe_wpm = max(1, wpm)
    return safe_chunk_size / safe_wpm * 60.0


def tts_max_words(max_minutes: int, rate_multiplier: float) -> int | None:
    """Возвращает примерный лимит слов для TTS или None для режима без лимита."""
    if max_minutes <= 0:
        return None
    return max(1, int(TTS_BASE_WORDS_PER_MINUTE * max_minutes * max(rate_multiplier, 0.1)))


def _parse_int(value: object) -> int | None:
    """Безопасно приводит persistence-значение к int."""
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError:
            return None
    return None


def _parse_float(value: object) -> float | None:
    """Безопасно приводит persistence-значение к float."""
    if isinstance(value, bool):
        return float(value)
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value.replace(",", "."))
        except ValueError:
            return None
    return None
