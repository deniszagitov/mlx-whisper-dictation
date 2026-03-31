"""Use case-сценарии управления хоткеями."""

from __future__ import annotations

import logging
from typing import Any

from ..domain.constants import Config
from ..domain.hotkeys import normalize_key_combination

LOGGER = logging.getLogger(__name__)


class HotkeyManagementUseCases:
    """Управляет изменением основных и LLM-хоткеев."""

    def __init__(
        self,
        runtime: Any,
        settings_store: Any,
        system_integration_service: Any,
        capture_hotkey_combination: Any,
        publish_snapshot: Any,
    ) -> None:
        self.runtime = runtime
        self.settings_store = settings_store
        self.system_integration_service = system_integration_service
        self.capture_hotkey_combination = capture_hotkey_combination
        self.publish_snapshot = publish_snapshot

    def change_hotkey(self) -> None:
        """Открывает диалог и меняет основной хоткей."""
        result = self.capture_hotkey_combination(
            "Изменить основной хоткей",
            "Нажмите нужную комбинацию клавиш.\nНапример: зажмите Ctrl+Shift+Alt и нажмите T.",
            current_combination=self.runtime.primary_key_combination,
        )
        if result is None:
            return

        try:
            normalized = normalize_key_combination(result)
            self._update_hotkey_value(is_secondary=False, new_combination=normalized)
        except ValueError as error:
            self.runtime.system_integration_service.notify("MLX Whisper Dictation", f"Ошибка: {error}")
            return

        self._apply_hotkey_changes()
        LOGGER.info("⌨️ Основной хоткей изменён на: %s", normalized)
        self.runtime.system_integration_service.notify(
            "MLX Whisper Dictation",
            f"Основной хоткей изменён: {self.runtime.hotkey_status}",
        )

    def change_secondary_hotkey(self) -> None:
        """Открывает диалог и меняет дополнительный хоткей."""
        result = self.capture_hotkey_combination(
            "Изменить доп. хоткей",
            "Нажмите нужную комбинацию клавиш.\nОставьте пустым и нажмите Применить, чтобы отключить.",
            current_combination=self.runtime.secondary_key_combination,
        )
        if result is None:
            return

        try:
            normalized = normalize_key_combination(result) if result else ""
            self._update_hotkey_value(is_secondary=True, new_combination=normalized)
        except ValueError as error:
            self.runtime.system_integration_service.notify("MLX Whisper Dictation", f"Ошибка: {error}")
            return

        self._apply_hotkey_changes()
        if normalized:
            LOGGER.info("⌨️ Дополнительный хоткей изменён на: %s", normalized)
            self.runtime.system_integration_service.notify(
                "MLX Whisper Dictation",
                f"Доп. хоткей изменён: {self.runtime.secondary_hotkey_status}",
            )
            return

        LOGGER.info("⌨️ Дополнительный хоткей отключён")
        self.runtime.system_integration_service.notify("MLX Whisper Dictation", "Доп. хоткей отключён.")

    def change_llm_hotkey(self) -> None:
        """Открывает диалог и меняет LLM-хоткей."""
        result = self.capture_hotkey_combination(
            "Изменить LLM-хоткей",
            "Нажмите нужную комбинацию клавиш.\nОставьте пустым и нажмите Применить, чтобы отключить.",
            current_combination=self.runtime.llm_key_combination,
        )
        if result is None:
            return

        try:
            normalized = normalize_key_combination(result) if result else ""
        except ValueError as error:
            self.runtime.system_integration_service.notify("MLX Whisper Dictation", f"Ошибка: {error}")
            return

        old_combination = self.runtime.llm_key_combination
        self.runtime.llm_key_combination = normalized
        self.settings_store.save_str(Config.DEFAULTS_KEY_LLM_HOTKEY, self.runtime.launch_config.hotkeys.llm_store_value)
        self._apply_hotkey_changes()

        if normalized:
            LOGGER.info("🤖 LLM-хоткей изменён на: %s", normalized)
            self.runtime.system_integration_service.notify(
                "MLX Whisper Dictation",
                f"LLM-хоткей изменён: {self.runtime.llm_hotkey_status}",
            )
        else:
            LOGGER.info("🤖 LLM-хоткей отключён (был: %s)", old_combination)
            self.runtime.system_integration_service.notify("MLX Whisper Dictation", "LLM-хоткей отключён.")
        self.publish_snapshot()

    def request_accessibility_access(self) -> None:
        """Повторно запрашивает Accessibility."""
        granted = self.runtime.system_integration_service.request_accessibility_permission()
        self.runtime.permission_status["accessibility"] = self.runtime.system_integration_service.get_accessibility_status()
        self.publish_snapshot()
        if granted or self.runtime.permission_status["accessibility"] is True:
            self.runtime.system_integration_service.notify("MLX Whisper Dictation", "Доступ к Accessibility подтвержден.")
            return

        self.runtime.system_integration_service.warn_missing_accessibility_permission()

    def request_input_monitoring_access(self) -> None:
        """Повторно запрашивает Input Monitoring."""
        granted = self.runtime.system_integration_service.request_input_monitoring_permission()
        self.runtime.permission_status["input_monitoring"] = self.runtime.system_integration_service.get_input_monitoring_status()
        self.publish_snapshot()
        if granted or self.runtime.permission_status["input_monitoring"] is True:
            self.runtime.system_integration_service.notify("MLX Whisper Dictation", "Доступ к Input Monitoring подтвержден.")
            return

        self.runtime.system_integration_service.warn_missing_input_monitoring_permission()

    def active_key_combinations(self) -> list[str]:
        """Возвращает все включённые комбинации для основного listener-а."""
        return list(self.runtime.launch_config.hotkeys.active_key_combinations)

    def refresh_hotkey_statuses(self) -> None:
        """Синхронизирует display-строки хоткеев с текущими комбинациями."""
        self._refresh_hotkey_statuses()

    def _refresh_hotkey_statuses(self) -> None:
        self.runtime.hotkey_status = self.runtime.launch_config.hotkeys.hotkey_status
        self.runtime.secondary_hotkey_status = self.runtime.launch_config.hotkeys.secondary_hotkey_status
        self.runtime.llm_hotkey_status = self.runtime.launch_config.hotkeys.llm_hotkey_status

    def _persist_hotkey_settings(self) -> None:
        self.settings_store.save_str(Config.DEFAULTS_KEY_PRIMARY_HOTKEY, self.runtime.launch_config.hotkeys.primary_store_value)
        self.settings_store.save_str(Config.DEFAULTS_KEY_SECONDARY_HOTKEY, self.runtime.launch_config.hotkeys.secondary_store_value)

    def _can_update_hotkeys_runtime(self) -> bool:
        return hasattr(self.runtime.key_listener, "update_hotkeys")

    def _apply_hotkey_changes(self) -> bool:
        self._refresh_hotkey_statuses()
        self._persist_hotkey_settings()
        self.publish_snapshot()
        if self._can_update_hotkeys_runtime():
            self.runtime.key_listener.update_hotkeys(
                self.runtime.primary_key_combination,
                self.runtime.secondary_key_combination,
                self.runtime.llm_key_combination,
            )
            return True
        return False

    def _update_hotkey_value(self, *, is_secondary: bool, new_combination: str) -> None:
        if is_secondary:
            if new_combination and new_combination == self.runtime.primary_key_combination:
                raise ValueError("Дополнительный хоткей должен отличаться от основного.")
            if new_combination and new_combination == self.runtime.llm_key_combination:
                raise ValueError("Дополнительный хоткей должен отличаться от LLM-хоткея.")
            self.runtime.secondary_key_combination = new_combination
            return

        if new_combination == self.runtime.secondary_key_combination:
            raise ValueError("Основной хоткей должен отличаться от дополнительного.")
        if new_combination == self.runtime.llm_key_combination:
            raise ValueError("Основной хоткей должен отличаться от LLM-хоткея.")
        self.runtime.primary_key_combination = new_combination
