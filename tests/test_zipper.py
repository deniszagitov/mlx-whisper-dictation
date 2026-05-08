"""Тесты голосового агента Zipper."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any, ClassVar

from src.adapters import zipper_windows as zipper_windows_module
from src.adapters.zipper_windows import ZipperTextOutput, ZipperVoiceOutput
from src.domain.constants import Config
from src.domain.model_downloads import ModelRequiredError
from src.domain.reader_types import TTSConfig
from src.domain.zipper import (
    ZipperAgentResult,
    ZipperCliCommand,
    ZipperConfig,
    ZipperMemorySnapshot,
)
from src.infrastructure.llm_runtime import LlmGateway
from src.infrastructure.model_runtime_service import ModelRuntimeService
from src.infrastructure.zipper_config import ZipperConfigProvider, normalize_config
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

    def summarize_memory(self, events_text: str, *, memory: str = "") -> str:
        """Возвращает краткое резюме для тестов памяти."""
        self.calls.append({"summary_events": events_text, "memory": memory})
        return "пользователь часто просит дату"


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


def make_use_case(config: ZipperConfig | None = None, agent: FakeAgent | None = None, llm_cached: bool = True):
    """Создаёт ZipperUseCases с фейковыми зависимостями."""
    runtime = FakeRuntime()
    recorder = FakeRecorder()
    text_output = FakeTextOutput()
    voice_output = FakeVoiceOutput()
    memory = FakeMemoryStore()
    use_case = ZipperUseCases(
        runtime=runtime,
        recorder=recorder,
        transcriber=FakeTranscriber(),
        llm_processor=FakeLLM(cached=llm_cached),
        config_provider=FakeConfigProvider(config),
        memory_store=memory,
        agent_service=agent or FakeAgent(),
        text_output=text_output,
        voice_output=voice_output,
        system_integration_service=FakeNotify(),
        recording_overlay=FakeOverlay(),
        publish_snapshot=lambda: setattr(runtime, "snapshots", runtime.snapshots + 1),
    )
    return use_case, runtime, recorder, text_output, memory


def test_zipper_text_output_show_text_creates_retained_window(monkeypatch):
    """Текстовый вывод Zipper создаёт удерживаемое окно, а не modal alert."""

    class FakeFramePart:
        def __init__(self, **values: float) -> None:
            self.__dict__.update(values)

    class FakeFrame:
        def __init__(self) -> None:
            self.origin = FakeFramePart(x=100, y=80)
            self.size = FakeFramePart(width=1440, height=900)

    class FakeThread:
        @staticmethod
        def isMainThread() -> bool:
            return True

    class FakeApplication:
        instance: FakeApplication

        def __init__(self) -> None:
            self.activation_requests: list[bool] = []

        @classmethod
        def sharedApplication(cls) -> FakeApplication:
            return cls.instance

        def activateIgnoringOtherApps_(self, value: bool) -> None:
            self.activation_requests.append(value)

    FakeApplication.instance = FakeApplication()

    class FakeScreen:
        @staticmethod
        def mainScreen() -> FakeScreen:
            return FakeScreen()

        def visibleFrame(self) -> FakeFrame:
            return FakeFrame()

    class FakeAlert:
        @classmethod
        def alloc(cls) -> FakeAlert:
            raise AssertionError("show_text не должен создавать NSAlert")

    class FakeView:
        def __init__(self) -> None:
            self.frame: Any | None = None
            self.subviews: list[Any] = []
            self.autoresizing_mask: int | None = None

        @classmethod
        def alloc(cls) -> FakeView:
            return cls()

        def initWithFrame_(self, frame: Any) -> FakeView:
            self.frame = frame
            return self

        def setAutoresizingMask_(self, mask: int) -> None:
            self.autoresizing_mask = mask

        def addSubview_(self, view: Any) -> None:
            self.subviews.append(view)

    class FakeScrollView(FakeView):
        def __init__(self) -> None:
            super().__init__()
            self.has_vertical_scroller = False
            self.document_view: Any | None = None

        def setHasVerticalScroller_(self, value: bool) -> None:
            self.has_vertical_scroller = value

        def setDocumentView_(self, view: Any) -> None:
            self.document_view = view

    class FakeTextView(FakeView):
        def __init__(self) -> None:
            super().__init__()
            self.editable: bool | None = None
            self.selectable: bool | None = None
            self.text = ""

        def setEditable_(self, value: bool) -> None:
            self.editable = value

        def setSelectable_(self, value: bool) -> None:
            self.selectable = value

        def setRichText_(self, _value: bool) -> None:
            return None

        def setImportsGraphics_(self, _value: bool) -> None:
            return None

        def setUsesFindPanel_(self, _value: bool) -> None:
            return None

        def setFont_(self, _font: Any) -> None:
            return None

        def setString_(self, text: str) -> None:
            self.text = text

    class FakeButton(FakeView):
        def __init__(self) -> None:
            super().__init__()
            self.title = ""
            self.target: Any | None = None
            self.action: str | None = None

        def setTitle_(self, title: str) -> None:
            self.title = title

        def setBezelStyle_(self, _style: int) -> None:
            return None

        def setTarget_(self, target: Any) -> None:
            self.target = target

        def setAction_(self, action: str) -> None:
            self.action = action

    class FakeWindow:
        created: ClassVar[list[FakeWindow]] = []

        def __init__(self) -> None:
            self.title = ""
            self.level: int | None = None
            self.collection_behavior: int | None = None
            self.released_when_closed: bool | None = None
            self.content_view: Any | None = None
            self.delegate: Any | None = None
            self.front_regardless_calls = 0
            self.key_order_calls = 0
            self.closed = False

        @classmethod
        def alloc(cls) -> FakeWindow:
            return cls()

        def initWithContentRect_styleMask_backing_defer_(self, frame: Any, style_mask: int, backing: int, defer: bool) -> FakeWindow:
            self.frame = frame
            self.style_mask = style_mask
            self.backing = backing
            self.defer = defer
            self.created.append(self)
            return self

        def setTitle_(self, title: str) -> None:
            self.title = title

        def setLevel_(self, level: int) -> None:
            self.level = level

        def setReleasedWhenClosed_(self, value: bool) -> None:
            self.released_when_closed = value

        def setCollectionBehavior_(self, value: int) -> None:
            self.collection_behavior = value

        def setContentView_(self, view: Any) -> None:
            self.content_view = view

        def setDelegate_(self, delegate: Any | None) -> None:
            self.delegate = delegate

        def makeKeyAndOrderFront_(self, _sender: Any) -> None:
            self.key_order_calls += 1

        def orderFrontRegardless(self) -> None:
            self.front_regardless_calls += 1

        def orderOut_(self, _sender: Any) -> None:
            return None

        def close(self) -> None:
            self.closed = True
            if self.delegate is not None:
                self.delegate.windowWillClose_(None)

    class FakeFont:
        @staticmethod
        def systemFontOfSize_(_size: int) -> str:
            return "font"

    fake_appkit = SimpleNamespace(
        NSThread=FakeThread,
        NSApplication=FakeApplication,
        NSScreen=FakeScreen,
        NSAlert=FakeAlert,
        NSWindow=FakeWindow,
        NSView=FakeView,
        NSScrollView=FakeScrollView,
        NSTextView=FakeTextView,
        NSButton=FakeButton,
        NSFont=FakeFont,
        NSWindowStyleMaskTitled=1,
        NSWindowStyleMaskClosable=2,
        NSWindowStyleMaskResizable=4,
        NSWindowStyleMaskMiniaturizable=8,
        NSBackingStoreBuffered=16,
        NSFloatingWindowLevel=32,
        NSWindowCollectionBehaviorCanJoinAllSpaces=64,
        NSWindowCollectionBehaviorFullScreenAuxiliary=128,
        NSViewWidthSizable=256,
        NSViewHeightSizable=512,
        NSViewMinXMargin=1024,
        NSViewMaxYMargin=2048,
        NSBezelStyleRounded=4096,
    )
    monkeypatch.setattr(zipper_windows_module, "AppKit", fake_appkit)

    output = ZipperTextOutput()
    output.show_text("Zipper", "длинный ответ\nсо ссылкой https://example.test")

    assert len(FakeWindow.created) == 1
    window = FakeWindow.created[0]
    assert output._result_window is window
    assert output._result_window_delegate is window.delegate
    assert window.title == "Zipper"
    assert window.level == fake_appkit.NSFloatingWindowLevel
    assert window.released_when_closed is False
    assert window.front_regardless_calls == 1
    assert window.key_order_calls == 1
    assert FakeApplication.instance.activation_requests == [True, True]

    assert window.content_view is not None
    scroll_view = window.content_view.subviews[0]
    close_button = window.content_view.subviews[1]
    assert scroll_view.has_vertical_scroller is True
    assert scroll_view.document_view.text == "длинный ответ\nсо ссылкой https://example.test"
    assert scroll_view.document_view.editable is False
    assert scroll_view.document_view.selectable is True
    assert close_button.title == "Закрыть"
    assert close_button.action == "closeWindow:"

    close_button.target.closeWindow_(close_button)

    assert window.closed is True
    assert output._result_window is None
    assert output._result_text_view is None
    assert output._result_window_delegate is None

    output.show_text("Zipper", "ещё один ответ")
    second_window = FakeWindow.created[1]
    second_window.close()

    assert output._result_window is None
    assert output._result_text_view is None
    assert output._result_window_delegate is None


def test_zipper_agent_runtime_keeps_prompts_and_tools_together():
    """Инфраструктурный runtime хранит prompt-контракт и tools в одном объекте."""
    agent = LangChainZipperAgent(FakeLLM(), clipboard_service=FakeClipboard())

    assert agent._system_message("").startswith("Ты Zipper")
    system_message = agent._system_message("пользователь часто просит дату")
    assert "Постоянная память Zipper" in system_message
    assert "пользователь часто просит дату" in system_message

    def ignore_event(_kind: str, _message: str, _payload: dict[str, Any] | None = None) -> None:
        return None

    tools = agent._build_tools(ZipperConfig(), ignore_event)
    assert [tool.name for tool in tools[:6]] == [
        "get_clipboard",
        "set_clipboard",
        "current_datetime",
        "open_url",
        "show_text",
        "speak_text",
    ]
    speak_text = next(tool for tool in tools if tool.name == "speak_text")
    assert "готовую фразу для TTS" in speak_text.description
    assert "русские числа, время, даты, проценты и суммы пиши словами" in speak_text.description
    assert "English terms, API names, CLI commands and short code tokens stay in English" in speak_text.description
    assert "без дополнительной обработки в коде" in speak_text.description


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
    assert agent.calls[0]["memory"] == ""
    assert "tools" not in agent.calls[0]
    assert text_output.messages[-1] == ("Zipper", "Показал результат")
    assert runtime.state == Config.STATUS_IDLE
    assert len(memory.snapshot.events) > 0
    assert any(event.kind == "user_speech" for event in memory.snapshot.events)


def test_zipper_speaks_voice_result_through_voice_output():
    """Zipper направляет голосовой ответ в сервис озвучивания."""
    text = "Сейчас двадцать два часа пятьдесят шесть минут, API is ready."
    agent = FakeAgent(ZipperAgentResult(text=text, output_mode="voice"))
    use_case, _runtime, _recorder, text_output, _memory = make_use_case(agent=agent)

    use_case._run_agent("ответь голосом", lambda: True)

    assert use_case.voice_output.spoken == [text]
    assert text_output.messages == []
    assert any(event.kind == "agent_output" and event.payload["text"] == text for event in text_output.events)


def test_zipper_window_result_keeps_raw_text():
    """Оконный вывод Zipper не применяет голосовую TTS-нормализацию."""
    agent = FakeAgent(ZipperAgentResult(text="Версия 2.0: https://example.test", output_mode="window"))
    use_case, _runtime, _recorder, text_output, _memory = make_use_case(agent=agent)

    use_case._run_agent("покажи версию", lambda: True)

    assert text_output.messages[-1] == ("Zipper", "Версия 2.0: https://example.test")
    assert use_case.voice_output.spoken == []


def test_zipper_both_result_uses_voice_and_window_outputs():
    """Режим вывода both отправляет один ответ в TTS и текстовое окно."""
    agent = FakeAgent(ZipperAgentResult(text="Готово и показано", output_mode="both"))
    use_case, _runtime, _recorder, text_output, _memory = make_use_case(agent=agent)

    use_case._run_agent("ответь двумя способами", lambda: True)

    assert use_case.voice_output.spoken == ["Готово и показано"]
    assert text_output.messages[-1] == ("Zipper", "Готово и показано")


def test_zipper_voice_output_uses_current_tts_config():
    """Адаптер голосового вывода Zipper использует текущую настройку TTS."""

    class FakeSpeaker:
        def __init__(self) -> None:
            self.spoken: list[tuple[str, TTSConfig]] = []

        def speak(self, text: str, config: TTSConfig) -> None:
            self.spoken.append((text, config))

    speaker = FakeSpeaker()
    output = ZipperVoiceOutput(speaker, config_factory=lambda: TTSConfig(tone_instruction="утвердительно"))

    output.speak("Готово")

    assert speaker.spoken[0][0] == "Готово"
    assert speaker.spoken[0][1].tone_instruction == "утвердительно"


def test_zipper_voice_output_passes_agent_text_without_postprocessing():
    """Голосовой вывод Zipper не нормализует текст после агента."""

    class FakeSpeaker:
        def __init__(self) -> None:
            self.spoken: list[tuple[str, TTSConfig]] = []

        def speak(self, text: str, config: TTSConfig) -> None:
            self.spoken.append((text, config))

    speaker = FakeSpeaker()
    output = ZipperVoiceOutput(speaker, config_factory=TTSConfig)

    output.speak("купи 2 печенья")

    assert speaker.spoken[0][0] == "купи 2 печенья"


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
        command=("/bin/echo", "cli output"),
        require_confirmation=False,
    )
    clipboard = FakeClipboard()
    agent = LangChainZipperAgent(FakeLLM(), clipboard_service=clipboard, text_output=FakeTextOutput())

    tools = {tool.name: tool for tool in agent._build_tools(ZipperConfig(cli_commands=(command,)), lambda *_args: None)}
    assert tools["get_clipboard"].invoke("") == "из буфера"
    assert tools["set_clipboard"].invoke("новый текст") == "Текст положен в буфер обмена."
    assert clipboard.text == "новый текст"
    assert tools["cli_date"].invoke("") == "cli output"
    assert "write_note" not in tools

def test_zipper_config_provider_merges_local_and_user(tmp_path, caplog):
    """Конфиг Zipper поддерживает local/user с ожидаемым приоритетом."""
    local = tmp_path / "zipper.local.toml"
    user = tmp_path / "Application Support" / "Dictator" / "zipper.toml"
    local.write_text(
        """
enabled = false

[context]
max_tokens = 10
max_events = 3
""",
        encoding="utf-8",
    )
    user.parent.mkdir(parents=True)
    user.write_text(
        """
enabled = true

[debug]
enabled = true
""",
        encoding="utf-8",
    )

    provider = ZipperConfigProvider(local_path=local, user_path=user, open_path=lambda path: True)
    caplog.set_level("INFO", logger="src.infrastructure.zipper_config")
    config = provider.load_config()

    assert config.enabled is True
    assert config.context.max_tokens == 10
    assert config.context.max_events == 3
    assert config.debug.enabled is True
    assert "Конфиг Zipper загружен: enabled=True, debug=True" in caplog.text
    assert str(local) in caplog.text
    assert str(user) in caplog.text


def test_zipper_user_config_template_does_not_store_agent_prompts(tmp_path):
    """Стартовый пользовательский конфиг не должен содержать prompt-тексты агента."""
    local = tmp_path / "zipper.local.toml"
    user = tmp_path / "Application Support" / "Dictator" / "zipper.toml"

    ZipperConfigProvider(local_path=local, user_path=user, open_path=lambda path: True)

    text = user.read_text(encoding="utf-8")
    assert "Ты Zipper" not in text
    assert "system_message" not in text


def test_zipper_config_ignores_agent_prompt_fields_from_toml():
    """Prompt-поля не должны быть частью TOML-конфига Zipper."""
    config = normalize_config({"system_message": "Внешний prompt не используется.", "enabled": False})

    assert config.enabled is False
    assert not hasattr(config, "system_message")


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

    runtime_service = ModelRuntimeService(lm_loader=load_runtime)
    processor = LlmGateway(
        "fake-agent-model",
        runtime_loader=runtime_service.get_lm,
        generation_runner=generate,
        memory_cleanup=lambda: cleanup_calls.append(True),
    )
    agent = LangChainZipperAgent(processor)

    result = agent.invoke(
        "скажи дату",
        memory="",
        events=(),
        config=ZipperConfig(),
    )

    assert result == ZipperAgentResult(text="Сейчас 2026-05-08.", output_mode="window")
    assert load_calls == ["fake-agent-model"]
    assert len(generation_prompts) == 2
    assert "готовую фразу для TTS" in generation_prompts[0]
    assert "русские числа, время, даты, проценты и суммы пиши словами" in generation_prompts[0]
    assert "English terms, API names, CLI commands and short code tokens stay in English" in generation_prompts[0]
    assert "без дополнительной обработки в коде" in generation_prompts[0]
    assert processor._cached_model is None
    assert processor.performance_mode == "normal"
    assert cleanup_calls == []


def test_zipper_qwen_uses_hermes_tool_calls_without_react_iteration_limit():
    """Qwen-модель должна вызывать инструменты через Hermes-разметку, а не ReAct stopwords."""
    generation_prompts: list[str] = []
    events: list[tuple[str, str, dict[str, Any] | None]] = []
    responses = iter(
        (
            '<tool_call>{"name": "current_datetime", "arguments": {}}</tool_call>',
            "Время получено через инструмент.\noutput_mode: window",
        )
    )

    def load_runtime(model_name: str) -> tuple[object, FakeAgentTokenizer]:
        assert model_name == "mlx-community/Qwen3.6-35B-A3B-4bit"
        return object(), FakeAgentTokenizer()

    def generate(_model: object, _tokenizer: FakeAgentTokenizer, prompt: str, max_tokens: int) -> str:
        generation_prompts.append(prompt)
        assert max_tokens == 1000
        return next(responses)

    def emit_event(kind: str, message: str, payload: dict[str, Any] | None = None) -> None:
        events.append((kind, message, payload))

    processor = LlmGateway(
        "mlx-community/Qwen3.6-35B-A3B-4bit",
        runtime_loader=load_runtime,
        generation_runner=generate,
    )
    agent = LangChainZipperAgent(processor)

    result = agent.invoke(
        "сколько времени",
        memory="",
        events=(),
        config=ZipperConfig(),
        emit_event=emit_event,
    )

    assert result == ZipperAgentResult(text="Время получено через инструмент.", output_mode="window")
    assert len(generation_prompts) == 2
    assert "Action:" not in generation_prompts[0]
    assert "<tool_call>" in generation_prompts[0]
    assert "готовую фразу для TTS" in generation_prompts[0]
    assert "русские числа, время, даты, проценты и суммы пиши словами" in generation_prompts[0]
    assert "English terms, API names, CLI commands and short code tokens stay in English" in generation_prompts[0]
    assert "без дополнительной обработки в коде" in generation_prompts[0]
    assert "tone_instruction" not in generation_prompts[0]
    assert "tool current_datetime" in generation_prompts[1]
    assert any(kind == "tool" and message == "current_datetime" for kind, message, _payload in events)


def test_zipper_qwen_maps_output_tool_to_result_without_double_speaking():
    """Если Qwen вызвала speak_text, вывод выполняет use case, чтобы не озвучивать ответ дважды."""
    generation_prompts: list[str] = []
    events: list[tuple[str, str, dict[str, Any] | None]] = []

    def load_runtime(model_name: str) -> tuple[object, FakeAgentTokenizer]:
        assert model_name == "mlx-community/Qwen3.6-35B-A3B-4bit"
        return object(), FakeAgentTokenizer()

    def generate(_model: object, _tokenizer: FakeAgentTokenizer, prompt: str, max_tokens: int) -> str:
        generation_prompts.append(prompt)
        assert max_tokens == 1000
        return (
            '<tool_call>{"name": "speak_text", "arguments": '
            '{"input": "Я не могу управлять медиаплеером.", "tone_instruction": "дружелюбный и бодрый"}}</tool_call>'
        )

    def emit_event(kind: str, message: str, payload: dict[str, Any] | None = None) -> None:
        events.append((kind, message, payload))

    processor = LlmGateway(
        "mlx-community/Qwen3.6-35B-A3B-4bit",
        runtime_loader=load_runtime,
        generation_runner=generate,
    )
    voice_output = FakeVoiceOutput()
    agent = LangChainZipperAgent(processor, voice_output=voice_output)

    result = agent.invoke(
        "озвучь отказ",
        memory="",
        events=(),
        config=ZipperConfig(),
        emit_event=emit_event,
    )

    assert result == ZipperAgentResult(text="Я не могу управлять медиаплеером.", output_mode="voice")
    assert len(generation_prompts) == 1
    assert "tone_instruction" not in generation_prompts[0]
    assert voice_output.spoken == []
    assert events[0][0] == "tool"
    assert events[0][1] == "speak_text"
    assert events[0][2] == {"chars": len("Я не могу управлять медиаплеером."), "deferred_to_output": True}


def test_zipper_speak_text_tool_uses_input_argument_for_voice_output():
    """Инструмент speak_text озвучивает значение input из JSON-аргументов."""
    events: list[tuple[str, str, dict[str, Any] | None]] = []
    voice_output = FakeVoiceOutput()
    agent = LangChainZipperAgent(object(), voice_output=voice_output)

    def emit_event(kind: str, message: str, payload: dict[str, Any] | None = None) -> None:
        events.append((kind, message, payload))

    result = agent._tool_speak_text('{"input": "Готово.", "tone_instruction": "спокойный и чёткий"}', emit_event)

    assert result == "Текст озвучен."
    assert voice_output.spoken == ["Готово."]
    assert events == [("tool", "speak_text", {"chars": len("Готово.")})]


def test_zipper_langchain_keeps_loaded_model_between_agent_invocations():
    """Zipper не должен выгружать LLM между отдельными голосовыми командами."""
    load_calls: list[str] = []
    cleanup_calls: list[bool] = []
    responses = iter(
        (
            "Thought: отвечаю\nFinal Answer: Первый ответ.\noutput_mode: voice\ntone_instruction: дружелюбный и бодрый",
            "Thought: отвечаю снова\nFinal Answer: Второй ответ.\noutput_mode: voice\ntone_instruction: спокойный и чёткий",
        )
    )

    def load_runtime(model_name: str) -> tuple[object, FakeAgentTokenizer]:
        load_calls.append(model_name)
        return object(), FakeAgentTokenizer()

    def generate(_model: object, _tokenizer: FakeAgentTokenizer, _prompt: str, max_tokens: int) -> str:
        assert max_tokens == 1000
        return next(responses)

    runtime_service = ModelRuntimeService(lm_loader=load_runtime)
    processor = LlmGateway(
        "fake-agent-model",
        runtime_loader=runtime_service.get_lm,
        generation_runner=generate,
        memory_cleanup=lambda: cleanup_calls.append(True),
    )
    agent = LangChainZipperAgent(processor)

    first = agent.invoke(
        "первая команда",
        memory="",
        events=(),
        config=ZipperConfig(),
    )
    second = agent.invoke(
        "вторая команда",
        memory="",
        events=(),
        config=ZipperConfig(),
    )

    assert first == ZipperAgentResult(text="Первый ответ.", output_mode="voice")
    assert second == ZipperAgentResult(text="Второй ответ.", output_mode="voice")
    assert load_calls == ["fake-agent-model"]
    assert processor._cached_model is None
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

    runtime_service = ModelRuntimeService(lm_loader=load_runtime)
    processor = FakeCachedLLM(
        "fake-agent-model",
        runtime_loader=runtime_service.get_lm,
        generation_runner=generate,
        memory_cleanup=lambda: cleanup_calls.append(True),
    )
    runtime = FakeRuntime()
    recorder = FakeRecorder()
    text_output = FakeTextOutput()
    voice_output = FakeVoiceOutput()
    memory = FakeMemoryStore()
    use_case = ZipperUseCases(
        runtime=runtime,
        recorder=recorder,
        transcriber=FakeTranscriber("скажи дату"),
        llm_processor=processor,
        config_provider=FakeConfigProvider(ZipperConfig()),
        memory_store=memory,
        agent_service=LangChainZipperAgent(
            processor,
            clipboard_service=FakeClipboard(),
            text_output=text_output,
            voice_output=voice_output,
        ),
        text_output=text_output,
        voice_output=voice_output,
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
    assert processor._cached_model is None
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
