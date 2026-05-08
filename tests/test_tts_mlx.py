"""Тесты MLX TTS backend-а без реальной модели."""

from types import SimpleNamespace

import numpy as np
from src.domain.reader_constants import (
    DEFAULT_TTS_MLX_MODEL,
    DEFAULT_TTS_MLX_VOICE_DESCRIPTION,
    TTS_ENGINE_MLX,
    TTS_MLX_GENERATION_REPETITION_PENALTY,
    TTS_MLX_GENERATION_SEED,
    TTS_MLX_GENERATION_TEMPERATURE,
    TTS_MLX_GENERATION_TOP_K,
    TTS_MLX_GENERATION_TOP_P,
    TTS_MLX_LANGUAGE_CODE,
)
from src.domain.reader_types import TTSConfig
from src.infrastructure.model_runtime_service import ModelRuntimeService
from src.infrastructure.tts_mlx import MlxStreamingTTSController
from src.infrastructure.tts_router import ReaderTTSRouter


class FakeModel:
    """Фейковая потоковая TTS-модель."""

    sample_rate = 24_000

    def __init__(self):
        self.calls = []

    def generate(self, **kwargs):
        self.calls.append(kwargs)
        yield SimpleNamespace(audio=np.array([0.1, 0.2], dtype=np.float32))
        yield SimpleNamespace(audio=np.array([0.3], dtype=np.float32))


class FakePlayer:
    """Фейковый потоковый audio player."""

    def __init__(self, sample_rate):
        self.sample_rate = sample_rate
        self.chunks = []
        self.playing = False
        self.started = 0
        self.stopped = 0
        self.flushed = 0

    def queue_audio(self, samples):
        self.chunks.append(np.asarray(samples))

    def buffered_samples(self):
        return sum(len(chunk) for chunk in self.chunks)

    def start_stream(self):
        self.started += 1
        self.playing = True

    def stop(self):
        self.stopped += 1
        self.playing = False

    def flush(self):
        self.flushed += 1
        self.chunks.clear()
        self.playing = False


class FakeMx:
    """Фейковый MLX runtime."""

    def __init__(self):
        self.clear_calls = 0
        self.seed_calls: list[int] = []
        self.random = SimpleNamespace(seed=self.seed_calls.append)

    def clear_cache(self):
        self.clear_calls += 1


class FakeSpeaker:
    """Фейковый TTSPort для router-тестов."""

    def __init__(self):
        self.spoken = []
        self.stopped = 0
        self.keep_loaded = None
        self.speaking = False

    def speak(self, text, config):
        self.spoken.append((text, config))
        self.speaking = True

    def stop(self):
        self.stopped += 1
        self.speaking = False

    def is_speaking(self):
        return self.speaking

    def available_voices(self):
        return ["голос"]

    def set_keep_model_loaded(self, enabled):
        self.keep_loaded = enabled


def test_mlx_streaming_tts_generates_and_queues_audio_chunks():
    model = FakeModel()
    players = []
    mx = FakeMx()

    def create_player(sample_rate):
        player = FakePlayer(sample_rate)
        players.append(player)
        return player

    controller = MlxStreamingTTSController(
        model_loader=lambda _model_name: model,
        player_factory=create_player,
        mx_module=mx,
    )

    controller.speak(
        "Привет",
        TTSConfig.from_values(
            rate_multiplier=2.35,
            voice_id=None,
            engine=TTS_ENGINE_MLX,
            mlx_model=DEFAULT_TTS_MLX_MODEL,
            mlx_voice_description="Старое описание",
            tone_instruction="коротко и уверенно",
        ),
    )

    assert model.calls[0]["stream"] is True
    assert model.calls[0]["streaming_interval"] == 0.32
    assert model.calls[0]["voice"] is None
    assert model.calls[0]["instruct"] == f"{DEFAULT_TTS_MLX_VOICE_DESCRIPTION}\nИнтонация TTS: коротко и уверенно."
    assert model.calls[0]["lang_code"] == TTS_MLX_LANGUAGE_CODE
    assert model.calls[0]["temperature"] == TTS_MLX_GENERATION_TEMPERATURE
    assert model.calls[0]["top_p"] == TTS_MLX_GENERATION_TOP_P
    assert model.calls[0]["top_k"] == TTS_MLX_GENERATION_TOP_K
    assert model.calls[0]["repetition_penalty"] == TTS_MLX_GENERATION_REPETITION_PENALTY
    assert model.calls[0]["speed"] == 2.35
    assert mx.seed_calls == [TTS_MLX_GENERATION_SEED]
    np.testing.assert_allclose(players[0].chunks[0], np.array([0.1, 0.2], dtype=np.float32))
    np.testing.assert_allclose(players[0].chunks[1], np.array([0.3], dtype=np.float32))
    assert players[0].started == 1
    assert players[0].stopped == 1
    assert mx.clear_calls >= 1


def test_mlx_streaming_tts_uses_shared_runtime_cache_regardless_keep_flag():
    loader_calls = []
    model = FakeModel()

    def load_model(model_name):
        loader_calls.append(model_name)
        return model

    runtime_service = ModelRuntimeService(mlx_tts_loader=load_model)
    controller = MlxStreamingTTSController(
        model_loader=runtime_service.get_mlx_tts,
        player_factory=FakePlayer,
        mx_module=FakeMx(),
    )
    config = TTSConfig.from_values(
        rate_multiplier=1,
        voice_id=None,
        engine=TTS_ENGINE_MLX,
        mlx_model="model",
        mlx_voice_description="голос",
    )

    controller.set_keep_model_loaded(True)
    controller.speak("раз", config)
    controller.speak("два", config)
    assert loader_calls == ["model"]

    controller.set_keep_model_loaded(False)
    controller.speak("три", config)
    assert loader_calls == ["model"]


def test_mlx_streaming_tts_flush_closes_existing_stream_when_not_playing():
    """Shutdown должен закрывать stream, даже если player уже сбросил флаг playing."""
    events: list[str] = []

    class PlayerWithStoppedFlag:
        playing = False
        stream = object()

        def flush(self):
            events.append("flush")

        def stop_stream(self):
            events.append("stop_stream")
            self.stream = None

    controller = MlxStreamingTTSController(model_loader=lambda _model_name: FakeModel(), player_factory=FakePlayer, mx_module=FakeMx())

    controller._flush_player(PlayerWithStoppedFlag())

    assert events == ["flush", "stop_stream"]


def test_tts_router_uses_mlx_backend_when_selected():
    apple = FakeSpeaker()
    mlx = FakeSpeaker()
    router = ReaderTTSRouter(apple_speaker=apple, mlx_speaker=mlx)
    config = TTSConfig.from_values(rate_multiplier=1, voice_id=None, engine=TTS_ENGINE_MLX)

    router.speak("текст", config)
    router.set_keep_model_loaded(True)
    router.stop()

    assert apple.spoken == []
    assert mlx.spoken == [("текст", config)]
    assert apple.keep_loaded is True
    assert mlx.keep_loaded is True
    assert apple.stopped == 1
    assert mlx.stopped == 1
