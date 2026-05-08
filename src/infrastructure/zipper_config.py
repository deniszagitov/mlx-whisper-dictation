"""Загрузка и нормализация TOML-конфига Zipper."""

from __future__ import annotations

import shutil
import tomllib
from pathlib import Path
from typing import Any

from ..domain.zipper import (
    ZipperCliCommand,
    ZipperConfig,
    ZipperContextConfig,
    ZipperCustomTool,
    ZipperDebugConfig,
    ZipperMCPServer,
)


def example_config_path() -> Path:
    """Возвращает путь к закоммиченному примеру конфига Zipper."""
    return Path(__file__).resolve().parents[2] / "docs" / "zipper" / "zipper.example.toml"


def local_config_path() -> Path:
    """Возвращает путь к локальному dev-конфигу для запуска через uv."""
    return Path.cwd() / "zipper.local.toml"


def user_config_path() -> Path:
    """Возвращает путь к пользовательскому конфигу установленного приложения."""
    return Path.home() / "Library" / "Application Support" / "Dictator" / "zipper.toml"


def _read_toml(path: Path) -> dict[str, Any]:
    with path.open("rb") as file:
        data = tomllib.load(file)
    if not isinstance(data, dict):
        return {}
    return data


def _deep_merge(left: dict[str, Any], right: dict[str, Any]) -> dict[str, Any]:
    merged = dict(left)
    for key, value in right.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def _as_bool(value: object, fallback: bool) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return fallback
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"true", "1", "yes", "on"}:
            return True
        if normalized in {"false", "0", "no", "off", ""}:
            return False
    return bool(value)


def _as_int(value: object, fallback: int) -> int:
    if isinstance(value, bool):
        return fallback
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError:
            return fallback
    return fallback


def _as_str_tuple(value: object) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        return (value,)
    if isinstance(value, list | tuple):
        return tuple(str(item) for item in value)
    return (str(value),)


def _normalize_cli_commands(raw_items: object) -> tuple[ZipperCliCommand, ...]:
    if not isinstance(raw_items, list):
        return ()
    commands: list[ZipperCliCommand] = []
    for item in raw_items:
        if not isinstance(item, dict):
            continue
        command = _as_str_tuple(item.get("command"))
        name = str(item.get("name") or "").strip()
        if not name or not command:
            continue
        commands.append(
            ZipperCliCommand(
                name=name,
                description=str(item.get("description") or name),
                command=command,
                require_confirmation=_as_bool(item.get("require_confirmation"), True),
            )
        )
    return tuple(commands)


def _normalize_mcp_servers(raw_items: object) -> tuple[ZipperMCPServer, ...]:
    if not isinstance(raw_items, list):
        return ()
    servers: list[ZipperMCPServer] = []
    for item in raw_items:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "").strip()
        command = str(item.get("command") or "").strip()
        if not name or not command:
            continue
        env_raw = item.get("env")
        env = {str(key): str(value) for key, value in env_raw.items()} if isinstance(env_raw, dict) else {}
        servers.append(
            ZipperMCPServer(
                name=name,
                enabled=_as_bool(item.get("enabled"), False),
                command=command,
                args=_as_str_tuple(item.get("args")),
                env=env,
            )
        )
    return tuple(servers)


def _normalize_custom_tools(raw_items: object) -> tuple[ZipperCustomTool, ...]:
    if not isinstance(raw_items, list):
        return ()
    tools: list[ZipperCustomTool] = []
    for item in raw_items:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "").strip()
        kind = str(item.get("kind") or "").strip()
        if not name or not kind:
            continue
        tools.append(
            ZipperCustomTool(
                name=name,
                description=str(item.get("description") or name),
                kind=kind,
                value=str(item.get("value") or ""),
            )
        )
    return tuple(tools)


def normalize_config(raw: dict[str, Any]) -> ZipperConfig:
    """Преобразует сырой TOML-словарь в доменный конфиг Zipper."""
    context_value = raw.get("context")
    debug_value = raw.get("debug")
    context_raw: dict[str, Any] = context_value if isinstance(context_value, dict) else {}
    debug_raw: dict[str, Any] = debug_value if isinstance(debug_value, dict) else {}
    context = ZipperContextConfig(
        max_tokens=_as_int(context_raw.get("max_tokens"), 32768),
        max_events=_as_int(context_raw.get("max_events"), 200),
        memory_enabled=_as_bool(context_raw.get("memory_enabled"), True),
    )
    debug = ZipperDebugConfig(enabled=_as_bool(debug_raw.get("enabled"), False))
    return ZipperConfig(
        enabled=_as_bool(raw.get("enabled"), True),
        system_message=str(raw.get("system_message") or ZipperConfig().system_message),
        notes_directory=str(raw.get("notes_directory") or ZipperConfig().notes_directory),
        context=context,
        debug=debug,
        cli_commands=_normalize_cli_commands(raw.get("cli_commands")),
        mcp_servers=_normalize_mcp_servers(raw.get("mcp_servers")),
        custom_tools=_normalize_custom_tools(raw.get("custom_tools")),
    )


class ZipperConfigProvider:
    """Читает конфиг Zipper из example/local/user TOML-файлов."""

    def __init__(
        self,
        *,
        example_path: Path | None = None,
        local_path: Path | None = None,
        user_path: Path | None = None,
        open_path: Any | None = None,
    ) -> None:
        self.example_path = example_path or example_config_path()
        self.local_path = local_path or local_config_path()
        self.user_path = user_path or user_config_path()
        self._open_path = open_path
        self.ensure_user_config()

    def ensure_user_config(self) -> None:
        """Создаёт пользовательский конфиг установленного приложения, если его нет."""
        if self.user_path.exists():
            return
        self.user_path.parent.mkdir(parents=True, exist_ok=True)
        if self.example_path.exists():
            shutil.copyfile(self.example_path, self.user_path)
        else:
            self.user_path.write_text("# Конфиг Zipper\nenabled = true\n", encoding="utf-8")

    def config_path(self) -> str:
        """Возвращает путь пользовательского конфига."""
        return str(self.user_path)

    def load_config(self) -> ZipperConfig:
        """Загружает конфиг с приоритетом user > local > example."""
        raw: dict[str, Any] = {}
        for path in (self.example_path, self.local_path, self.user_path):
            if path.exists():
                raw = _deep_merge(raw, _read_toml(path))
        return normalize_config(raw)

    def open_config(self) -> bool:
        """Открывает пользовательский конфиг через системную интеграцию."""
        self.ensure_user_config()
        if self._open_path is None:
            return False
        return bool(self._open_path(str(self.user_path)))
