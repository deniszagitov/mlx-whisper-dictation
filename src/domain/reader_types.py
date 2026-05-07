"""Доменные типы и порты модуля чтения буфера обмена."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Protocol

from .constants import Config
from .hotkeys import format_hotkey_status, normalize_key_combination
from .reader_constants import (
    DEFAULT_READER_PREPROCESS_ENABLED,
    DEFAULT_RSVP_BACKGROUND_COLOR,
    DEFAULT_RSVP_CHUNK_SIZE,
    DEFAULT_RSVP_FONT_SIZE,
    DEFAULT_RSVP_HOTKEY,
    DEFAULT_RSVP_ORP_COLOR,
    DEFAULT_RSVP_TEXT_COLOR,
    DEFAULT_RSVP_WPM,
    DEFAULT_TTS_ENGINE,
    DEFAULT_TTS_HOTKEY,
    DEFAULT_TTS_MAX_MINUTES,
    DEFAULT_TTS_MLX_MODEL,
    DEFAULT_TTS_MLX_VOICE_DESCRIPTION,
    DEFAULT_TTS_RATE_MULTIPLIER,
    clamp_rsvp_chunk_size,
    clamp_rsvp_font_size,
    clamp_rsvp_wpm,
    clamp_tts_engine,
    clamp_tts_max_minutes,
    clamp_tts_rate_multiplier,
    normalize_tts_mlx_model,
    normalize_tts_mlx_voice_description,
    reader_orp_index,
    reader_words,
)


class OutputMode(Enum):
    """Режим выдачи результата reader-сценария."""

    RSVP = "rsvp"
    TTS = "tts"


@dataclass(frozen=True, slots=True)
class ClipboardContent:
    """Снимок текстового состояния системного буфера обмена."""

    text: str | None
    has_text_type: bool


@dataclass(frozen=True, slots=True)
class ProcessedText:
    """Результат подготовки текста для быстрого восприятия."""

    text: str
    mode: OutputMode
    source_char_count: int
    truncated: bool = False
    used_fallback: bool = False


@dataclass(frozen=True, slots=True)
class RSVPToken:
    """Один видимый RSVP-токен с рассчитанной точкой ORP."""

    text: str
    orp_index: int

    @classmethod
    def from_text(cls, text: str) -> RSVPToken:
        """Создаёт токен из слова и рассчитывает ORP."""
        return cls(text=text, orp_index=reader_orp_index(text))


@dataclass(frozen=True, slots=True)
class RSVPFrame:
    """Один кадр RSVP-показа, содержащий один или несколько токенов."""

    tokens: tuple[RSVPToken, ...]

    @property
    def word_count(self) -> int:
        """Возвращает количество слов в кадре."""
        return len(self.tokens)

    @property
    def text(self) -> str:
        """Возвращает plain text кадра."""
        return " ".join(token.text for token in self.tokens)


@dataclass(frozen=True, slots=True)
class RSVPConfig:
    """Настройки RSVP-дисплея."""

    wpm: int = DEFAULT_RSVP_WPM
    chunk_size: int = DEFAULT_RSVP_CHUNK_SIZE
    font_size: int = DEFAULT_RSVP_FONT_SIZE
    background_color: str = DEFAULT_RSVP_BACKGROUND_COLOR
    text_color: str = DEFAULT_RSVP_TEXT_COLOR
    orp_color: str = DEFAULT_RSVP_ORP_COLOR

    @classmethod
    def from_values(
        cls,
        *,
        wpm: object,
        chunk_size: object,
        font_size: object,
        background_color: object = DEFAULT_RSVP_BACKGROUND_COLOR,
        text_color: object = DEFAULT_RSVP_TEXT_COLOR,
        orp_color: object = DEFAULT_RSVP_ORP_COLOR,
    ) -> RSVPConfig:
        """Создаёт валидный RSVPConfig из сырых persistence-значений."""
        return cls(
            wpm=clamp_rsvp_wpm(wpm),
            chunk_size=clamp_rsvp_chunk_size(chunk_size),
            font_size=clamp_rsvp_font_size(font_size),
            background_color=str(background_color or DEFAULT_RSVP_BACKGROUND_COLOR),
            text_color=str(text_color or DEFAULT_RSVP_TEXT_COLOR),
            orp_color=str(orp_color or DEFAULT_RSVP_ORP_COLOR),
        )


@dataclass(frozen=True, slots=True)
class TTSConfig:
    """Настройки локального голосового воспроизведения."""

    rate_multiplier: float = DEFAULT_TTS_RATE_MULTIPLIER
    voice_id: str | None = None
    max_minutes: int = DEFAULT_TTS_MAX_MINUTES
    engine: str = DEFAULT_TTS_ENGINE
    mlx_model: str = DEFAULT_TTS_MLX_MODEL
    mlx_voice_description: str = DEFAULT_TTS_MLX_VOICE_DESCRIPTION

    @classmethod
    def from_values(
        cls,
        *,
        rate_multiplier: object,
        voice_id: object,
        max_minutes: object = DEFAULT_TTS_MAX_MINUTES,
        engine: object = DEFAULT_TTS_ENGINE,
        mlx_model: object = DEFAULT_TTS_MLX_MODEL,
        mlx_voice_description: object = DEFAULT_TTS_MLX_VOICE_DESCRIPTION,
    ) -> TTSConfig:
        """Создаёт валидный TTSConfig из сырых persistence-значений."""
        normalized_voice = None if voice_id is None else str(voice_id).strip() or None
        return cls(
            rate_multiplier=clamp_tts_rate_multiplier(rate_multiplier),
            voice_id=normalized_voice,
            max_minutes=clamp_tts_max_minutes(max_minutes),
            engine=clamp_tts_engine(engine),
            mlx_model=normalize_tts_mlx_model(mlx_model),
            mlx_voice_description=normalize_tts_mlx_voice_description(mlx_voice_description),
        )


@dataclass(frozen=True, slots=True)
class TTSVoice:
    """Описание системного голоса TTS."""

    identifier: str
    name: str
    language: str

    @property
    def menu_title(self) -> str:
        """Возвращает подпись голоса для меню."""
        if self.language:
            return f"{self.name} ({self.language})"
        return self.name


@dataclass(frozen=True, slots=True)
class ReaderPreferences:
    """Сохранённые настройки reader-модуля."""

    rsvp_hotkey: str
    tts_hotkey: str
    rsvp_config: RSVPConfig
    tts_config: TTSConfig
    preprocess_model: str
    preprocess_enabled: bool

    @classmethod
    def from_store(cls, settings_store: Any, *, llm_model: str) -> ReaderPreferences:
        """Читает reader-настройки из persistence-слоя."""
        rsvp_hotkey = _load_optional_hotkey(
            settings_store.load_str(Config.DEFAULTS_KEY_READER_RSVP_HOTKEY, fallback=DEFAULT_RSVP_HOTKEY),
            fallback=DEFAULT_RSVP_HOTKEY,
        )
        tts_hotkey = _load_optional_hotkey(
            settings_store.load_str(Config.DEFAULTS_KEY_READER_TTS_HOTKEY, fallback=DEFAULT_TTS_HOTKEY),
            fallback=DEFAULT_TTS_HOTKEY,
        )
        preprocess_model = settings_store.load_str(Config.DEFAULTS_KEY_READER_PREPROCESS_MODEL, fallback=llm_model)
        return cls(
            rsvp_hotkey=rsvp_hotkey,
            tts_hotkey=tts_hotkey,
            rsvp_config=RSVPConfig.from_values(
                wpm=settings_store.load_int(Config.DEFAULTS_KEY_READER_RSVP_WPM, fallback=DEFAULT_RSVP_WPM),
                chunk_size=settings_store.load_int(
                    Config.DEFAULTS_KEY_READER_RSVP_CHUNK_SIZE,
                    fallback=DEFAULT_RSVP_CHUNK_SIZE,
                ),
                font_size=settings_store.load_int(Config.DEFAULTS_KEY_READER_RSVP_FONT_SIZE, fallback=DEFAULT_RSVP_FONT_SIZE),
            ),
            tts_config=TTSConfig.from_values(
                rate_multiplier=settings_store.load_str(
                    Config.DEFAULTS_KEY_READER_TTS_RATE_MULTIPLIER,
                    fallback=str(DEFAULT_TTS_RATE_MULTIPLIER),
                ),
                voice_id=settings_store.load_str(Config.DEFAULTS_KEY_READER_TTS_VOICE_ID, fallback=None),
                max_minutes=settings_store.load_int(Config.DEFAULTS_KEY_READER_TTS_MAX_MINUTES, fallback=DEFAULT_TTS_MAX_MINUTES),
                engine=settings_store.load_str(Config.DEFAULTS_KEY_READER_TTS_ENGINE, fallback=DEFAULT_TTS_ENGINE),
                mlx_model=settings_store.load_str(Config.DEFAULTS_KEY_READER_TTS_MLX_MODEL, fallback=DEFAULT_TTS_MLX_MODEL),
                mlx_voice_description=settings_store.load_str(
                    Config.DEFAULTS_KEY_READER_TTS_MLX_VOICE_DESCRIPTION,
                    fallback=DEFAULT_TTS_MLX_VOICE_DESCRIPTION,
                ),
            ),
            preprocess_model=preprocess_model or llm_model,
            preprocess_enabled=settings_store.load_bool(
                Config.DEFAULTS_KEY_READER_PREPROCESS_ENABLED,
                fallback=DEFAULT_READER_PREPROCESS_ENABLED,
            ),
        )

    @property
    def rsvp_hotkey_status(self) -> str:
        """Возвращает display-строку RSVP-хоткея."""
        return format_hotkey_status(self.rsvp_hotkey) if self.rsvp_hotkey else "не задан"

    @property
    def tts_hotkey_status(self) -> str:
        """Возвращает display-строку TTS-хоткея."""
        return format_hotkey_status(self.tts_hotkey) if self.tts_hotkey else "не задан"

    def with_rsvp_hotkey(self, value: object) -> ReaderPreferences:
        """Возвращает настройки с обновлённым RSVP-хоткеем."""
        return self.__class__(
            rsvp_hotkey=_load_optional_hotkey(value, fallback=""),
            tts_hotkey=self.tts_hotkey,
            rsvp_config=self.rsvp_config,
            tts_config=self.tts_config,
            preprocess_model=self.preprocess_model,
            preprocess_enabled=self.preprocess_enabled,
        )

    def with_tts_hotkey(self, value: object) -> ReaderPreferences:
        """Возвращает настройки с обновлённым TTS-хоткеем."""
        return self.__class__(
            rsvp_hotkey=self.rsvp_hotkey,
            tts_hotkey=_load_optional_hotkey(value, fallback=""),
            rsvp_config=self.rsvp_config,
            tts_config=self.tts_config,
            preprocess_model=self.preprocess_model,
            preprocess_enabled=self.preprocess_enabled,
        )

    def with_rsvp_config(self, config: RSVPConfig) -> ReaderPreferences:
        """Возвращает настройки с обновлённым RSVPConfig."""
        return self.__class__(
            rsvp_hotkey=self.rsvp_hotkey,
            tts_hotkey=self.tts_hotkey,
            rsvp_config=config,
            tts_config=self.tts_config,
            preprocess_model=self.preprocess_model,
            preprocess_enabled=self.preprocess_enabled,
        )

    def with_tts_config(self, config: TTSConfig) -> ReaderPreferences:
        """Возвращает настройки с обновлённым TTSConfig."""
        return self.__class__(
            rsvp_hotkey=self.rsvp_hotkey,
            tts_hotkey=self.tts_hotkey,
            rsvp_config=self.rsvp_config,
            tts_config=config,
            preprocess_model=self.preprocess_model,
            preprocess_enabled=self.preprocess_enabled,
        )

    def with_preprocess_enabled(self, enabled: object) -> ReaderPreferences:
        """Возвращает настройки с обновлённым флагом LLM-предобработки."""
        return self.__class__(
            rsvp_hotkey=self.rsvp_hotkey,
            tts_hotkey=self.tts_hotkey,
            rsvp_config=self.rsvp_config,
            tts_config=self.tts_config,
            preprocess_model=self.preprocess_model,
            preprocess_enabled=bool(enabled),
        )

    def with_preprocess_model(self, model_name: object) -> ReaderPreferences:
        """Возвращает настройки с обновлённым именем LLM-модели предобработки."""
        normalized = str(model_name or "").strip() or self.preprocess_model
        return self.__class__(
            rsvp_hotkey=self.rsvp_hotkey,
            tts_hotkey=self.tts_hotkey,
            rsvp_config=self.rsvp_config,
            tts_config=self.tts_config,
            preprocess_model=normalized,
            preprocess_enabled=self.preprocess_enabled,
        )


class ReaderClipboardPort(Protocol):
    """Порт чтения системного буфера обмена для reader-сценариев."""

    def read_content(self) -> ClipboardContent:
        """Читает текстовый снимок буфера без модификации содержимого."""
        ...


class LLMReformatterPort(Protocol):
    """Порт локальной LLM-предобработки текста."""

    last_token_usage: int

    def is_model_cached(self) -> bool:
        """Проверяет, загружена ли LLM-модель в локальный кэш."""
        ...

    def process_text(
        self,
        text: str,
        system_prompt: str,
        *,
        context: str | None = None,
        max_tokens: int | None = None,
    ) -> str:
        """Возвращает переформатированный текст."""
        ...


class RSVPDisplayPort(Protocol):
    """Порт отображения RSVP overlay."""

    def show_frames(self, frames: list[RSVPFrame], config: RSVPConfig) -> None:
        """Показывает overlay и запускает воспроизведение кадров."""
        ...

    def close(self) -> None:
        """Закрывает overlay."""
        ...

    def is_running(self) -> bool:
        """Сообщает, открыт ли RSVP overlay."""
        ...

    def handle_key(self, key_name: str) -> bool:
        """Обрабатывает управляющую клавишу RSVP."""
        ...


class TTSPort(Protocol):
    """Порт локального голосового воспроизведения."""

    def speak(self, text: str, config: TTSConfig) -> None:
        """Начинает голосовое воспроизведение."""
        ...

    def stop(self) -> None:
        """Останавливает голосовое воспроизведение."""
        ...

    def is_speaking(self) -> bool:
        """Сообщает, идёт ли воспроизведение."""
        ...

    def available_voices(self) -> list[TTSVoice]:
        """Возвращает доступные системные голоса."""
        ...

    def set_keep_model_loaded(self, enabled: bool) -> None:
        """Меняет режим удержания MLX TTS-модели в памяти."""
        ...


def build_rsvp_frames(text: str, chunk_size: int) -> list[RSVPFrame]:
    """Разбивает текст на RSVP-кадры заданного размера."""
    safe_chunk_size = clamp_rsvp_chunk_size(chunk_size)
    words = reader_words(text)
    frames: list[RSVPFrame] = []
    for index in range(0, len(words), safe_chunk_size):
        chunk = words[index : index + safe_chunk_size]
        frames.append(RSVPFrame(tuple(RSVPToken.from_text(word) for word in chunk)))
    return frames


def _load_optional_hotkey(value: object, *, fallback: str) -> str:
    """Нормализует опциональный хоткей из persistence."""
    if value is None:
        return fallback
    normalized = str(value).strip()
    if not normalized:
        return ""
    try:
        return normalize_key_combination(normalized)
    except ValueError:
        return fallback
