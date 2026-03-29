"""Persistence быстрых профилей микрофона через NSUserDefaults."""

from __future__ import annotations

import json
import logging

from ...domain.constants import Config
from ...domain.types import MicrophoneProfile
from .defaults import Defaults

LOGGER = logging.getLogger(__name__)

defaults = Defaults()


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
        profile = MicrophoneProfile.from_payload(raw_profile)
        if profile is not None:
            profiles.append(profile)
    return profiles


def _save_microphone_profiles(profiles: list[MicrophoneProfile]) -> None:
    """Сохраняет быстрые профили микрофона в NSUserDefaults."""
    serialized_profiles = [profile.to_payload() for profile in profiles[:Config.MAX_MICROPHONE_PROFILES]]
    defaults.save_str(
        Config.DEFAULTS_KEY_MICROPHONE_PROFILES,
        json.dumps(serialized_profiles, ensure_ascii=False),
    )
