"""Доменные типы Zipper: конфиг, события, инструменты и ответы агента."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Literal

if TYPE_CHECKING:
    from collections.abc import Callable


ZipperOutputMode = Literal["voice", "window", "both"]


@dataclass(frozen=True, slots=True)
class ZipperCliCommand:
    """Разрешённая CLI-команда Zipper из конфига."""

    name: str
    description: str
    command: tuple[str, ...]
    require_confirmation: bool = True


@dataclass(frozen=True, slots=True)
class ZipperMCPServer:
    """Описание MCP-сервера, доступного Zipper."""

    name: str
    enabled: bool
    command: str
    args: tuple[str, ...] = ()
    env: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ZipperCustomTool:
    """Простой пользовательский инструмент Zipper из конфига."""

    name: str
    description: str
    kind: str
    value: str


@dataclass(frozen=True, slots=True)
class ZipperContextConfig:
    """Настройки контекста и постоянной памяти Zipper."""

    max_tokens: int = 32768
    max_events: int = 200
    memory_enabled: bool = True


@dataclass(frozen=True, slots=True)
class ZipperDebugConfig:
    """Настройки debug-панели Zipper."""

    enabled: bool = False


@dataclass(frozen=True, slots=True)
class ZipperConfig:
    """Нормализованный конфиг Zipper."""

    enabled: bool = True
    system_message: str = (
        "Ты Zipper, локальный голосовой агент Dictator. "
        "Выполняй только безопасные действия через доступные инструменты. "
        "Отвечай по-русски, кратко и практично."
    )
    notes_directory: str = "~/Library/Application Support/Dictator/Zipper/Notes"
    context: ZipperContextConfig = field(default_factory=ZipperContextConfig)
    debug: ZipperDebugConfig = field(default_factory=ZipperDebugConfig)
    cli_commands: tuple[ZipperCliCommand, ...] = ()
    mcp_servers: tuple[ZipperMCPServer, ...] = ()
    custom_tools: tuple[ZipperCustomTool, ...] = ()


@dataclass(frozen=True, slots=True)
class ZipperEvent:
    """Одно событие потока работы Zipper."""

    kind: str
    message: str
    payload: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ZipperMemorySnapshot:
    """Сохранённые контекст и постоянная память Zipper."""

    memory: str
    events: tuple[ZipperEvent, ...]


@dataclass(frozen=True, slots=True)
class ZipperToolSpec:
    """Tool spec, который use case отдаёт LangChain-агенту."""

    name: str
    description: str
    run: Callable[[str], str]


@dataclass(frozen=True, slots=True)
class ZipperAgentResult:
    """Финальный ответ агента и выбранный способ вывода."""

    text: str
    output_mode: ZipperOutputMode = "window"
