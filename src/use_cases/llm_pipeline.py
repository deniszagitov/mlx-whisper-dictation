"""Use case-сценарии LLM-пайплайна и загрузки модели."""

from __future__ import annotations

import logging
import threading
import time
from typing import TYPE_CHECKING, Any

from ..domain.constants import Config
from ..domain.llm_processing import should_use_clipboard_context
from ..domain.model_downloads import ModelRequiredError, format_bytes, format_model_download_metrics

if TYPE_CHECKING:
    import numpy as np
    import numpy.typing as npt

LOGGER = logging.getLogger(__name__)


def _prevent_display_sleep(runtime: Any) -> None:
    """Включает временную защиту дисплея от сна, если runtime её поддерживает."""
    prevent = getattr(runtime, "prevent_display_sleep_for_active_session", None)
    if callable(prevent):
        prevent()


def _release_display_sleep(runtime: Any) -> None:
    """Отпускает временную защиту дисплея от сна, если runtime её поддерживает."""
    release = getattr(runtime, "release_display_sleep_for_active_session", None)
    if callable(release):
        release(immediate=True, reason="llm_cancel_or_start_failure")


class LlmPipelineUseCases:
    """Оркестрирует сценарий запись → Whisper → LLM."""

    def __init__(
        self,
        runtime: Any,
        recorder: Any,
        transcriber: Any,
        llm_processor: Any,
        clipboard_service: Any,
        system_integration_service: Any,
        recording_overlay: Any,
        stop_recording: Any,
        publish_snapshot: Any,
        obsidian_service: Any | None = None,
    ) -> None:
        self.runtime = runtime
        self.recorder = recorder
        self.transcriber = transcriber
        self.llm_processor = llm_processor
        self.clipboard_service = clipboard_service
        self.system_integration_service = system_integration_service
        self.recording_overlay = recording_overlay
        self.stop_recording = stop_recording
        self.publish_snapshot = publish_snapshot
        self.obsidian_service = obsidian_service

    def toggle_llm(self) -> None:
        """Переключает сценарий запись → Whisper → LLM."""
        if self.runtime.started:
            self.stop_recording()
            return

        if self.llm_processor is None:
            self.runtime.system_integration_service.notify("MLX Whisper Dictation", "LLM-процессор не инициализирован.")
            return

        if not self.llm_processor.is_model_cached():
            self.runtime.system_integration_service.notify("MLX Whisper Dictation", "LLM-модель ещё не скачана. Запускаю загрузку…")
            self.download_llm_model()
            return

        if not self.runtime.prepare_recording():
            return

        LOGGER.info("🤖 Запуск LLM-пайплайна, промпт=%r", self.runtime.llm_prompt_name)
        self.runtime.state = Config.STATUS_RECORDING
        _prevent_display_sleep(self.runtime)
        if self.runtime.show_recording_notification:
            self.runtime.system_integration_service.notify("MLX Whisper Dictation", "Запись для LLM. Говорите.")
        self.runtime.started = True

        system_prompt = Config.LLM_PROMPT_PRESETS.get(
            self.runtime.llm_prompt_name,
            Config.LLM_PROMPT_PRESETS[Config.DEFAULT_LLM_PROMPT_NAME],
        )
        llm_processor = self.llm_processor
        is_obsidian = self.runtime.llm_prompt_name in Config.OBSIDIAN_PROMPT_NAMES
        is_obsidian_remind = self.runtime.llm_prompt_name == "📝 Obsidian: напомни"
        obsidian_service = self.obsidian_service

        def on_audio_ready(
            audio_data: npt.NDArray[np.float32],
            language: str | None,
            set_status: Any,
            is_current: Any,
        ) -> None:
            whisper_text = self.transcriber.transcribe_to_text(audio_data, language)
            if not whisper_text or not is_current():
                return

            use_clipboard = getattr(self.transcriber, "llm_clipboard_enabled", True)
            context = None

            if is_obsidian_remind and obsidian_service is not None:
                vault_context = obsidian_service.search_notes(whisper_text)
                if vault_context:
                    context = vault_context
            elif use_clipboard:
                clipboard_text = self.clipboard_service.read_text()
                if should_use_clipboard_context(whisper_text, clipboard_text):
                    context = clipboard_text

            set_status(Config.STATUS_LLM_PROCESSING)
            max_tokens = Config.LLM_OBSIDIAN_MAX_TOKENS if is_obsidian else None
            try:
                llm_response = llm_processor.process_text(
                    whisper_text,
                    system_prompt,
                    context=context,
                    max_tokens=max_tokens,
                )
            except ModelRequiredError as error:
                LOGGER.warning("📥 LLM-пайплайн запросил загрузку модели: label=%s, model=%s", error.label, error.model_name)
                download_required = getattr(self.runtime, "download_required_model", None)
                if callable(download_required):
                    download_required(error)
                else:
                    self.download_llm_model()
                self.runtime.system_integration_service.notify(
                    "MLX Whisper Dictation",
                    f"{error.label} ещё не готова. Запускаю загрузку; исходный текст сохранён в буфер обмена.",
                )
                self.clipboard_service.write_text(whisper_text)
                self.transcriber.add_to_history(whisper_text)
                return
            except Exception:
                LOGGER.exception("❌ Ошибка LLM-обработки")
                self.runtime.system_integration_service.notify(
                    "MLX Whisper Dictation",
                    "Ошибка LLM. Текст сохранён в буфер обмена.",
                )
                self.clipboard_service.write_text(whisper_text)
                self.transcriber.add_to_history(whisper_text)
                return

            self.transcriber.add_token_usage(llm_processor.last_token_usage)
            if not is_current():
                LOGGER.info("🤖 Ответ LLM устарел, пропускаю вставку")
                return

            final_text = llm_response or whisper_text

            if is_obsidian and not is_obsidian_remind and obsidian_service is not None:
                try:
                    note_path = obsidian_service.write_note(final_text)
                except Exception:
                    LOGGER.exception("❌ Ошибка записи в Obsidian vault")
                else:
                    self.transcriber.add_to_history(final_text)
                    self.runtime.system_integration_service.notify(
                        "MLX Whisper Dictation",
                        f"📝 Заметка сохранена: {note_path.name}",
                    )
                    return

            self.transcriber.add_to_history(final_text)
            if use_clipboard:
                self.clipboard_service.write_text(final_text)
                LOGGER.info("🤖 LLM-ответ скопирован в буфер обмена")
                self.runtime.system_integration_service.notify(
                    "MLX Whisper Dictation",
                    "LLM-ответ скопирован в буфер обмена.",
                )
            else:
                LOGGER.info("🤖 LLM-ответ добавлен в историю (буфер обмена отключён)")
                self.runtime.system_integration_service.notify("MLX Whisper Dictation", "LLM-ответ сохранён в историю.")

        try:
            self.recorder.start(self.runtime.current_language, on_audio_ready=on_audio_ready)
        except Exception:
            LOGGER.exception("❌ Не удалось запустить запись для LLM")
            self.runtime.started = False
            self.runtime.state = Config.STATUS_IDLE
            _release_display_sleep(self.runtime)
            self.publish_snapshot()
            raise
        self.runtime.start_time = time.time()
        self.runtime.elapsed_time = 0
        if self.runtime.show_recording_overlay:
            self.runtime.recording_overlay.show()
        self.publish_snapshot()

    def is_model_cached(self) -> bool:
        """Проверяет, что LLM-модель уже доступна локально."""
        return self.llm_processor.is_model_cached() if self.llm_processor is not None else False

    def download_llm_model(self) -> None:
        """Запускает загрузку LLM-модели и публикует прогресс."""
        llm_proc = self.llm_processor
        if llm_proc is None:
            return
        if self.runtime.llm_downloading:
            self.runtime.system_integration_service.notify("MLX Whisper Dictation", "Загрузка уже выполняется…")
            return

        LOGGER.info("📥 Запускаю загрузку LLM-модели")
        self.runtime.llm_downloading = True
        self.runtime.llm_download_title = "📥 Загрузка LLM: 0%"
        raw_model_name = getattr(llm_proc, "model_name", None)
        model_fragment = f" {raw_model_name}" if raw_model_name else ""
        self.runtime.system_integration_service.notify(
            "MLX Whisper Dictation",
            f"LLM-модель{model_fragment} не найдена локально. Загружаю из Hugging Face…",
        )
        self.publish_snapshot()

        def on_progress(
            desc: str,
            pct: float,
            total_bytes: int,
            speed_bytes_per_second: float | None = None,
            eta_seconds: float | None = None,
            warning: str | None = None,
        ) -> None:
            metrics = format_model_download_metrics(speed_bytes_per_second, eta_seconds)
            suffix = f" · {metrics}" if metrics else ""
            prefix = "⚠️" if warning else "📥"
            warning_suffix = f" · {warning}" if warning else ""
            if total_bytes > 0:
                self.runtime.llm_download_title = f"{prefix} Загрузка LLM: {pct:.0f}% ({format_bytes(total_bytes)}){warning_suffix}{suffix}"
            elif pct >= Config.DOWNLOAD_COMPLETE_PCT:
                self.runtime.llm_download_title = "✅ LLM-модель загружена"
            else:
                self.runtime.llm_download_title = f"{prefix} Загрузка LLM: {desc}{warning_suffix}{suffix}"
            self.publish_snapshot()

        def download_thread() -> None:
            try:
                LOGGER.info("📥 Thread загрузки LLM-модели стартовал")
                llm_proc.download_progress_callback = on_progress
                llm_proc.ensure_model_downloaded()
                self.runtime.llm_download_title = "✅ LLM-модель загружена"
                self.runtime.system_integration_service.notify("MLX Whisper Dictation", "LLM-модель успешно загружена.")
            except Exception:
                LOGGER.exception("❌ Ошибка загрузки LLM-модели")
                self.runtime.llm_download_title = "❌ Ошибка загрузки LLM"
                self.runtime.system_integration_service.notify(
                    "MLX Whisper Dictation",
                    "Не удалось скачать LLM-модель. Попробуйте снова.",
                )
            finally:
                llm_proc.download_progress_callback = None
                self.runtime.llm_downloading = False
                self.publish_snapshot()

        thread = threading.Thread(target=download_thread, daemon=True)
        thread.start()
