"""Инфраструктурные адаптеры Zipper: память, инструменты, URL и агент."""

from __future__ import annotations

import asyncio
import importlib
import inspect
import json
import logging
import re
import subprocess
import webbrowser
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from langchain.agents import AgentExecutor, create_react_agent
from langchain_core.language_models.llms import LLM
from langchain_core.prompts import PromptTemplate
from langchain_core.tools import Tool

from ..domain.zipper import (
    ZipperAgentResult,
    ZipperCliCommand,
    ZipperConfig,
    ZipperCustomTool,
    ZipperEvent,
    ZipperMemorySnapshot,
)

LOGGER = logging.getLogger(__name__)
_MAX_TOOL_OUTPUT_CHARS = 8000
_ZIPPER_AGENT_MAX_ITERATIONS = 4
_ZIPPER_AGENT_MAX_EXECUTION_SECONDS = 60
_ZIPPER_AGENT_MAX_TOKENS = 1000
_ZIPPER_MEMORY_SUMMARY_MAX_TOKENS = 1000
_ZIPPER_RECENT_EVENTS_LIMIT = 20
_ZIPPER_SYSTEM_MESSAGE = (
    "Ты Zipper, локальный голосовой агент Dictator. "
    "Выполняй только безопасные действия через доступные инструменты. "
    "Отвечай по-русски, кратко и практично."
)
_ZIPPER_PROMPT_TEMPLATE = (
    "{system_message}\n\n"
    "Используй только перечисленные инструменты и не выполняй произвольный shell.\n"
    "Для финального ответа обязательно добавь строку output_mode: voice|window|both.\n"
    "Память:\n"
    "{memory}\n\n"
    "Последние события:\n"
    "{events}\n\n"
    "Доступные инструменты:\n"
    "{tools}\n\n"
    "Используй формат:\n"
    "Question: вход\n"
    "Thought: размышление\n"
    "Action: один из [{tool_names}]\n"
    "Action Input: аргумент\n"
    "Observation: результат\n"
    "... при необходимости повтори ...\n"
    "Final Answer: ответ пользователю\n"
    "output_mode: voice|window|both\n\n"
    "Question: {input}\n"
    "{agent_scratchpad}"
)
_ZIPPER_MEMORY_SUMMARY_PROMPT = (
    "Суммаризуй события Zipper в постоянную память. "
    "Сохрани важные факты, устойчивые предпочтения, повторяющиеся действия, часто используемые команды "
    "и полезные выводы. Не дублируй уже известную память."
)
_ZipperEventSink = Callable[[str, str, dict[str, Any] | None], None]


def _noop_event(_kind: str, _message: str, _payload: dict[str, Any] | None = None) -> None:
    """Игнорирует события Zipper в прямых тестах runtime."""
    return None


def _trim_tool_output(text: str) -> str:
    """Ограничивает слишком длинный вывод инструмента для контекста агента."""
    if len(text) <= _MAX_TOOL_OUTPUT_CHARS:
        return text
    return f"{text[:_MAX_TOOL_OUTPUT_CHARS]}\n\n... вывод обрезан ..."


async def _await_any(awaitable: Any) -> Any:
    """Ожидает произвольный awaitable объект MCP-адаптера."""
    return await awaitable


class FileZipperMemoryStore:
    """Хранит контекст и постоянную память Zipper в Application Support."""

    def __init__(self, path: Path | None = None) -> None:
        self.path = path or Path.home() / "Library" / "Application Support" / "Dictator" / "zipper_memory.json"

    def load(self) -> ZipperMemorySnapshot:
        """Читает память и события Zipper с диска."""
        if not self.path.exists():
            return ZipperMemorySnapshot(memory="", events=())
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except Exception:
            LOGGER.exception("🧷 Не удалось прочитать память Zipper")
            return ZipperMemorySnapshot(memory="", events=())
        events = [
            ZipperEvent(
                kind=str(item.get("kind") or "event"),
                message=str(item.get("message") or ""),
                payload=dict(item.get("payload") or {}),
            )
            for item in raw.get("events", [])
            if isinstance(item, dict)
        ]
        return ZipperMemorySnapshot(memory=str(raw.get("memory") or ""), events=tuple(events))

    def save(self, snapshot: ZipperMemorySnapshot) -> None:
        """Сохраняет память и события Zipper на диск."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "memory": snapshot.memory,
            "events": [
                {
                    "kind": event.kind,
                    "message": event.message,
                    "payload": event.payload,
                }
                for event in snapshot.events
            ],
        }
        self.path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


class LangChainZipperAgent:
    """Весь агент Zipper: prompts, LangChain runtime и tools в одном месте."""

    def __init__(
        self,
        llm_processor: Any,
        *,
        clipboard_service: Any | None = None,
        text_output: Any | None = None,
        voice_output: Any | None = None,
    ) -> None:
        self.llm_processor = llm_processor
        self.clipboard_service = clipboard_service
        self.text_output = text_output
        self.voice_output = voice_output

    def invoke(
        self,
        request: str,
        *,
        memory: str,
        events: tuple[ZipperEvent, ...],
        config: ZipperConfig,
        emit_event: _ZipperEventSink | None = None,
    ) -> ZipperAgentResult:
        """Запускает агентский runtime Zipper через LangChain и настроенные tools."""
        event = emit_event or _noop_event
        tools = self._build_tools(config, event)
        return self._invoke_langchain(
            request,
            memory=memory,
            events=events,
            tools=tools,
            config=config,
        )

    def summarize_memory(self, events_text: str, *, memory: str = "") -> str:
        """Суммаризует старые события Zipper в постоянную память через текущую LLM."""
        try:
            return str(
                self.llm_processor.process_text(
                    events_text,
                    _ZIPPER_MEMORY_SUMMARY_PROMPT,
                    context=memory or None,
                    max_tokens=_ZIPPER_MEMORY_SUMMARY_MAX_TOKENS,
                    keep_loaded=True,
                )
            ).strip()
        except TypeError:
            return str(
                self.llm_processor.process_text(
                    events_text,
                    _ZIPPER_MEMORY_SUMMARY_PROMPT,
                    context=memory or None,
                    max_tokens=_ZIPPER_MEMORY_SUMMARY_MAX_TOKENS,
                )
            ).strip()

    def _invoke_langchain(
        self,
        request: str,
        *,
        memory: str,
        events: tuple[ZipperEvent, ...],
        tools: list[Tool],
        config: ZipperConfig,
    ) -> ZipperAgentResult:
        processor = self.llm_processor
        system_message = self._system_message(memory)

        class _MlxLLM(LLM):
            @property
            def _llm_type(self) -> str:
                return "dictator_mlx"

            def _call(self, prompt: str, stop: list[str] | None = None, run_manager: Any | None = None, **kwargs: Any) -> str:
                del run_manager, kwargs
                try:
                    text = str(
                        processor.process_text(
                            prompt,
                            system_message,
                            max_tokens=_ZIPPER_AGENT_MAX_TOKENS,
                            sanitize=False,
                            keep_loaded=True,
                        )
                    )
                except TypeError:
                    text = str(processor.process_text(prompt, system_message, max_tokens=_ZIPPER_AGENT_MAX_TOKENS))
                if stop:
                    for marker in stop:
                        if marker and marker in text:
                            text = text.split(marker, maxsplit=1)[0]
                return text

        tool_names = ", ".join(tool.name for tool in tools)
        prompt = PromptTemplate.from_template(_ZIPPER_PROMPT_TEMPLATE)
        agent = create_react_agent(_MlxLLM(), tools, prompt)
        executor = AgentExecutor(
            agent=agent,
            tools=tools,
            verbose=bool(config.debug.enabled),
            handle_parsing_errors=True,
            max_iterations=_ZIPPER_AGENT_MAX_ITERATIONS,
            max_execution_time=_ZIPPER_AGENT_MAX_EXECUTION_SECONDS,
        )
        result = executor.invoke(
            {
                "input": request,
                "system_message": system_message,
                "memory": memory,
                "events": self._render_events(events),
                "tool_names": tool_names,
            }
        )
        text = str(result.get("output") or "").strip()
        return self._parse_output_mode(text)

    def _build_tools(self, config: ZipperConfig, event: _ZipperEventSink) -> list[Tool]:
        """Собирает LangChain tools: описание и код каждого tool находятся рядом."""
        tools: list[Tool] = [
            Tool(
                name="get_clipboard",
                description="Получить текст из системного буфера обмена.",
                func=lambda _arg: self._tool_get_clipboard(event),
            ),
            Tool(
                name="set_clipboard",
                description="Положить переданный текст в системный буфер обмена.",
                func=lambda arg: self._tool_set_clipboard(arg, event),
            ),
            Tool(
                name="current_datetime",
                description="Получить текущие дату и время.",
                func=lambda _arg: self._tool_current_datetime(event),
            ),
            Tool(
                name="open_url",
                description="Открыть URL в браузере по умолчанию.",
                func=lambda arg: self._tool_open_url(arg, event),
            ),
            Tool(
                name="show_text",
                description="Показать текстовое окно с переданным содержимым.",
                func=lambda arg: self._tool_show_text(arg, event),
            ),
            Tool(
                name="speak_text",
                description="Озвучить переданный текст.",
                func=lambda arg: self._tool_speak_text(arg, event),
            ),
        ]
        tools.extend(
            (
                Tool(
                    name=self._tool_name("cli", command.name),
                    description=f"{command.description} Разрешённая команда: {command.name}.",
                    func=lambda arg, configured=command: self._tool_cli(configured, arg, event),
                )
            )
            for command in config.cli_commands
        )
        tools.extend(
            (
                Tool(
                    name=self._tool_name("custom", custom_tool.name),
                    description=custom_tool.description,
                    func=lambda arg, configured=custom_tool: self._tool_custom(configured, arg),
                )
            )
            for custom_tool in config.custom_tools
        )
        tools.extend(self._mcp_tools(config, event))
        return tools

    def _mcp_tools(self, config: ZipperConfig, event: _ZipperEventSink) -> list[Tool]:
        enabled = [server for server in config.mcp_servers if server.enabled]
        if not enabled:
            return []
        try:
            client_module = importlib.import_module("langchain_mcp_adapters.client")
            client_class = client_module.MultiServerMCPClient
        except Exception as error:
            event("mcp_error", "MCP недоступен", {"error": f"Пакет langchain-mcp-adapters недоступен: {error}"})
            return []

        tools: list[Tool] = []
        for server in enabled:
            try:
                client = client_class(
                    {
                        server.name: {
                            "command": server.command,
                            "args": list(server.args),
                            "env": dict(server.env),
                            "transport": "stdio",
                        }
                    }
                )
                tools_result = client.get_tools()
                mcp_tools = asyncio.run(_await_any(tools_result)) if inspect.isawaitable(tools_result) else tools_result
            except Exception as error:
                event("mcp_error", "MCP недоступен", {"error": f"{server.name}: {error}"})
                continue

            for tool in mcp_tools:
                name = f"mcp_{server.name}_{getattr(tool, 'name', 'tool')}"
                description = str(getattr(tool, "description", name))
                tools.append(
                    Tool(
                        name=name,
                        description=description,
                        func=lambda arg, configured=tool: str(configured.invoke(arg)),
                    )
                )
        return tools

    def _tool_get_clipboard(self, event: _ZipperEventSink) -> str:
        text = self.clipboard_service.read_text() if self.clipboard_service is not None else ""
        text = text or ""
        event("tool", "get_clipboard", {"result": text})
        return text or "Буфер обмена пуст."

    def _tool_set_clipboard(self, arg: str, event: _ZipperEventSink) -> str:
        if self.clipboard_service is not None:
            self.clipboard_service.write_text(arg)
        event("tool", "set_clipboard", {"chars": len(arg)})
        return "Текст положен в буфер обмена."

    def _tool_current_datetime(self, event: _ZipperEventSink) -> str:
        value = datetime.now().astimezone().isoformat(timespec="seconds")
        event("tool", "current_datetime", {"result": value})
        return value

    def _tool_open_url(self, arg: str, event: _ZipperEventSink) -> str:
        url = arg.strip()
        parsed = urlparse(url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            return "Ошибка: можно открывать только корректные http/https URL."
        try:
            opened = bool(webbrowser.open(url))
        except Exception:
            LOGGER.exception("🧷 Не удалось открыть URL: %s", url)
            opened = False
        event("tool", "open_url", {"url": url, "opened": opened})
        return "URL открыт." if opened else "Не удалось открыть URL."

    def _tool_show_text(self, arg: str, event: _ZipperEventSink) -> str:
        if self.text_output is not None:
            self.text_output.show_text("Zipper", arg)
        event("tool", "show_text", {"chars": len(arg)})
        return "Текстовое окно показано."

    def _tool_speak_text(self, arg: str, event: _ZipperEventSink) -> str:
        if self.voice_output is not None:
            self.voice_output.speak(arg)
        event("tool", "speak_text", {"chars": len(arg)})
        return "Текст озвучен."

    def _tool_cli(self, command: ZipperCliCommand, arg: str, event: _ZipperEventSink) -> str:
        if command.require_confirmation and self.text_output is not None and not self.text_output.confirm(
            "Подтвердить команду Zipper",
            f"{command.description}\n\nКоманда: {' '.join(command.command)}\n\nАргумент агента: {arg}",
        ):
            event("tool", "cli_cancelled", {"name": command.name})
            return "Выполнение команды отменено пользователем."
        completed = subprocess.run(
            list(command.command),
            check=False,
            capture_output=True,
            text=True,
            timeout=30,
        )
        output = "\n".join(part for part in (completed.stdout.strip(), completed.stderr.strip()) if part)
        result = f"Команда завершилась с кодом {completed.returncode}.\n{output}".strip() if completed.returncode else output
        result = result or "Команда выполнена без вывода."
        event("tool", "cli", {"name": command.name, "result": result})
        return _trim_tool_output(result)

    def _tool_custom(self, tool: ZipperCustomTool, argument: str = "") -> str:
        if tool.kind == "static_text":
            return tool.value
        if tool.kind == "template_text":
            return tool.value.format(input=argument)
        if tool.kind == "url":
            opened = webbrowser.open(tool.value.format(input=argument))
            return "URL пользовательского инструмента открыт." if opened else "Не удалось открыть URL пользовательского инструмента."
        return f"Неизвестный тип пользовательского инструмента: {tool.kind}"

    def _run_tool(self, tools: list[Tool], name: str, argument: str) -> str:
        for tool in tools:
            if tool.name == name:
                return str(tool.invoke(argument))
        return f"Инструмент {name} недоступен."

    def _system_message(self, memory: str) -> str:
        normalized_memory = memory.strip()
        if not normalized_memory:
            return _ZIPPER_SYSTEM_MESSAGE
        return f"{_ZIPPER_SYSTEM_MESSAGE}\n\nПостоянная память Zipper:\n{normalized_memory}"

    def _render_events(self, events: tuple[ZipperEvent, ...]) -> str:
        return "\n".join(
            f"{event.kind}: {event.message} {event.payload}"
            for event in events[-_ZIPPER_RECENT_EVENTS_LIMIT :]
        )

    def _tool_name(self, prefix: str, raw_name: str) -> str:
        normalized = re.sub(r"[^a-zA-Z0-9_]+", "_", raw_name.strip().lower()).strip("_")
        return f"{prefix}_{normalized or 'tool'}"

    def _parse_output_mode(self, text: str) -> ZipperAgentResult:
        mode = "window"
        lines = []
        for line in text.splitlines():
            normalized = line.strip().lower()
            if normalized.startswith("output_mode:"):
                raw_mode = normalized.split(":", maxsplit=1)[1].strip()
                if raw_mode in {"voice", "window", "both"}:
                    mode = raw_mode
                continue
            lines.append(line)
        return ZipperAgentResult(text="\n".join(lines).strip() or text, output_mode=mode)  # type: ignore[arg-type]
