"""Use case-сценарии управления хоткеями."""

from __future__ import annotations

import logging
from typing import Any

from ..domain.constants import Config
from ..domain.hotkeys import format_hotkey_status, normalize_key_combination

LOGGER = logging.getLogger(__name__)


class HotkeyManagementUseCases:
    """Управляет изменением основных и LLM-хоткеев."""

    def __init__(
        self,
        runtime: Any,
        settings_store: Any,
        system_integration_service: Any,
        capture_hotkey_combination: Any,
        create_hotkey_listener: Any,
        toggle_app: Any,
        toggle_llm_callback: Any,
        publish_snapshot: Any,
    ) -> None:
        self.runtime = runtime
        self.settings_store = settings_store
        self.system_integration_service = system_integration_service
        self.capture_hotkey_combination = capture_hotkey_combination
        self.create_hotkey_listener = create_hotkey_listener
        self.toggle_app = toggle_app
        self.toggle_llm_callback = toggle_llm_callback
        self.publish_snapshot = publish_snapshot

    def change_hotkey(self) -> None:
        """Открывает диалог и меняет основной хоткей."""
        if not self._can_update_hotkeys_runtime():
            self.runtime.system_integration_service.notify(
                "MLX Whisper Dictation",
                "Смена хоткея недоступна в режиме двойного нажатия Command.",
            )
            return

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
        if not self._can_update_hotkeys_runtime():
            self.runtime.system_integration_service.notify(
                "MLX Whisper Dictation",
                "Смена хоткея недоступна в режиме двойного нажатия Command.",
            )
            return

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
        self.settings_store.save_str(Config.DEFAULTS_KEY_LLM_HOTKEY, self.runtime.llm_key_combination)
        self._refresh_hotkey_statuses()

        if self.runtime.llm_key_listener is not None:
            self.runtime.llm_key_listener.stop()

        if normalized:
            new_listener = self.create_hotkey_listener(self.toggle_app, normalized, self.toggle_llm_callback)
            new_listener.start()
            self.runtime.llm_key_listener = new_listener
            LOGGER.info("🤖 LLM-хоткей изменён на: %s", normalized)
            self.runtime.system_integration_service.notify(
                "MLX Whisper Dictation",
                f"LLM-хоткей изменён: {self.runtime.llm_hotkey_status}",
            )
        else:
            self.runtime.llm_key_listener = None
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
        return [
            key_combination
            for key_combination in (self.runtime.primary_key_combination, self.runtime.secondary_key_combination)
            if key_combination
        ]

    def refresh_hotkey_statuses(self) -> None:
        """Синхронизирует display-строки хоткеев с текущими комбинациями."""
        self._refresh_hotkey_statuses()

    def _refresh_hotkey_statuses(self) -> None:
        if self.runtime.primary_key_combination:
            self.runtime.hotkey_status = format_hotkey_status(self.runtime.primary_key_combination)
        if self.runtime.secondary_key_combination:
            self.runtime.secondary_hotkey_status = format_hotkey_status(self.runtime.secondary_key_combination)
        else:
            self.runtime.secondary_hotkey_status = "не задан"
        if self.runtime.llm_key_combination:
            self.runtime.llm_hotkey_status = format_hotkey_status(self.runtime.llm_key_combination)
        else:
            self.runtime.llm_hotkey_status = "не задан"

    def _persist_hotkey_settings(self) -> None:
        self.settings_store.save_str(Config.DEFAULTS_KEY_PRIMARY_HOTKEY, self.runtime.primary_key_combination)
        self.settings_store.save_str(Config.DEFAULTS_KEY_SECONDARY_HOTKEY, self.runtime.secondary_key_combination)

    def _can_update_hotkeys_runtime(self) -> bool:
        return hasattr(self.runtime.key_listener, "update_key_combinations")

    def _apply_hotkey_changes(self) -> bool:
        self._refresh_hotkey_statuses()
        self._persist_hotkey_settings()
        self.publish_snapshot()
        if self._can_update_hotkeys_runtime():
            self.runtime.key_listener.update_key_combinations(self.active_key_combinations())
            return True
        return False

    def _update_hotkey_value(self, *, is_secondary: bool, new_combination: str) -> None:
        if is_secondary:
            if new_combination and new_combination == self.runtime.primary_key_combination:
                raise ValueError("Дополнительный хоткей должен отличаться от основного.")
            self.runtime.secondary_key_combination = new_combination
            return

        if new_combination == self.runtime.secondary_key_combination:
            raise ValueError("Основной хоткей должен отличаться от дополнительного.")
        self.runtime.primary_key_combination = new_combination
