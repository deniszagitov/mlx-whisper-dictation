"""Распознавание речи и вставка текста в активное приложение.

Содержит класс SpeechTranscriber — ядро диктовки: транскрипция аудио
через MLX Whisper, автовставка через CGEvent/AX/Clipboard, история
распознанного текста и интеграция с LLM.
"""

import logging
import re
import time
from typing import Any, cast

import AppKit
import mlx_whisper
import Quartz
from Foundation import NSUserDefaults
from pynput import keyboard

from .config import (
    ARTIFACT_TTL_SECONDS,
    CGEVENT_CHUNK_DELAY,
    CGEVENT_UNICODE_CHUNK_SIZE,
    CLIPBOARD_RESTORE_DELAY,
    DEFAULTS_KEY_HISTORY,
    DEFAULTS_KEY_LLM_CLIPBOARD,
    DEFAULTS_KEY_PASTE_AX,
    DEFAULTS_KEY_PASTE_CGEVENT,
    DEFAULTS_KEY_PASTE_CLIPBOARD,
    DEFAULTS_KEY_PRIVATE_MODE,
    DEFAULTS_KEY_TOTAL_TOKENS,
    HALLUCINATION_RMS_THRESHOLD,
    KEYCODE_COMMAND,
    KEYCODE_V,
    LLM_NOTIFICATION_CHAR_LIMIT,
    LLM_RESPONSE_CHAR_LIMIT,
    SHORT_AUDIO_WARNING_SECONDS,
    SILENCE_RMS_THRESHOLD,
    _load_defaults_bool,
    _load_defaults_int,
    _save_defaults_bool,
    _save_defaults_int,
)
from .diagnostics import DiagnosticsStore, looks_like_hallucination
from .permissions import (
    frontmost_application_info,
    get_input_monitoring_status,
    is_accessibility_trusted,
    notify_user,
    request_accessibility_permission,
    request_input_monitoring_permission,
    warn_missing_accessibility_permission,
    warn_missing_input_monitoring_permission,
)

LOGGER = logging.getLogger(__name__)

_CLIPBOARD_CONTEXT_HINT_RE = re.compile(
    r"(этот|это|здесь|выше|ниже|буфер|clipboard|text|текст|сообщени|документ|"
    r"перевед|исправ|отредакт|сократ|резюм|перескаж|перефраз|объясни|о чем|"
    r"what is this|about this|translate|rewrite|fix|summari[sz]e|proofread)",
    re.IGNORECASE,
)


def _is_mapping(obj):
    """Проверяет, является ли объект словарём (включая NSDictionary от PyObjC)."""
    return isinstance(obj, dict) or hasattr(obj, "objectForKey_")


def _normalize_history_record(item, now):
    """Приводит запись истории к внутреннему формату с TTL."""
    if _is_mapping(item):
        text = item.get("text", "")
        created_at = item.get("created_at", now)
    else:
        text = item
        created_at = now

    # Защита от вложенных NSDictionary: если text не строка, пропускаем запись
    if _is_mapping(text):
        LOGGER.warning("Пропущена повреждённая запись истории (text является словарём)")
        return None

    text = str(text)

    try:
        created_at = float(created_at)
    except (TypeError, ValueError):
        created_at = now

    created_at = min(created_at, now)

    if now - created_at > ARTIFACT_TTL_SECONDS:
        return None

    return {"text": text, "created_at": created_at}


def _load_history_records(now=None):
    """Читает историю из NSUserDefaults с фильтрацией по TTL."""
    current_time = time.time() if now is None else float(now)
    defaults = NSUserDefaults.standardUserDefaults()
    value = defaults.objectForKey_(DEFAULTS_KEY_HISTORY)
    if value is None:
        return []

    records = []
    for item in list(value):
        normalized = _normalize_history_record(item, current_time)
        if normalized is not None:
            records.append(normalized)
    return records


def _save_history_records(records):
    """Сохраняет историю в NSUserDefaults в формате с timestamp."""
    # Явное преобразование в Python-типы, чтобы PyObjC не сериализовал
    # NSDictionary/NSString и не вносил рекурсивные вложенности.
    safe_records = [{"text": str(r["text"]), "created_at": float(r["created_at"])} for r in records]
    NSUserDefaults.standardUserDefaults().setObject_forKey_(safe_records, DEFAULTS_KEY_HISTORY)


class SpeechTranscriber:
    """Распознает аудио и вставляет текст в активное приложение.

    Attributes:
        pykeyboard: Контроллер клавиатуры pynput для вставки текста.
        diagnostics_store: Изолированное хранилище диагностических артефактов.
        model_name: Имя или путь к модели MLX Whisper.
        paste_cgevent_enabled: Включён ли метод прямого ввода через CGEvent Unicode.
        paste_ax_enabled: Включён ли метод ввода через Accessibility API.
        paste_clipboard_enabled: Включён ли метод ввода через буфер обмена (Cmd+V).
        history: Список ранее распознанных текстов.
        history_callback: Callback для уведомления UI об изменении истории.
    """

    def __init__(self, model_name, diagnostics_store=None):
        """Создает объект распознавания.

        Args:
            model_name: Имя модели Hugging Face или локальный путь к модели.
            diagnostics_store: Необязательное хранилище диагностических файлов.
        """
        self.pykeyboard = keyboard.Controller()
        self.diagnostics_store = diagnostics_store or DiagnosticsStore()
        self.model_name = model_name
        self.paste_cgevent_enabled = _load_defaults_bool(DEFAULTS_KEY_PASTE_CGEVENT, fallback=True)
        self.paste_ax_enabled = _load_defaults_bool(DEFAULTS_KEY_PASTE_AX, fallback=False)
        self.paste_clipboard_enabled = _load_defaults_bool(DEFAULTS_KEY_PASTE_CLIPBOARD, fallback=False)
        self.llm_clipboard_enabled = _load_defaults_bool(DEFAULTS_KEY_LLM_CLIPBOARD, fallback=True)
        self.private_mode_enabled = _load_defaults_bool(DEFAULTS_KEY_PRIVATE_MODE, fallback=False)
        self._history_records = []
        self.history = []
        if not self.private_mode_enabled:
            self._reload_persisted_history()
        self.history_callback = None
        self.total_tokens = _load_defaults_int(DEFAULTS_KEY_TOTAL_TOKENS, fallback=0)
        self.token_usage_callback = None

    def set_private_mode(self, enabled):
        """Переключает private mode для истории текста.

        В private mode история не загружается из NSUserDefaults и не
        сохраняется между перезапусками. Уже сохранённая история остаётся
        в defaults, но скрывается до выхода из private mode.

        Args:
            enabled: Нужно ли включить private mode.
        """
        self.private_mode_enabled = bool(enabled)
        _save_defaults_bool(DEFAULTS_KEY_PRIVATE_MODE, self.private_mode_enabled)
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

    def _current_time(self):
        """Возвращает текущее время в Unix timestamp."""
        return time.time()

    def _sync_history_state(self):
        """Синхронизирует публичный список истории с внутренними записями."""
        self.history = [record["text"] for record in self._history_records]

    def _sync_internal_history_from_public_list(self):
        """Подхватывает прямые изменения self.history, используемые в тестах."""
        if len(self._history_records) == len(self.history) and all(
            record["text"] == text for record, text in zip(self._history_records, self.history, strict=False)
        ):
            return

        current_time = self._current_time()
        self._history_records = [{"text": str(text), "created_at": current_time} for text in self.history]

    def _prune_expired_history(self):
        """Удаляет записи истории старше 24 часов."""
        current_time = self._current_time()
        retained_records = []
        for record in self._history_records:
            normalized = _normalize_history_record(record, current_time)
            if normalized is not None:
                retained_records.append(normalized)

        changed = retained_records != self._history_records
        self._history_records = retained_records
        self._sync_history_state()
        return changed

    def _reload_persisted_history(self):
        """Перечитывает историю из NSUserDefaults и сразу удаляет просроченные записи."""
        self._history_records = _load_history_records(now=self._current_time())
        self._sync_history_state()
        _save_history_records(self._history_records)

    def prune_expired_history(self):
        """Публично очищает историю старше 24 часов и сохраняет результат."""
        self._sync_internal_history_from_public_list()
        changed = self._prune_expired_history()
        if changed and not self.private_mode_enabled:
            _save_history_records(self._history_records)
        return changed

    def _notify_token_usage_changed(self):
        """Вызывает callback обновления UI после изменения счётчика токенов."""
        if self.token_usage_callback is not None:
            try:
                self.token_usage_callback()
            except Exception:
                LOGGER.exception("⚠️ Ошибка в token_usage_callback")

    def _add_token_usage(self, token_count):
        """Добавляет подтверждённое количество токенов к общему счётчику."""
        confirmed_tokens = max(int(token_count), 0)
        if confirmed_tokens == 0:
            return

        self.total_tokens += confirmed_tokens
        _save_defaults_int(DEFAULTS_KEY_TOTAL_TOKENS, self.total_tokens)
        LOGGER.debug("🔢 Токены добавлены в счётчик: +%d, всего=%d", confirmed_tokens, self.total_tokens)
        self._notify_token_usage_changed()

    def _extract_transcription_token_count(self, result):
        """Извлекает количество Whisper-токенов из сегментов результата."""
        token_count = 0
        segments = result.get("segments", []) if isinstance(result, dict) else []
        for segment in segments:
            if not isinstance(segment, dict):
                continue
            tokens = segment.get("tokens")
            if isinstance(tokens, (list, tuple)):
                token_count += len(tokens)
            elif isinstance(tokens, int):
                token_count += tokens
        return token_count

    def _copy_text_to_clipboard(self, text):
        """Копирует текст в системный буфер обмена.

        Args:
            text: Текст для сохранения в буфере обмена.
        """
        appkit = cast("Any", AppKit)
        pasteboard = appkit.NSPasteboard.generalPasteboard()
        pasteboard.clearContents()
        pasteboard.setString_forType_(text, appkit.NSPasteboardTypeString)

    def _read_clipboard(self):
        """Читает текстовое содержимое из системного буфера обмена.

        Returns:
            Текст из буфера обмена или None, если буфер пуст.
        """
        appkit = cast("Any", AppKit)
        pasteboard = appkit.NSPasteboard.generalPasteboard()
        return pasteboard.stringForType_(appkit.NSPasteboardTypeString)

    def _should_use_clipboard_context(self, request_text, clipboard_text):
        """Решает, нужно ли передавать буфер обмена как контекст для LLM."""
        if not clipboard_text:
            return False

        normalized_request = str(request_text or "").strip()
        if not normalized_request:
            return False

        return _CLIPBOARD_CONTEXT_HINT_RE.search(normalized_request) is not None

    def _can_deliver_llm_result(self, should_deliver_result):
        """Проверяет, можно ли выводить ответ LLM в текущий момент."""
        if should_deliver_result is None:
            return True

        try:
            return bool(should_deliver_result())
        except Exception:
            LOGGER.exception("⚠️ Ошибка в should_deliver_result для LLM")
            return False

    def _type_text_via_cgevent(self, text):
        """Вставляет текст через отправку Unicode-символов посредством CGEvent.

        Разбивает текст на пакеты и отправляет каждый пакет как пару
        keyDown/keyUp событий с прикреплённой Unicode-строкой.
        Не трогает буфер обмена.

        Args:
            text: Текст для ввода.

        Raises:
            RuntimeError: Если не удалось создать источник событий.
        """
        time.sleep(0.05)
        active_app = frontmost_application_info()
        if active_app is not None:
            LOGGER.info(
                "⌨️ CGEvent Unicode ввод в приложение: name=%s, bundle_id=%s, pid=%s",
                active_app["name"],
                active_app["bundle_id"],
                active_app["pid"],
            )

        event_source = Quartz.CGEventSourceCreate(Quartz.kCGEventSourceStateHIDSystemState)
        if event_source is None:
            raise RuntimeError("Не удалось создать источник системных keyboard events")

        for i in range(0, len(text), CGEVENT_UNICODE_CHUNK_SIZE):
            chunk = text[i : i + CGEVENT_UNICODE_CHUNK_SIZE]

            event_down = Quartz.CGEventCreateKeyboardEvent(event_source, 0, True)
            if event_down is None:
                raise RuntimeError("Не удалось создать keyDown event для CGEvent Unicode ввода")
            Quartz.CGEventKeyboardSetUnicodeString(event_down, len(chunk), chunk)
            Quartz.CGEventPost(Quartz.kCGHIDEventTap, event_down)

            event_up = Quartz.CGEventCreateKeyboardEvent(event_source, 0, False)
            if event_up is None:
                raise RuntimeError("Не удалось создать keyUp event для CGEvent Unicode ввода")
            Quartz.CGEventKeyboardSetUnicodeString(event_up, len(chunk), chunk)
            Quartz.CGEventPost(Quartz.kCGHIDEventTap, event_up)

            if i + CGEVENT_UNICODE_CHUNK_SIZE < len(text):
                time.sleep(CGEVENT_CHUNK_DELAY)

    def _insert_text_via_ax(self, text):
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
        import HIServices

        system_wide = HIServices.AXUIElementCreateSystemWide()

        err, focused_element = HIServices.AXUIElementCopyAttributeValue(system_wide, HIServices.kAXFocusedUIElementAttribute, None)
        if err != 0 or focused_element is None:
            raise RuntimeError(f"Не удалось получить сфокусированный UI-элемент (AXError={err})")

        err = HIServices.AXUIElementSetAttributeValue(focused_element, HIServices.kAXSelectedTextAttribute, text)
        if err != 0:
            raise RuntimeError(f"Не удалось записать текст через AX API (AXError={err})")

    def _paste_via_clipboard(self, text):
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
            self._copy_text_to_clipboard(text)
            self._send_cmd_v()
            time.sleep(CLIPBOARD_RESTORE_DELAY)
        finally:
            if old_clipboard is not None:
                try:
                    self._copy_text_to_clipboard(old_clipboard)
                    LOGGER.debug("📋 Буфер обмена восстановлен")
                except Exception:
                    LOGGER.exception("⚠️ Не удалось восстановить буфер обмена")
            else:
                LOGGER.debug("📋 Предыдущее содержимое буфера было пустым, восстановление не требуется")

    def _send_cmd_v(self):
        """Отправляет системные keyboard events для Cmd+V."""
        time.sleep(0.05)
        active_app = frontmost_application_info()
        if active_app is not None:
            LOGGER.info(
                "🎤 Пытаюсь вставить в активное приложение: name=%s, bundle_id=%s, pid=%s",
                active_app["name"],
                active_app["bundle_id"],
                active_app["pid"],
            )

        event_source = Quartz.CGEventSourceCreate(Quartz.kCGEventSourceStateHIDSystemState)
        if event_source is None:
            raise RuntimeError("Не удалось создать источник системных keyboard events")

        command_down = Quartz.CGEventCreateKeyboardEvent(event_source, KEYCODE_COMMAND, True)
        paste_down = Quartz.CGEventCreateKeyboardEvent(event_source, KEYCODE_V, True)
        paste_up = Quartz.CGEventCreateKeyboardEvent(event_source, KEYCODE_V, False)
        command_up = Quartz.CGEventCreateKeyboardEvent(event_source, KEYCODE_COMMAND, False)

        if not all((command_down, paste_down, paste_up, command_up)):
            raise RuntimeError("Не удалось создать keyboard events для Cmd+V")

        Quartz.CGEventSetFlags(command_down, Quartz.kCGEventFlagMaskCommand)
        Quartz.CGEventSetFlags(paste_down, Quartz.kCGEventFlagMaskCommand)
        Quartz.CGEventSetFlags(paste_up, Quartz.kCGEventFlagMaskCommand)

        Quartz.CGEventPost(Quartz.kCGHIDEventTap, command_down)
        Quartz.CGEventPost(Quartz.kCGHIDEventTap, paste_down)
        Quartz.CGEventPost(Quartz.kCGHIDEventTap, paste_up)
        Quartz.CGEventPost(Quartz.kCGHIDEventTap, command_up)

    def _add_to_history(self, text):
        """Добавляет распознанный текст в историю.

        Вставляет текст в начало списка, удаляет записи старше 24 часов,
        сохраняет в NSUserDefaults и вызывает callback для обновления UI.

        Args:
            text: Распознанный текст.
        """
        self._sync_internal_history_from_public_list()
        self._prune_expired_history()
        self._history_records.insert(0, {"text": text, "created_at": self._current_time()})
        self._sync_history_state()
        if not self.private_mode_enabled:
            _save_history_records(self._history_records)
        LOGGER.debug("📜 Текст добавлен в историю (%d записей)", len(self.history))
        if self.history_callback is not None:
            try:
                self.history_callback()
            except Exception:
                LOGGER.exception("⚠️ Ошибка в history_callback")

    def _run_transcription(self, audio_data, language):
        """Запускает один проход распознавания с заданными параметрами языка."""
        return mlx_whisper.transcribe(
            audio_data,
            language=language,
            path_or_hf_repo=self.model_name,
            condition_on_previous_text=False,
            hallucination_silence_threshold=2.0,
        )

    def transcribe(self, audio_data, language=None):
        """Распознает аудио и вставляет результат в активное приложение.

        Args:
            audio_data: Массив с аудио в формате float32.
            language: Необязательный код языка для улучшения распознавания.
        """
        stem = self.diagnostics_store.artifact_stem()
        diagnostics = self.diagnostics_store.build_audio_diagnostics(audio_data, language)
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
        if audio_duration_seconds < SHORT_AUDIO_WARNING_SECONDS:
            LOGGER.warning("⚠️ Аудио короткое (%.2f с), но распознавание всё равно будет запущено", audio_duration_seconds)
        if rms_energy < SILENCE_RMS_THRESHOLD:
            LOGGER.warning(
                "🔇 Аудио очень тихое (RMS=%.6f < %.4f), но распознавание всё равно будет запущено",
                rms_energy,
                SILENCE_RMS_THRESHOLD,
            )

        try:
            result = self._run_transcription(audio_data, language)
        except Exception:
            LOGGER.exception("❌ Ошибка распознавания")
            self.diagnostics_store.save_transcription_artifacts(stem, diagnostics, error_message="Ошибка распознавания")
            notify_user(
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
        self._add_token_usage(self._extract_transcription_token_count(result))

        if not text:
            LOGGER.warning("⚠️ Результат распознавания пустой")
            notify_user(
                "MLX Whisper Dictation",
                "Речь не распознана. Проверьте микрофон, уровень сигнала и попробуйте еще раз.",
            )
            return

        if looks_like_hallucination(text) and rms_energy < HALLUCINATION_RMS_THRESHOLD:
            LOGGER.warning("👻 Отброшен вероятный галлюцинаторный результат: %r", text)

        # Сохраняем текст в историю независимо от метода вставки
        self._add_to_history(text)

        # Проверяем разрешения macOS, необходимые для всех методов автовставки
        if not is_accessibility_trusted():
            LOGGER.warning("🔐 Перед вставкой нет доступа к Accessibility, повторно запрашиваю разрешение")
            request_accessibility_permission()
            time.sleep(0.2)

        if get_input_monitoring_status() is not True:
            LOGGER.warning("🔐 Перед вставкой нет доступа к Input Monitoring, повторно запрашиваю разрешение")
            request_input_monitoring_permission()
            time.sleep(0.2)

        if not is_accessibility_trusted():
            warn_missing_accessibility_permission()
            notify_user(
                "MLX Whisper Dictation",
                "Текст распознан и сохранён в историю. Вставьте его вручную, потому что у приложения нет доступа к Accessibility.",
            )
            return

        if get_input_monitoring_status() is False:
            warn_missing_input_monitoring_permission()
            notify_user(
                "MLX Whisper Dictation",
                "Текст распознан и сохранён в историю. Вставьте его вручную, потому что macOS не дала доступ к Input Monitoring.",
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
            notify_user(
                "MLX Whisper Dictation",
                "Текст распознан и сохранён в историю. Включите хотя бы один метод вставки в меню приложения.",
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
            notify_user(
                "MLX Whisper Dictation",
                "Не удалось вставить текст автоматически. Текст доступен в «📋 История текста» в меню приложения.",
            )

    def transcribe_for_llm(
        self,
        audio_data,
        language=None,
        *,
        llm_processor,
        system_prompt,
        on_llm_processing_started=None,
        should_deliver_result=None,
    ):
        """Распознаёт аудио через Whisper и отправляет результат в LLM.

        После получения транскрипции передаёт текст в LLM-модель
        с указанным системным промптом. Ответ LLM вставляется в активное
        приложение через стандартную цепочку методов ввода.

        Args:
            audio_data: Массив с аудио в формате float32.
            language: Необязательный код языка для распознавания.
            llm_processor: Экземпляр LLMProcessor для обработки текста.
            system_prompt: Системный промпт для LLM.
            on_llm_processing_started: Необязательный callback, вызываемый
                перед запуском LLM-обработки для обновления UI-статуса.
            should_deliver_result: Необязательный callback, который решает,
                можно ли показывать и копировать итоговый ответ LLM.
        """
        stem = self.diagnostics_store.artifact_stem()
        diagnostics = self.diagnostics_store.build_audio_diagnostics(audio_data, language)
        audio_duration_seconds = diagnostics["duration_seconds"]
        rms_energy = diagnostics["rms_energy"]
        self.diagnostics_store.save_audio_recording(stem, audio_data, diagnostics)

        if audio_duration_seconds < SHORT_AUDIO_WARNING_SECONDS:
            LOGGER.warning("⚠️ Аудио короткое (%.2f с) для LLM-пайплайна", audio_duration_seconds)
        if rms_energy < SILENCE_RMS_THRESHOLD:
            LOGGER.warning("🔇 Аудио тихое (RMS=%.6f) для LLM-пайплайна", rms_energy)

        try:
            result = self._run_transcription(audio_data, language)
        except Exception:
            LOGGER.exception("❌ Ошибка распознавания (LLM-пайплайн)")
            notify_user("MLX Whisper Dictation", "Ошибка распознавания. Смотрите stderr.log.")
            return

        text = str(result.get("text", "")).strip()
        LOGGER.info("🤖 Транскрипция для LLM: длина=%d, текст=%r", len(text), text[:120])
        self._add_token_usage(self._extract_transcription_token_count(result))

        if not text:
            LOGGER.warning("⚠️ Пустая транскрипция, LLM не вызывается")
            notify_user("MLX Whisper Dictation", "Речь не распознана. Попробуйте ещё раз.")
            return

        if looks_like_hallucination(text) and rms_energy < HALLUCINATION_RMS_THRESHOLD:
            LOGGER.warning("👻 Отброшен галлюцинаторный результат в LLM-пайплайне: %r", text)
            return

        raw_clipboard_context = self._read_clipboard() if self.llm_clipboard_enabled else None
        if not self.llm_clipboard_enabled:
            clipboard_context = None
            LOGGER.info("📋 Буфер обмена для LLM выключен, работаю без контекста")
        elif self._should_use_clipboard_context(text, raw_clipboard_context):
            clipboard_context = raw_clipboard_context
            LOGGER.info("📋 Буфер обмена передан как контекст для LLM, длина=%d", len(clipboard_context))
        else:
            clipboard_context = None
            if raw_clipboard_context:
                LOGGER.info("📋 Буфер обмена есть, но пропущен: запрос не ссылается на внешний текст")
            else:
                LOGGER.info("📋 Буфер обмена пуст, LLM работает без контекста")

        if on_llm_processing_started is not None:
            try:
                on_llm_processing_started()
            except Exception:
                LOGGER.exception("⚠️ Ошибка в on_llm_processing_started")

        try:
            llm_response = llm_processor.process_text(text, system_prompt, context=clipboard_context)
        except Exception:
            LOGGER.exception("❌ Ошибка LLM")
            if self.llm_clipboard_enabled:
                self._copy_text_to_clipboard(text)
                notify_user(
                    "MLX Whisper Dictation",
                    "Ошибка LLM. Транскрипция сохранена в буфер обмена.",
                )
            else:
                self._add_to_history(text)
                notify_user(
                    "MLX Whisper Dictation",
                    "Ошибка LLM. Транскрипция сохранена в историю.",
                )
            return

        self._add_token_usage(getattr(llm_processor, "last_token_usage", 0))

        if not llm_response:
            LOGGER.warning("⚠️ LLM вернула пустой ответ")
            if self.llm_clipboard_enabled:
                self._copy_text_to_clipboard(text)
                notify_user("MLX Whisper Dictation", "LLM вернула пустой ответ. Транскрипция в буфере обмена.")
            else:
                self._add_to_history(text)
                notify_user("MLX Whisper Dictation", "LLM вернула пустой ответ. Транскрипция сохранена в историю.")
            return

        self._add_to_history(f"🤖 {llm_response}")

        if not self._can_deliver_llm_result(should_deliver_result):
            LOGGER.info("🤖 Ответ LLM сохранён без вывода: появился более новый запрос")
            notify_user(
                "MLX Whisper Dictation",
                "Ответ LLM сохранён в историю. Новый запрос диктовки получил приоритет.",
            )
            return

        LOGGER.info("🤖 Агентский ответ для вставки: длина=%d, текст=%r", len(llm_response), llm_response)
        if self.llm_clipboard_enabled:
            self._copy_text_to_clipboard(llm_response)
        else:
            LOGGER.info("📋 Буфер обмена для LLM выключен, ответ не копируется")
        notify_user("🤖 LLM", llm_response[: min(LLM_NOTIFICATION_CHAR_LIMIT, LLM_RESPONSE_CHAR_LIMIT)])
