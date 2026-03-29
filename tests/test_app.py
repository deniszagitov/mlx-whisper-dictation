"""Тесты orchestration-слоя DictationApp без menu bar UI."""

from __future__ import annotations

from typing import Any, cast

import src.app as app_module
from src.domain.constants import Config
from src.domain.types import LaunchConfig


class FakeRecorder:
    """Фейковый recorder для тестов DictationApp."""

    def __init__(self) -> None:
        self.started = False
        self.stopped = False
        self.cancelled = False
        self.last_language = None
        self.last_on_audio_ready = None
        self.input_device = None
        self.performance_mode = None

    def set_status_callback(self, callback) -> None:
        """Сохраняет callback обновления статуса."""
        self.status_callback = callback

    def set_permission_callback(self, callback) -> None:
        """Сохраняет callback обновления разрешений."""
        self.permission_callback = callback

    def set_input_device(self, device_info) -> None:
        """Запоминает выбранное устройство ввода."""
        self.input_device = device_info

    def set_performance_mode(self, performance_mode) -> None:
        """Запоминает выбранный режим производительности."""
        self.performance_mode = performance_mode

    def start(self, language=None, on_audio_ready=None) -> None:
        """Имитирует старт записи."""
        self.started = True
        self.last_language = language
        self.last_on_audio_ready = on_audio_ready

    def stop(self) -> None:
        """Имитирует остановку записи."""
        self.stopped = True

    def cancel(self) -> None:
        """Имитирует отмену записи."""
        self.cancelled = True


class FakeTranscriber:
    """Фейковый transcriber для тестов DictationApp."""

    def __init__(self) -> None:
        self.model_name = "mlx-community/whisper-large-v3-turbo"
        self.paste_cgevent_enabled = True
        self.paste_ax_enabled = False
        self.paste_clipboard_enabled = False
        self.llm_clipboard_enabled = True
        self.private_mode_enabled = False
        self.history: list[str] = []
        self.total_tokens = 0
        self.history_callback = None
        self.token_usage_callback = None

    def set_private_mode(self, enabled) -> None:
        """Переключает private mode."""
        self.private_mode_enabled = bool(enabled)

    def prune_expired_history(self) -> None:
        """Заглушка для очистки истории."""
        return None

    def transcribe(self, audio_data, language=None) -> None:
        """Заглушка для обычной транскрибации."""
        return None

    def transcribe_to_text(self, audio_data, language=None) -> str:
        """Возвращает тестовую транскрибацию."""
        return "текст"

    def add_to_history(self, text: str) -> None:
        """Добавляет запись в историю."""
        self.history.insert(0, text)

    def add_token_usage(self, token_count: int) -> None:
        """Добавляет токены в тестовый счётчик."""
        self.total_tokens += token_count


class FakeLLMProcessor:
    """Фейковый LLM-процессор для тестов DictationApp."""

    def __init__(self) -> None:
        self.performance_mode = None
        self.last_token_usage = 0
        self.download_progress_callback = None

    def is_model_cached(self) -> bool:
        """Сообщает, что модель уже доступна локально."""
        return True

    def set_performance_mode(self, mode) -> None:
        """Запоминает выбранный режим производительности."""
        self.performance_mode = mode

    def process_text(self, text: str, system_prompt: str, *, context: str | None = None) -> str:
        """Возвращает входной текст без изменений."""
        return text

    def ensure_model_downloaded(self) -> None:
        """Заглушка для загрузки модели."""
        return None


class FakeSettingsStore:
    """Фейковое хранилище настроек для тестов DictationApp."""

    def contains_key(self, _key) -> bool:
        """Сообщает, что сохранённых значений нет."""
        return False

    def load_str(self, _key, fallback=None):
        """Возвращает fallback-значение для строковых настроек."""
        return fallback

    def load_int(self, _key, fallback=0):
        """Возвращает fallback-значение для целочисленных настроек."""
        return fallback

    def load_bool(self, _key, fallback):
        """Возвращает fallback-значение для bool-настроек."""
        return fallback

    def load_input_device_index(self):
        """Не выбирает сохранённый микрофон."""
        return None

    def save_str(self, _key, _value) -> None:
        """Игнорирует сохранение строковых настроек."""
        return None

    def save_bool(self, _key, _value) -> None:
        """Игнорирует сохранение bool-настроек."""
        return None

    def save_max_time(self, _value) -> None:
        """Игнорирует сохранение лимита записи."""
        return None

    def save_input_device_index(self, _value) -> None:
        """Игнорирует сохранение индекса микрофона."""
        return None

    def remove_key(self, _key) -> None:
        """Игнорирует удаление ключа."""
        return None


def make_system_integration_service(*, notifications=None):
    """Создаёт concrete bundle системных уведомлений и permission-status для тестов."""
    sink = notifications if notifications is not None else []

    def notify(title: str, message: str) -> None:
        sink.append((title, message))

    return app_module.SystemIntegrationService(
        notify=notify,
        get_accessibility_status=lambda: True,
        get_input_monitoring_status=lambda: True,
        request_accessibility_permission=lambda: True,
        request_input_monitoring_permission=lambda: True,
        warn_missing_accessibility_permission=lambda: None,
        warn_missing_input_monitoring_permission=lambda: None,
    )


def make_input_device_catalog(*, devices=None):
    """Создаёт concrete bundle списка устройств ввода для тестов."""
    input_devices = list(
        devices
        or [
            {
                "index": 0,
                "name": "Built-in Microphone",
                "max_input_channels": 1,
                "default_sample_rate": 48000.0,
                "is_default": True,
            },
        ],
    )
    return app_module.InputDeviceCatalogService(list_input_devices=lambda: list(input_devices))


def make_controller(monkeypatch):
    """Создаёт DictationApp с замоканными внешними зависимостями."""
    recorder = FakeRecorder()
    transcriber = FakeTranscriber()
    llm_processor = FakeLLMProcessor()
    settings_store = FakeSettingsStore()
    input_device_catalog = make_input_device_catalog()
    clipboard_service = app_module.ClipboardService(
        read_text=lambda: None,
        write_text=lambda _text: None,
    )
    microphone_profiles_service = app_module.MicrophoneProfilesService(
        load_profiles=lambda: [],
        save_profiles=lambda _profiles: None,
    )
    system_integration_service = make_system_integration_service()
    launch_config = LaunchConfig.from_sources(
        model="mlx-community/whisper-large-v3-turbo",
        language=["ru"],
        max_time=30,
        llm_model=Config.DEFAULT_LLM_MODEL_NAME,
        key_combination="cmd_l+alt",
        secondary_key_combination=None,
        llm_key_combination=None,
        k_double_cmd=False,
    )
    controller = app_module.DictationApp(
        recorder=cast("Any", recorder),
        transcriber=cast("Any", transcriber),
        llm_processor=cast("Any", llm_processor),
        launch_config=launch_config,
        clipboard_service=clipboard_service,
        microphone_profiles_service=microphone_profiles_service,
        system_integration_service=system_integration_service,
        input_device_catalog=input_device_catalog,
        settings_store=cast("Any", settings_store),
    )
    return controller, recorder, transcriber


def test_snapshot_reflects_initial_runtime_state(monkeypatch):
    """Snapshot должен отражать исходные runtime-настройки приложения."""
    controller, recorder, _transcriber = make_controller(monkeypatch)

    snapshot = controller.snapshot()

    assert snapshot.state == Config.STATUS_IDLE
    assert snapshot.started is False
    assert snapshot.model_name == "whisper-large-v3-turbo"
    assert snapshot.current_language == "ru"
    assert snapshot.current_input_device["index"] == 0
    assert recorder.input_device["index"] == 0


def test_subscribe_receives_state_transitions(monkeypatch):
    """Подписчик должен получать новые snapshot при смене состояния."""
    controller, recorder, _transcriber = make_controller(monkeypatch)
    states: list[str] = []

    controller.subscribe(lambda snapshot: states.append(snapshot.state))
    controller.start_recording()
    controller.stop_recording()

    assert states == [
        Config.STATUS_IDLE,
        Config.STATUS_RECORDING,
        Config.STATUS_TRANSCRIBING,
    ]
    assert recorder.started is True
    assert recorder.stopped is True


def test_change_secondary_hotkey_updates_listener_and_snapshot(monkeypatch):
    """Изменение второго хоткея должно менять snapshot и runtime-listener."""
    controller, _recorder, _transcriber = make_controller(monkeypatch)
    listener_calls = []

    class ListenerStub:
        def update_key_combinations(self, combinations):
            listener_calls.append(combinations)

    controller.hotkey_management_use_cases.capture_hotkey_combination = lambda *args, **kwargs: "ctrl+shift+space"
    controller.key_listener = ListenerStub()

    controller.change_secondary_hotkey()

    assert controller.snapshot().secondary_key_combination == "ctrl+shift+space"
    assert listener_calls == [["cmd_l+alt", "ctrl+shift+space"]]


def test_copy_history_text_uses_injected_clipboard_service(monkeypatch):
    """Копирование записи истории должно идти через clipboard bundle приложения."""
    written_texts: list[str] = []
    settings_store = FakeSettingsStore()
    launch_config = LaunchConfig.from_sources(
        model="mlx-community/whisper-large-v3-turbo",
        language=["ru"],
        max_time=30,
        llm_model=Config.DEFAULT_LLM_MODEL_NAME,
        key_combination="cmd_l+alt",
        secondary_key_combination=None,
        llm_key_combination=None,
        k_double_cmd=False,
    )
    controller = app_module.DictationApp(
        recorder=cast("Any", FakeRecorder()),
        transcriber=cast("Any", FakeTranscriber()),
        llm_processor=cast("Any", FakeLLMProcessor()),
        launch_config=launch_config,
        clipboard_service=app_module.ClipboardService(
            read_text=lambda: None,
            write_text=written_texts.append,
        ),
        microphone_profiles_service=app_module.MicrophoneProfilesService(
            load_profiles=lambda: [],
            save_profiles=lambda _profiles: None,
        ),
        system_integration_service=make_system_integration_service(),
        input_device_catalog=make_input_device_catalog(),
        settings_store=cast("Any", settings_store),
    )

    controller.copy_history_text("готовый текст")

    assert written_texts == ["готовый текст"]
