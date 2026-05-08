"""Тесты голосового агента Zipper."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from src.domain.constants import Config
from src.domain.model_downloads import ModelRequiredError
from src.domain.zipper import (
    ZipperAgentResult,
    ZipperCliCommand,
    ZipperConfig,
    ZipperCustomTool,
    ZipperMemorySnapshot,
)
from src.infrastructure.zipper_config import ZipperConfigProvider
from src.use_cases.zipper import ZipperUseCases


class FakeRuntime:
    """Минимальный runtime для ZipperUseCases."""

    def __init__(self) -> None:
        self.started = False
        self.zipper_recording_active = False
        self.zipper_enabled = True
        self.zipper_debug_panel_enabled = False
        self.state = Config.STATUS_IDLE
        self.current_language = "ru"
        self.show_recording_notification = False
        self.show_recording_overlay = False
        self.start_time = 0.0
        self.elapsed_time = 0
        self.max_time = 30
        self.snapshots = 0
        self.download_requests = 0
        self.required_downloads: list[tuple[str, str]] = []

    def prepare_recording(self) -> bool:
        """Разрешает запись."""
        return True

    def prevent_display_sleep_for_active_session(self) -> None:
        """Заглушка power assertion."""
        return None

    def release_display_sleep_for_active_session(self, *, immediate: bool = False, reason: str = "unknown") -> None:
        """Заглушка отпускания power assertion."""
        return None

    def download_llm_model(self) -> None:
        """Фиксирует запрос загрузки LLM-модели."""
        self.download_requests += 1

    def download_required_model(self, requirement: ModelRequiredError) -> None:
        """Фиксирует запрос общей загрузки модели."""
        self.required_downloads.append((requirement.label, requirement.model_name))


class FakeRecorder:
    """Фейковый recorder для Zipper."""

    def __init__(self) -> None:
        self.started = False
        self.stopped = False
        self.cancelled = False
        self.callback: Any | None = None

    def start(self, language: str | None, on_audio_ready: Any) -> None:
        """Запоминает callback готового аудио."""
        self.started = True
        self.language = language
        self.callback = on_audio_ready

    def stop(self) -> None:
        """Фиксирует остановку записи."""
        self.stopped = True

    def cancel(self) -> None:
        """Фиксирует отмену записи."""
        self.cancelled = True


class FakeTranscriber:
    """Фейковый transcriber, который не вставляет текст."""

    def __init__(self, text: str = "запиши заметку тест") -> None:
        self.text = text
        self.transcribe_called = False
        self.transcribe_to_text_called = False

    def transcribe(self, audio_data: Any, language: str | None = None) -> None:
        """Обычная вставка не должна вызываться Zipper."""
        self.transcribe_called = True

    def transcribe_to_text(self, audio_data: Any, language: str | None = None) -> str:
        """Возвращает распознанную голосовую команду."""
        self.transcribe_to_text_called = True
        return self.text


class FakeLLM:
    """Фейковый локальный LLM gateway."""

    last_token_usage = 0

    def __init__(self, cached: bool = True) -> None:
        self.cached = cached

    def is_model_cached(self) -> bool:
        """Считает модель доступной локально."""
        return self.cached

    def process_text(self, text: str, system_prompt: str, *, context: str | None = None, max_tokens: int | None = None) -> str:
        """Возвращает краткое резюме для тестов памяти."""
        return "пользователь часто просит заметки"


class FakeConfigProvider:
    """Фейковый provider конфига."""

    def __init__(self, config: ZipperConfig | None = None) -> None:
        self.config = config or ZipperConfig()

    def load_config(self) -> ZipperConfig:
        """Возвращает тестовый конфиг."""
        return self.config

    def config_path(self) -> str:
        """Возвращает путь тестового конфига."""
        return "/tmp/zipper.toml"

    def open_config(self) -> bool:
        """Имитирует успешное открытие конфига."""
        return True


class FakeMemoryStore:
    """In-memory persistence Zipper."""

    def __init__(self, snapshot: ZipperMemorySnapshot | None = None) -> None:
        self.snapshot = snapshot or ZipperMemorySnapshot(memory="", events=())

    def load(self) -> ZipperMemorySnapshot:
        """Возвращает текущий snapshot."""
        return self.snapshot

    def save(self, snapshot: ZipperMemorySnapshot) -> None:
        """Сохраняет snapshot."""
        self.snapshot = snapshot


class FakeAgent:
    """Фейковый агент Zipper."""

    def __init__(self, result: ZipperAgentResult | None = None) -> None:
        self.result = result or ZipperAgentResult(text="Готово", output_mode="window")
        self.calls: list[dict[str, Any]] = []

    def invoke(self, request: str, **kwargs: Any) -> ZipperAgentResult:
        """Запоминает запрос и возвращает тестовый ответ."""
        self.calls.append({"request": request, **kwargs})
        return self.result


class FakeClipboard:
    """Фейковый системный буфер обмена."""

    def __init__(self, text: str | None = "из буфера") -> None:
        self.text = text

    def read_text(self) -> str | None:
        """Читает буфер."""
        return self.text

    def write_text(self, text: str) -> None:
        """Пишет буфер."""
        self.text = text


class FakeTextOutput:
    """Фейковое окно результата и debug-панель."""

    def __init__(self) -> None:
        self.messages: list[tuple[str, str]] = []
        self.events: list[Any] = []
        self.confirmed = True
        self.debug_visible = False

    def show_text(self, title: str, text: str) -> None:
        """Запоминает окно."""
        self.messages.append((title, text))

    def confirm(self, title: str, message: str) -> bool:
        """Возвращает тестовое подтверждение."""
        return self.confirmed

    def set_debug_visible(self, visible: bool) -> None:
        """Запоминает видимость debug-панели."""
        self.debug_visible = visible

    def append_debug_event(self, event: Any) -> None:
        """Запоминает событие debug-панели."""
        self.events.append(event)

    def debug_events(self) -> list[Any]:
        """Возвращает события debug-панели."""
        return list(self.events)


class FakeVoiceOutput:
    """Фейковая озвучка."""

    def __init__(self) -> None:
        self.spoken: list[str] = []

    def speak(self, text: str) -> None:
        """Запоминает озвученный текст."""
        self.spoken.append(text)


class FakeCommandRunner:
    """Фейковый runner разрешённых CLI-команд."""

    def __init__(self) -> None:
        self.calls: list[tuple[ZipperCliCommand, str]] = []

    def run(self, command: ZipperCliCommand, argument: str) -> str:
        """Запоминает разрешённую команду."""
        self.calls.append((command, argument))
        return "cli output"


class FakeCustomToolRunner:
    """Фейковый runner пользовательских инструментов."""

    def run(self, tool: ZipperCustomTool, argument: str) -> str:
        """Возвращает результат пользовательского инструмента."""
        return f"{tool.value}:{argument}"


class FakeMCPProvider:
    """Фейковый MCP provider."""

    def tools_for_config(self, config: ZipperConfig) -> tuple[list[Any], list[str]]:
        """Возвращает отсутствие MCP-инструментов."""
        return [], []


class FakeNoteWriter:
    """Фейковая запись заметок."""

    def __init__(self) -> None:
        self.notes: list[str] = []

    def write_note(self, text: str, config: ZipperConfig) -> Path:
        """Запоминает заметку."""
        self.notes.append(text)
        return Path("/tmp/note.md")


class FakeNotify:
    """Фейковая системная интеграция."""

    def __init__(self) -> None:
        self.notifications: list[tuple[str, str]] = []

    def notify(self, title: str, message: str) -> None:
        """Запоминает уведомление."""
        self.notifications.append((title, message))


class FakeOverlay:
    """Фейковый overlay записи."""

    def show(self) -> None:
        """Заглушка."""
        return None

    def hide(self) -> None:
        """Заглушка."""
        return None

    def update_time(self, elapsed_seconds: int) -> None:
        """Заглушка."""
        return None


class FakeUrlOpener:
    """Фейковое открытие URL."""

    def __init__(self) -> None:
        self.urls: list[str] = []

    def open_url(self, url: str) -> bool:
        """Запоминает URL."""
        self.urls.append(url)
        return True


def make_use_case(config: ZipperConfig | None = None, agent: FakeAgent | None = None, llm_cached: bool = True):
    """Создаёт ZipperUseCases с фейковыми зависимостями."""
    runtime = FakeRuntime()
    recorder = FakeRecorder()
    text_output = FakeTextOutput()
    memory = FakeMemoryStore()
    use_case = ZipperUseCases(
        runtime=runtime,
        recorder=recorder,
        transcriber=FakeTranscriber(),
        llm_processor=FakeLLM(cached=llm_cached),
        config_provider=FakeConfigProvider(config),
        memory_store=memory,
        agent_service=agent or FakeAgent(),
        clipboard_service=FakeClipboard(),
        text_output=text_output,
        voice_output=FakeVoiceOutput(),
        url_opener=FakeUrlOpener(),
        command_runner=FakeCommandRunner(),
        custom_tool_runner=FakeCustomToolRunner(),
        mcp_tool_provider=FakeMCPProvider(),
        note_writer=FakeNoteWriter(),
        system_integration_service=FakeNotify(),
        recording_overlay=FakeOverlay(),
        publish_snapshot=lambda: setattr(runtime, "snapshots", runtime.snapshots + 1),
    )
    return use_case, runtime, recorder, text_output, memory


def test_zipper_records_voice_command_without_regular_insertion():
    """Команда Zipper распознаётся через transcribe_to_text и не вставляется как диктовка."""
    agent = FakeAgent(ZipperAgentResult(text="Показал результат", output_mode="window"))
    use_case, runtime, recorder, text_output, memory = make_use_case(agent=agent)

    use_case.toggle()
    assert runtime.started is True
    assert runtime.zipper_recording_active is True
    assert recorder.callback is not None

    use_case.stop_recording()
    recorder.callback(object(), "ru", lambda status: None, lambda: True)
    assert use_case._worker is not None
    use_case._worker.join(timeout=2)

    assert use_case.transcriber.transcribe_called is False
    assert use_case.transcriber.transcribe_to_text_called is True
    assert agent.calls[0]["request"] == "запиши заметку тест"
    assert text_output.messages[-1] == ("Zipper", "Показал результат")
    assert runtime.state == Config.STATUS_IDLE
    assert len(memory.snapshot.events) > 0


def test_zipper_hotkey_reports_uncached_llm_and_starts_download():
    """Если LLM не скачана, Zipper пишет причину в debug-поток и запускает загрузку."""
    use_case, runtime, recorder, text_output, _memory = make_use_case(llm_cached=False)

    use_case.toggle()

    assert recorder.started is False
    assert runtime.download_requests == 1
    assert any(event.kind == "toggle" for event in text_output.events)
    assert any(event.kind == "error" and "LLM-модель ещё не скачана" in event.message for event in text_output.events)


def test_zipper_starts_download_before_blocking_error_window():
    """Загрузка LLM должна стартовать до modal-окна с предупреждением."""
    use_case, runtime, recorder, text_output, _memory = make_use_case(llm_cached=False)
    order: list[str] = []

    def download_llm_model() -> None:
        order.append("download")
        runtime.download_requests += 1

    def show_text(title: str, text: str) -> None:
        del title, text
        order.append("window")

    runtime.download_llm_model = download_llm_model
    text_output.show_text = show_text

    use_case.toggle()

    assert recorder.started is False
    assert runtime.download_requests == 1
    assert order == ["download", "window"]


def test_zipper_downloads_required_model_outside_agent_context():
    """Если агентский runtime запросил модель, Zipper делегирует скачивание приложению."""

    class FailingAgent(FakeAgent):
        def invoke(self, request: str, **kwargs: Any) -> ZipperAgentResult:
            del request, kwargs
            raise ModelRequiredError("mlx-community/gemma", label="VLM-модель")

    use_case, runtime, _recorder, text_output, _memory = make_use_case(agent=FailingAgent())
    order: list[str] = []

    def download_required_model(requirement: ModelRequiredError) -> None:
        order.append("download")
        runtime.required_downloads.append((requirement.label, requirement.model_name))

    def show_text(title: str, text: str) -> None:
        del title, text
        order.append("window")

    runtime.download_required_model = download_required_model
    text_output.show_text = show_text

    use_case._run_agent("скажи привет", lambda: True)

    assert runtime.required_downloads == [("VLM-модель", "mlx-community/gemma")]
    assert order == ["download", "window"]
    assert any(event.kind == "model_download_required" for event in text_output.events)


def test_zipper_builtin_tools_keep_clipboard_and_cli_explicitly_configured():
    """Встроенные инструменты и CLI-команды доступны только из конфига."""
    command = ZipperCliCommand(
        name="date",
        description="Показать дату",
        command=("/bin/date",),
        require_confirmation=False,
    )
    use_case, *_ = make_use_case(ZipperConfig(cli_commands=(command,)))

    tools = {tool.name: tool for tool in use_case._build_tools()}
    assert tools["get_clipboard"].run("") == "из буфера"
    assert tools["set_clipboard"].run("новый текст") == "Текст положен в буфер обмена."
    assert tools["cli_date"].run("") == "cli output"


def test_zipper_config_provider_merges_example_local_and_user(tmp_path, caplog):
    """Конфиг Zipper поддерживает example/local/user с ожидаемым приоритетом."""
    example = tmp_path / "example.toml"
    local = tmp_path / "zipper.local.toml"
    user = tmp_path / "Application Support" / "Dictator" / "zipper.toml"
    example.write_text(
        """
enabled = false
notes_directory = "/example"

[context]
max_tokens = 10
max_events = 3
""",
        encoding="utf-8",
    )
    local.write_text("enabled = true\n", encoding="utf-8")
    user.parent.mkdir(parents=True)
    user.write_text(
        """
notes_directory = "/user"

[debug]
enabled = true
""",
        encoding="utf-8",
    )

    provider = ZipperConfigProvider(example_path=example, local_path=local, user_path=user, open_path=lambda path: True)
    caplog.set_level("INFO", logger="src.infrastructure.zipper_config")
    config = provider.load_config()

    assert config.enabled is True
    assert config.notes_directory == "/user"
    assert config.context.max_tokens == 10
    assert config.context.max_events == 3
    assert config.debug.enabled is True
    assert "Конфиг Zipper загружен: enabled=True, debug=True" in caplog.text
    assert str(example) in caplog.text
    assert str(local) in caplog.text
    assert str(user) in caplog.text


def test_zipper_summarizes_context_to_persistent_memory():
    """При превышении лимита события суммаризуются в постоянную память."""
    use_case, *_unused, memory = make_use_case(
        ZipperConfig(context=ZipperConfig().context.__class__(max_tokens=1, max_events=1, memory_enabled=True))
    )
    for index in range(45):
        use_case._event("tool", f"событие {index}", {"index": index})
    use_case._append_context_events()
    use_case._summarize_context_if_needed()

    assert "пользователь часто просит заметки" in memory.snapshot.memory
    assert len(memory.snapshot.events) <= 40
