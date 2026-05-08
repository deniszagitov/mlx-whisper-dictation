"""Инфраструктурные адаптеры Zipper: память, инструменты, URL и агент."""

from __future__ import annotations

import asyncio
import importlib
import inspect
import json
import logging
import subprocess
import time
import webbrowser
from pathlib import Path
from typing import Any

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
    ZipperToolSpec,
)

LOGGER = logging.getLogger(__name__)
_ZIPPER_AGENT_MAX_ITERATIONS = 4
_ZIPPER_AGENT_MAX_EXECUTION_SECONDS = 60


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


class ZipperUrlOpener:
    """Открывает URL в браузере по умолчанию."""

    def open_url(self, url: str) -> bool:
        """Открывает URL через стандартный браузер."""
        try:
            return bool(webbrowser.open(url))
        except Exception:
            LOGGER.exception("🧷 Не удалось открыть URL: %s", url)
            return False


class ZipperCommandRunner:
    """Запускает только команды, явно описанные в конфиге Zipper."""

    def run(self, command: ZipperCliCommand, _argument: str = "") -> str:
        """Выполняет разрешённую команду без shell."""
        completed = subprocess.run(
            list(command.command),
            check=False,
            capture_output=True,
            text=True,
            timeout=30,
        )
        output = "\n".join(part for part in (completed.stdout.strip(), completed.stderr.strip()) if part)
        if completed.returncode != 0:
            return f"Команда завершилась с кодом {completed.returncode}.\n{output}".strip()
        return output or "Команда выполнена без вывода."


class ZipperCustomToolRunner:
    """Выполняет простые пользовательские инструменты из конфига."""

    def run(self, tool: ZipperCustomTool, argument: str = "") -> str:
        """Выполняет пользовательский инструмент по его kind."""
        if tool.kind == "static_text":
            return tool.value
        if tool.kind == "template_text":
            return tool.value.format(input=argument)
        if tool.kind == "url":
            opened = webbrowser.open(tool.value.format(input=argument))
            return "URL пользовательского инструмента открыт." if opened else "Не удалось открыть URL пользовательского инструмента."
        return f"Неизвестный тип пользовательского инструмента: {tool.kind}"


class ZipperNoteWriter:
    """Сохраняет заметки Zipper в локальную markdown-папку."""

    def write_note(self, text: str, config: ZipperConfig) -> Path:
        """Записывает заметку и возвращает путь к файлу."""
        notes_dir = Path(config.notes_directory).expanduser()
        notes_dir.mkdir(parents=True, exist_ok=True)
        stamp = time.strftime("%Y%m%d-%H%M%S")
        path = notes_dir / f"zipper-{stamp}.md"
        path.write_text(text.strip() + "\n", encoding="utf-8")
        return path


class ZipperMCPToolProvider:
    """Подключает MCP-инструменты из конфига, если доступен langchain-mcp-adapters."""

    def tools_for_config(self, config: ZipperConfig) -> tuple[list[ZipperToolSpec], list[str]]:
        """Возвращает MCP-инструменты и список ошибок подключения."""
        enabled = [server for server in config.mcp_servers if server.enabled]
        if not enabled:
            return [], []
        errors: list[str] = []
        specs: list[ZipperToolSpec] = []
        try:
            client_module = importlib.import_module("langchain_mcp_adapters.client")
            client_class = client_module.MultiServerMCPClient
        except Exception as error:
            return [], [f"Пакет langchain-mcp-adapters недоступен: {error}"]
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
                tools = asyncio.run(_await_any(tools_result)) if inspect.isawaitable(tools_result) else tools_result
            except Exception as error:
                errors.append(f"{server.name}: {error}")
                continue
            for tool in tools:
                name = f"mcp_{server.name}_{getattr(tool, 'name', 'tool')}"
                description = str(getattr(tool, "description", name))

                def run_mcp_tool(arg: str, configured: Any = tool) -> str:
                    result = configured.invoke(arg)
                    return str(result)

                specs.append(
                    ZipperToolSpec(
                        name=name,
                        description=description,
                        run=run_mcp_tool,
                    )
                )
        return specs, errors


class LangChainZipperAgent:
    """LangChain-агент Zipper поверх текущего локального MLX LLM gateway."""

    def __init__(self, llm_processor: Any) -> None:
        self.llm_processor = llm_processor

    def invoke(
        self,
        request: str,
        *,
        system_message: str,
        memory: str,
        events: tuple[ZipperEvent, ...],
        tools: list[ZipperToolSpec],
        config: ZipperConfig,
    ) -> ZipperAgentResult:
        """Запускает LangChain ReAct agent или безопасный fallback без произвольных команд."""
        try:
            return self._invoke_langchain(
                request,
                system_message=system_message,
                memory=memory,
                events=events,
                tools=tools,
                config=config,
            )
        except ImportError as error:
            LOGGER.warning("🧷 LangChain недоступен, использую простой fallback Zipper: %s", error)
            return self._invoke_fallback(request, system_message=system_message, tools=tools)

    def _invoke_langchain(
        self,
        request: str,
        *,
        system_message: str,
        memory: str,
        events: tuple[ZipperEvent, ...],
        tools: list[ZipperToolSpec],
        config: ZipperConfig,
    ) -> ZipperAgentResult:
        processor = self.llm_processor

        class _MlxLLM(LLM):
            @property
            def _llm_type(self) -> str:
                return "dictator_mlx"

            def _call(self, prompt: str, stop: list[str] | None = None, run_manager: Any | None = None, **kwargs: Any) -> str:
                del run_manager, kwargs
                try:
                    text = str(processor.process_text(prompt, system_message, max_tokens=1000, sanitize=False))
                except TypeError:
                    text = str(processor.process_text(prompt, system_message, max_tokens=1000))
                if stop:
                    for marker in stop:
                        if marker and marker in text:
                            text = text.split(marker, maxsplit=1)[0]
                return text

        langchain_tools = [Tool(name=tool.name, description=tool.description, func=tool.run) for tool in tools]
        tool_names = ", ".join(tool.name for tool in tools)
        template = (
            "{system_message}\n\n"
            "Ты работаешь как ReAct agent. Используй только перечисленные инструменты.\n"
            "Для финального ответа обязательно добавь строку output_mode: voice|window|both.\n"
            "Память:\n{memory}\n\n"
            "Последние события:\n{events}\n\n"
            "Доступные инструменты:\n{tools}\n\n"
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
        prompt = PromptTemplate.from_template(template)
        agent = create_react_agent(_MlxLLM(), langchain_tools, prompt)
        executor = AgentExecutor(
            agent=agent,
            tools=langchain_tools,
            verbose=bool(config.debug.enabled),
            handle_parsing_errors=True,
            max_iterations=_ZIPPER_AGENT_MAX_ITERATIONS,
            max_execution_time=_ZIPPER_AGENT_MAX_EXECUTION_SECONDS,
        )
        previous_performance_mode = getattr(processor, "performance_mode", None)
        set_performance_mode = getattr(processor, "set_performance_mode", None)
        if callable(set_performance_mode):
            set_performance_mode("fast")
        try:
            result = executor.invoke(
                {
                    "input": request,
                    "system_message": system_message,
                    "memory": memory,
                    "events": "\n".join(f"{event.kind}: {event.message} {event.payload}" for event in events[-20:]),
                    "tool_names": tool_names,
                }
            )
            text = str(result.get("output") or "").strip()
            return self._parse_output_mode(text)
        finally:
            if callable(set_performance_mode) and previous_performance_mode is not None:
                set_performance_mode(previous_performance_mode)

    def _invoke_fallback(self, request: str, *, system_message: str, tools: list[ZipperToolSpec]) -> ZipperAgentResult:
        normalized = request.strip().lower()
        if "буфер" in normalized and any(word in normalized for word in ("прочитай", "получи", "что")):
            return ZipperAgentResult(text=self._run_tool(tools, "get_clipboard", ""), output_mode="window")
        if normalized.startswith("открой ") and "http" in normalized:
            url = request[request.find("http") :].strip()
            return ZipperAgentResult(text=self._run_tool(tools, "open_url", url), output_mode="voice")
        if "дата" in normalized or "время" in normalized:
            return ZipperAgentResult(text=self._run_tool(tools, "current_datetime", ""), output_mode="voice")
        if "запиши заметку" in normalized:
            text = request.lower().split("запиши заметку", maxsplit=1)[-1].strip() or request
            return ZipperAgentResult(text=self._run_tool(tools, "write_note", text), output_mode="voice")
        response = self.llm_processor.process_text(
            request,
            system_message,
            context="\n".join(f"{tool.name}: {tool.description}" for tool in tools),
            max_tokens=500,
        )
        return ZipperAgentResult(text=response or "Готово.", output_mode="window")

    def _run_tool(self, tools: list[ZipperToolSpec], name: str, argument: str) -> str:
        for tool in tools:
            if tool.name == name:
                return tool.run(argument)
        return f"Инструмент {name} недоступен."

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
