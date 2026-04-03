"""Use case распознавания речи, вставки текста и истории."""

from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Callable

    import numpy as np
    import numpy.typing as npt

    from ..domain.ports import SettingsStoreProtocol
    from ..domain.types import AudioDiagnostics, HistoryRecord, TranscriberPreferences

from ..domain.constants import Config
from ..domain.transcription import (
    build_audio_diagnostics,
    extract_transcription_token_count,
    looks_like_hallucination,
    normalize_history_record,
)
from ..domain.types import TranscriberPreferences

LOGGER = logging.getLogger(__name__)


class _DisabledDiagnosticsStore:
    """Null-object для сценариев, где сохранение диагностических файлов отключено."""

    def artifact_stem(self) -> str:
        """Возвращает псевдо-имя диагностической группы."""
        timestamp = time.strftime("%Y%m%d-%H%M%S")
        milliseconds = int((time.time() % 1) * 1000)
        return f"{timestamp}-{milliseconds:03d}"

    def save_audio_recording(
        self,
        stem: str,
        audio_data: npt.NDArray[np.float32],
        diagnostics: AudioDiagnostics,
    ) -> None:
        """Игнорирует сохранение WAV-артефактов."""
        return None

    def save_transcription_artifacts(
        self,
        stem: str,
        diagnostics: AudioDiagnostics,
        result: Any = None,
        text: str = "",
        error_message: str | None = None,
    ) -> None:
        """Игнорирует сохранение диагностических результатов."""
        return None


class _InMemorySettingsStore:
    """Простейшее in-memory хранилище настроек для fallback-сценариев."""

    def __init__(self) -> None:
        self._values: dict[str, object] = {}

    def load_bool(self, key: str, fallback: bool) -> bool:
        return bool(self._values.get(key, fallback))

    def contains_key(self, key: str) -> bool:
        return key in self._values

    def save_bool(self, key: str, value: bool) -> None:
        self._values[key] = bool(value)

    def load_list(self, key: str) -> list[str]:
        value = self._values.get(key, [])
        return list(value) if isinstance(value, list) else []

    def save_list(self, key: str, value: list[str]) -> None:
        self._values[key] = list(value)

    def load_int(self, key: str, fallback: int) -> int:
        value = self._values.get(key, fallback)
        return value if isinstance(value, int) else fallback

    def save_int(self, key: str, value: int) -> None:
        self._values[key] = int(value)

    def load_str(self, key: str, fallback: str | None = None) -> str | None:
        value = self._values.get(key, fallback)
        return None if value is None else str(value)

    def save_str(self, key: str, value: object) -> None:
        self._values[key] = value

    def load_max_time(self, fallback: int | float | None) -> int | float | None:
        return self._values.get(Config.DEFAULTS_KEY_MAX_TIME, fallback)  # type: ignore[return-value]

    def save_max_time(self, value: int | float | None) -> None:
        self._values[Config.DEFAULTS_KEY_MAX_TIME] = value

    def load_input_device_index(self) -> int | None:
        value = self._values.get(Config.DEFAULTS_KEY_INPUT_DEVICE_INDEX)
        return value if isinstance(value, int) else None

    def load_input_device_name(self) -> str | None:
        value = self._values.get(Config.DEFAULTS_KEY_INPUT_DEVICE_NAME)
        if value is None:
            return None
        normalized = str(value).strip()
        return normalized or None

    def save_input_device_index(self, value: int | None) -> None:
        self._values[Config.DEFAULTS_KEY_INPUT_DEVICE_INDEX] = value

    def save_input_device_name(self, value: str | None) -> None:
        if value is None:
            self._values.pop(Config.DEFAULTS_KEY_INPUT_DEVICE_NAME, None)
            return
        normalized = str(value).strip()
        if not normalized:
            self._values.pop(Config.DEFAULTS_KEY_INPUT_DEVICE_NAME, None)
            return
        self._values[Config.DEFAULTS_KEY_INPUT_DEVICE_NAME] = normalized

    def remove_key(self, key: str) -> None:
        self._values.pop(key, None)


def _noop_notify_user(_title: str, _message: str) -> None:
    """Игнорирует системные уведомления в тестовых и headless-сценариях."""
    return None


def _default_accessibility_status() -> bool:
    """Считает Accessibility доступным, если integration-hook не подключён."""
    return True


def _default_input_monitoring_status() -> bool | None:
    """Считает Input Monitoring доступным, если integration-hook не подключён."""
    return True


def _default_accessibility_request() -> bool:
    """Возвращает успешный результат для request-hook по умолчанию."""
    return True


def _default_input_monitoring_request() -> bool | None:
    """Возвращает успешный результат для request-hook по умолчанию."""
    return True


def _noop_permission_warning() -> None:
    """Игнорирует предупреждение о недостающих правах."""
    return None


class TranscriptionUseCases:
    """Распознаёт аудио, вставляет результат и ведёт историю.

    Attributes:
        diagnostics_store: Adapter сохранения диагностических артефактов.
        model_name: Имя или путь к модели MLX Whisper.
        paste_cgevent_enabled: Включён ли метод прямого ввода через CGEvent Unicode.
        paste_ax_enabled: Включён ли метод ввода через Accessibility API.
        paste_clipboard_enabled: Включён ли метод ввода через буфер обмена (Cmd+V).
        history: Список ранее распознанных текстов.
        history_callback: Callback для уведомления UI об изменении истории.
    """

    def __init__(
        self,
        model_name: str,
        settings_store: SettingsStoreProtocol | None = None,
        preferences: TranscriberPreferences | None = None,
        diagnostics_store: Any | None = None,
        transcription_runner: Callable[[npt.NDArray[np.float32], str, str | None], dict[str, Any]] | None = None,
        type_text_via_cgevent: Callable[[str], None] | None = None,
        insert_text_via_ax: Callable[[str], None] | None = None,
        send_cmd_v: Callable[[], None] | None = None,
        clipboard_reader: Callable[[], str | None] | None = None,
        clipboard_writer: Callable[[str], None] | None = None,
        history_item_loader: Callable[[], list[Any]] | None = None,
        history_record_saver: Callable[[list[HistoryRecord]], None] | None = None,
        notify_user: Callable[[str, str], None] | None = None,
        is_accessibility_trusted: Callable[[], bool] | None = None,
        get_input_monitoring_status: Callable[[], bool | None] | None = None,
        request_accessibility_permission: Callable[[], bool] | None = None,
        request_input_monitoring_permission: Callable[[], bool | None] | None = None,
        warn_missing_accessibility_permission: Callable[[], None] | None = None,
        warn_missing_input_monitoring_permission: Callable[[], None] | None = None,
    ) -> None:
        """Создаёт use case распознавания и вставки.

        Args:
            model_name: Имя модели Hugging Face или локальный путь к модели.
            settings_store: Хранилище пользовательских настроек и флагов runtime.
            preferences: Нормализованные настройки методов вставки и private mode.
            diagnostics_store: Необязательный adapter сохранения диагностических файлов.
            transcription_runner: Необязательный runtime-вызов Whisper.
            type_text_via_cgevent: Необязательный runtime-ввод через CGEvent.
            insert_text_via_ax: Необязательный runtime-ввод через Accessibility API.
            send_cmd_v: Необязательный runtime для Cmd+V.
            clipboard_reader: Необязательное чтение системного буфера обмена.
            clipboard_writer: Необязательная запись в системный буфер обмена.
            history_item_loader: Необязательное чтение сырых записей истории.
            history_record_saver: Необязательное сохранение нормализованной истории.
            notify_user: Необязательное системное уведомление для ошибок и fallback.
            is_accessibility_trusted: Необязательная проверка права Accessibility.
            get_input_monitoring_status: Необязательная проверка права Input Monitoring.
            request_accessibility_permission: Необязательный повторный запрос права Accessibility.
            request_input_monitoring_permission: Необязательный повторный запрос права Input Monitoring.
            warn_missing_accessibility_permission: Необязательное предупреждение о недостающем Accessibility.
            warn_missing_input_monitoring_permission: Необязательное предупреждение о недостающем Input Monitoring.
        """
        self.settings_store = settings_store or _InMemorySettingsStore()
        self.diagnostics_store = diagnostics_store or _DisabledDiagnosticsStore()
        self._transcription_runner = transcription_runner
        self._type_text_via_cgevent_runtime = type_text_via_cgevent
        self._insert_text_via_ax_runtime = insert_text_via_ax
        self._send_cmd_v_runtime = send_cmd_v
        self._clipboard_reader = clipboard_reader
        self._clipboard_writer = clipboard_writer
        self._history_item_loader = history_item_loader or (lambda: [])
        self._history_record_saver = history_record_saver or (lambda _records: None)
        self._notify_user_runtime = notify_user or _noop_notify_user
        self._accessibility_status_reader = is_accessibility_trusted or _default_accessibility_status
        self._input_monitoring_status_reader = get_input_monitoring_status or _default_input_monitoring_status
        self._request_accessibility_permission_runtime = request_accessibility_permission or _default_accessibility_request
        self._request_input_monitoring_permission_runtime = (
            request_input_monitoring_permission or _default_input_monitoring_request
        )
        self._warn_missing_accessibility_permission_runtime = (
            warn_missing_accessibility_permission or _noop_permission_warning
        )
        self._warn_missing_input_monitoring_permission_runtime = (
            warn_missing_input_monitoring_permission or _noop_permission_warning
        )
        self.model_name = model_name
        self.preferences = preferences or TranscriberPreferences.from_store(self.settings_store)
        self._history_records: list[HistoryRecord] = []
        self.history: list[str] = []
        if not self.private_mode_enabled:
            self._reload_persisted_history()
        self.history_callback: Callable[[], None] | None = None
        self.token_usage_callback: Callable[[], None] | None = None

    @property
    def paste_cgevent_enabled(self) -> bool:
        """Возвращает флаг метода вставки через CGEvent."""
        return self.preferences.paste_cgevent_enabled

    @paste_cgevent_enabled.setter
    def paste_cgevent_enabled(self, enabled: object) -> None:
        self.preferences = self.preferences.with_paste_cgevent_enabled(enabled)

    @property
    def paste_ax_enabled(self) -> bool:
        """Возвращает флаг метода вставки через Accessibility API."""
        return self.preferences.paste_ax_enabled

    @paste_ax_enabled.setter
    def paste_ax_enabled(self, enabled: object) -> None:
        self.preferences = self.preferences.with_paste_ax_enabled(enabled)

    @property
    def paste_clipboard_enabled(self) -> bool:
        """Возвращает флаг метода вставки через буфер обмена."""
        return self.preferences.paste_clipboard_enabled

    @paste_clipboard_enabled.setter
    def paste_clipboard_enabled(self, enabled: object) -> None:
        self.preferences = self.preferences.with_paste_clipboard_enabled(enabled)

    @property
    def llm_clipboard_enabled(self) -> bool:
        """Возвращает флаг использования буфера обмена для LLM."""
        return self.preferences.llm_clipboard_enabled

    @llm_clipboard_enabled.setter
    def llm_clipboard_enabled(self, enabled: object) -> None:
        self.preferences = self.preferences.with_llm_clipboard_enabled(enabled)

    @property
    def private_mode_enabled(self) -> bool:
        """Возвращает флаг private mode."""
        return self.preferences.private_mode_enabled

    @private_mode_enabled.setter
    def private_mode_enabled(self, enabled: object) -> None:
        self.preferences = self.preferences.with_private_mode(enabled)

    @property
    def total_tokens(self) -> int:
        """Возвращает общий счётчик токенов."""
        return self.preferences.total_tokens

    @total_tokens.setter
    def total_tokens(self, token_count: object) -> None:
        self.preferences = self.preferences.with_total_tokens(token_count)

    def set_private_mode(self, enabled: object) -> None:
        """Переключает private mode для истории текста.

        В private mode история не загружается из persistence-адаптера и не
        сохраняется между перезапусками. Уже сохранённая история остаётся
        в defaults, но скрывается до выхода из private mode.

        Args:
            enabled: Нужно ли включить private mode.
        """
        self.private_mode_enabled = enabled
        self.settings_store.save_bool(Config.DEFAULTS_KEY_PRIVATE_MODE, self.private_mode_enabled)
        if self.private_mode_enabled:
            self._history_records = []
            self.history = []
        else:
            self._reload_persisted_history()
        if self.history_callback is not None:
            try:
                self.history_callback()
            except Exception:
                LOGGER.exception("⚠️ Ошибка в history_callback")

    def _current_time(self) -> float:
        """Возвращает текущее время в Unix timestamp."""
        return time.time()

    def _sync_history_state(self) -> None:
        """Синхронизирует публичный список истории с внутренними записями."""
        self.history = [record["text"] for record in self._history_records]

    def _sync_internal_history_from_public_list(self) -> None:
        """Подхватывает прямые изменения self.history, используемые в тестах."""
        if len(self._history_records) == len(self.history) and all(
            record["text"] == text for record, text in zip(self._history_records, self.history, strict=False)
        ):
            return

        current_time = self._current_time()
        self._history_records = [{"text": str(text), "created_at": current_time} for text in self.history]

    def _prune_expired_history(self) -> bool:
        """Удаляет записи истории старше 24 часов."""
        current_time = self._current_time()
        retained_records = []
        for record in self._history_records:
            normalized = normalize_history_record(record, current_time)
            if normalized is not None:
                retained_records.append(normalized)

        changed = retained_records != self._history_records
        self._history_records = retained_records
        self._sync_history_state()
        return changed

    def _reload_persisted_history(self) -> None:
        """Перечитывает историю из persistence-адаптера и сразу удаляет просроченные записи."""
        current_time = self._current_time()
        self._history_records = [
            normalized
            for item in self._load_history_items()
            if (normalized := normalize_history_record(item, current_time)) is not None
        ]
        self._sync_history_state()
        self._save_history_records(self._history_records)

    def prune_expired_history(self) -> bool:
        """Публично очищает историю старше 24 часов и сохраняет результат."""
        self._sync_internal_history_from_public_list()
        changed = self._prune_expired_history()
        if changed and not self.private_mode_enabled:
            self._save_history_records(self._history_records)
        return changed

    def _notify_token_usage_changed(self) -> None:
        """Вызывает callback обновления UI после изменения счётчика токенов."""
        if self.token_usage_callback is not None:
            try:
                self.token_usage_callback()
            except Exception:
                LOGGER.exception("⚠️ Ошибка в token_usage_callback")

    def add_token_usage(self, token_count: int) -> None:
        """Добавляет подтверждённое количество токенов к общему счётчику."""
        confirmed_tokens = max(int(token_count), 0)
        if confirmed_tokens == 0:
            return

        self.total_tokens = self.total_tokens + confirmed_tokens
        self.settings_store.save_int(Config.DEFAULTS_KEY_TOTAL_TOKENS, self.total_tokens)
        LOGGER.debug("🔢 Токены добавлены в счётчик: +%d, всего=%d", confirmed_tokens, self.total_tokens)
        self._notify_token_usage_changed()

    def _type_text_via_cgevent(self, text: str) -> None:
        """Вставляет текст через отправку Unicode-символов посредством CGEvent.

        Разбивает текст на пакеты и отправляет каждый пакет как пару
        keyDown/keyUp событий с прикреплённой Unicode-строкой.
        Не трогает буфер обмена.

        Args:
            text: Текст для ввода.

        Raises:
            RuntimeError: Если не удалось создать источник событий.
        """
        if self._type_text_via_cgevent_runtime is None:
            raise RuntimeError("CGEvent runtime не настроен")
        self._type_text_via_cgevent_runtime(text)

    def _insert_text_via_ax(self, text: str) -> None:
        """Вставляет текст через macOS Accessibility API.

        Находит сфокусированный элемент UI и записывает текст
        через атрибут kAXSelectedTextAttribute, что вставляет текст
        в позицию курсора или заменяет выделение.
        Не трогает буфер обмена.

        Args:
            text: Текст для вставки.

        Raises:
            RuntimeError: Если не удалось получить сфокусированный элемент
                или записать текст через Accessibility API.
        """
        if self._insert_text_via_ax_runtime is None:
            raise RuntimeError("AX runtime не настроен")
        self._insert_text_via_ax_runtime(text)

    def _read_clipboard(self) -> str | None:
        """Читает текст из системного буфера обмена через runtime-адаптер."""
        if self._clipboard_reader is None:
            raise RuntimeError("Clipboard read runtime не настроен")
        return self._clipboard_reader()

    def _copy_to_clipboard(self, text: str) -> None:
        """Копирует текст в системный буфер обмена через runtime-адаптер."""
        if self._clipboard_writer is None:
            raise RuntimeError("Clipboard write runtime не настроен")
        self._clipboard_writer(text)

    def _load_history_items(self) -> list[Any]:
        """Читает сырые записи истории через runtime-адаптер."""
        return self._history_item_loader()

    def _save_history_records(self, records: list[HistoryRecord]) -> None:
        """Сохраняет нормализованные записи истории через runtime-адаптер."""
        self._history_record_saver(records)

    def _notify_user(self, title: str, message: str) -> None:
        """Показывает системное уведомление через injected runtime-hook."""
        self._notify_user_runtime(title, message)

    def _is_accessibility_trusted(self) -> bool:
        """Проверяет право Accessibility через injected runtime-hook."""
        return self._accessibility_status_reader()

    def _get_input_monitoring_status(self) -> bool | None:
        """Проверяет право Input Monitoring через injected runtime-hook."""
        return self._input_monitoring_status_reader()

    def _request_accessibility_permission(self) -> bool:
        """Повторно запрашивает право Accessibility через runtime-hook."""
        return self._request_accessibility_permission_runtime()

    def _request_input_monitoring_permission(self) -> bool | None:
        """Повторно запрашивает право Input Monitoring через runtime-hook."""
        return self._request_input_monitoring_permission_runtime()

    def _warn_missing_accessibility_permission(self) -> None:
        """Вызывает предупреждение о недостающем Accessibility."""
        self._warn_missing_accessibility_permission_runtime()

    def _warn_missing_input_monitoring_permission(self) -> None:
        """Вызывает предупреждение о недостающем Input Monitoring."""
        self._warn_missing_input_monitoring_permission_runtime()

    def _copy_result_to_clipboard_fallback(self, text: str) -> bool:
        """Пытается сохранить результат в буфер обмена для ручной вставки."""
        try:
            self._copy_to_clipboard(text)
        except Exception:
            LOGGER.exception("⚠️ Не удалось сохранить распознанный текст в буфер обмена")
            return False
        return True

    def _fallback_storage_message(self, *, clipboard_saved: bool) -> str:
        """Формирует хвост пользовательского сообщения о сохранённом результате."""
        if clipboard_saved:
            return "сохранён в буфер обмена и историю"
        return "сохранён в историю"

    def _paste_via_clipboard(self, text: str) -> None:
        """Вставляет текст через буфер обмена с последующим восстановлением.

        Сохраняет текущее содержимое буфера обмена, записывает новый текст,
        отправляет Cmd+V, а затем восстанавливает предыдущее содержимое.

        Args:
            text: Текст для вставки.

        Raises:
            RuntimeError: Если не удалось создать keyboard events.
        """
        old_clipboard = self._read_clipboard()
        try:
            self._copy_to_clipboard(text)
            self._send_cmd_v()
            time.sleep(Config.CLIPBOARD_RESTORE_DELAY)
        finally:
            if old_clipboard is not None:
                try:
                    self._copy_to_clipboard(old_clipboard)
                    LOGGER.debug("📋 Буфер обмена восстановлен")
                except Exception:
                    LOGGER.exception("⚠️ Не удалось восстановить буфер обмена")
            else:
                LOGGER.debug("📋 Предыдущее содержимое буфера было пустым, восстановление не требуется")

    def _send_cmd_v(self) -> None:
        """Отправляет системные keyboard events для Cmd+V."""
        if self._send_cmd_v_runtime is None:
            raise RuntimeError("Cmd+V runtime не настроен")
        self._send_cmd_v_runtime()

    def add_to_history(self, text: str) -> None:
        """Добавляет распознанный текст в историю.

        Вставляет текст в начало списка, удаляет записи старше 24 часов,
        сохраняет через persistence-адаптер и вызывает callback для обновления UI.

        Args:
            text: Распознанный текст.
        """
        self._sync_internal_history_from_public_list()
        self._prune_expired_history()
        self._history_records.insert(0, {"text": text, "created_at": self._current_time()})
        self._sync_history_state()
        if not self.private_mode_enabled:
            self._save_history_records(self._history_records)
        LOGGER.debug("📜 Текст добавлен в историю (%d записей)", len(self.history))
        if self.history_callback is not None:
            try:
                self.history_callback()
            except Exception:
                LOGGER.exception("⚠️ Ошибка в history_callback")

    def _run_transcription(self, audio_data: npt.NDArray[np.float32], language: str | None) -> dict[str, Any]:
        """Запускает один проход распознавания с заданными параметрами языка."""
        if self._transcription_runner is None:
            raise RuntimeError("Whisper runtime не настроен")
        return self._transcription_runner(audio_data, self.model_name, language)

    def transcribe(self, audio_data: npt.NDArray[np.float32], language: str | None = None) -> None:
        """Распознает аудио и вставляет результат в активное приложение.

        Args:
            audio_data: Массив с аудио в формате float32.
            language: Необязательный код языка для улучшения распознавания.
        """
        stem = self.diagnostics_store.artifact_stem()
        diagnostics = build_audio_diagnostics(audio_data, language)
        audio_duration_seconds = diagnostics["duration_seconds"]
        rms_energy = diagnostics["rms_energy"]
        peak_amplitude = diagnostics["peak_amplitude"]
        wav_path = self.diagnostics_store.save_audio_recording(stem, audio_data, diagnostics)
        if wav_path is None:
            LOGGER.info(
                "🔍 Диагностика аудио: длительность=%.2f с, RMS=%.6f, peak=%.6f, language=%s",
                audio_duration_seconds,
                rms_energy,
                peak_amplitude,
                language,
            )
        else:
            LOGGER.info(
                "🔍 Диагностика аудио: длительность=%.2f с, RMS=%.6f, peak=%.6f, language=%s, wav=%s",
                audio_duration_seconds,
                rms_energy,
                peak_amplitude,
                language,
                wav_path,
            )
        if audio_duration_seconds < Config.SHORT_AUDIO_WARNING_SECONDS:
            LOGGER.warning("⚠️ Аудио короткое (%.2f с), но распознавание всё равно будет запущено", audio_duration_seconds)
        if rms_energy < Config.SILENCE_RMS_THRESHOLD:
            LOGGER.warning(
                "🔇 Аудио очень тихое (RMS=%.6f < %.4f), но распознавание всё равно будет запущено",
                rms_energy,
                Config.SILENCE_RMS_THRESHOLD,
            )

        try:
            result = self._run_transcription(audio_data, language)
        except Exception:
            LOGGER.exception("❌ Ошибка распознавания")
            self.diagnostics_store.save_transcription_artifacts(stem, diagnostics, error_message="Ошибка распознавания")
            self._notify_user(
                "MLX Whisper Dictation",
                "Ошибка распознавания. Смотрите stderr.log.",
            )
            return

        text = str(result.get("text", "")).strip()
        LOGGER.info("🧠 Первый проход распознавания завершен, длина текста=%s, текст=%r", len(text), text[:120])

        if not text and language is not None:
            LOGGER.info("🔄 Первый проход вернул пустой результат, повторяю распознавание без фиксированного языка")
            try:
                result = self._run_transcription(audio_data, None)
            except Exception:
                LOGGER.exception("❌ Ошибка повторного распознавания без языка")
            else:
                text = str(result.get("text", "")).strip()
                LOGGER.info("🧠 Повторный проход завершен, длина текста=%s, текст=%r", len(text), text[:120])

        self.diagnostics_store.save_transcription_artifacts(stem, diagnostics, result=result, text=text)
        self.add_token_usage(extract_transcription_token_count(result))

        if not text:
            LOGGER.warning("⚠️ Результат распознавания пустой")
            self._notify_user(
                "MLX Whisper Dictation",
                "Речь не распознана. Проверьте микрофон, уровень сигнала и попробуйте еще раз.",
            )
            return

        if looks_like_hallucination(text) and rms_energy < Config.HALLUCINATION_RMS_THRESHOLD:
            LOGGER.warning("👻 Отброшен вероятный галлюцинаторный результат: %r", text)

        # Сохраняем текст в историю независимо от метода вставки
        self.add_to_history(text)

        # Проверяем разрешения macOS, необходимые для всех методов автовставки
        if not self._is_accessibility_trusted():
            LOGGER.warning("🔐 Перед вставкой нет доступа к Accessibility, повторно запрашиваю разрешение")
            self._request_accessibility_permission()
            time.sleep(0.2)

        if self._get_input_monitoring_status() is not True:
            LOGGER.warning("🔐 Перед вставкой нет доступа к Input Monitoring, повторно запрашиваю разрешение")
            self._request_input_monitoring_permission()
            time.sleep(0.2)

        if not self._is_accessibility_trusted():
            self._warn_missing_accessibility_permission()
            clipboard_saved = self._copy_result_to_clipboard_fallback(text)
            self._notify_user(
                "MLX Whisper Dictation",
                "Текст распознан и "
                f"{self._fallback_storage_message(clipboard_saved=clipboard_saved)}. "
                "Вставьте его вручную, потому что у приложения нет доступа к Accessibility.",
            )
            return

        if self._get_input_monitoring_status() is False:
            self._warn_missing_input_monitoring_permission()
            clipboard_saved = self._copy_result_to_clipboard_fallback(text)
            self._notify_user(
                "MLX Whisper Dictation",
                "Текст распознан и "
                f"{self._fallback_storage_message(clipboard_saved=clipboard_saved)}. "
                "Вставьте его вручную, потому что macOS не дала доступ к Input Monitoring.",
            )
            return

        # Собираем цепочку включённых методов вставки
        methods = []
        if self.paste_cgevent_enabled:
            methods.append(("Прямой ввод (CGEvent)", self._type_text_via_cgevent))
        if self.paste_ax_enabled:
            methods.append(("Accessibility API", self._insert_text_via_ax))
        if self.paste_clipboard_enabled:
            methods.append(("Буфер обмена (Cmd+V)", self._paste_via_clipboard))

        if not methods:
            LOGGER.warning("⚠️ Ни один метод вставки не включён")
            clipboard_saved = self._copy_result_to_clipboard_fallback(text)
            self._notify_user(
                "MLX Whisper Dictation",
                "Текст распознан и "
                f"{self._fallback_storage_message(clipboard_saved=clipboard_saved)}. "
                "Включите хотя бы один метод вставки в меню приложения.",
            )
            return

        inserted = False
        for method_name, method_fn in methods:
            try:
                method_fn(text)
                LOGGER.info("✅ Текст вставлен через: %s", method_name)
                inserted = True
                break
            except Exception:
                LOGGER.exception("⚠️ Метод «%s» не сработал", method_name)

        if not inserted:
            clipboard_saved = self._copy_result_to_clipboard_fallback(text)
            self._notify_user(
                "MLX Whisper Dictation",
                "Не удалось вставить текст автоматически. "
                f"Результат {self._fallback_storage_message(clipboard_saved=clipboard_saved)}.",
            )

    def transcribe_to_text(self, audio_data: npt.NDArray[np.float32], language: str | None = None) -> str | None:
        """Распознаёт аудио через Whisper и возвращает текст без вставки.

        Выполняет диагностику аудио, один проход Whisper, учёт токенов
        и проверку на галлюцинации. Не вставляет текст и не работает с LLM.

        Args:
            audio_data: Массив с аудио в формате float32.
            language: Необязательный код языка для улучшения распознавания.

        Returns:
            Распознанный текст или None, если речь не обнаружена
            или результат отброшен как галлюцинация.
        """
        stem = self.diagnostics_store.artifact_stem()
        diagnostics = build_audio_diagnostics(audio_data, language)
        audio_duration_seconds = diagnostics["duration_seconds"]
        rms_energy = diagnostics["rms_energy"]
        self.diagnostics_store.save_audio_recording(stem, audio_data, diagnostics)

        if audio_duration_seconds < Config.SHORT_AUDIO_WARNING_SECONDS:
            LOGGER.warning("⚠️ Аудио короткое (%.2f с)", audio_duration_seconds)
        if rms_energy < Config.SILENCE_RMS_THRESHOLD:
            LOGGER.warning("🔇 Аудио тихое (RMS=%.6f)", rms_energy)

        try:
            result = self._run_transcription(audio_data, language)
        except Exception:
            LOGGER.exception("❌ Ошибка распознавания")
            self._notify_user("MLX Whisper Dictation", "Ошибка распознавания. Смотрите stderr.log.")
            return None

        text = str(result.get("text", "")).strip()
        LOGGER.info("🧠 Транскрипция завершена: длина=%d, текст=%r", len(text), text[:120])
        self.add_token_usage(extract_transcription_token_count(result))

        if not text:
            LOGGER.warning("⚠️ Пустая транскрипция")
            self._notify_user("MLX Whisper Dictation", "Речь не распознана. Попробуйте ещё раз.")
            return None

        if looks_like_hallucination(text) and rms_energy < Config.HALLUCINATION_RMS_THRESHOLD:
            LOGGER.warning("👻 Отброшен галлюцинаторный результат: %r", text)
            return None

        return text
