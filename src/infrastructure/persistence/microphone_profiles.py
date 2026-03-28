"""Persistence быстрых профилей микрофона через NSUserDefaults."""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING

from ...domain.constants import Config
from .defaults import Defaults

if TYPE_CHECKING:
    from ...domain.types import MicrophoneProfile

LOGGER = logging.getLogger(__name__)

defaults = Defaults()


def _normalize_microphone_profile(raw_profile: object) -> MicrophoneProfile | None:
    """Нормализует сохранённый профиль микрофона."""
    if not isinstance(raw_profile, dict):
        return None

    name = str(raw_profile.get("name") or "").strip()
    input_device_index = raw_profile.get("input_device_index")
    if not name or input_device_index is None:
        return None

    try:
        normalized_index = int(input_device_index)
    except (TypeError, ValueError):
        return None

    max_time = raw_profile.get("max_time")
    if max_time is not None:
        try:
            parsed_max_time = float(max_time)
        except (TypeError, ValueError):
            max_time = None
        else:
            max_time = int(parsed_max_time) if parsed_max_time.is_integer() else parsed_max_time

    language = raw_profile.get("language")
    if language is not None:
        language = str(language)

    model_repo = str(raw_profile.get("model_repo") or Config.DEFAULT_MODEL_NAME)
    performance_mode = Config.normalize_performance_mode(raw_profile.get("performance_mode"))

    return {
        "name": name,
        "input_device_index": normalized_index,
        "input_device_name": str(raw_profile.get("input_device_name") or ""),
        "model_repo": model_repo,
        "language": language,
        "max_time": max_time,
        "performance_mode": performance_mode,
        "private_mode": bool(raw_profile.get("private_mode", False)),
        "paste_cgevent": bool(raw_profile.get("paste_cgevent", True)),
        "paste_ax": bool(raw_profile.get("paste_ax", False)),
        "paste_clipboard": bool(raw_profile.get("paste_clipboard", False)),
        "llm_clipboard": bool(raw_profile.get("llm_clipboard", True)),
    }


def _load_microphone_profiles() -> list[MicrophoneProfile]:
    """Читает быстрые профили микрофона из NSUserDefaults."""
    raw_value = defaults.load_str(Config.DEFAULTS_KEY_MICROPHONE_PROFILES, fallback="")
    if not raw_value:
        return []

    try:
        payload = json.loads(raw_value)
    except Exception:
        LOGGER.exception("⚠️ Не удалось прочитать сохранённые профили микрофона")
        return []

    if not isinstance(payload, list):
        return []

    profiles = []
    for raw_profile in payload[:Config.MAX_MICROPHONE_PROFILES]:
        normalized_profile = _normalize_microphone_profile(raw_profile)
        if normalized_profile is not None:
            profiles.append(normalized_profile)
    return profiles


def _save_microphone_profiles(profiles: list[MicrophoneProfile]) -> None:
    """Сохраняет быстрые профили микрофона в NSUserDefaults."""
    serialized_profiles = []
    for profile in profiles[:Config.MAX_MICROPHONE_PROFILES]:
        normalized_profile = _normalize_microphone_profile(profile)
        if normalized_profile is not None:
            serialized_profiles.append(normalized_profile)
    defaults.save_str(
        Config.DEFAULTS_KEY_MICROPHONE_PROFILES,
        json.dumps(serialized_profiles, ensure_ascii=False),
    )
