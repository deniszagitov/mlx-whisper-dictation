"""Use case-сценарии голосового агента Zipper."""

from __future__ import annotations

import logging
import re
import threading
import time
from datetime import datetime
from typing import Any, cast
from urllib.parse import urlparse

from ..domain.constants import Config
from ..domain.model_downloads import ModelRequiredError
from ..domain.zipper import (
    ZipperAgentResult,
    ZipperConfig,
    ZipperEvent,
    ZipperMemorySnapshot,
    ZipperToolSpec,
)

LOGGER = logging.getLogger(__name__)

_KEYCODE_ESCAPE = 53
_MAX_TOOL_OUTPUT_CHARS = 8000
_MEMORY_SUMMARY_KEEP_EVENTS = 40


def _prevent_display_sleep(runtime: Any) -> None:
    """Включает временную защиту дисплея от сна, если runtime её поддерживает."""
    prevent = getattr(runtime, "prevent_display_sleep_for_active_session", None)
    if callable(prevent):
        prevent()


def _release_display_sleep(runtime: Any) -> None:
    """Отпускает временную защиту дисплея от сна, если runtime её поддерживает."""
    release = getattr(runtime, "release_display_sleep_for_active_session", None)
    if callable(release):
        release(immediate=True, reason="zipper_cancel_or_start_failure")


def _tool_name(prefix: str, raw_name: str) -> str:
    """Нормализует имя инструмента под ограничения LangChain."""
    normalized = re.sub(r"[^a-zA-Z0-9_]+", "_", raw_name.strip().lower()).strip("_")
    return f"{prefix}_{normalized or 'tool'}"


def _trim_tool_output(text: str) -> str:
    """Ограничивает слишком длинный вывод инструмента для контекста агента."""
    if len(text) <= _MAX_TOOL_OUTPUT_CHARS:
        return text
    return f"{text[:_MAX_TOOL_OUTPUT_CHARS]}\n\n... вывод обрезан ..."


class ZipperUseCases:
    """Оркестрирует голосовой сценарий Zipper и инструменты агента."""

    def __init__(
        self,
        runtime: Any,
        recorder: Any,
        transcriber: Any,
        llm_processor: Any,
        config_provider: Any,
        memory_store: Any,
        agent_service: Any,
        clipboard_service: Any,
        text_output: Any,
        voice_output: Any,
        url_opener: Any,
        command_runner: Any,
        custom_tool_runner: Any,
        mcp_tool_provider: Any,
        system_integration_service: Any,
        recording_overlay: Any,
        publish_snapshot: Any,
    ) -> None:
        self.runtime = runtime
        self.recorder = recorder
        self.transcriber = transcriber
        self.llm_processor = llm_processor
        self.config_provider = config_provider
        self.memory_store = memory_store
        self.agent_service = agent_service
        self.clipboard_service = clipboard_service
        self.text_output = text_output
        self.voice_output = voice_output
        self.url_opener = url_opener
        self.command_runner = command_runner
        self.custom_tool_runner = custom_tool_runner
        self.mcp_tool_provider = mcp_tool_provider
        self.system_integration_service = system_integration_service
        self.recording_overlay = recording_overlay
        self.publish_snapshot = publish_snapshot
        self._worker: threading.Thread | None = None
        self._session_events: list[ZipperEvent] = []
        self._config = self._load_config()

    @property
    def config(self) -> ZipperConfig:
        """Возвращает текущий конфиг Zipper."""
        return self._config

    def reload_config(self) -> None:
        """Перечитывает конфиг Zipper и обновляет состояние debug-панели."""
        self._config = self._load_config()
        self.runtime.zipper_enabled = self._config.enabled
        self.runtime.zipper_debug_panel_enabled = self._config.debug.enabled
        self.text_output.set_debug_visible(self.runtime.zipper_debug_panel_enabled)
        self._event("config_reloaded", "Конфиг Zipper перечитан", {"path": self.config_provider.config_path()})
        self.system_integration_service.notify("MLX Whisper Dictation", "Конфиг Zipper перечитан.")
        self.publish_snapshot()

    def open_config(self) -> None:
        """Открывает пользовательский конфиг Zipper."""
        opened = self.config_provider.open_config()
        if not opened:
            self.system_integration_service.notify("MLX Whisper Dictation", "Не удалось открыть конфиг Zipper.")

    def toggle_enabled(self) -> None:
        """Включает или выключает Zipper в runtime."""
        self.runtime.zipper_enabled = not self.runtime.zipper_enabled
        self.system_integration_service.notify(
            "MLX Whisper Dictation",
            "Zipper включён." if self.runtime.zipper_enabled else "Zipper выключен.",
        )
        self.publish_snapshot()

    def toggle_debug_panel(self) -> None:
        """Включает или выключает debug-панель Zipper."""
        self.runtime.zipper_debug_panel_enabled = not self.runtime.zipper_debug_panel_enabled
        self.text_output.set_debug_visible(self.runtime.zipper_debug_panel_enabled)
        self._event(
            "debug_panel",
            "Debug-панель переключена",
            {"enabled": self.runtime.zipper_debug_panel_enabled},
        )
        self.publish_snapshot()

    def clear_context(self) -> None:
        """Очищает текущий контекст Zipper, не трогая постоянную память."""
        snapshot = self.memory_store.load()
        self.memory_store.save(ZipperMemorySnapshot(memory=snapshot.memory, events=()))
        self._event("memory", "Контекст Zipper очищен")
        self.publish_snapshot()

    def clear_memory(self) -> None:
        """Очищает постоянную память Zipper, не трогая текущий контекст."""
        snapshot = self.memory_store.load()
        self.memory_store.save(ZipperMemorySnapshot(memory="", events=snapshot.events))
        self._event("memory", "Постоянная память Zipper очищена")
        self.publish_snapshot()

    def toggle(self) -> None:
        """Переключает сценарий записи голосовой команды Zipper."""
        self._event(
            "toggle",
            "Получен запрос на переключение Zipper",
            {
                "enabled": self.runtime.zipper_enabled,
                "recording_active": self.runtime.zipper_recording_active,
                "started": self.runtime.started,
                "state": self.runtime.state,
            },
        )
        if not self.runtime.zipper_enabled:
            self._show_error("Zipper выключен.")
            return
        if self.runtime.zipper_recording_active:
            self.stop_recording()
            return
        if self.runtime.started:
            self._show_error("Другая запись уже активна.")
            return
        self.start_recording()

    def start_recording(self) -> None:
        """Запускает запись голосовой команды Zipper."""
        LOGGER.info(
            "🧷 Проверяю готовность Zipper перед записью: enabled=%s, state=%s, started=%s",
            self.runtime.zipper_enabled,
            self.runtime.state,
            self.runtime.started,
        )
        self._event("recording_prepare", "Zipper проверяет готовность к записи")
        if self.llm_processor is None:
            self._show_error("LLM-процессор не инициализирован.")
            return
        if not self.llm_processor.is_model_cached():
            raw_model_name = getattr(self.llm_processor, "model_name", None)
            model_fragment = f" {raw_model_name}" if raw_model_name else ""
            message = (
                f"LLM-модель{model_fragment} ещё не скачана из Hugging Face. "
                "Запускаю загрузку; после завершения нажмите хоткей Zipper ещё раз."
            )
            download = getattr(self.runtime, "download_llm_model", None)
            if callable(download):
                LOGGER.info("🧷 Zipper запускает загрузку LLM-модели перед записью")
                download()
            self._show_error(message)
            return
        if not self.runtime.prepare_recording():
            self._show_error("Zipper не смог начать запись: нет доступного микрофона или приложение не готово к записи.")
            return

        LOGGER.info("🧷 Запуск записи команды Zipper")
        self._event("recording_started", "Zipper начал запись голосовой команды")
        self.runtime.started = True
        self.runtime.zipper_recording_active = True
        self.runtime.state = Config.STATUS_RECORDING
        _prevent_display_sleep(self.runtime)
        if self.runtime.show_recording_notification:
            self.system_integration_service.notify("MLX Whisper Dictation", "Zipper слушает команду. Говорите.")
        try:
            self.recorder.start(self.runtime.current_language, on_audio_ready=self._on_audio_ready)
        except Exception:
            LOGGER.exception("❌ Не удалось запустить запись для Zipper")
            self.runtime.started = False
            self.runtime.zipper_recording_active = False
            self.runtime.state = Config.STATUS_IDLE
            _release_display_sleep(self.runtime)
            self.publish_snapshot()
            raise
        self.runtime.start_time = time.time()
        self.runtime.elapsed_time = 0
        if self.runtime.show_recording_overlay:
            self.recording_overlay.show()
        self.publish_snapshot()

    def stop_recording(self) -> None:
        """Останавливает запись Zipper и запускает распознавание."""
        if not self.runtime.zipper_recording_active:
            return
        LOGGER.info("🧷 Запись Zipper остановлена, запускаю распознавание")
        self.runtime.started = False
        self.runtime.zipper_recording_active = False
        self.runtime.state = Config.STATUS_TRANSCRIBING
        self.recorder.stop()
        self.recording_overlay.hide()
        self.publish_snapshot()

    def cancel_recording(self) -> None:
        """Отменяет активную запись команды Zipper."""
        if not self.runtime.zipper_recording_active:
            return
        LOGGER.info("🧷 Запись Zipper отменена пользователем")
        self.runtime.started = False
        self.runtime.zipper_recording_active = False
        self.runtime.state = Config.STATUS_IDLE
        self.recorder.cancel()
        self.recording_overlay.hide()
        _release_display_sleep(self.runtime)
        self._event("cancelled", "Команда Zipper отменена")
        self.publish_snapshot()

    def handle_escape_keycode(self, keycode: int) -> bool:
        """Обрабатывает Escape для активной записи Zipper."""
        if keycode != _KEYCODE_ESCAPE or not self.runtime.zipper_recording_active:
            return False
        self.cancel_recording()
        return True

    def on_status_tick(self) -> None:
        """Обновляет длительность записи Zipper и применяет общий max_time."""
        if not self.runtime.zipper_recording_active:
            return
        self.runtime.elapsed_time = int(time.time() - self.runtime.start_time)
        self.recording_overlay.update_time(self.runtime.elapsed_time)
        if self.runtime.max_time is not None and self.runtime.elapsed_time >= self.runtime.max_time:
            self.stop_recording()

    def _on_audio_ready(self, audio_data: Any, language: str | None, _set_status: Any, is_current: Any) -> None:
        """Распознаёт голосовую команду и передаёт её агенту."""
        whisper_text = self.transcriber.transcribe_to_text(audio_data, language)
        if not whisper_text or not is_current():
            self._show_error("Zipper не смог распознать команду. Попробуйте ещё раз.")
            self._finish_processing()
            return

        self._session_events = []
        self._event("user_speech", "Пользователь сказал", {"text": whisper_text})
        self._start_worker(lambda: self._run_agent(whisper_text, is_current))

    def _start_worker(self, target: Any) -> None:
        if self._worker is not None and self._worker.is_alive():
            self._show_error("Zipper уже обрабатывает предыдущую команду.")
            return
        thread = threading.Thread(target=target, daemon=True)
        self._worker = thread
        thread.start()

    def _run_agent(self, command_text: str, is_current: Any) -> None:
        self.runtime.state = Config.STATUS_ZIPPER_PROCESSING
        if not self._session_events or self._session_events[-1].kind != "user_speech":
            self._session_events = []
        self.publish_snapshot()
        try:
            snapshot = self.memory_store.load()
            tools = self._build_tools()
            self._event(
                "agent_input",
                "Текст передан агенту",
                {"text": command_text, "tools": [tool.name for tool in tools]},
            )
            result = self.agent_service.invoke(
                command_text,
                system_message=self._system_message(snapshot),
                memory=snapshot.memory,
                events=snapshot.events,
                tools=tools,
                config=self._config,
            )
            self._event(
                "agent_output",
                "Агент сформировал ответ",
                {"text": result.text, "output_mode": result.output_mode},
            )
            if is_current():
                self._publish_result(result)
            self._append_context_events()
            self._summarize_context_if_needed()
        except ModelRequiredError as error:
            LOGGER.warning("📥 Zipper запросил загрузку модели: label=%s, model=%s", error.label, error.model_name)
            self._download_required_model(error)
            message = f"{error.label} ещё не готова. Запускаю загрузку; после завершения повторите команду Zipper."
            self._event("model_download_required", message, {"model": error.model_name, "label": error.label})
            self._show_error(message)
        except Exception as error:
            LOGGER.exception("❌ Ошибка Zipper")
            self._event("error", "Ошибка Zipper", {"error": str(error)})
            self._show_error(f"Ошибка Zipper: {error}")
        finally:
            self._finish_processing()

    def _finish_processing(self) -> None:
        if not self.runtime.started and self.runtime.state in {Config.STATUS_TRANSCRIBING, Config.STATUS_ZIPPER_PROCESSING}:
            self.runtime.state = Config.STATUS_IDLE
        _release_display_sleep(self.runtime)
        self.publish_snapshot()

    def _download_required_model(self, requirement: ModelRequiredError) -> None:
        """Делегирует загрузку модели управляющему runtime вне контекста агента."""
        download_required = getattr(self.runtime, "download_required_model", None)
        if callable(download_required):
            download_required(requirement)
            return
        download_llm = getattr(self.runtime, "download_llm_model", None)
        if callable(download_llm):
            download_llm()

    def _load_config(self) -> ZipperConfig:
        try:
            return cast("ZipperConfig", self.config_provider.load_config())
        except Exception as error:
            LOGGER.exception("❌ Некорректный конфиг Zipper")
            self._show_error(f"Некорректный конфиг Zipper: {error}")
            return ZipperConfig(enabled=False)

    def _system_message(self, snapshot: ZipperMemorySnapshot) -> str:
        if not snapshot.memory.strip():
            return self._config.system_message
        return f"{self._config.system_message}\n\nПостоянная память Zipper:\n{snapshot.memory.strip()}"

    def _build_tools(self) -> list[ZipperToolSpec]:
        tools = [
            ZipperToolSpec("get_clipboard", "Получить текст из системного буфера обмена.", self._tool_get_clipboard),
            ZipperToolSpec("set_clipboard", "Положить переданный текст в системный буфер обмена.", self._tool_set_clipboard),
            ZipperToolSpec("current_datetime", "Получить текущие дату и время.", self._tool_current_datetime),
            ZipperToolSpec("open_url", "Открыть URL в браузере по умолчанию.", self._tool_open_url),
            ZipperToolSpec("show_text", "Показать текстовое окно с переданным содержимым.", self._tool_show_text),
            ZipperToolSpec("speak_text", "Озвучить переданный текст.", self._tool_speak_text),
        ]
        tools.extend(self._cli_tools())
        tools.extend(self._custom_tools())
        tools.extend(self._mcp_tools())
        return tools

    def _cli_tools(self) -> list[ZipperToolSpec]:
        def make_tool(command: Any) -> ZipperToolSpec:
            return ZipperToolSpec(
                _tool_name("cli", command.name),
                f"{command.description} Разрешённая команда: {command.name}.",
                lambda arg: self._tool_cli(command, arg),
            )

        return [
            make_tool(command)
            for command in self._config.cli_commands
        ]

    def _custom_tools(self) -> list[ZipperToolSpec]:
        def make_tool(tool: Any) -> ZipperToolSpec:
            return ZipperToolSpec(
                _tool_name("custom", tool.name),
                tool.description,
                lambda arg: self.custom_tool_runner.run(tool, arg),
            )

        return [
            make_tool(tool)
            for tool in self._config.custom_tools
        ]

    def _mcp_tools(self) -> list[ZipperToolSpec]:
        try:
            tools, errors = self.mcp_tool_provider.tools_for_config(self._config)
        except Exception as error:
            self._event("mcp_error", "MCP недоступен", {"error": str(error)})
            return []
        for error_message in errors:
            self._event("mcp_error", "MCP недоступен", {"error": error_message})
        return list(tools)

    def _tool_get_clipboard(self, _arg: str) -> str:
        text = self.clipboard_service.read_text() or ""
        self._event("tool", "get_clipboard", {"result": text})
        return text or "Буфер обмена пуст."

    def _tool_set_clipboard(self, arg: str) -> str:
        self.clipboard_service.write_text(arg)
        self._event("tool", "set_clipboard", {"chars": len(arg)})
        return "Текст положен в буфер обмена."

    def _tool_current_datetime(self, _arg: str) -> str:
        value = datetime.now().astimezone().isoformat(timespec="seconds")
        self._event("tool", "current_datetime", {"result": value})
        return value

    def _tool_open_url(self, arg: str) -> str:
        url = arg.strip()
        parsed = urlparse(url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            return "Ошибка: можно открывать только корректные http/https URL."
        opened = self.url_opener.open_url(url)
        self._event("tool", "open_url", {"url": url, "opened": opened})
        return "URL открыт." if opened else "Не удалось открыть URL."

    def _tool_show_text(self, arg: str) -> str:
        self.text_output.show_text("Zipper", arg)
        self._event("tool", "show_text", {"chars": len(arg)})
        return "Текстовое окно показано."

    def _tool_speak_text(self, arg: str) -> str:
        self.voice_output.speak(arg)
        self._event("tool", "speak_text", {"chars": len(arg)})
        return "Текст озвучен."

    def _tool_cli(self, command: Any, arg: str) -> str:
        if command.require_confirmation and not self.text_output.confirm(
            "Подтвердить команду Zipper",
            f"{command.description}\n\nКоманда: {' '.join(command.command)}\n\nАргумент агента: {arg}",
        ):
            self._event("tool", "cli_cancelled", {"name": command.name})
            return "Выполнение команды отменено пользователем."
        result = self.command_runner.run(command, arg)
        self._event("tool", "cli", {"name": command.name, "result": result})
        return _trim_tool_output(result)

    def _publish_result(self, result: ZipperAgentResult) -> None:
        text = result.text.strip()
        if not text:
            self._show_error("LLM не вернула ответ.")
            return
        if result.output_mode in {"voice", "both"}:
            self.voice_output.speak(text)
        if result.output_mode in {"window", "both"}:
            self.text_output.show_text("Zipper", text)

    def _show_error(self, message: str) -> None:
        LOGGER.warning("🧷 %s", message)
        self._event("error", message)
        self.system_integration_service.notify("MLX Whisper Dictation", message)
        self.text_output.show_text("Zipper: ошибка", message)

    def _event(self, kind: str, message: str, payload: dict[str, Any] | None = None) -> None:
        event = ZipperEvent(kind=kind, message=message, payload=payload or {})
        self._session_events.append(event)
        self.text_output.append_debug_event(event)
        LOGGER.info("🧷 Zipper event: %s %s", kind, payload or message)

    def _append_context_events(self) -> None:
        # Persistent context хранит последние события работы агента между запусками.
        debug_events = tuple(self._session_events)
        snapshot = self.memory_store.load()
        self.memory_store.save(ZipperMemorySnapshot(memory=snapshot.memory, events=(*snapshot.events, *debug_events)))

    def _summarize_context_if_needed(self) -> None:
        snapshot = self.memory_store.load()
        if not self._config.context.memory_enabled:
            self.memory_store.save(ZipperMemorySnapshot(memory=snapshot.memory, events=snapshot.events[-self._config.context.max_events :]))
            return
        approx_tokens = sum(len(event.message) + len(str(event.payload)) for event in snapshot.events) // 4
        if len(snapshot.events) <= self._config.context.max_events and approx_tokens <= self._config.context.max_tokens:
            return

        old_events = snapshot.events[:-_MEMORY_SUMMARY_KEEP_EVENTS]
        recent_events = snapshot.events[-_MEMORY_SUMMARY_KEEP_EVENTS:]
        if not old_events:
            return
        events_text = "\n".join(f"{event.kind}: {event.message} {event.payload}" for event in old_events)
        prompt = (
            "Суммаризуй события Zipper в постоянную память. "
            "Сохрани важные факты, устойчивые предпочтения, повторяющиеся действия, часто используемые команды "
            "и полезные выводы. Не дублируй уже известную память."
        )
        try:
            try:
                summary = self.llm_processor.process_text(
                    events_text,
                    prompt,
                    context=snapshot.memory or None,
                    max_tokens=1000,
                    keep_loaded=True,
                ).strip()
            except TypeError:
                summary = self.llm_processor.process_text(
                    events_text,
                    prompt,
                    context=snapshot.memory or None,
                    max_tokens=1000,
                ).strip()
        except Exception:
            LOGGER.exception("🧷 Не удалось суммаризовать контекст Zipper")
            return
        if not summary:
            return
        memory = snapshot.memory.strip()
        new_memory = memory if summary in memory else f"{memory}\n\n{summary}".strip() if memory else summary
        self.memory_store.save(ZipperMemorySnapshot(memory=new_memory, events=recent_events))
        self._event("memory", "Контекст Zipper суммаризован в постоянную память", {"summary_chars": len(summary)})
