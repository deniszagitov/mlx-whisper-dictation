"""Тесты orchestration-сценариев LLM-пайплайна."""

from __future__ import annotations

from types import SimpleNamespace
from typing import TYPE_CHECKING, Any

from src.domain.constants import Config
from src.use_cases import llm_pipeline as llm_pipeline_module
from src.use_cases.llm_pipeline import LlmPipelineUseCases

if TYPE_CHECKING:
    import pytest


class FakeRecorder:
    """Фейковый recorder, сохраняющий callback обработки аудио."""

    def __init__(self) -> None:
        self.started = False
        self.last_language: str | None = None
        self.on_audio_ready = None

    def start(self, language: str | None, on_audio_ready: Any) -> None:
        """Имитирует старт записи и сохраняет callback."""
        self.started = True
        self.last_language = language
        self.on_audio_ready = on_audio_ready


class FakeTranscriber:
    """Фейковый transcriber для проверки побочных эффектов пайплайна."""

    def __init__(self, recognized_text: str = "текст") -> None:
        self.recognized_text = recognized_text
        self.llm_clipboard_enabled = True
        self.history: list[str] = []
        self.token_usage: list[int] = []

    def transcribe_to_text(self, _audio_data: Any, _language: str | None) -> str:
        """Возвращает заранее подготовленный результат Whisper."""
        return self.recognized_text

    def add_to_history(self, text: str) -> None:
        """Сохраняет итоговый текст в историю."""
        self.history.append(text)

    def add_token_usage(self, token_count: int) -> None:
        """Сохраняет число израсходованных токенов."""
        self.token_usage.append(token_count)


class FakeLlmProcessor:
    """Фейковый LLM gateway с настраиваемым поведением."""

    def __init__(
        self,
        *,
        cached: bool = True,
        response: str = "готово",
        token_usage: int = 11,
        process_error: Exception | None = None,
        download_error: Exception | None = None,
    ) -> None:
        self.cached = cached
        self.response = response
        self.last_token_usage = token_usage
        self.process_error = process_error
        self.download_error = download_error
        self.process_calls: list[tuple[str, str, str | None]] = []
        self.download_progress_callback = None

    def is_model_cached(self) -> bool:
        """Сообщает, скачана ли модель."""
        return self.cached

    def process_text(self, text: str, system_prompt: str, *, context: str | None = None) -> str:
        """Возвращает заготовленный ответ или бросает ошибку."""
        self.process_calls.append((text, system_prompt, context))
        if self.process_error is not None:
            raise self.process_error
        return self.response

    def ensure_model_downloaded(self) -> None:
        """Эмулирует загрузку модели с callback прогресса."""
        if self.download_progress_callback is not None:
            self.download_progress_callback("weights", 25.0, 50 * 1024 * 1024)
            self.download_progress_callback("", Config.DOWNLOAD_COMPLETE_PCT, 0)
        if self.download_error is not None:
            raise self.download_error


class FakeClipboardService:
    """Фейковый буфер обмена."""

    def __init__(self, text: str | None = None) -> None:
        self.text = text
        self.writes: list[str] = []

    def read_text(self) -> str | None:
        """Возвращает текущее содержимое буфера."""
        return self.text

    def write_text(self, text: str) -> None:
        """Запоминает запись в буфер."""
        self.writes.append(text)


class FakeOverlay:
    """Фейковый overlay записи."""

    def __init__(self) -> None:
        self.show_calls = 0

    def show(self) -> None:
        """Считает вызовы показа overlay."""
        self.show_calls += 1


def make_runtime(*, overlay: FakeOverlay, notifications: list[tuple[str, str]]) -> SimpleNamespace:
    """Создаёт минимальный runtime для тестов LLM-пайплайна."""

    def notify(title: str, message: str) -> None:
        notifications.append((title, message))

    return SimpleNamespace(
        started=False,
        state=Config.STATUS_IDLE,
        llm_prompt_name=Config.DEFAULT_LLM_PROMPT_NAME,
        show_recording_notification=True,
        current_language="ru",
        start_time=0.0,
        elapsed_time=0,
        show_recording_overlay=True,
        show_recording_time_in_menu_bar=True,
        recording_overlay=overlay,
        system_integration_service=SimpleNamespace(notify=notify),
        llm_downloading=False,
        llm_download_title="",
        prepare_recording=lambda: True,
    )


def make_use_cases(
    *,
    runtime: SimpleNamespace,
    recorder: FakeRecorder | None = None,
    transcriber: FakeTranscriber | None = None,
    llm_processor: FakeLlmProcessor | None = None,
    clipboard: FakeClipboardService | None = None,
    stop_calls: list[bool] | None = None,
    published_titles: list[str] | None = None,
) -> tuple[LlmPipelineUseCases, FakeRecorder, FakeTranscriber, FakeClipboardService]:
    """Собирает use case с тестовыми зависимостями."""
    actual_recorder = recorder or FakeRecorder()
    actual_transcriber = transcriber or FakeTranscriber()
    actual_clipboard = clipboard or FakeClipboardService()
    actual_stop_calls = stop_calls if stop_calls is not None else []
    actual_published_titles = published_titles if published_titles is not None else []

    use_cases = LlmPipelineUseCases(
        runtime=runtime,
        recorder=actual_recorder,
        transcriber=actual_transcriber,
        llm_processor=llm_processor,
        clipboard_service=actual_clipboard,
        system_integration_service=runtime.system_integration_service,
        recording_overlay=runtime.recording_overlay,
        stop_recording=lambda: actual_stop_calls.append(True),
        publish_snapshot=lambda: actual_published_titles.append(runtime.llm_download_title or runtime.state),
    )
    return use_cases, actual_recorder, actual_transcriber, actual_clipboard


def test_toggle_llm_stops_active_recording() -> None:
    """Если запись уже идёт, toggle_llm должен делегировать остановку."""
    notifications: list[tuple[str, str]] = []
    overlay = FakeOverlay()
    runtime = make_runtime(overlay=overlay, notifications=notifications)
    runtime.started = True
    stop_calls: list[bool] = []

    use_cases, recorder, _, _ = make_use_cases(runtime=runtime, stop_calls=stop_calls)

    use_cases.toggle_llm()

    assert stop_calls == [True]
    assert recorder.started is False
    assert notifications == []


def test_toggle_llm_notifies_when_processor_missing() -> None:
    """Без LLM gateway сценарий должен завершиться понятным уведомлением."""
    notifications: list[tuple[str, str]] = []
    overlay = FakeOverlay()
    runtime = make_runtime(overlay=overlay, notifications=notifications)

    use_cases, recorder, _, _ = make_use_cases(runtime=runtime, llm_processor=None)

    use_cases.toggle_llm()

    assert recorder.started is False
    assert notifications == [("MLX Whisper Dictation", "LLM-процессор не инициализирован.")]


def test_toggle_llm_downloads_model_when_cache_is_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    """Если LLM-модель не скачана, toggle_llm должен запустить её загрузку."""
    notifications: list[tuple[str, str]] = []
    overlay = FakeOverlay()
    runtime = make_runtime(overlay=overlay, notifications=notifications)
    llm_processor = FakeLlmProcessor(cached=False)
    download_calls: list[bool] = []

    use_cases, recorder, _, _ = make_use_cases(runtime=runtime, llm_processor=llm_processor)
    monkeypatch.setattr(use_cases, "download_llm_model", lambda: download_calls.append(True))

    use_cases.toggle_llm()

    assert recorder.started is False
    assert download_calls == [True]
    assert notifications == [("MLX Whisper Dictation", "LLM-модель ещё не скачана. Запускаю загрузку…")]


def test_toggle_llm_processes_result_and_uses_clipboard_context() -> None:
    """Успешный сценарий должен взять контекст из буфера и сохранить итоговый ответ."""
    notifications: list[tuple[str, str]] = []
    published: list[str] = []
    overlay = FakeOverlay()
    runtime = make_runtime(overlay=overlay, notifications=notifications)
    recorder = FakeRecorder()
    transcriber = FakeTranscriber("переведи это")
    llm_processor = FakeLlmProcessor(response="Hello, world!", token_usage=17)
    clipboard = FakeClipboardService("Hello world")
    statuses: list[str] = []

    use_cases, recorder, transcriber, clipboard = make_use_cases(
        runtime=runtime,
        recorder=recorder,
        transcriber=transcriber,
        llm_processor=llm_processor,
        clipboard=clipboard,
        published_titles=published,
    )

    use_cases.toggle_llm()

    assert recorder.started is True
    assert recorder.last_language == "ru"
    assert overlay.show_calls == 1
    assert runtime.started is True
    assert runtime.state == Config.STATUS_RECORDING
    assert published

    assert recorder.on_audio_ready is not None
    recorder.on_audio_ready(object(), "ru", statuses.append, lambda: True)

    assert statuses == [Config.STATUS_LLM_PROCESSING]
    assert llm_processor.process_calls
    assert llm_processor.process_calls[0][0] == "переведи это"
    assert llm_processor.process_calls[0][2] == "Hello world"
    assert transcriber.history == ["Hello, world!"]
    assert transcriber.token_usage == [17]
    assert clipboard.writes == ["Hello, world!"]
    assert ("MLX Whisper Dictation", "Запись для LLM. Говорите.") in notifications
    assert ("MLX Whisper Dictation", "LLM-ответ скопирован в буфер обмена.") in notifications


def test_toggle_llm_aborts_when_prepare_recording_fails() -> None:
    """LLM-сценарий не должен стартовать, если preflight микрофона завершился неуспешно."""
    notifications: list[tuple[str, str]] = []
    overlay = FakeOverlay()
    runtime = make_runtime(overlay=overlay, notifications=notifications)
    runtime.prepare_recording = lambda: False

    use_cases, recorder, _, _ = make_use_cases(runtime=runtime, llm_processor=FakeLlmProcessor())

    use_cases.toggle_llm()

    assert recorder.started is False
    assert runtime.started is False
    assert runtime.state == Config.STATUS_IDLE
    assert overlay.show_calls == 0
    assert notifications == []


def test_toggle_llm_falls_back_to_clipboard_on_processing_error() -> None:
    """При ошибке LLM должен сохраняться исходный Whisper-текст."""
    notifications: list[tuple[str, str]] = []
    overlay = FakeOverlay()
    runtime = make_runtime(overlay=overlay, notifications=notifications)
    recorder = FakeRecorder()
    transcriber = FakeTranscriber("исходный текст")
    llm_processor = FakeLlmProcessor(process_error=RuntimeError("boom"))
    clipboard = FakeClipboardService("контекст")

    use_cases, recorder, transcriber, clipboard = make_use_cases(
        runtime=runtime,
        recorder=recorder,
        transcriber=transcriber,
        llm_processor=llm_processor,
        clipboard=clipboard,
    )

    use_cases.toggle_llm()
    assert recorder.on_audio_ready is not None
    recorder.on_audio_ready(object(), "ru", lambda _status: None, lambda: True)

    assert clipboard.writes == ["исходный текст"]
    assert transcriber.history == ["исходный текст"]
    assert transcriber.token_usage == []
    assert ("MLX Whisper Dictation", "Ошибка LLM. Текст сохранён в буфер обмена.") in notifications


def test_download_llm_model_updates_progress_and_finishes(monkeypatch: pytest.MonkeyPatch) -> None:
    """Загрузка модели должна публиковать прогресс и сбрасывать runtime-флаг."""
    notifications: list[tuple[str, str]] = []
    published: list[str] = []
    overlay = FakeOverlay()
    runtime = make_runtime(overlay=overlay, notifications=notifications)
    llm_processor = FakeLlmProcessor()

    class ImmediateThread:
        """Поток, немедленно выполняющий target в тесте."""

        def __init__(self, *, target: Any, daemon: bool) -> None:
            self._target = target
            self.daemon = daemon

        def start(self) -> None:
            self._target()

    monkeypatch.setattr(llm_pipeline_module.threading, "Thread", ImmediateThread)
    use_cases, _, _, _ = make_use_cases(
        runtime=runtime,
        llm_processor=llm_processor,
        published_titles=published,
    )

    use_cases.download_llm_model()

    assert runtime.llm_downloading is False
    assert runtime.llm_download_title == "✅ LLM-модель загружена"
    assert any("25%" in title for title in published)
    assert published[-1] == "✅ LLM-модель загружена"
    assert llm_processor.download_progress_callback is None
    assert ("MLX Whisper Dictation", "LLM-модель успешно загружена.") in notifications


def test_download_llm_model_reports_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    """Ошибка загрузки должна сбрасывать состояние и показывать уведомление."""
    notifications: list[tuple[str, str]] = []
    overlay = FakeOverlay()
    runtime = make_runtime(overlay=overlay, notifications=notifications)
    llm_processor = FakeLlmProcessor(download_error=RuntimeError("network"))

    class ImmediateThread:
        """Поток, немедленно выполняющий target в тесте."""

        def __init__(self, *, target: Any, daemon: bool) -> None:
            self._target = target
            self.daemon = daemon

        def start(self) -> None:
            self._target()

    monkeypatch.setattr(llm_pipeline_module.threading, "Thread", ImmediateThread)
    use_cases, _, _, _ = make_use_cases(runtime=runtime, llm_processor=llm_processor)

    use_cases.download_llm_model()

    assert runtime.llm_downloading is False
    assert runtime.llm_download_title == "❌ Ошибка загрузки LLM"
    assert llm_processor.download_progress_callback is None
    assert ("MLX Whisper Dictation", "Не удалось скачать LLM-модель. Попробуйте снова.") in notifications
