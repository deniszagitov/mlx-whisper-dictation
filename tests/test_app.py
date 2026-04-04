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
        self.runtime_error_callback = None

    def set_status_callback(self, callback) -> None:
        """Сохраняет callback обновления статуса."""
        self.status_callback = callback

    def set_permission_callback(self, callback) -> None:
        """Сохраняет callback обновления разрешений."""
        self.permission_callback = callback

    def set_input_device(self, device_info) -> None:
        """Запоминает выбранное устройство ввода."""
        self.input_device = device_info

    def set_runtime_error_callback(self, callback) -> None:
        """Сохраняет callback сброса runtime после ошибки записи."""
        self.runtime_error_callback = callback

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
        self.capitalize_first_letter_enabled = True
        self.remove_trailing_period_for_single_sentence_enabled = True
        self.restore_trailing_period_on_next_dictation_enabled = False
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

    def load_input_device_name(self):
        """Не выбирает сохранённый микрофон по имени."""
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

    def save_input_device_name(self, _value) -> None:
        """Игнорирует сохранение имени микрофона."""
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


def test_refresh_input_devices_rebinds_selected_microphone_by_name(monkeypatch):
    """После переиндексации устройств приложение должно вернуть выбранный микрофон по имени."""
    recorder = FakeRecorder()
    settings_store = FakeSettingsStore()

    def contains_key(key):
        return key == Config.DEFAULTS_KEY_INPUT_DEVICE_INDEX

    def load_int(key, fallback=0):
        return 7 if key == Config.DEFAULTS_KEY_INPUT_DEVICE_INDEX else fallback

    def load_str(key, fallback=None):
        return "Studio Mic" if key == Config.DEFAULTS_KEY_INPUT_DEVICE_NAME else fallback

    settings_store.contains_key = contains_key  # type: ignore[assignment]
    settings_store.load_int = load_int  # type: ignore[assignment]
    settings_store.load_str = load_str  # type: ignore[assignment]
    catalogs = [
        [
            {"index": 7, "name": "Studio Mic", "max_input_channels": 1, "default_sample_rate": 48000.0, "is_default": False},
            {"index": 0, "name": "Built-in Microphone", "max_input_channels": 1, "default_sample_rate": 48000.0, "is_default": True},
        ],
        [
            {"index": 13, "name": "Studio Mic", "max_input_channels": 1, "default_sample_rate": 48000.0, "is_default": False},
            {"index": 0, "name": "Built-in Microphone", "max_input_channels": 1, "default_sample_rate": 48000.0, "is_default": True},
        ],
    ]

    def list_input_devices():
        current = catalogs.pop(0)
        return list(current)

    controller = app_module.DictationApp(
        recorder=cast("Any", recorder),
        transcriber=cast("Any", FakeTranscriber()),
        llm_processor=cast("Any", FakeLLMProcessor()),
        launch_config=LaunchConfig.from_sources(
            model="mlx-community/whisper-large-v3-turbo",
            language=["ru"],
            max_time=30,
            llm_model=Config.DEFAULT_LLM_MODEL_NAME,
            key_combination="cmd_l+alt",
            secondary_key_combination=None,
            llm_key_combination=None,
        ),
        clipboard_service=app_module.ClipboardService(read_text=lambda: None, write_text=lambda _text: None),
        microphone_profiles_service=app_module.MicrophoneProfilesService(load_profiles=lambda: [], save_profiles=lambda _profiles: None),
        system_integration_service=make_system_integration_service(),
        input_device_catalog=app_module.InputDeviceCatalogService(list_input_devices=list_input_devices),
        settings_store=cast("Any", settings_store),
    )

    assert controller.current_input_device is not None
    assert controller.current_input_device["index"] == 7

    controller.refresh_input_devices()

    assert controller.current_input_device is not None
    assert controller.current_input_device["index"] == 13
    assert recorder.input_device is not None
    assert recorder.input_device["index"] == 13
    assert controller.app_preferences.selected_input_device_index == 13
    assert controller.app_preferences.selected_input_device_name == "Studio Mic"


def test_prepare_recording_falls_back_to_default_device(monkeypatch):
    """Перед записью приложение должно уйти на default device, если выбранный микрофон пропал."""
    notifications: list[tuple[str, str]] = []
    recorder = FakeRecorder()
    settings_store = FakeSettingsStore()

    def contains_key(key):
        return key == Config.DEFAULTS_KEY_INPUT_DEVICE_INDEX

    def load_int(key, fallback=0):
        return 7 if key == Config.DEFAULTS_KEY_INPUT_DEVICE_INDEX else fallback

    def load_str(key, fallback=None):
        return "USB Mic" if key == Config.DEFAULTS_KEY_INPUT_DEVICE_NAME else fallback

    settings_store.contains_key = contains_key  # type: ignore[assignment]
    settings_store.load_int = load_int  # type: ignore[assignment]
    settings_store.load_str = load_str  # type: ignore[assignment]
    controller = app_module.DictationApp(
        recorder=cast("Any", recorder),
        transcriber=cast("Any", FakeTranscriber()),
        llm_processor=cast("Any", FakeLLMProcessor()),
        launch_config=LaunchConfig.from_sources(
            model="mlx-community/whisper-large-v3-turbo",
            language=["ru"],
            max_time=30,
            llm_model=Config.DEFAULT_LLM_MODEL_NAME,
            key_combination="cmd_l+alt",
            secondary_key_combination=None,
            llm_key_combination=None,
        ),
        clipboard_service=app_module.ClipboardService(read_text=lambda: None, write_text=lambda _text: None),
        microphone_profiles_service=app_module.MicrophoneProfilesService(load_profiles=lambda: [], save_profiles=lambda _profiles: None),
        system_integration_service=make_system_integration_service(notifications=notifications),
        input_device_catalog=make_input_device_catalog(
            devices=[
                {"index": 0, "name": "Built-in Microphone", "max_input_channels": 1, "default_sample_rate": 48000.0, "is_default": True},
            ]
        ),
        settings_store=cast("Any", settings_store),
    )

    assert controller.prepare_recording() is True
    assert controller.current_input_device is not None
    assert controller.current_input_device["index"] == 0
    assert recorder.input_device is not None
    assert recorder.input_device["index"] == 0
    assert notifications == [
        ("MLX Whisper Dictation", "Выбранный микрофон временно недоступен. Переключаюсь на: Built-in Microphone")
    ]


def test_handle_recording_runtime_error_resets_runtime_state(monkeypatch):
    """Runtime-ошибка записи должна возвращать приложение в idle и обновлять каталог микрофонов."""
    controller, recorder, _transcriber = make_controller(monkeypatch)
    controller.started = True
    controller.state = Config.STATUS_RECORDING
    hidden_calls: list[bool] = []
    controller.recording_overlay = cast("Any", type("OverlayStub", (), {"hide": lambda self: hidden_calls.append(True)})())

    controller.handle_recording_runtime_error("MLX Whisper Dictation", "boom")

    assert controller.started is False
    assert controller.state == Config.STATUS_IDLE
    assert hidden_calls == [True]
    assert recorder.input_device["index"] == 0


def test_handle_system_wake_cancels_recording_and_recovers_listener(monkeypatch):
    """После wake приложение должно отменить запись, обновить аудио и восстановить listener."""
    notifications: list[tuple[str, str]] = []
    controller, recorder, _transcriber = make_controller(monkeypatch)
    controller.system_integration_service = make_system_integration_service(notifications=notifications)
    controller.started = True
    controller.state = Config.STATUS_RECORDING
    hide_calls: list[bool] = []
    controller.recording_overlay = cast("Any", type("OverlayStub", (), {"hide": lambda self: hide_calls.append(True)})())
    wake_calls: list[bool] = []

    class ListenerStub:
        def on_system_wake(self):
            wake_calls.append(True)

    controller.key_listener = ListenerStub()

    controller.handle_system_wake()

    assert recorder.cancelled is True
    assert controller.started is False
    assert controller.state == Config.STATUS_IDLE
    assert hide_calls == [True]
    assert wake_calls == [True]
    assert controller.current_input_device["index"] == 0
    assert notifications == []


def test_snapshot_reflects_initial_runtime_state(monkeypatch):
    """Snapshot должен отражать исходные runtime-настройки приложения."""
    controller, recorder, _transcriber = make_controller(monkeypatch)

    snapshot = controller.snapshot()

    assert snapshot.state == Config.STATUS_IDLE
    assert snapshot.started is False
    assert snapshot.model_name == "whisper-large-v3-turbo"
    assert snapshot.current_language == "ru"
    assert snapshot.show_recording_time_in_menu_bar is True
    assert snapshot.capitalize_first_letter_enabled is True
    assert snapshot.remove_trailing_period_for_single_sentence_enabled is True
    assert snapshot.restore_trailing_period_on_next_dictation_enabled is False
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
        def update_hotkeys(self, primary, secondary, llm):
            listener_calls.append((primary, secondary, llm))

    controller.hotkey_management_use_cases.capture_hotkey_combination = lambda *args, **kwargs: "ctrl+shift+space"
    controller.key_listener = ListenerStub()

    controller.change_secondary_hotkey()

    assert controller.snapshot().secondary_key_combination == "ctrl+shift+space"
    assert listener_calls == [("cmd_l+alt", "ctrl+shift+space", "")]


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
