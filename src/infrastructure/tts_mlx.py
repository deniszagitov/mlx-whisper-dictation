"""Локальное потоковое TTS-воспроизведение через mlx-audio."""

from __future__ import annotations

import logging
import threading
from typing import TYPE_CHECKING, Any

import numpy as np

from ..domain.reader_constants import (
    TTS_MLX_GENERATION_REPETITION_PENALTY,
    TTS_MLX_GENERATION_SEED,
    TTS_MLX_GENERATION_TEMPERATURE,
    TTS_MLX_GENERATION_TOP_K,
    TTS_MLX_GENERATION_TOP_P,
    TTS_MLX_LANGUAGE_CODE,
    TTS_MLX_STREAMING_INTERVAL_SECONDS,
)
from .model_manager import default_model_manager

if TYPE_CHECKING:
    from collections.abc import Callable

    from ..domain.reader_types import TTSConfig, TTSVoice

LOGGER = logging.getLogger(__name__)


class MlxStreamingTTSController:
    """Обёртка над mlx-audio TTS с потоковой выдачей audio chunks."""

    def __init__(
        self,
        *,
        model_loader: Callable[[str], Any] | None = None,
        player_factory: Callable[[int], Any] | None = None,
        mx_module: Any | None = None,
    ) -> None:
        self._model_loader = model_loader or self._load_model_from_mlx_audio
        self._player_factory = player_factory or self._create_audio_player
        self._mx = mx_module
        self._state_lock = threading.RLock()
        self._stop_event = threading.Event()
        self._player: Any | None = None
        self._speaking = False
        self._keep_model_loaded = False

    def speak(self, text: str, config: TTSConfig) -> None:
        """Генерирует речь потоковыми chunk-ами и сразу отдаёт их в audio output."""
        if not text.strip():
            return
        if self.is_speaking():
            self.stop()

        self._stop_event.clear()
        with self._state_lock:
            self._speaking = True
            self._player = None

        model_name = config.mlx_model
        player = None
        try:
            model = self._get_model(model_name)
            if self._stop_event.is_set():
                return

            sample_rate = int(getattr(model, "sample_rate", 24_000))
            player = self._player_factory(sample_rate)
            with self._state_lock:
                self._player = player

            LOGGER.info("🔈 MLX TTS запускает поток: model=%s, chars=%d", model_name, len(text))
            self._seed_mlx_random()
            results = model.generate(
                text=text,
                voice=None,
                instruct=config.mlx_instruct,
                stream=True,
                streaming_interval=TTS_MLX_STREAMING_INTERVAL_SECONDS,
                speed=max(config.rate_multiplier, 0.1),
                lang_code=TTS_MLX_LANGUAGE_CODE,
                temperature=TTS_MLX_GENERATION_TEMPERATURE,
                top_p=TTS_MLX_GENERATION_TOP_P,
                top_k=TTS_MLX_GENERATION_TOP_K,
                repetition_penalty=TTS_MLX_GENERATION_REPETITION_PENALTY,
                verbose=False,
            )
            for result in results:
                if self._stop_event.is_set():
                    break
                audio = getattr(result, "audio", None)
                if audio is None:
                    continue
                player.queue_audio(np.asarray(audio))
        finally:
            try:
                if player is not None:
                    if self._stop_event.is_set():
                        self._flush_player(player)
                    else:
                        self._drain_player(player)
            finally:
                with self._state_lock:
                    self._speaking = False
                    self._player = None
                self._clear_mlx_cache()
                LOGGER.info("🔈 MLX TTS поток завершён")

    def stop(self) -> None:
        """Останавливает текущую генерацию и очищает audio buffer."""
        self._stop_event.set()
        with self._state_lock:
            player = self._player
        if player is not None:
            self._flush_player(player)
        LOGGER.info("🔈 MLX TTS остановлен")

    def is_speaking(self) -> bool:
        """Сообщает, идёт ли генерация или воспроизведение MLX TTS."""
        with self._state_lock:
            player = self._player
            speaking = self._speaking
        return bool(speaking or getattr(player, "playing", False))

    def available_voices(self) -> list[TTSVoice]:
        """Возвращает пустой список: VoiceDesign управляется описанием голоса."""
        return []

    def set_keep_model_loaded(self, enabled: bool) -> None:
        """Сохраняет совместимый флаг; MLX TTS удерживает единый runtime-сервис."""
        self._keep_model_loaded = bool(enabled)

    def _get_model(self, model_name: str) -> Any:
        """Получает MLX TTS-модель через единый runtime-сервис."""
        return self._model_loader(model_name)

    def _load_model_from_mlx_audio(self, model_name: str) -> Any:
        """Загружает TTS-модель через централизованный менеджер моделей."""
        return default_model_manager().load_tts_model(model_name)

    def _create_audio_player(self, sample_rate: int) -> Any:
        """Создаёт потоковый audio player mlx-audio."""
        try:
            from mlx_audio.tts.audio_player import AudioPlayer  # noqa: PLC0415
        except ImportError as exc:
            raise RuntimeError("Для MLX TTS нужен audio output из mlx-audio. Выполните uv sync --dev.") from exc
        player = AudioPlayer(sample_rate=sample_rate)
        player.min_buffer_seconds = 0.25
        return player

    def _clear_mlx_cache(self) -> None:
        """Очищает временный cache MLX, если runtime доступен."""
        mx_module = self._mx
        if mx_module is None:
            try:
                import mlx.core as mx_module  # noqa: PLC0415
            except ImportError:
                return
            self._mx = mx_module
        clear_cache = getattr(mx_module, "clear_cache", None)
        if callable(clear_cache):
            clear_cache()

    def _seed_mlx_random(self) -> None:
        """Фиксирует seed MLX RNG перед генерацией TTS."""
        mx_module = self._mx
        if mx_module is None:
            try:
                import mlx.core as mx_module  # noqa: PLC0415
            except ImportError:
                return
            self._mx = mx_module
        random_module = getattr(mx_module, "random", None)
        seed = getattr(random_module, "seed", None)
        if callable(seed):
            seed(TTS_MLX_GENERATION_SEED)

    def _drain_player(self, player: Any) -> None:
        """Дожидается воспроизведения накопленных chunk-ов."""
        buffered_samples = getattr(player, "buffered_samples", lambda: 0)
        if callable(buffered_samples) and buffered_samples() > 0 and not getattr(player, "playing", False):
            start_stream = getattr(player, "start_stream", None)
            if callable(start_stream):
                start_stream()
        stop = getattr(player, "stop", None)
        if callable(stop):
            stop()
        self._close_player_stream(player)

    def _flush_player(self, player: Any) -> None:
        """Сбрасывает накопленный звук немедленно."""
        flush = getattr(player, "flush", None)
        if callable(flush):
            flush()
        self._close_player_stream(player)

    def _close_player_stream(self, player: Any) -> None:
        """Закрывает audio stream, даже если player уже сбросил флаг playing."""
        stop_stream = getattr(player, "stop_stream", None)
        if callable(stop_stream) and getattr(player, "stream", None) is not None:
            stop_stream()
