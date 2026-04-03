"""Use case-сценарии пользовательских настроек приложения."""

from __future__ import annotations

import logging
from typing import Any

from ..domain.constants import Config

LOGGER = logging.getLogger(__name__)


class SettingsUseCases:
    """Управляет настройками модели, языка, записи и методов вставки."""

    def __init__(
        self,
        runtime: Any,
        settings_store: Any,
        recorder: Any,
        transcriber: Any,
        llm_processor: Any,
        system_integration_service: Any,
        publish_snapshot: Any,
    ) -> None:
        self.runtime = runtime
        self.settings_store = settings_store
        self.recorder = recorder
        self.transcriber = transcriber
        self.llm_processor = llm_processor
        self.system_integration_service = system_integration_service
        self.publish_snapshot = publish_snapshot

    def change_input_device(self, device_index: int | None) -> None:
        """Переключает активное устройство ввода по индексу."""
        self.runtime.refresh_input_devices(publish_snapshot=False)
        selected_device = None
        if device_index is not None:
            selected_device = next((device for device in self.runtime.input_devices if device["index"] == device_index), None)
            if selected_device is None or selected_device == self.runtime.current_input_device:
                return

        self.runtime._select_runtime_input_device(selected_device)
        self.runtime._persist_selected_input_device_preference(selected_device)
        if selected_device is not None:
            LOGGER.info(
                "🎙️ Выбран микрофон: index=%s, name=%s",
                selected_device["index"],
                selected_device["name"],
            )
        else:
            LOGGER.info("🎙️ Сброшен выбор микрофона: использую системный по умолчанию")
        self.publish_snapshot()

    def change_language(self, language: str | None) -> None:
        """Переключает язык распознавания."""
        if self.runtime.languages is None:
            return
        if language == self.runtime.current_language:
            return
        if language is not None and language not in self.runtime.languages:
            return

        self.runtime.current_language = language
        if self.runtime.current_language is None:
            self.settings_store.remove_key(Config.DEFAULTS_KEY_LANGUAGE)
        else:
            self.settings_store.save_str(Config.DEFAULTS_KEY_LANGUAGE, self.runtime.current_language)
        self.publish_snapshot()

    def change_model(self, model_repo: str) -> None:
        """Переключает модель распознавания."""
        if model_repo not in self.runtime.model_options or model_repo == self.runtime.model_repo:
            return

        self.runtime.model_repo = model_repo
        self.runtime.model_name = model_repo.rsplit("/", maxsplit=1)[-1]
        self.transcriber.model_name = model_repo
        self.settings_store.save_str(Config.DEFAULTS_KEY_MODEL, model_repo)
        LOGGER.info("🧠 Выбрана модель: %s", model_repo)
        self.runtime.system_integration_service.notify("MLX Whisper Dictation", f"Модель переключена: {self.runtime.model_name}")
        self.publish_snapshot()

    def change_max_time(self, max_time: float | None) -> None:
        """Переключает лимит записи."""
        if max_time == self.runtime.max_time:
            return

        self.runtime.max_time = max_time
        self.settings_store.save_str(Config.DEFAULTS_KEY_MAX_TIME, self.runtime.launch_config.max_time_store_value)
        LOGGER.info("⏱ Обновлен лимит записи: %s", Config.format_max_time_status(self.runtime.max_time))
        self.publish_snapshot()

    def toggle_recording_notification(self) -> None:
        """Переключает уведомление о старте записи."""
        self.runtime.show_recording_notification = not self.runtime.show_recording_notification
        self.settings_store.save_bool(Config.DEFAULTS_KEY_RECORDING_NOTIFICATION, self.runtime.show_recording_notification)
        LOGGER.info(
            "🔔 Уведомление о старте записи: %s",
            "включено" if self.runtime.show_recording_notification else "выключено",
        )
        self.publish_snapshot()

    def toggle_recording_overlay(self) -> None:
        """Переключает всплывающий индикатор у курсора."""
        self.runtime.show_recording_overlay = not self.runtime.show_recording_overlay
        self.settings_store.save_bool(Config.DEFAULTS_KEY_RECORDING_OVERLAY, self.runtime.show_recording_overlay)
        LOGGER.info(
            "🎯 Индикатор у курсора и время: %s",
            "включён" if self.runtime.show_recording_overlay else "выключен",
        )
        self.publish_snapshot()

    def toggle_recording_time_in_menu_bar(self) -> None:
        """Переключает отображение времени записи в menu bar."""
        self.runtime.show_recording_time_in_menu_bar = not self.runtime.show_recording_time_in_menu_bar
        self.settings_store.save_bool(
            Config.DEFAULTS_KEY_RECORDING_TIME_IN_MENU_BAR,
            self.runtime.show_recording_time_in_menu_bar,
        )
        LOGGER.info(
            "⏱ Таймер записи в menu bar: %s",
            "включён" if self.runtime.show_recording_time_in_menu_bar else "выключен",
        )
        self.publish_snapshot()

    def change_performance_mode(self, performance_mode: object) -> None:
        """Меняет баланс между задержкой и ресурсами."""
        normalized_mode = Config.normalize_performance_mode(performance_mode)
        if normalized_mode == self.runtime.performance_mode:
            return

        self.runtime.performance_mode = normalized_mode
        self.settings_store.save_str(Config.DEFAULTS_KEY_PERFORMANCE_MODE, self.runtime.performance_mode)
        if hasattr(self.recorder, "set_performance_mode"):
            self.recorder.set_performance_mode(self.runtime.performance_mode)
        if self.llm_processor is not None:
            self.llm_processor.set_performance_mode(self.runtime.performance_mode)
        LOGGER.info("⚡ Режим работы переключён: %s", Config.performance_mode_label(self.runtime.performance_mode))
        self.publish_snapshot()

    def toggle_private_mode(self) -> None:
        """Переключает private mode для истории."""
        new_state = not self.transcriber.private_mode_enabled
        self.transcriber.set_private_mode(new_state)
        LOGGER.info(
            "🕶 Приватный режим: %s",
            "включён" if self.transcriber.private_mode_enabled else "выключен",
        )
        self.publish_snapshot()

    def toggle_paste_cgevent(self) -> None:
        """Переключает метод вставки через CGEvent."""
        self.transcriber.paste_cgevent_enabled = not self.transcriber.paste_cgevent_enabled
        self.settings_store.save_bool(Config.DEFAULTS_KEY_PASTE_CGEVENT, self.transcriber.paste_cgevent_enabled)
        LOGGER.info(
            "📝 Прямой ввод (CGEvent): %s",
            "включён" if self.transcriber.paste_cgevent_enabled else "выключен",
        )
        self.publish_snapshot()

    def toggle_paste_ax(self) -> None:
        """Переключает метод вставки через Accessibility API."""
        self.transcriber.paste_ax_enabled = not self.transcriber.paste_ax_enabled
        self.settings_store.save_bool(Config.DEFAULTS_KEY_PASTE_AX, self.transcriber.paste_ax_enabled)
        LOGGER.info(
            "📝 Accessibility API: %s",
            "включён" if self.transcriber.paste_ax_enabled else "выключен",
        )
        self.publish_snapshot()

    def toggle_paste_clipboard(self) -> None:
        """Переключает метод вставки через буфер обмена."""
        self.transcriber.paste_clipboard_enabled = not self.transcriber.paste_clipboard_enabled
        self.settings_store.save_bool(Config.DEFAULTS_KEY_PASTE_CLIPBOARD, self.transcriber.paste_clipboard_enabled)
        LOGGER.info(
            "📝 Буфер обмена (Cmd+V): %s",
            "включён" if self.transcriber.paste_clipboard_enabled else "выключен",
        )
        self.publish_snapshot()

    def toggle_llm_clipboard(self) -> None:
        """Переключает использование буфера обмена для LLM."""
        self.transcriber.llm_clipboard_enabled = not getattr(self.transcriber, "llm_clipboard_enabled", True)
        self.settings_store.save_bool(Config.DEFAULTS_KEY_LLM_CLIPBOARD, self.transcriber.llm_clipboard_enabled)
        LOGGER.info(
            "🤖 Буфер обмена для LLM: %s",
            "включён" if self.transcriber.llm_clipboard_enabled else "выключен",
        )
        self.publish_snapshot()

    def change_llm_prompt(self, prompt_name: str) -> None:
        """Переключает текущий пресет системного промпта LLM."""
        if prompt_name not in Config.LLM_PROMPT_PRESETS:
            return

        self.runtime.llm_prompt_name = prompt_name
        self.settings_store.save_str(Config.DEFAULTS_KEY_LLM_PROMPT, self.runtime.llm_prompt_name)
        LOGGER.info("🤖 Выбран промпт LLM: %s", self.runtime.llm_prompt_name)
        self.publish_snapshot()

    def prune_expired_history(self) -> None:
        """Удаляет просроченную историю, если transcriber поддерживает это."""
        if hasattr(self.transcriber, "prune_expired_history"):
            self.transcriber.prune_expired_history()
