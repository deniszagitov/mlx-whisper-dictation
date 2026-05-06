"""Use case-сценарии записи и базовой транскрибации."""

from __future__ import annotations

import logging
import time
from typing import Any

from ..domain.constants import Config

LOGGER = logging.getLogger(__name__)

_KEYCODE_ESCAPE = 53


def _prevent_display_sleep(runtime: Any) -> None:
    """Включает временную защиту дисплея от сна, если runtime её поддерживает."""
    prevent = getattr(runtime, "prevent_display_sleep_for_active_session", None)
    if callable(prevent):
        prevent()


def _release_display_sleep(runtime: Any) -> None:
    """Отпускает временную защиту дисплея от сна, если runtime её поддерживает."""
    release = getattr(runtime, "release_display_sleep_for_active_session", None)
    if callable(release):
        release(immediate=True, reason="recording_cancel_or_start_failure")


class RecordingUseCases:
    """Управляет обычным сценарием записи и её жизненным циклом."""

    def __init__(
        self,
        runtime: Any,
        recorder: Any,
        transcriber: Any,
        system_integration_service: Any,
        recording_overlay: Any,
        publish_snapshot: Any,
    ) -> None:
        self.runtime = runtime
        self.recorder = recorder
        self.transcriber = transcriber
        self.system_integration_service = system_integration_service
        self.recording_overlay = recording_overlay
        self.publish_snapshot = publish_snapshot

    def start_recording(self) -> None:
        """Запускает обычный сценарий записи и распознавания."""
        if not self.runtime.prepare_recording():
            return

        LOGGER.info("🎙️ Запись началась")
        self.runtime.state = Config.STATUS_RECORDING
        _prevent_display_sleep(self.runtime)
        if self.runtime.show_recording_notification:
            self.runtime.system_integration_service.notify(
                "MLX Whisper Dictation",
                "Запись началась. Говорите, пока в строке меню горит красный индикатор.",
            )
        self.runtime.started = True
        try:
            self.recorder.start(self.runtime.current_language, on_audio_ready=self._on_audio_ready)
        except Exception:
            LOGGER.exception("❌ Не удалось запустить запись")
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

    def stop_recording(self) -> None:
        """Останавливает активную запись и запускает этап распознавания."""
        if not self.runtime.started:
            return

        LOGGER.info("⏹ Запись остановлена, запускаю распознавание")
        self.runtime.started = False
        self.runtime.state = Config.STATUS_TRANSCRIBING
        self.recorder.stop()
        self.runtime.recording_overlay.hide()
        self.publish_snapshot()

    def cancel_recording(self) -> None:
        """Отменяет активную запись без распознавания."""
        if not self.runtime.started:
            return

        LOGGER.info("❌ Запись отменена пользователем (Escape)")
        self.runtime.started = False
        self.runtime.state = Config.STATUS_IDLE
        self.recorder.cancel()
        self.runtime.recording_overlay.hide()
        _release_display_sleep(self.runtime)
        self.publish_snapshot()

    def on_status_tick(self) -> None:
        """Обновляет счётчик времени записи и контролирует max_time."""
        if not self.runtime.started:
            return

        self.runtime.elapsed_time = int(time.time() - self.runtime.start_time)
        self.runtime.recording_overlay.update_time(self.runtime.elapsed_time)
        if self.runtime.max_time is not None and self.runtime.elapsed_time >= self.runtime.max_time:
            self.stop_recording()

    def toggle(self) -> None:
        """Переключает обычный сценарий записи."""
        if self.runtime.started:
            self.stop_recording()
        else:
            self.start_recording()

    def handle_escape_keycode(self, keycode: int) -> None:
        """Отменяет запись по Escape."""
        if keycode == _KEYCODE_ESCAPE and self.runtime.started:
            self.cancel_recording()

    def _on_audio_ready(
        self,
        audio_data: Any,
        language: str | None,
        _set_status: Any,
        _is_current: Any,
    ) -> None:
        """Передаёт записанный звук в use case транскрибации."""
        self.transcriber.transcribe(audio_data, language)
