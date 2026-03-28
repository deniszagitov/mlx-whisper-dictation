"""Use case-сценарии быстрых профилей микрофона."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from ..domain.constants import Config

if TYPE_CHECKING:
    from ..domain.types import MicrophoneProfile

LOGGER = logging.getLogger(__name__)


class MicrophoneProfilesUseCases:
    """Управляет сохранением и применением профилей микрофона."""

    def __init__(
        self,
        runtime: Any,
        settings_store: Any,
        recorder: Any,
        transcriber: Any,
        microphone_profiles_service: Any,
        system_integration_service: Any,
        change_performance_mode: Any,
        publish_snapshot: Any,
    ) -> None:
        self.runtime = runtime
        self.settings_store = settings_store
        self.recorder = recorder
        self.transcriber = transcriber
        self.microphone_profiles_service = microphone_profiles_service
        self.system_integration_service = system_integration_service
        self.change_performance_mode = change_performance_mode
        self.publish_snapshot = publish_snapshot

    def is_microphone_profile_active(self, profile: MicrophoneProfile) -> bool:
        """Проверяет, соответствует ли профиль текущим runtime-настройкам."""
        if profile.get("input_device_index") != self._active_input_device_index():
            return False
        if profile.get("model_repo") != self.runtime.model_repo:
            return False
        if profile.get("language") != self.runtime.current_language:
            return False
        if profile.get("max_time") != self.runtime.max_time:
            return False
        if profile.get("performance_mode") != self.runtime.performance_mode:
            return False

        return (
            bool(profile.get("private_mode", False)) == bool(getattr(self.transcriber, "private_mode_enabled", False))
            and bool(profile.get("paste_cgevent", True)) == bool(getattr(self.transcriber, "paste_cgevent_enabled", True))
            and bool(profile.get("paste_ax", False)) == bool(getattr(self.transcriber, "paste_ax_enabled", False))
            and bool(profile.get("paste_clipboard", False))
            == bool(getattr(self.transcriber, "paste_clipboard_enabled", False))
            and bool(profile.get("llm_clipboard", True)) == bool(getattr(self.transcriber, "llm_clipboard_enabled", True))
        )

    def suggest_microphone_profile_name(self) -> str:
        """Предлагает имя для нового быстрого профиля."""
        if self.runtime.current_input_device is None:
            return "Новый профиль"
        return str(self.runtime.current_input_device.get("name") or "Новый профиль")

    def add_current_microphone_profile(self, profile_name: str) -> None:
        """Сохраняет текущий runtime как новый быстрый профиль."""
        if self.runtime.current_input_device is None:
            self.runtime.system_integration_service.notify(
                "MLX Whisper Dictation",
                "Нельзя сохранить профиль без выбранного микрофона.",
            )
            return

        if len(self.runtime.microphone_profiles) >= Config.MAX_MICROPHONE_PROFILES:
            self.runtime.system_integration_service.notify(
                "MLX Whisper Dictation",
                f"Можно сохранить не больше {Config.MAX_MICROPHONE_PROFILES} быстрых профилей.",
            )
            return

        unique_name = self._unique_microphone_profile_name(profile_name)
        self.runtime.microphone_profiles.append(self._current_microphone_profile(unique_name))
        self._persist_microphone_profiles()
        LOGGER.info("🎚 Добавлен быстрый профиль микрофона: %s", unique_name)
        self.runtime.system_integration_service.notify("MLX Whisper Dictation", f"Профиль сохранён: {unique_name}")
        self.publish_snapshot()

    def apply_microphone_profile(self, profile_name: str) -> None:
        """Применяет быстрый профиль по его имени."""
        profile = next((item for item in self.runtime.microphone_profiles if item["name"] == profile_name), None)
        if profile is None:
            return

        selected_device = next(
            (device for device in self.runtime.input_devices if device["index"] == profile["input_device_index"]),
            None,
        )
        if selected_device is None:
            self.runtime.system_integration_service.notify(
                "MLX Whisper Dictation",
                f"Микрофон для профиля «{profile['name']}» сейчас недоступен.",
            )
            return

        self.runtime.current_input_device = selected_device
        self.recorder.set_input_device(selected_device)
        self.settings_store.save_input_device_index(selected_device["index"])

        self.runtime.model_repo = profile["model_repo"]
        self.runtime.model_name = self.runtime.model_repo.rsplit("/", maxsplit=1)[-1]
        self.transcriber.model_name = self.runtime.model_repo
        self.settings_store.save_str(Config.DEFAULTS_KEY_MODEL, self.runtime.model_repo)

        profile_language = profile.get("language")
        if self.runtime.languages is None:
            self.runtime.current_language = None
        elif profile_language in self.runtime.languages or profile_language is None:
            self.runtime.current_language = profile_language
        if self.runtime.current_language is None:
            self.settings_store.remove_key(Config.DEFAULTS_KEY_LANGUAGE)
        else:
            self.settings_store.save_str(Config.DEFAULTS_KEY_LANGUAGE, self.runtime.current_language)

        self.runtime.max_time = profile.get("max_time")
        self.settings_store.save_max_time(self.runtime.max_time)

        self.change_performance_mode(profile.get("performance_mode"))

        private_mode = bool(profile.get("private_mode", False))
        self.transcriber.set_private_mode(private_mode)

        self.transcriber.paste_cgevent_enabled = bool(profile.get("paste_cgevent", True))
        self.transcriber.paste_ax_enabled = bool(profile.get("paste_ax", False))
        self.transcriber.paste_clipboard_enabled = bool(profile.get("paste_clipboard", False))
        self.transcriber.llm_clipboard_enabled = bool(profile.get("llm_clipboard", True))
        self.settings_store.save_bool(Config.DEFAULTS_KEY_PASTE_CGEVENT, self.transcriber.paste_cgevent_enabled)
        self.settings_store.save_bool(Config.DEFAULTS_KEY_PASTE_AX, self.transcriber.paste_ax_enabled)
        self.settings_store.save_bool(Config.DEFAULTS_KEY_PASTE_CLIPBOARD, self.transcriber.paste_clipboard_enabled)
        self.settings_store.save_bool(Config.DEFAULTS_KEY_LLM_CLIPBOARD, self.transcriber.llm_clipboard_enabled)

        LOGGER.info("🎚 Применён быстрый профиль микрофона: %s", profile["name"])
        self.runtime.system_integration_service.notify("MLX Whisper Dictation", f"Профиль применён: {profile['name']}")
        self.publish_snapshot()

    def delete_microphone_profile(self, profile_name: str) -> None:
        """Удаляет быстрый профиль по имени."""
        if not any(item["name"] == profile_name for item in self.runtime.microphone_profiles):
            return

        self.runtime.microphone_profiles = [
            item for item in self.runtime.microphone_profiles if item["name"] != profile_name
        ]
        self._persist_microphone_profiles()
        LOGGER.info("🗑 Удалён быстрый профиль микрофона: %s", profile_name)
        self.runtime.system_integration_service.notify("MLX Whisper Dictation", f"Профиль удалён: {profile_name}")
        self.publish_snapshot()

    def _persist_microphone_profiles(self) -> None:
        """Сохраняет быстрые профили микрофона."""
        self.runtime.microphone_profiles_service.save_profiles(self.runtime.microphone_profiles)

    def _active_input_device_index(self) -> int | None:
        """Возвращает индекс текущего микрофона."""
        if self.runtime.current_input_device is None:
            return None
        return int(self.runtime.current_input_device["index"])

    def _unique_microphone_profile_name(self, base_name: str) -> str:
        """Нормализует и делает имя профиля уникальным."""
        normalized_name = " ".join(base_name.split()) or "Новый профиль"
        existing_names = {profile["name"] for profile in self.runtime.microphone_profiles}
        if normalized_name not in existing_names:
            return normalized_name

        suffix = 2
        while f"{normalized_name} {suffix}" in existing_names:
            suffix += 1
        return f"{normalized_name} {suffix}"

    def _current_microphone_profile(self, profile_name: str) -> dict[str, Any]:
        """Собирает профиль из текущих runtime-настроек."""
        return {
            "name": profile_name,
            "input_device_index": self._active_input_device_index(),
            "input_device_name": ""
            if self.runtime.current_input_device is None
            else str(self.runtime.current_input_device.get("name") or ""),
            "model_repo": self.runtime.model_repo,
            "language": self.runtime.current_language,
            "max_time": self.runtime.max_time,
            "performance_mode": self.runtime.performance_mode,
            "private_mode": bool(getattr(self.transcriber, "private_mode_enabled", False)),
            "paste_cgevent": bool(getattr(self.transcriber, "paste_cgevent_enabled", True)),
            "paste_ax": bool(getattr(self.transcriber, "paste_ax_enabled", False)),
            "paste_clipboard": bool(getattr(self.transcriber, "paste_clipboard_enabled", False)),
            "llm_clipboard": bool(getattr(self.transcriber, "llm_clipboard_enabled", True)),
        }
