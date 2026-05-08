"""Тесты orchestration-слоя DictationApp без menu bar UI."""

from __future__ import annotations

from typing import Any, cast

import src.app as app_module
from src.domain.constants import Config
from src.domain.model_downloads import ModelDownloadProgress, ModelRequiredError
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
        self.high_quality_mac_builtin_enabled: bool | None = None
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

    def set_high_quality_mac_builtin(self, enabled) -> None:
        """Запоминает флаг MacBook HQ-профиля."""
        self.high_quality_mac_builtin_enabled = bool(enabled)

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
        self.gain_normalization_enabled = True
        self.audio_artifact_cleanup_enabled = False
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
        self.model_memory_loading_callback = None
        self.model_name = Config.DEFAULT_LLM_MODEL_NAME

    def is_model_cached(self) -> bool:
        """Сообщает, что модель уже доступна локально."""
        return True

    def set_performance_mode(self, mode) -> None:
        """Запоминает выбранный режим производительности."""
        self.performance_mode = mode

    def process_text(
        self,
        text: str,
        system_prompt: str,
        *,
        context: str | None = None,
        max_tokens: int | None = None,
        keep_loaded: bool = False,
    ) -> str:
        """Возвращает входной текст без изменений."""
        del keep_loaded
        return text

    def change_model(self, model_name: str) -> None:
        """Запоминает выбранную модель."""
        self.model_name = model_name

    def ensure_model_downloaded(self) -> None:
        """Заглушка для загрузки модели."""
        return None

    def set_model_memory_loading_callback(self, callback) -> None:
        """Запоминает callback статуса загрузки модели в память."""
        self.model_memory_loading_callback = callback


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


def make_system_integration_service(
    *,
    notifications=None,
    open_paths=None,
    open_path_result: bool = True,
):
    """Создаёт concrete bundle системных уведомлений и permission-status для тестов."""
    sink = notifications if notifications is not None else []
    path_sink = open_paths if open_paths is not None else []

    def notify(title: str, message: str) -> None:
        sink.append((title, message))

    def open_path(path: str) -> bool:
        path_sink.append(path)
        return open_path_result

    return app_module.SystemIntegrationService(
        notify=notify,
        get_accessibility_status=lambda: True,
        get_input_monitoring_status=lambda: True,
        request_accessibility_permission=lambda: True,
        request_input_monitoring_permission=lambda: True,
        warn_missing_accessibility_permission=lambda: None,
        warn_missing_input_monitoring_permission=lambda: None,
        open_path=open_path,
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


def install_display_sleep_prevention(controller):
    """Подключает к контроллеру фейковый display sleep assertion и возвращает журнал событий."""
    events: list[str] = []

    def acquire() -> bool:
        events.append("acquire")
        return True

    def release() -> None:
        events.append("release")

    controller.display_sleep_prevention_service = app_module.DisplaySleepPreventionService(
        acquire=acquire,
        release=release,
    )
    return events


def install_system_diagnostics(controller):
    """Подключает к контроллеру фейковый сбор системной диагностики."""
    events: list[str] = []
    controller.system_diagnostics_service = app_module.SystemDiagnosticsService(capture=events.append)
    return events


def make_controller(monkeypatch, *, system_integration_service=None):
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
    system_integration_service = system_integration_service or make_system_integration_service()
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
    controller.display_sleep_release_delay_seconds = 0
    return controller, recorder, transcriber


def test_zipper_uses_separate_llm_runtime_for_agent_memory_policy(monkeypatch):
    """Zipper должен иметь отдельный LLM runtime и не наследовать общий режим выгрузки."""
    del monkeypatch
    recorder = FakeRecorder()
    transcriber = FakeTranscriber()
    llm_processor = FakeLLMProcessor()
    zipper_llm_processor = FakeLLMProcessor()
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
        recorder=cast("Any", recorder),
        transcriber=cast("Any", transcriber),
        llm_processor=cast("Any", llm_processor),
        launch_config=launch_config,
        zipper_llm_processor=cast("Any", zipper_llm_processor),
        clipboard_service=app_module.ClipboardService(read_text=lambda: None, write_text=lambda _text: None),
        microphone_profiles_service=app_module.MicrophoneProfilesService(load_profiles=lambda: [], save_profiles=lambda _profiles: None),
        system_integration_service=make_system_integration_service(),
        input_device_catalog=make_input_device_catalog(),
        settings_store=cast("Any", settings_store),
    )

    assert controller.zipper_use_cases.llm_processor is zipper_llm_processor
    assert llm_processor.performance_mode == Config.PERFORMANCE_MODE_NORMAL
    assert zipper_llm_processor.performance_mode is None
    assert llm_processor.model_memory_loading_callback is not None
    assert zipper_llm_processor.model_memory_loading_callback is not None

    controller.change_performance_mode(Config.PERFORMANCE_MODE_FAST)

    assert llm_processor.performance_mode == Config.PERFORMANCE_MODE_FAST
    assert zipper_llm_processor.performance_mode is None

    next_model = next(model for model in Config.LLM_MODEL_PRESETS if model != Config.DEFAULT_LLM_MODEL_NAME)
    controller.change_llm_model(next_model)

    assert llm_processor.model_name == next_model
    assert zipper_llm_processor.model_name == next_model


def test_reader_tts_rate_default_migration_resets_previous_speed_once():
    """Старый сохранённый множитель TTS один раз сбрасывается на новый дефолт 1×."""
    values: dict[str, object] = {
        Config.DEFAULTS_KEY_READER_TTS_RATE_MULTIPLIER: "1.5",
    }
    settings_store = FakeSettingsStore()

    def contains_key(key):
        return key in values

    def load_str(key, fallback=None):
        return values.get(key, fallback)

    def save_str(key, value):
        values[key] = str(value)

    def save_bool(key, value):
        values[key] = bool(value)

    settings_store.contains_key = contains_key  # type: ignore[assignment]
    settings_store.load_str = load_str  # type: ignore[assignment]
    settings_store.save_str = save_str  # type: ignore[assignment]
    settings_store.save_bool = save_bool  # type: ignore[assignment]

    def create_controller():
        return app_module.DictationApp(
            recorder=cast("Any", FakeRecorder()),
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
            microphone_profiles_service=app_module.MicrophoneProfilesService(
                load_profiles=lambda: [],
                save_profiles=lambda _profiles: None,
            ),
            system_integration_service=make_system_integration_service(),
            input_device_catalog=app_module.InputDeviceCatalogService(list_input_devices=lambda: []),
            settings_store=cast("Any", settings_store),
        )

    controller = create_controller()

    assert controller.reader_tts_rate_multiplier == 1.0
    assert values[Config.DEFAULTS_KEY_READER_TTS_RATE_MULTIPLIER] == "1.0"
    assert values[Config.DEFAULTS_KEY_READER_TTS_RATE_DEFAULT_V2] is True

    values[Config.DEFAULTS_KEY_READER_TTS_RATE_MULTIPLIER] = "1.4"
    controller = create_controller()

    assert controller.reader_tts_rate_multiplier == 1.4


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
    assert notifications == [("MLX Whisper Dictation", "Выбранный микрофон временно недоступен. Переключаюсь на: Built-in Microphone")]


def test_handle_recording_runtime_error_resets_runtime_state(monkeypatch):
    """Runtime-ошибка записи должна возвращать приложение в idle и обновлять каталог микрофонов."""
    controller, recorder, _transcriber = make_controller(monkeypatch)
    display_events = install_display_sleep_prevention(controller)
    controller.started = True
    controller.state = Config.STATUS_RECORDING
    controller.prevent_display_sleep_for_active_session()
    hidden_calls: list[bool] = []
    controller.recording_overlay = cast("Any", type("OverlayStub", (), {"hide": lambda self: hidden_calls.append(True)})())

    controller.handle_recording_runtime_error("MLX Whisper Dictation", "boom")

    assert controller.started is False
    assert controller.state == Config.STATUS_IDLE
    assert hidden_calls == [True]
    assert display_events == ["acquire", "release"]
    assert recorder.input_device["index"] == 0


def test_handle_system_wake_cancels_recording_and_recovers_listener(monkeypatch):
    """После wake приложение должно отменить запись, обновить аудио и восстановить listener."""
    notifications: list[tuple[str, str]] = []
    controller, recorder, _transcriber = make_controller(monkeypatch)
    display_events = install_display_sleep_prevention(controller)
    controller.system_integration_service = make_system_integration_service(notifications=notifications)
    controller.started = True
    controller.state = Config.STATUS_RECORDING
    controller.prevent_display_sleep_for_active_session()
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
    assert display_events == ["acquire", "release"]
    assert controller.current_input_device["index"] == 0
    assert notifications == []


def test_system_wake_during_grace_keeps_display_sleep_prevention(monkeypatch):
    """Wake во время post-dictation grace-паузы не должен сам отпускать assertion."""
    controller, recorder, _transcriber = make_controller(monkeypatch)
    controller.display_sleep_release_delay_seconds = 120
    display_events = install_display_sleep_prevention(controller)
    diagnostics_events = install_system_diagnostics(controller)

    class FakeTimer:
        def __init__(self, _delay, _callback):
            self.daemon = False
            self.cancelled = False

        def start(self):
            return None

        def cancel(self):
            self.cancelled = True

        def is_alive(self):
            return not self.cancelled

    monkeypatch.setattr(app_module.threading, "Timer", FakeTimer)

    controller.start_recording()
    controller.stop_recording()
    controller.set_state(Config.STATUS_IDLE)
    controller.handle_system_wake()

    assert recorder.cancelled is False
    assert display_events == ["acquire"]
    assert diagnostics_events == ["system_wake"]


def test_system_power_event_logs_diagnostics_without_wake(monkeypatch):
    """Не-wake системные события должны писать расширенную диагностику."""
    controller, _recorder, _transcriber = make_controller(monkeypatch)
    diagnostics_events = install_system_diagnostics(controller)

    controller.handle_system_power_event("screens_did_sleep")

    assert diagnostics_events == ["system_event_screens_did_sleep"]


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
    assert snapshot.audio_artifact_cleanup_enabled is False
    assert snapshot.model_download_title == "📦 Загрузка моделей: нет"
    assert snapshot.model_download_active is False
    assert snapshot.current_input_device["index"] == 0
    assert recorder.input_device["index"] == 0


def test_model_download_progress_updates_snapshot(monkeypatch):
    """Прогресс загрузки моделей должен попадать в snapshot приложения."""
    controller, _recorder, _transcriber = make_controller(monkeypatch)
    titles: list[str] = []
    controller.subscribe(lambda snapshot: titles.append(snapshot.model_download_title))

    controller.handle_model_download_progress(
        ModelDownloadProgress(
            label="ASR-модель",
            model_name="mlx-community/whisper-turbo",
            stage="Downloading",
            downloaded_bytes=10 * 1024 * 1024,
            total_bytes=20 * 1024 * 1024,
            percent=50.0,
            speed_bytes_per_second=2 * 1024 * 1024,
            eta_seconds=5,
        )
    )

    snapshot = controller.snapshot()
    assert snapshot.model_download_active is True
    assert "50%" in snapshot.model_download_title
    assert "2 МБ/с" in snapshot.model_download_title
    assert "осталось 5 с" in snapshot.model_download_title
    assert titles[-1] == snapshot.model_download_title

    controller.handle_model_download_progress(
        ModelDownloadProgress(
            label="ASR-модель",
            model_name="mlx-community/whisper-turbo",
            stage="",
            percent=Config.DOWNLOAD_COMPLETE_PCT,
            complete=True,
        )
    )

    assert controller.snapshot().model_download_active is False


def test_model_memory_loading_updates_status_and_restores_previous_state(monkeypatch):
    """Загрузка MLX-модели в память должна быть видна в snapshot и не сбивать состояние Zipper."""
    controller, _recorder, _transcriber = make_controller(monkeypatch)
    controller.zipper_enabled = True
    controller.state = Config.STATUS_ZIPPER_PROCESSING
    states: list[str] = []
    titles: list[str] = []
    zipper_statuses: list[str] = []

    def collect_snapshot(snapshot) -> None:
        states.append(snapshot.state)
        titles.append(snapshot.model_download_title)
        zipper_statuses.append(snapshot.zipper_status)

    controller.subscribe(collect_snapshot)

    controller.handle_model_memory_loading(True, "mlx-community/gemma", "VLM-модель")

    assert controller.state == Config.STATUS_MODEL_LOADING
    assert states[-1] == Config.STATUS_MODEL_LOADING
    assert titles[-1] == "🧠 VLM-модель: загрузка в память (gemma)"
    assert zipper_statuses[-1] == "загрузка модели"

    controller.handle_model_memory_loading(False, "mlx-community/gemma", "VLM-модель")

    assert controller.state == Config.STATUS_ZIPPER_PROCESSING
    assert states[-1] == Config.STATUS_ZIPPER_PROCESSING
    assert titles[-1] == "📦 Загрузка моделей: нет"


def test_download_required_model_uses_common_download_service(monkeypatch):
    """Сигнал runtime-слоя должен запускать общий downloader приложения."""
    notifications: list[tuple[str, str]] = []
    controller, _recorder, _transcriber = make_controller(
        monkeypatch,
        system_integration_service=make_system_integration_service(notifications=notifications),
    )
    download_calls: list[tuple[str, str]] = []
    controller.model_download_service = app_module.ModelDownloadService(
        ensure_downloaded=lambda model_name, label: download_calls.append((label, model_name)),
    )

    class ImmediateThread:
        """Поток, немедленно выполняющий target в тесте."""

        def __init__(self, *, target: Any, daemon: bool) -> None:
            self._target = target
            self.daemon = daemon

        def start(self) -> None:
            self._target()

        def is_alive(self) -> bool:
            return False

    monkeypatch.setattr(app_module.threading, "Thread", ImmediateThread)

    controller.download_required_model(ModelRequiredError("mlx-community/gemma", label="VLM-модель"))

    assert download_calls == [("VLM-модель", "mlx-community/gemma")]
    assert controller.snapshot().model_download_active is False
    assert controller.snapshot().model_download_title == "✅ VLM-модель: загружена"
    assert (
        "MLX Whisper Dictation",
        "VLM-модель mlx-community/gemma не найдена локально. Загружаю из Hugging Face…",
    ) in notifications
    assert ("MLX Whisper Dictation", "VLM-модель загружена. Повторите действие.") in notifications


def test_reader_worker_downloads_required_model_from_tts(monkeypatch):
    """Reader должен отдавать загрузку MLX TTS-модели общему downloader-у."""
    notifications: list[tuple[str, str]] = []
    controller, _recorder, _transcriber = make_controller(
        monkeypatch,
        system_integration_service=make_system_integration_service(notifications=notifications),
    )
    download_calls: list[tuple[str, str]] = []
    controller.model_download_service = app_module.ModelDownloadService(
        ensure_downloaded=lambda model_name, label: download_calls.append((label, model_name)),
    )

    class ImmediateThread:
        """Поток, немедленно выполняющий target в тесте."""

        def __init__(self, *, target: Any, daemon: bool) -> None:
            self._target = target
            self.daemon = daemon

        def start(self) -> None:
            self._target()

        def is_alive(self) -> bool:
            return False

    monkeypatch.setattr(app_module.threading, "Thread", ImmediateThread)

    controller._start_reader_worker(
        "tts",
        lambda: (_ for _ in ()).throw(ModelRequiredError("mlx-community/Qwen3-TTS", label="TTS-модель")),
    )

    assert download_calls == [("TTS-модель", "mlx-community/Qwen3-TTS")]
    message = "TTS-модель ещё не готова. Запускаю загрузку; после завершения повторите reader-сценарий."
    assert ("MLX Whisper Dictation", message) in notifications


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


def test_open_recordings_directory_creates_folder_and_opens_it(monkeypatch, tmp_path):
    """Команда меню должна открыть папку диагностических WAV-записей."""
    open_paths: list[str] = []
    service = make_system_integration_service(open_paths=open_paths)
    monkeypatch.setattr(Config, "LOG_DIR", tmp_path)
    controller, _recorder, _transcriber = make_controller(monkeypatch, system_integration_service=service)

    controller.open_recordings_directory()

    expected_dir = tmp_path / "recordings"
    assert expected_dir.is_dir()
    assert open_paths == [str(expected_dir)]


def test_open_recordings_directory_notifies_when_finder_open_fails(monkeypatch, tmp_path):
    """Если Finder не открыл папку, пользователь должен получить уведомление."""
    notifications: list[tuple[str, str]] = []
    service = make_system_integration_service(notifications=notifications, open_path_result=False)
    monkeypatch.setattr(Config, "LOG_DIR", tmp_path)
    controller, _recorder, _transcriber = make_controller(monkeypatch, system_integration_service=service)

    controller.open_recordings_directory()

    assert notifications
    assert "Не удалось открыть папку WAV-записей" in notifications[0][1]


def test_recording_prevents_display_sleep_until_recorder_returns_idle(monkeypatch):
    """Дисплей должен удерживаться от сна до завершения обработки после stop_recording()."""
    controller, _recorder, _transcriber = make_controller(monkeypatch)
    display_events = install_display_sleep_prevention(controller)

    controller.start_recording()
    controller.stop_recording()

    assert display_events == ["acquire"]

    controller.set_state(Config.STATUS_IDLE)
    controller.set_state(Config.STATUS_IDLE)

    assert display_events == ["acquire", "release"]


def test_recording_keeps_display_awake_for_grace_period_after_idle(monkeypatch):
    """После успешной диктовки release должен откладываться на grace-паузу."""
    controller, _recorder, _transcriber = make_controller(monkeypatch)
    controller.display_sleep_release_delay_seconds = 120
    display_events = install_display_sleep_prevention(controller)
    timers = []

    class FakeTimer:
        def __init__(self, delay, callback):
            self.delay = delay
            self.callback = callback
            self.daemon = False
            self.started = False
            self.cancelled = False
            timers.append(self)

        def start(self):
            self.started = True

        def cancel(self):
            self.cancelled = True

        def is_alive(self):
            return self.started and not self.cancelled

    monkeypatch.setattr(app_module.threading, "Timer", FakeTimer)

    controller.start_recording()
    controller.stop_recording()
    controller.set_state(Config.STATUS_IDLE)

    assert display_events == ["acquire"]
    assert len(timers) == 1
    assert timers[0].delay == 120
    assert timers[0].started is True

    timers[0].callback()

    assert display_events == ["acquire", "release"]


def test_new_recording_cancels_pending_display_sleep_release(monkeypatch):
    """Новая запись должна отменять отложенное отпускание старого assertion."""
    controller, _recorder, _transcriber = make_controller(monkeypatch)
    controller.display_sleep_release_delay_seconds = 120
    display_events = install_display_sleep_prevention(controller)
    timers = []

    class FakeTimer:
        def __init__(self, delay, callback):
            self.delay = delay
            self.callback = callback
            self.daemon = False
            self.started = False
            self.cancelled = False
            timers.append(self)

        def start(self):
            self.started = True

        def cancel(self):
            self.cancelled = True

        def is_alive(self):
            return self.started and not self.cancelled

    monkeypatch.setattr(app_module.threading, "Timer", FakeTimer)

    controller.start_recording()
    controller.stop_recording()
    controller.set_state(Config.STATUS_IDLE)
    controller.start_recording()

    assert display_events == ["acquire"]
    assert timers[0].cancelled is True


def test_cancel_recording_releases_display_sleep_prevention(monkeypatch):
    """Отмена записи должна сразу отпускать защиту дисплея от сна."""
    controller, recorder, _transcriber = make_controller(monkeypatch)
    display_events = install_display_sleep_prevention(controller)

    controller.start_recording()
    controller.cancel_recording()

    assert recorder.cancelled is True
    assert controller.state == Config.STATUS_IDLE
    assert display_events == ["acquire", "release"]


def test_llm_recording_prevents_display_sleep_until_idle(monkeypatch):
    """LLM-сценарий должен удерживать дисплей от сна так же, как обычная диктовка."""
    controller, _recorder, _transcriber = make_controller(monkeypatch)
    display_events = install_display_sleep_prevention(controller)

    controller.toggle_llm()

    assert controller.state == Config.STATUS_RECORDING
    assert display_events == ["acquire"]

    controller.stop_recording()
    controller.set_state(Config.STATUS_IDLE)

    assert display_events == ["acquire", "release"]


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
