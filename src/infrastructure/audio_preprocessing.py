"""Preprocessing аудио перед локальной ASR-моделью."""

from __future__ import annotations

import logging
import math
from typing import Any

import numpy as np
import numpy.typing as npt
import soxr

try:
    import webrtcvad
except ImportError:  # pragma: no cover - runtime fallback для неполной сборки
    webrtcvad = None

from ..domain.constants import Config
from ..domain.types import PreprocessedAudio, RecordedAudio

LOGGER = logging.getLogger(__name__)


def _legacy_recorded_audio(audio_input: object) -> RecordedAudio:
    """Оборачивает старый ndarray-контракт в RecordedAudio."""
    samples = np.asarray(audio_input)
    sample_format = "int16" if samples.dtype == np.int16 else "float32"
    return RecordedAudio(
        samples=samples,
        sample_rate=Config.AUDIO_SAMPLE_RATE,
        channels=Config.AUDIO_CHANNELS_MONO,
        sample_format=sample_format,
        device_index=None,
        device_name=None,
        profile_name=Config.AUDIO_PROFILE_GENERIC,
        metadata={"legacy_ndarray": True, "post_roll_ms": 0},
    )


def _as_recorded_audio(audio_input: RecordedAudio | object) -> RecordedAudio:
    """Нормализует входной объект в RecordedAudio."""
    if isinstance(audio_input, RecordedAudio):
        return audio_input
    return _legacy_recorded_audio(audio_input)


def _duration_seconds(samples: npt.NDArray[Any], sample_rate: int) -> float:
    """Считает длительность массива с защитой от некорректной частоты."""
    if sample_rate <= 0:
        return 0.0
    return float(len(samples)) / float(sample_rate)


def _to_mono(samples: npt.NDArray[Any], channels: int) -> npt.NDArray[Any]:
    """Приводит interleaved audio к mono без удаления пауз."""
    if channels <= 1:
        mono: npt.NDArray[Any] = np.asarray(samples.reshape(-1))
        return mono
    usable_length = (len(samples) // channels) * channels
    if usable_length <= 0:
        return np.asarray([], dtype=samples.dtype)
    mono = np.asarray(samples[:usable_length].reshape(-1, channels).mean(axis=1))
    return mono


def _convert_to_float32(recorded_audio: RecordedAudio) -> npt.NDArray[np.float32]:
    """Преобразует samples в float32 waveform."""
    samples = np.asarray(recorded_audio.samples)
    mono_samples = _to_mono(samples, max(int(recorded_audio.channels), 1))
    if recorded_audio.sample_format == "int16" or mono_samples.dtype == np.int16:
        return (mono_samples.astype(np.float32) / 32768.0).astype(np.float32, copy=False)
    return mono_samples.astype(np.float32, copy=False)


def resample_to_16k(audio: npt.NDArray[np.float32], source_sample_rate: int) -> npt.NDArray[np.float32]:
    """Ресемплит waveform в 16 kHz через soxr HQ."""
    if source_sample_rate == Config.AUDIO_SAMPLE_RATE:
        return audio.astype(np.float32, copy=False)
    if len(audio) == 0:
        return audio.astype(np.float32, copy=False)
    resampled: npt.NDArray[np.float32] = soxr.resample(
        audio.astype(np.float32, copy=False),
        source_sample_rate,
        Config.AUDIO_SAMPLE_RATE,
        quality="HQ",
    ).astype(np.float32, copy=False)
    return resampled


def _rms(audio: npt.NDArray[np.float32]) -> float:
    """Считает RMS аудиосигнала."""
    return float(np.sqrt(np.mean(audio**2))) if len(audio) else 0.0


def _peak(audio: npt.NDArray[np.float32]) -> float:
    """Считает peak amplitude аудиосигнала."""
    return float(np.max(np.abs(audio))) if len(audio) else 0.0


def _clipping_ratio(audio: npt.NDArray[np.float32]) -> float:
    """Считает долю сэмплов около клиппинга."""
    if len(audio) == 0:
        return 0.0
    return float(np.mean(np.abs(audio) >= Config.AUDIO_CLIPPING_THRESHOLD))


def _audio_to_pcm16_bytes(audio: npt.NDArray[np.float32]) -> bytes:
    """Преобразует float32 waveform в int16 PCM для WebRTC VAD."""
    pcm16 = np.clip(audio * 32768.0, -32768, 32767).astype(np.int16)
    return bytes(pcm16.tobytes())


def _run_webrtc_vad(audio: npt.NDArray[np.float32]) -> tuple[float | None, float | None, float | None]:
    """Возвращает speech duration, speech ratio и speech RMS через WebRTC VAD."""
    if webrtcvad is None:
        return None, None, None

    frame_samples = int(Config.AUDIO_SAMPLE_RATE * Config.AUDIO_VAD_FRAME_MS / 1000)
    if frame_samples <= 0 or len(audio) < frame_samples:
        return 0.0, 0.0, None

    vad = webrtcvad.Vad(Config.AUDIO_VAD_MODE)
    speech_frames = 0
    total_frames = 0
    speech_chunks: list[npt.NDArray[np.float32]] = []
    pcm_bytes = _audio_to_pcm16_bytes(audio)
    bytes_per_frame = frame_samples * 2

    for offset in range(0, len(audio) - frame_samples + 1, frame_samples):
        byte_start = offset * 2
        frame = pcm_bytes[byte_start : byte_start + bytes_per_frame]
        total_frames += 1
        if vad.is_speech(frame, Config.AUDIO_SAMPLE_RATE):
            speech_frames += 1
            speech_chunks.append(audio[offset : offset + frame_samples])

    if total_frames == 0:
        return 0.0, 0.0, None

    speech_duration_s = speech_frames * (Config.AUDIO_VAD_FRAME_MS / 1000.0)
    speech_ratio = speech_frames / total_frames
    speech_rms = _rms(np.concatenate(speech_chunks)) if speech_chunks else None
    return speech_duration_s, speech_ratio, speech_rms


def _gain_db(gain: float) -> float:
    """Преобразует множитель gain в децибелы."""
    if gain <= 0:
        return 0.0
    return 20.0 * math.log10(gain)


def _apply_safe_gain(
    audio: npt.NDArray[np.float32],
    *,
    speech_rms: float | None,
    total_rms: float,
    peak: float,
    enable_gain_normalization: bool,
) -> tuple[npt.NDArray[np.float32], float]:
    """Применяет бережную нормализацию без усиления тишины."""
    if not enable_gain_normalization or len(audio) == 0:
        return audio, 0.0
    if peak > Config.AUDIO_DO_NOT_NORMALIZE_IF_PEAK_ABOVE:
        return audio, 0.0

    effective_rms = speech_rms
    if effective_rms is None or effective_rms <= 0:
        return audio, 0.0
    if effective_rms < Config.AUDIO_DO_NOT_NORMALIZE_IF_RMS_BELOW_WITHOUT_VAD_SPEECH and total_rms <= effective_rms:
        return audio, 0.0

    target_gain = Config.AUDIO_TARGET_SPEECH_RMS / effective_rms
    max_gain = 10 ** (Config.AUDIO_MAX_GAIN_DB / 20.0)
    gain = min(max(target_gain, 1.0), max_gain)
    if gain <= 1.0:
        return audio, 0.0

    normalized = audio * gain
    output_peak = _peak(normalized)
    if output_peak > Config.AUDIO_PEAK_LIMIT:
        normalized = normalized * (Config.AUDIO_PEAK_LIMIT / output_peak)
    return normalized.astype(np.float32, copy=False), _gain_db(gain)


def preprocess_recorded_audio(
    audio_input: RecordedAudio | object,
    language: str | None = None,
    *,
    enable_gain_normalization: bool = True,
) -> PreprocessedAudio:
    """Готовит записанное аудио к ASR без trim и шумоподавления."""
    recorded_audio = _as_recorded_audio(audio_input)
    raw_samples = np.asarray(recorded_audio.samples)
    duration_before_s = _duration_seconds(raw_samples, int(recorded_audio.sample_rate))

    audio = _convert_to_float32(recorded_audio)
    audio = np.nan_to_num(audio, nan=0.0, posinf=0.0, neginf=0.0)
    audio = np.clip(audio, -1.0, 1.0).astype(np.float32, copy=False)
    dc_offset_before = float(np.mean(audio)) if len(audio) else 0.0
    clipping_ratio = _clipping_ratio(audio)
    if clipping_ratio > Config.AUDIO_CLIPPING_WARNING_RATIO:
        LOGGER.warning(
            "🎙️ Входной сигнал выглядит клиппированным: clipping_ratio=%.6f. "
            "Уменьшите уровень микрофона или отодвиньтесь от него.",
            clipping_ratio,
        )

    resampled = int(recorded_audio.sample_rate) != Config.AUDIO_SAMPLE_RATE
    audio = resample_to_16k(audio, int(recorded_audio.sample_rate))
    audio = audio - float(np.mean(audio)) if len(audio) else audio
    audio = np.clip(audio, -1.0, 1.0).astype(np.float32, copy=False)
    dc_offset_after = float(np.mean(audio)) if len(audio) else 0.0

    rms = _rms(audio)
    peak = _peak(audio)
    speech_duration_s, speech_ratio, speech_rms = _run_webrtc_vad(audio)
    vad_detected_no_speech = speech_duration_s == 0
    duration_after_s = _duration_seconds(audio, Config.AUDIO_SAMPLE_RATE)
    skip_asr = (
        duration_after_s >= Config.AUDIO_MIN_RECORDING_DURATION_FOR_SKIP_S
        and rms < Config.AUDIO_NO_SPEECH_RMS_THRESHOLD
        and peak < Config.AUDIO_NO_SPEECH_PEAK_THRESHOLD
        and vad_detected_no_speech
    )

    normalized_audio, gain_applied_db = _apply_safe_gain(
        audio,
        speech_rms=speech_rms,
        total_rms=rms,
        peak=peak,
        enable_gain_normalization=enable_gain_normalization,
    )
    final_peak = _peak(normalized_audio)

    diagnostics: dict[str, Any] = {
        "language": language,
        "device_name": recorded_audio.device_name,
        "device_index": recorded_audio.device_index,
        "profile_name": recorded_audio.profile_name,
        "capture_sample_rate": int(recorded_audio.sample_rate),
        "capture_format": recorded_audio.sample_format,
        "capture_channels": int(recorded_audio.channels),
        "final_sample_rate": Config.AUDIO_SAMPLE_RATE,
        "duration_before_preprocessing_s": duration_before_s,
        "duration_after_preprocessing_s": duration_after_s,
        "pre_roll_ms": int(recorded_audio.metadata.get("pre_roll_ms", 0)),
        "post_roll_ms": int(recorded_audio.metadata.get("post_roll_ms", 0)),
        "rms": rms,
        "peak": peak,
        "final_peak": final_peak,
        "clipping_ratio": clipping_ratio,
        "dc_offset_before": dc_offset_before,
        "dc_offset_after": dc_offset_after,
        "vad_available": webrtcvad is not None,
        "vad_speech_duration_s": speech_duration_s,
        "vad_speech_ratio": speech_ratio,
        "gain_applied_db": gain_applied_db,
        "resampled": resampled,
        "skip_asr": skip_asr,
        "samples_before_preprocessing": len(raw_samples),
        "samples_after_preprocessing": len(normalized_audio),
    }

    return PreprocessedAudio(
        audio=normalized_audio.astype(np.float32, copy=False),
        sample_rate=Config.AUDIO_SAMPLE_RATE,
        speech_detected=not skip_asr,
        duration_s=duration_after_s,
        speech_duration_s=speech_duration_s,
        diagnostics=diagnostics,
    )
