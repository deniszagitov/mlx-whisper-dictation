"""Тесты голосового агента Zipper."""

from __future__ import annotations

from typing import Any

from src.domain.constants import Config
from src.domain.model_downloads import ModelRequiredError
from src.domain.zipper import (
    ZipperAgentResult,
    ZipperCliCommand,
    ZipperConfig,
    ZipperCustomTool,
    ZipperMemorySnapshot,
    ZipperToolSpec,
)
from src.infrastructure.llm_runtime import LlmGateway
from src.infrastructure.zipper_config import ZipperConfigProvider
from src.infrastructure.zipper_runtime import LangChainZipperAgent
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

    def __init__(self, text: str = "скажи дату") -> None:
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
        return "пользователь часто просит дату"


class FakeCachedLLM(LlmGateway):
    """Тестовый LlmGateway, который считает модель доступной локально."""

    def is_model_cached(self) -> bool:
        """Не запускает downloader перед E2E-сценарием."""
        return True


class FakeAgentTokenizer:
    """Простой tokenizer для e2e-проверки Zipper agent runtime."""

    def apply_chat_template(
        self,
        messages: list[dict[str, str]],
        tokenize: bool = False,
        add_generation_prompt: bool = True,
        **kwargs: Any,
    ) -> str:
        """Возвращает текстовый prompt без настоящей токенизации."""
        del tokenize, add_generation_prompt, kwargs
        return "\n\n".join(message["content"] for message in messages)

    def encode(self, text: str) -> list[str]:
        """Считает токены словами."""
        return text.split()


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
    assert agent.calls[0]["request"] == "скажи дату"
    assert text_output.messages[-1] == ("Zipper", "Показал результат")
    assert runtime.state == Config.STATUS_IDLE
    assert len(memory.snapshot.events) > 0
    assert any(event.kind == "user_speech" for event in memory.snapshot.events)


def test_zipper_debug_panel_toggle_updates_state_and_stream():
    """Debug-панель Zipper должна менять состояние runtime и получать событие."""
    use_case, runtime, _recorder, text_output, _memory = make_use_case()

    use_case.toggle_debug_panel()

    assert runtime.zipper_debug_panel_enabled is True
    assert text_output.debug_visible is True
    assert text_output.events[-1].kind == "debug_panel"
    assert text_output.events[-1].payload == {"enabled": True}
    assert runtime.snapshots == 1

    use_case.toggle_debug_panel()

    assert runtime.zipper_debug_panel_enabled is False
    assert text_output.debug_visible is False
    assert text_output.events[-1].payload == {"enabled": False}


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
    assert "write_note" not in tools


def test_zipper_fallback_no_longer_handles_note_command_as_tool():
    """Фраза про заметку больше не вызывает локальный writer Zipper."""
    agent = LangChainZipperAgent(FakeLLM())

    result = agent._invoke_fallback("запиши заметку тест", system_message="Ты тестовый Zipper.", tools=[])

    assert result == ZipperAgentResult(text="пользователь часто просит дату", output_mode="window")


def test_zipper_config_provider_merges_example_local_and_user(tmp_path, caplog):
    """Конфиг Zipper поддерживает example/local/user с ожидаемым приоритетом."""
    example = tmp_path / "example.toml"
    local = tmp_path / "zipper.local.toml"
    user = tmp_path / "Application Support" / "Dictator" / "zipper.toml"
    example.write_text(
        """
enabled = false

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
[debug]
enabled = true
""",
        encoding="utf-8",
    )

    provider = ZipperConfigProvider(example_path=example, local_path=local, user_path=user, open_path=lambda path: True)
    caplog.set_level("INFO", logger="src.infrastructure.zipper_config")
    config = provider.load_config()

    assert config.enabled is True
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

    assert "пользователь часто просит дату" in memory.snapshot.memory
    assert len(memory.snapshot.events) <= 40


def test_zipper_langchain_e2e_loads_model_once_generates_answer_and_calls_tool():
    """E2E: Zipper agent загружает модель один раз, генерирует ответ и вызывает инструмент."""
    load_calls: list[str] = []
    cleanup_calls: list[bool] = []
    generation_prompts: list[str] = []
    tool_calls: list[str] = []
    responses = iter(
        (
            "Thought: нужно узнать дату\nAction: current_datetime\nAction Input: сейчас",
            "Thought: дата получена\nFinal Answer: Сейчас 2026-05-08.\noutput_mode: window",
        )
    )

    def load_runtime(model_name: str) -> tuple[object, FakeAgentTokenizer]:
        load_calls.append(model_name)
        return object(), FakeAgentTokenizer()

    def generate(_model: object, _tokenizer: FakeAgentTokenizer, prompt: str, max_tokens: int) -> str:
        generation_prompts.append(prompt)
        assert max_tokens == 1000
        return next(responses)

    def tool(argument: str) -> str:
        tool_calls.append(argument)
        return "2026-05-08T15:00:00+03:00"

    processor = LlmGateway(
        "fake-agent-model",
        runtime_loader=load_runtime,
        generation_runner=generate,
        memory_cleanup=lambda: cleanup_calls.append(True),
    )
    agent = LangChainZipperAgent(processor)

    result = agent.invoke(
        "скажи дату",
        system_message="Ты тестовый Zipper.",
        memory="",
        events=(),
        tools=[ZipperToolSpec("current_datetime", "Получить текущие дату и время.", tool)],
        config=ZipperConfig(),
    )

    assert result == ZipperAgentResult(text="Сейчас 2026-05-08.", output_mode="window")
    assert tool_calls == ["сейчас"]
    assert load_calls == ["fake-agent-model"]
    assert len(generation_prompts) == 2
    assert processor._cached_model is not None
    assert processor.performance_mode == "normal"
    assert cleanup_calls == []


def test_zipper_langchain_keeps_loaded_model_between_agent_invocations():
    """Zipper не должен выгружать LLM между отдельными голосовыми командами."""
    load_calls: list[str] = []
    cleanup_calls: list[bool] = []
    responses = iter(
        (
            "Thought: отвечаю\nFinal Answer: Первый ответ.\noutput_mode: voice",
            "Thought: отвечаю снова\nFinal Answer: Второй ответ.\noutput_mode: voice",
        )
    )

    def load_runtime(model_name: str) -> tuple[object, FakeAgentTokenizer]:
        load_calls.append(model_name)
        return object(), FakeAgentTokenizer()

    def generate(_model: object, _tokenizer: FakeAgentTokenizer, _prompt: str, max_tokens: int) -> str:
        assert max_tokens == 1000
        return next(responses)

    processor = LlmGateway(
        "fake-agent-model",
        runtime_loader=load_runtime,
        generation_runner=generate,
        memory_cleanup=lambda: cleanup_calls.append(True),
    )
    agent = LangChainZipperAgent(processor)
    tools = [ZipperToolSpec("current_datetime", "Получить текущие дату и время.", lambda _argument: "2026-05-08")]

    first = agent.invoke(
        "первая команда",
        system_message="Ты тестовый Zipper.",
        memory="",
        events=(),
        tools=tools,
        config=ZipperConfig(),
    )
    second = agent.invoke(
        "вторая команда",
        system_message="Ты тестовый Zipper.",
        memory="",
        events=(),
        tools=tools,
        config=ZipperConfig(),
    )

    assert first == ZipperAgentResult(text="Первый ответ.", output_mode="voice")
    assert second == ZipperAgentResult(text="Второй ответ.", output_mode="voice")
    assert load_calls == ["fake-agent-model"]
    assert processor._cached_model is not None
    assert processor.performance_mode == "normal"
    assert cleanup_calls == []


def test_zipper_voice_command_e2e_runs_langchain_model_tool_output_and_memory():
    """E2E: hotkey-сценарий Zipper доходит до LLM, вызывает tool и сохраняет debug-контекст."""
    load_calls: list[str] = []
    cleanup_calls: list[bool] = []
    generation_prompts: list[str] = []
    responses = iter(
        (
            "Thought: нужно узнать текущую дату\nAction: current_datetime\nAction Input: сейчас",
            "Thought: инструмент вернул дату\nFinal Answer: Сейчас 2026-05-08.\noutput_mode: window",
        )
    )

    def load_runtime(model_name: str) -> tuple[object, FakeAgentTokenizer]:
        load_calls.append(model_name)
        return object(), FakeAgentTokenizer()

    def generate(_model: object, _tokenizer: FakeAgentTokenizer, prompt: str, max_tokens: int) -> str:
        generation_prompts.append(prompt)
        assert max_tokens == 1000
        return next(responses)

    processor = FakeCachedLLM(
        "fake-agent-model",
        runtime_loader=load_runtime,
        generation_runner=generate,
        memory_cleanup=lambda: cleanup_calls.append(True),
    )
    runtime = FakeRuntime()
    recorder = FakeRecorder()
    text_output = FakeTextOutput()
    memory = FakeMemoryStore()
    use_case = ZipperUseCases(
        runtime=runtime,
        recorder=recorder,
        transcriber=FakeTranscriber("скажи дату"),
        llm_processor=processor,
        config_provider=FakeConfigProvider(ZipperConfig()),
        memory_store=memory,
        agent_service=LangChainZipperAgent(processor),
        clipboard_service=FakeClipboard(),
        text_output=text_output,
        voice_output=FakeVoiceOutput(),
        url_opener=FakeUrlOpener(),
        command_runner=FakeCommandRunner(),
        custom_tool_runner=FakeCustomToolRunner(),
        mcp_tool_provider=FakeMCPProvider(),
        system_integration_service=FakeNotify(),
        recording_overlay=FakeOverlay(),
        publish_snapshot=lambda: setattr(runtime, "snapshots", runtime.snapshots + 1),
    )

    use_case.toggle()
    use_case.stop_recording()
    assert recorder.callback is not None
    recorder.callback(object(), "ru", lambda status: None, lambda: True)
    assert use_case._worker is not None
    use_case._worker.join(timeout=2)

    assert use_case._worker.is_alive() is False
    assert runtime.state == Config.STATUS_IDLE
    assert recorder.started is True
    assert recorder.stopped is True
    assert use_case.transcriber.transcribe_called is False
    assert use_case.transcriber.transcribe_to_text_called is True
    assert load_calls == ["fake-agent-model"]
    assert len(generation_prompts) == 2
    assert processor._cached_model is not None
    assert processor.performance_mode == "normal"
    assert cleanup_calls == []
    assert text_output.messages[-1] == ("Zipper", "Сейчас 2026-05-08.")

    event_kinds = [event.kind for event in text_output.events]
    assert "user_speech" in event_kinds
    assert "agent_input" in event_kinds
    assert "tool" in event_kinds
    assert "agent_output" in event_kinds
    assert any(event.kind == "tool" and event.message == "current_datetime" for event in text_output.events)
    assert any(event.kind == "agent_output" and event.payload["text"] == "Сейчас 2026-05-08." for event in memory.snapshot.events)
