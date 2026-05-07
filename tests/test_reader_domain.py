"""Тесты чистых правил reader-модуля."""

import pytest
from src.domain.reader_constants import (
    DEFAULT_TTS_MLX_MODEL,
    DEFAULT_TTS_MLX_VOICE_DESCRIPTION,
    TTS_ENGINE_MLX,
    clamp_tts_rate_multiplier,
    estimate_rsvp_duration_seconds,
    reader_orp_index,
    rsvp_frame_interval_seconds,
)
from src.domain.reader_types import TTSConfig, build_rsvp_frames


@pytest.mark.parametrize(
    ("word", "expected"),
    [
        ("я", 0),
        ("тест", 1),
        ("сложность", 2),
        ("производительность", 4),
    ],
)
def test_reader_orp_index_uses_spritz_rule(word, expected):
    assert reader_orp_index(word) == expected


def test_build_rsvp_frames_respects_chunk_size():
    frames = build_rsvp_frames("один два три четыре пять", 2)

    assert [frame.text for frame in frames] == ["один два", "три четыре", "пять"]
    assert [token.orp_index for token in frames[0].tokens] == [1, 0]


def test_build_rsvp_frames_falls_back_to_default_chunk_for_invalid_value():
    frames = build_rsvp_frames("один два три", 99)

    assert [frame.text for frame in frames] == ["один два", "три"]


def test_estimate_rsvp_duration_seconds_uses_word_count_and_wpm():
    assert estimate_rsvp_duration_seconds(400, 400) == 60
    assert estimate_rsvp_duration_seconds(0, 400) == 0


def test_rsvp_frame_interval_scales_by_chunk_size():
    assert rsvp_frame_interval_seconds(2, 400) == pytest.approx(0.3)


@pytest.mark.parametrize(
    ("raw_value", "expected"),
    [
        ("2.35", 2.35),
        ("2,35", 2.35),
        (1.27, 1.27),
        (-1, 0.1),
        (4, 3.0),
    ],
)
def test_tts_rate_multiplier_accepts_continuous_range(raw_value, expected):
    assert clamp_tts_rate_multiplier(raw_value) == expected


def test_tts_rate_multiplier_falls_back_for_invalid_values():
    assert clamp_tts_rate_multiplier("быстро") == 1.0


def test_tts_config_accepts_mlx_backend_settings():
    config = TTSConfig.from_values(
        rate_multiplier=1,
        voice_id=None,
        engine=TTS_ENGINE_MLX,
        mlx_model="mlx-community/custom-tts",
        mlx_voice_description="Спокойный голос",
    )

    assert config.engine == TTS_ENGINE_MLX
    assert config.mlx_model == "mlx-community/custom-tts"
    assert config.mlx_voice_description == "Спокойный голос"


def test_tts_config_falls_back_to_default_mlx_settings():
    config = TTSConfig.from_values(rate_multiplier=1, voice_id=None, engine="unknown", mlx_model="", mlx_voice_description="")

    assert config.engine == "apple"
    assert config.mlx_model == DEFAULT_TTS_MLX_MODEL
    assert config.mlx_voice_description == DEFAULT_TTS_MLX_VOICE_DESCRIPTION
