"""Тесты StatusBarApp — menu bar приложения.

Проверяет корректность инициализации, обновления состояний,
переключения записи и отображения статусов в меню.
"""

import time
from dataclasses import replace
from typing import Any, cast

import pytest
import src.adapters.ui as ui_module
import src.app as app_controller_module
from src.adapters import overlay
from src.domain.constants import Config
from src.domain.types import LaunchConfig, MicrophoneProfile


class FakeRecorder:
    """Фейковый Recorder для тестов StatusBarApp."""

    def __init__(self):
        """Инициализирует фейковый рекордер."""
        self.started = False
        self.stopped = False
        self.cancelled = False
        self.last_language = None
        self.last_on_audio_ready = None
        self.input_device: Any = None
        self.performance_mode: object = None

    def set_status_callback(self, callback):
        """Сохраняет callback статуса."""
        self.status_callback = callback

    def set_permission_callback(self, callback):
        """Сохраняет callback разрешений."""
        self.permission_callback = callback

    def set_input_device(self, device_info):
        """Сохраняет устройство ввода."""
        self.input_device = device_info

    def set_performance_mode(self, performance_mode):
        """Сохраняет выбранный режим производительности."""
        self.performance_mode = performance_mode

    def start(self, language=None, on_audio_ready=None):
        """Имитирует начало записи."""
        self.started = True
        self.last_language = language
        self.last_on_audio_ready = on_audio_ready

    def stop(self):
        """Имитирует остановку записи."""
        self.stopped = True

    def cancel(self):
        """Имитирует отмену записи."""
        self.cancelled = True


class FakeLLMProcessor:
    """Фейковый LLMProcessor для тестов StatusBarApp."""

    def __init__(self, *, cached=True):
        """Инициализирует фейковый LLM-процессор."""
        self._cached = cached
        self.performance_mode = None

    def is_model_cached(self):
        """Проверяет наличие модели."""
        return self._cached

    def set_performance_mode(self, mode):
        """Сохраняет режим производительности."""
        self.performance_mode = mode


class FakeSettingsStore:
    """Фейковое хранилище настроек для тестов StatusBarApp."""

    def contains_key(self, _key):
        """Сообщает, что сохранённых значений нет."""
        return False

    def load_str(self, _key, fallback=None):
        """Возвращает fallback-значение для строковых настроек."""
        return fallback

    def load_int(self, _key, fallback=0):
        """Возвращает fallback-значение для int-настроек."""
        return fallback

    def load_bool(self, _key, fallback):
        """Возвращает fallback-значение для bool-настроек."""
        return fallback

    def load_input_device_index(self):
        """Не выбирает сохранённый микрофон."""
        return None

    def save_str(self, _key, _value):
        """Игнорирует сохранение строковых настроек."""
        return None

    def save_bool(self, _key, _value):
        """Игнорирует сохранение bool-настроек."""
        return None

    def save_max_time(self, _value):
        """Игнорирует сохранение лимита записи."""
        return None

    def save_input_device_index(self, _value):
        """Игнорирует сохранение индекса микрофона."""
        return None

    def remove_key(self, _key):
        """Игнорирует удаление ключа."""
        return None


class FakeTranscriber:
    """Фейковый SpeechTranscriber для тестов StatusBarApp."""

    def __init__(self):
        """Инициализирует фейковый транскрайбер."""
        self.model_name = "mlx-community/whisper-large-v3-turbo"
        self.paste_cgevent_enabled = True
        self.paste_ax_enabled = False
        self.paste_clipboard_enabled = False
        self.llm_clipboard_enabled = True
        self.private_mode_enabled = False
        self.history: list[str] = []
        self.history_callback = None
        self.total_tokens = 0
        self.token_usage_callback = None

    def set_private_mode(self, enabled):
        """Переключает приватный режим."""
        self.private_mode_enabled = bool(enabled)

    def prune_expired_history(self):
        """Заглушка для очистки просроченных записей истории."""

    def transcribe(self, audio_data, language=None):
        """Заглушка для распознавания аудио."""


def make_clipboard_service(*, initial_text=None, written_texts=None):
    """Создаёт concrete clipboard bundle для тестов app/ui."""
    stored_text = {"value": initial_text}
    sink = written_texts if written_texts is not None else []

    def read_text():
        return stored_text["value"]

    def write_text(text):
        stored_text["value"] = text
        sink.append(text)

    return app_controller_module.ClipboardService(read_text=read_text, write_text=write_text)


def make_microphone_profiles_service(*, profiles=None, saved_profiles=None):
    """Создаёт concrete persistence bundle профилей микрофона для тестов."""
    current_profiles = [
        profile if isinstance(profile, MicrophoneProfile) else MicrophoneProfile.from_payload(profile)
        for profile in (profiles or [])
    ]
    current_profiles = [profile for profile in current_profiles if profile is not None]
    sink = saved_profiles if saved_profiles is not None else []

    def load_profiles():
        return list(current_profiles)

    def save_profiles(profiles_to_save):
        sink.append([profile.to_payload() for profile in profiles_to_save])

    return app_controller_module.MicrophoneProfilesService(
        load_profiles=load_profiles,
        save_profiles=save_profiles,
    )


def make_system_integration_service(*, notifications=None, accessibility_status=True, input_monitoring_status=True):
    """Создаёт concrete bundle уведомлений и статусов разрешений для тестов."""
    sink = notifications if notifications is not None else []

    def notify(title, message):
        sink.append((title, message))

    return app_controller_module.SystemIntegrationService(
        notify=notify,
        get_accessibility_status=lambda: accessibility_status,
        get_input_monitoring_status=lambda: input_monitoring_status,
        request_accessibility_permission=lambda: accessibility_status,
        request_input_monitoring_permission=lambda: input_monitoring_status,
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
    return app_controller_module.InputDeviceCatalogService(list_input_devices=lambda: list(input_devices))


def make_launch_config(*, languages=None, max_time=30, secondary_key_combination=None):
    """Создаёт launch-конфиг для тестов UI."""
    return LaunchConfig.from_sources(
        model="mlx-community/whisper-large-v3-turbo",
        language=languages,
        max_time=max_time,
        llm_model=Config.DEFAULT_LLM_MODEL_NAME,
        key_combination="cmd_l+alt",
        secondary_key_combination=secondary_key_combination,
        llm_key_combination=None,
    )


def make_snapshot(**overrides):
    """Создаёт AppSnapshot с безопасными значениями по умолчанию для UI-тестов."""
    base_snapshot = app_controller_module.AppSnapshot(
        state=Config.STATUS_IDLE,
        started=False,
        elapsed_time=0,
        model_repo="mlx-community/whisper-large-v3-turbo",
        model_name="whisper-large-v3-turbo",
        hotkey_status="левая ⌘ + ⌥",
        secondary_hotkey_status="не задан",
        llm_hotkey_status="не задан",
        primary_key_combination="cmd_l+alt",
        secondary_key_combination="",
        llm_key_combination="",
        llm_prompt_name=Config.DEFAULT_LLM_PROMPT_NAME,
        performance_mode=Config.DEFAULT_PERFORMANCE_MODE,
        max_time=30,
        max_time_options=list(Config.MAX_TIME_PRESETS),
        model_options=list(Config.MODEL_PRESETS),
        languages=["ru", "en"],
        current_language="ru",
        input_devices=[
            {"index": 0, "name": "Built-in Microphone", "max_input_channels": 1, "default_sample_rate": 48000.0, "is_default": True},
        ],
        current_input_device={
            "index": 0,
            "name": "Built-in Microphone",
            "max_input_channels": 1,
            "default_sample_rate": 48000.0,
            "is_default": True,
        },
        permission_status={"accessibility": True, "input_monitoring": True, "microphone": True},
        microphone_profiles=[],
        show_recording_notification=True,
        show_recording_overlay=True,
        private_mode_enabled=False,
        paste_cgevent_enabled=True,
        paste_ax_enabled=False,
        paste_clipboard_enabled=False,
        llm_clipboard_enabled=True,
        history=["Привет мир"],
        total_tokens=123,
        llm_download_title="✅ LLM-модель загружена",
        llm_download_interactive=False,
    )
    return replace(base_snapshot, **overrides)


class FakeDictationController:
    """Минимальный fake-controller для проверки UI-контракта StatusBarApp."""

    def __init__(self, snapshot):
        self.recording_overlay = type(
            "OverlayStub",
            (),
            {"show": lambda self: None, "hide": lambda self: None, "update_time": lambda self, _seconds: None},
        )()
        self.calls: list[tuple[str, object]] = []
        self._subscribers = []
        self._snapshot = snapshot
        self._apply_snapshot(snapshot)

    def _apply_snapshot(self, snapshot):
        self._snapshot = snapshot
        self.state = snapshot.state
        self.started = snapshot.started
        self.elapsed_time = snapshot.elapsed_time
        self.model_name = snapshot.model_name
        self.model_repo = snapshot.model_repo
        self.hotkey_status = snapshot.hotkey_status
        self.secondary_hotkey_status = snapshot.secondary_hotkey_status
        self.llm_hotkey_status = snapshot.llm_hotkey_status
        self.llm_prompt_name = snapshot.llm_prompt_name
        self.performance_mode = snapshot.performance_mode
        self.max_time = snapshot.max_time
        self.max_time_options = list(snapshot.max_time_options)
        self.model_options = list(snapshot.model_options)
        self.languages = None if snapshot.languages is None else list(snapshot.languages)
        self.current_language = snapshot.current_language
        self.input_devices = list(snapshot.input_devices)
        self.current_input_device = snapshot.current_input_device
        self.permission_status = dict(snapshot.permission_status)
        self.microphone_profiles = list(snapshot.microphone_profiles)
        self.show_recording_notification = snapshot.show_recording_notification
        self.show_recording_overlay = snapshot.show_recording_overlay
        self.private_mode_enabled = snapshot.private_mode_enabled
        self.paste_cgevent_enabled = snapshot.paste_cgevent_enabled
        self.paste_ax_enabled = snapshot.paste_ax_enabled
        self.paste_clipboard_enabled = snapshot.paste_clipboard_enabled
        self.llm_clipboard_enabled = snapshot.llm_clipboard_enabled
        self.history = list(snapshot.history)
        self.total_tokens = snapshot.total_tokens

    def subscribe(self, callback):
        """Подписывает UI на обновления snapshot и сразу отправляет текущее состояние."""
        self._subscribers.append(callback)
        callback(self.snapshot())

    def snapshot(self):
        """Возвращает последний snapshot fake-controller."""
        return self._snapshot

    def emit(self, snapshot):
        """Публикует новый snapshot всем подписчикам."""
        self._apply_snapshot(snapshot)
        for callback in list(self._subscribers):
            callback(snapshot)

    def microphone_menu_title(self, device_info):
        """Формирует подпись микрофона для меню UI."""
        return f"[{device_info['index']}] {device_info['name']}"

    def is_microphone_profile_active(self, _profile):
        """Сообщает, что ни один профиль не активен."""
        return False

    def prune_expired_history(self):
        """Имитирует отсутствие изменений в истории."""
        return False

    def change_language(self, language):
        """Запоминает команду смены языка."""
        self.calls.append(("change_language", language))

    def toggle_recording_overlay(self):
        """Запоминает команду переключения overlay."""
        self.calls.append(("toggle_recording_overlay", None))

    def start_recording(self):
        """Имитирует старт записи и публикует recording snapshot."""
        self.calls.append(("start_recording", None))
        self.emit(replace(self._snapshot, started=True, state=Config.STATUS_RECORDING))

    def stop_recording(self):
        """Имитирует остановку записи и публикует idle snapshot."""
        self.calls.append(("stop_recording", None))
        self.emit(replace(self._snapshot, started=False, state=Config.STATUS_IDLE))

    def on_status_tick(self):
        """Сохраняет совместимость с UI-таймером без дополнительной логики."""
        return None


@pytest.fixture
def patched_app_module(app_module, monkeypatch):
    """Подготавливает модуль приложения с замоканными системными вызовами."""
    settings_store = FakeSettingsStore()
    monkeypatch.setattr(app_controller_module, "_test_settings_store", settings_store, raising=False)
    monkeypatch.setattr(app_module, "_test_settings_store", settings_store, raising=False)
    return app_module


@pytest.fixture
def make_app(patched_app_module):
    """Фабрика для создания StatusBarApp с фейковым рекордером и транскрайбером."""

    def _make(languages=None, max_time=30, secondary_key_combination=None, microphone_profiles=None, written_texts=None):
        recorder = FakeRecorder()
        transcriber = FakeTranscriber()
        llm_processor = FakeLLMProcessor()
        clipboard_service = make_clipboard_service(written_texts=written_texts)
        microphone_profiles_service = make_microphone_profiles_service(profiles=microphone_profiles)
        system_integration_service = make_system_integration_service()
        input_device_catalog = make_input_device_catalog()
        controller = patched_app_module.DictationApp(
            recorder=recorder,
            transcriber=transcriber,
            llm_processor=llm_processor,
            launch_config=make_launch_config(
                languages=languages,
                max_time=max_time,
                secondary_key_combination=secondary_key_combination,
            ),
            clipboard_service=clipboard_service,
            microphone_profiles_service=microphone_profiles_service,
            system_integration_service=system_integration_service,
            input_device_catalog=input_device_catalog,
            recording_overlay=overlay.RecordingOverlay(),
            settings_store=patched_app_module._test_settings_store,
        )
        app = patched_app_module.StatusBarApp(controller)
        return app, recorder, transcriber

    return _make


class TestStatusBarInit:
    """Тесты инициализации StatusBarApp."""

    def test_initial_state_is_idle(self, make_app, patched_app_module):
        """После создания приложение в состоянии ожидания."""
        app, *_ = make_app(languages=["ru"])
        assert app.state == Config.STATUS_IDLE

    def test_initial_title_is_pause_icon(self, make_app):
        """Начальная иконка — ⏯."""
        app, *_ = make_app(languages=["ru"])
        assert app.title == "⏯"

    def test_model_name_in_menu(self, make_app):
        """Имя модели отображается в меню."""
        app, *_ = make_app(languages=["ru"])
        assert "whisper-large-v3-turbo" in app.model_item.title

    def test_hotkey_in_menu(self, make_app):
        """Хоткей отображается в меню."""
        app, *_ = make_app(languages=["ru"])
        assert "⌘" in app.hotkey_item.title

    def test_secondary_hotkey_in_menu_when_missing(self, make_app):
        """Если дополнительный хоткей не задан, это явно видно в меню."""
        app, *_ = make_app(languages=["ru"])
        assert "не задан" in app.secondary_hotkey_item.title

    def test_max_time_in_menu(self, make_app):
        """Лимит длительности отображается в меню."""
        app, *_ = make_app(languages=["ru"], max_time=30)
        assert "30 с" in app.max_time_item.title

    def test_language_in_menu(self, make_app):
        """Текущий язык отображается в меню."""
        app, *_ = make_app(languages=["ru"])
        assert "ru" in app.language_item.title

    def test_auto_language_when_none(self, make_app):
        """Без языков показывается автоопределение."""
        app, *_ = make_app(languages=None)
        assert "автоопределение" in app.language_item.title

    def test_permission_items_present(self, make_app):
        """Статусы разрешений отображаются в меню."""
        app, *_ = make_app(languages=["ru"])
        assert "Accessibility" in app.accessibility_item.title
        assert "Input Monitoring" in app.input_monitoring_item.title
        assert "Microphone" in app.microphone_item.title

    def test_token_usage_item_present(self, make_app):
        """В меню отображается общий счётчик токенов."""
        app, *_ = make_app(languages=["ru"])
        assert "Токены" in app.token_usage_item.title

    def test_started_is_false(self, make_app):
        """Запись не запущена при инициализации."""
        app, *_ = make_app(languages=["ru"])
        assert app.started is False

    def test_input_device_in_menu(self, make_app):
        """Микрофон отображается в меню."""
        app, *_ = make_app(languages=["ru"])
        assert "Built-in Microphone" in app.input_device_item.title

    def test_input_device_submenu_contains_microphones(self, make_app):
        """Полный список микрофонов вынесен в подменю выбора устройства."""
        app, *_ = make_app(languages=["ru"])
        assert app.input_device_menu["[0] Built-in Microphone"].state == 1

    def test_microphone_profiles_menu_is_present(self, make_app):
        """Быстрые профили микрофона доступны отдельным подменю."""
        app, *_ = make_app(languages=["ru"])
        assert app.microphone_profiles_menu["➕ Добавить текущий профиль…"].title == "➕ Добавить текущий профиль…"

    def test_recording_notification_enabled_by_default(self, make_app):
        """Уведомление о старте записи включено по умолчанию."""
        app, *_ = make_app(languages=["ru"])
        assert app.show_recording_notification is True
        assert app.recording_notification_item.state == 1

    def test_llm_clipboard_enabled_by_default(self, make_app):
        """Буфер обмена для LLM включён по умолчанию."""
        app, _recorder, transcriber = make_app(languages=["ru"])
        assert transcriber.llm_clipboard_enabled is True
        assert app.llm_clipboard_item.state == 1


class TestStatusBarStateTransitions:
    """Тесты переключения состояний записи."""

    def test_start_sets_recording_state(self, make_app, patched_app_module):
        """Начало записи переключает состояние в recording."""
        app, recorder, _ = make_app(languages=["ru"])
        app.start_app(None)
        assert app.state == Config.STATUS_RECORDING
        assert app.started is True
        assert recorder.started is True

    def test_start_passes_language_to_recorder(self, make_app):
        """Язык передаётся рекордеру при старте."""
        app, recorder, _ = make_app(languages=["ru"])
        app.start_app(None)
        assert recorder.last_language == "ru"

    def test_stop_sets_transcribing_state(self, make_app, patched_app_module):
        """Остановка записи переключает состояние в transcribing."""
        app, recorder, _ = make_app(languages=["ru"])
        app.start_app(None)
        app.stop_app(None)
        assert app.state == Config.STATUS_TRANSCRIBING
        assert app.started is False
        assert recorder.stopped is True

    def test_stop_without_start_does_nothing(self, make_app, patched_app_module):
        """Остановка без старта не меняет состояние."""
        app, recorder, _ = make_app(languages=["ru"])
        app.stop_app(None)
        assert app.state == Config.STATUS_IDLE
        assert recorder.stopped is False

    def test_toggle_starts_when_idle(self, make_app, patched_app_module):
        """Toggle запускает запись из состояния ожидания."""
        app, recorder, _ = make_app(languages=["ru"])
        app.toggle()
        assert app.started is True
        assert recorder.started is True

    def test_toggle_stops_when_recording(self, make_app):
        """Toggle останавливает запись из состояния записи."""
        app, recorder, _ = make_app(languages=["ru"])
        app.toggle()
        app.toggle()
        assert app.started is False
        assert recorder.stopped is True

    def test_start_shows_notification_when_enabled(self, make_app, patched_app_module, monkeypatch):
        """При включенном флаге старт записи показывает уведомление."""
        notifications: list[tuple[str, str]] = []

        app, *_ = make_app(languages=["ru"])
        app.app.system_integration_service = make_system_integration_service(notifications=notifications)
        app.show_recording_notification = True
        app.start_app(None)

        assert len(notifications) == 1
        assert notifications[0][0] == "MLX Whisper Dictation"
        assert "Запись началась" in notifications[0][1]

    def test_start_skips_notification_when_disabled(self, make_app, patched_app_module, monkeypatch):
        """При выключенном флаге старт записи не показывает уведомление."""
        notifications: list[tuple[str, str]] = []

        app, *_ = make_app(languages=["ru"])
        app.app.system_integration_service = make_system_integration_service(notifications=notifications)
        app.show_recording_notification = False
        app.start_app(None)

        assert notifications == []

    def test_toggle_recording_notification_updates_flag_and_state(self, make_app):
        """Переключатель уведомления меняет флаг и состояние пункта меню."""
        app, *_ = make_app(languages=["ru"])

        app.toggle_recording_notification(app.recording_notification_item)
        assert app.show_recording_notification is False
        assert app.recording_notification_item.state == 0

        app.toggle_recording_notification(app.recording_notification_item)
        assert app.show_recording_notification is True
        assert app.recording_notification_item.state == 1

    def test_toggle_recording_notification_persists_flag(self, make_app, patched_app_module, monkeypatch):
        """Флаг уведомления о записи должен сохраняться."""
        saved_values = []
        app, *_ = make_app(languages=["ru"])
        monkeypatch.setattr(app.app.settings_store, "save_bool", lambda key, value: saved_values.append((key, value)))

        app.toggle_recording_notification(app.recording_notification_item)

        assert (Config.DEFAULTS_KEY_RECORDING_NOTIFICATION, False) in saved_values


class TestStatusBarDisplay:
    """Тесты отображения иконки и статуса."""

    def test_recording_title_shows_timer(self, make_app):
        """Во время записи в заголовке показывается таймер."""
        app, *_ = make_app(languages=["ru"])
        app.start_app(None)
        app.on_status_tick(None)
        assert "🔴" in app.title

    def test_transcribing_title_shows_brain(self, make_app, patched_app_module):
        """Во время распознавания отображается мозг."""
        app, *_ = make_app(languages=["ru"])
        app.state = Config.STATUS_TRANSCRIBING
        app._refresh_title_and_status()
        assert app.title == "🧠"

    def test_idle_title_shows_pause(self, make_app, patched_app_module):
        """В состоянии ожидания отображается пауза."""
        app, *_ = make_app(languages=["ru"])
        app.state = Config.STATUS_IDLE
        app._refresh_title_and_status()
        assert app.title == "⏯"

    def test_state_label_idle(self, make_app, patched_app_module):
        """Метка idle → ожидание."""
        app, *_ = make_app(languages=["ru"])
        app.state = Config.STATUS_IDLE
        assert app._state_label() == "ожидание"

    def test_state_label_recording(self, make_app, patched_app_module):
        """Метка recording → запись."""
        app, *_ = make_app(languages=["ru"])
        app.state = Config.STATUS_RECORDING
        assert app._state_label() == "запись"

    def test_state_label_transcribing(self, make_app, patched_app_module):
        """Метка transcribing → распознавание."""
        app, *_ = make_app(languages=["ru"])
        app.state = Config.STATUS_TRANSCRIBING
        assert app._state_label() == "распознавание"

    def test_refresh_token_usage_item_updates_number(self, make_app):
        """Пункт меню со счётчиком токенов обновляется из transcriber."""
        app, _recorder, transcriber = make_app(languages=["ru"])
        transcriber.total_tokens = 12345

        app._refresh_token_usage_item()

        assert app.token_usage_item.title == "🔢 Токены: 12 345"


class TestStatusBarMaxTime:
    """Тесты автоматической остановки по лимиту."""

    def test_auto_stop_on_max_time(self, make_app, monkeypatch):
        """Запись автоматически останавливается по лимиту."""
        app, recorder, _ = make_app(languages=["ru"], max_time=5)
        app.start_app(None)
        app.start_time = time.time() - 6
        app.on_status_tick(None)
        assert app.started is False
        assert recorder.stopped is True

    def test_no_auto_stop_before_max_time(self, make_app):
        """Запись не останавливается до лимита."""
        app, _recorder, _ = make_app(languages=["ru"], max_time=30)
        app.start_app(None)
        app.on_status_tick(None)
        assert app.started is True

    def test_no_limit_means_no_auto_stop(self, make_app):
        """Без лимита запись не останавливается автоматически."""
        app, _recorder, _ = make_app(languages=["ru"], max_time=None)
        app.start_app(None)
        app.start_time = time.time() - 999
        app.on_status_tick(None)
        assert app.started is True


class TestStatusBarSetState:
    """Тесты set_state и set_permission_status."""

    def test_set_state_updates_state(self, make_app, patched_app_module):
        """set_state обновляет текущее состояние."""
        app, *_ = make_app(languages=["ru"])
        app.set_state(Config.STATUS_RECORDING)
        assert app.state == Config.STATUS_RECORDING

    def test_set_permission_status_updates_microphone(self, make_app):
        """set_permission_status обновляет статус микрофона."""
        app, *_ = make_app(languages=["ru"])
        app.set_permission_status("microphone", True)
        assert app.permission_status["microphone"] is True

    def test_set_permission_status_updates_accessibility(self, make_app):
        """set_permission_status обновляет статус accessibility."""
        app, *_ = make_app(languages=["ru"])
        app.set_permission_status("accessibility", False)
        assert app.permission_status["accessibility"] is False


class TestStatusBarMenuSelections:
    """Тесты выбора параметров через пункты меню."""

    def test_change_max_time_from_menu_updates_state(self, make_app):
        """Выбор лимита записи из меню должен обновлять max_time и заголовок."""
        app, *_ = make_app(languages=["ru"], max_time=30)
        item = app._menu_item("Лимит: 60 с")

        app.change_max_time(item)

        assert app.max_time == 60
        assert "60 с" in app.max_time_item.title
        assert item.state == 1

    def test_change_max_time_persists_selection(self, make_app, patched_app_module, monkeypatch):
        """Лимит записи должен сохраняться между перезапусками."""
        saved_values = []

        app, *_ = make_app(languages=["ru"], max_time=30)
        monkeypatch.setattr(app.app.settings_store, "save_str", lambda key, value: saved_values.append((key, value)))

        app.change_max_time(app._menu_item("Лимит: 60 с"))

        assert (Config.DEFAULTS_KEY_MAX_TIME, "60") in saved_values

    def test_change_model_from_menu_updates_transcriber(self, make_app):
        """Выбор модели из меню должен переключать модель в transcriber."""
        app, _recorder, transcriber = make_app(languages=["ru"], max_time=30)
        item = app._menu_item("Модель: whisper-turbo")

        app.change_model(item)

        assert app.model_name == "whisper-turbo"
        assert transcriber.model_name == "mlx-community/whisper-turbo"
        assert "whisper-turbo" in app.model_item.title
        assert item.state == 1

    def test_change_model_persists_selection(self, make_app, patched_app_module, monkeypatch):
        """Выбранная модель должна сохраняться в NSUserDefaults."""
        saved_values = []
        app, *_ = make_app(languages=["ru"], max_time=30)
        monkeypatch.setattr(app.app.settings_store, "save_str", lambda key, value: saved_values.append((key, value)))

        app.change_model(app._menu_item("Модель: whisper-turbo"))

        assert (Config.DEFAULTS_KEY_MODEL, "mlx-community/whisper-turbo") in saved_values

    def test_change_input_device_persists_selection(self, patched_app_module, monkeypatch):
        """Выбранный микрофон должен сохраняться в настройках."""
        saved_values = []
        settings_store = FakeSettingsStore()
        input_device_catalog = make_input_device_catalog(
            devices=[
                {"index": 0, "name": "Built-in Microphone", "max_input_channels": 1, "default_sample_rate": 48000.0, "is_default": True},
                {"index": 4, "name": "USB Mic", "max_input_channels": 1, "default_sample_rate": 44100.0, "is_default": False},
            ],
        )

        def save_defaults_input_device_index(value):
            saved_values.append(value)

        monkeypatch.setattr(settings_store, "save_input_device_index", save_defaults_input_device_index)
        recorder = FakeRecorder()
        controller = patched_app_module.DictationApp(
            recorder=recorder,
            transcriber=FakeTranscriber(),
            llm_processor=FakeLLMProcessor(),
            launch_config=make_launch_config(languages=["ru"], max_time=30),
            clipboard_service=make_clipboard_service(),
            microphone_profiles_service=make_microphone_profiles_service(),
            system_integration_service=make_system_integration_service(),
            input_device_catalog=input_device_catalog,
            recording_overlay=overlay.RecordingOverlay(),
            settings_store=settings_store,
        )
        app = patched_app_module.StatusBarApp(controller)

        app.change_input_device(app._menu_item("[4] USB Mic"))

        assert saved_values == [4]
        assert recorder.input_device["index"] == 4

    def test_add_current_microphone_profile_saves_current_settings(self, make_app, patched_app_module, monkeypatch):
        """Текущие настройки можно сохранить как быстрый профиль микрофона."""
        saved_profiles: list[list[dict[str, object]]] = []
        monkeypatch.setattr(ui_module, "prompt_text", lambda *args, **kwargs: "Звонки")
        app, _recorder, transcriber = make_app(languages=["ru"], max_time=30, written_texts=[], microphone_profiles=[])
        app.app.microphone_profiles_service = make_microphone_profiles_service(saved_profiles=saved_profiles)
        transcriber.paste_ax_enabled = True
        transcriber.paste_clipboard_enabled = True
        transcriber.llm_clipboard_enabled = False

        app.add_current_microphone_profile(None)

        assert app.microphone_profiles[0].name == "Звонки"
        assert app.microphone_profiles_menu["Звонки"].state == 1
        assert saved_profiles[-1][0]["input_device_index"] == 0
        assert saved_profiles[-1][0]["paste_ax"] is True
        assert saved_profiles[-1][0]["paste_clipboard"] is True
        assert saved_profiles[-1][0]["llm_clipboard"] is False

    def test_apply_microphone_profile_updates_basic_settings(self, patched_app_module, monkeypatch):
        """Профиль микрофона должен применять устройство и базовые настройки."""
        saved_device_indexes: list[object] = []
        saved_strings = []
        saved_bools = []
        settings_store = FakeSettingsStore()
        input_device_catalog = make_input_device_catalog(
            devices=[
                {"index": 0, "name": "Built-in Microphone", "max_input_channels": 1, "default_sample_rate": 48000.0, "is_default": True},
                {"index": 4, "name": "USB Mic", "max_input_channels": 1, "default_sample_rate": 44100.0, "is_default": False},
            ],
        )

        def save_defaults_str(key, value):
            saved_strings.append((key, value))

        def save_defaults_bool(key, value):
            saved_bools.append((key, value))

        monkeypatch.setattr(settings_store, "save_input_device_index", saved_device_indexes.append)
        monkeypatch.setattr(settings_store, "save_str", save_defaults_str)
        monkeypatch.setattr(settings_store, "save_bool", save_defaults_bool)

        recorder = FakeRecorder()
        transcriber = FakeTranscriber()
        controller = patched_app_module.DictationApp(
            recorder=recorder,
            transcriber=transcriber,
            llm_processor=FakeLLMProcessor(),
            launch_config=make_launch_config(languages=["ru"], max_time=30),
            clipboard_service=make_clipboard_service(),
            microphone_profiles_service=make_microphone_profiles_service(
                profiles=[
                    {
                        "name": "Встречи",
                        "input_device_index": 4,
                        "input_device_name": "USB Mic",
                        "model_repo": "mlx-community/whisper-turbo",
                        "language": "ru",
                        "max_time": 60,
                        "performance_mode": Config.PERFORMANCE_MODE_FAST,
                        "private_mode": True,
                        "paste_cgevent": False,
                        "paste_ax": True,
                        "paste_clipboard": True,
                        "llm_clipboard": False,
                    },
                ]
            ),
            system_integration_service=make_system_integration_service(),
            input_device_catalog=input_device_catalog,
            recording_overlay=overlay.RecordingOverlay(),
            settings_store=settings_store,
        )
        app = patched_app_module.StatusBarApp(controller)

        app.apply_microphone_profile(app.microphone_profiles_menu["Встречи"])

        assert recorder.input_device["index"] == 4
        assert app.model_name == "whisper-turbo"
        assert app.max_time == 60
        assert app.performance_mode == Config.PERFORMANCE_MODE_FAST
        assert transcriber.private_mode_enabled is True
        assert transcriber.paste_cgevent_enabled is False
        assert transcriber.paste_ax_enabled is True
        assert transcriber.paste_clipboard_enabled is True
        assert transcriber.llm_clipboard_enabled is False
        assert saved_device_indexes == [4]
        assert (Config.DEFAULTS_KEY_MODEL, "mlx-community/whisper-turbo") in saved_strings
        assert (Config.DEFAULTS_KEY_MAX_TIME, "60") in saved_strings
        assert (Config.DEFAULTS_KEY_PERFORMANCE_MODE, Config.PERFORMANCE_MODE_FAST) in saved_strings
        assert (Config.DEFAULTS_KEY_PASTE_CGEVENT, False) in saved_bools
        assert (Config.DEFAULTS_KEY_PASTE_AX, True) in saved_bools
        assert (Config.DEFAULTS_KEY_PASTE_CLIPBOARD, True) in saved_bools
        assert (Config.DEFAULTS_KEY_LLM_CLIPBOARD, False) in saved_bools

    def test_toggle_llm_clipboard_updates_transcriber_and_defaults(self, make_app, patched_app_module, monkeypatch):
        """Переключатель LLM-буфера должен менять runtime-state и сохраняться."""
        saved_bools = []
        app, _recorder, transcriber = make_app(languages=["ru"])
        monkeypatch.setattr(app.app.settings_store, "save_bool", lambda key, value: saved_bools.append((key, value)))

        app.toggle_llm_clipboard(app.llm_clipboard_item)

        assert transcriber.llm_clipboard_enabled is False
        assert app.llm_clipboard_item.state == 0
        assert (Config.DEFAULTS_KEY_LLM_CLIPBOARD, False) in saved_bools

    def test_delete_microphone_profile_removes_it(self, patched_app_module, monkeypatch):
        """Сохранённый профиль можно удалить из подменю быстрых профилей."""
        saved_profiles: list[list[dict[str, object]]] = []

        recorder = FakeRecorder()
        controller = patched_app_module.DictationApp(
            recorder=recorder,
            transcriber=FakeTranscriber(),
            llm_processor=FakeLLMProcessor(),
            launch_config=make_launch_config(languages=["ru"], max_time=30),
            clipboard_service=make_clipboard_service(),
            microphone_profiles_service=make_microphone_profiles_service(
                profiles=[
                    {
                        "name": "Встречи",
                        "input_device_index": 0,
                        "input_device_name": "Built-in Microphone",
                        "model_repo": "mlx-community/whisper-large-v3-turbo",
                        "language": "ru",
                        "max_time": 30,
                        "performance_mode": Config.PERFORMANCE_MODE_NORMAL,
                        "private_mode": False,
                        "paste_cgevent": True,
                        "paste_ax": False,
                        "paste_clipboard": False,
                    },
                ],
                saved_profiles=saved_profiles,
            ),
            system_integration_service=make_system_integration_service(),
            input_device_catalog=make_input_device_catalog(),
            recording_overlay=overlay.RecordingOverlay(),
            settings_store=FakeSettingsStore(),
        )
        app = patched_app_module.StatusBarApp(controller)

        app.delete_microphone_profile(app.microphone_profiles_menu["🗑 Удалить профиль"]["Встречи"])

        assert app.microphone_profiles == []
        assert saved_profiles[-1] == []

    def test_change_performance_mode_updates_recorder_and_menu(self, make_app, patched_app_module, monkeypatch):
        """Смена режима должна обновлять рекордер и сохраняться."""
        saved_values = []
        app, recorder, _ = make_app(languages=["ru"], max_time=30)
        monkeypatch.setattr(app.app.settings_store, "save_str", lambda key, value: saved_values.append((key, value)))

        app.change_performance_mode(app.performance_menu["Быстрый"])

        assert app.performance_mode == Config.PERFORMANCE_MODE_FAST
        assert recorder.performance_mode == Config.PERFORMANCE_MODE_FAST
        assert "Быстрый" in app.performance_menu.title
        assert (Config.DEFAULTS_KEY_PERFORMANCE_MODE, Config.PERFORMANCE_MODE_FAST) in saved_values

    def test_change_llm_prompt_persists_selection(self, make_app, patched_app_module, monkeypatch):
        """Выбор LLM-промпта должен сохраняться."""
        saved_values = []
        app, _recorder, _ = make_app(languages=["ru"], max_time=30)
        monkeypatch.setattr(app.app.settings_store, "save_str", lambda key, value: saved_values.append((key, value)))

        app._change_llm_prompt(app.llm_prompt_menu["Исправь текст"])

        assert app.llm_prompt_name == "Исправь текст"
        assert (Config.DEFAULTS_KEY_LLM_PROMPT, "Исправь текст") in saved_values


class TestStatusBarHotkeys:
    """Тесты изменения основного и дополнительного хоткеев."""

    def test_change_secondary_hotkey_updates_menu_and_listener(self, make_app, patched_app_module, monkeypatch):
        """Изменение дополнительного хоткея должно обновить меню и runtime listener."""
        app, *_ = make_app(languages=["ru"])
        calls = []

        class ListenerStub:
            def update_hotkeys(self, primary, secondary, llm):
                calls.append((primary, secondary, llm))

        app.app.hotkey_management_use_cases.capture_hotkey_combination = lambda *args, **kwargs: "ctrl+shift+space"
        app.key_listener = ListenerStub()

        app.change_secondary_hotkey(None)

        assert app._secondary_key_combination == "ctrl+shift+space"
        assert "Space" in app.secondary_hotkey_item.title
        assert calls == [("cmd_l+alt", "ctrl+shift+space", "")]

    def test_change_secondary_hotkey_persists_value(self, make_app, patched_app_module, monkeypatch):
        """Изменение дополнительного хоткея должно сохраняться."""
        saved_values = []

        class ListenerStub:
            def update_hotkeys(self, _primary, _secondary, _llm):
                return None

        app, *_ = make_app(languages=["ru"])
        app.app.hotkey_management_use_cases.capture_hotkey_combination = lambda *args, **kwargs: "ctrl+shift+space"
        monkeypatch.setattr(app.app.settings_store, "save_str", lambda key, value: saved_values.append((key, value)))
        app.key_listener = ListenerStub()

        app.change_secondary_hotkey(None)

        assert (Config.DEFAULTS_KEY_PRIMARY_HOTKEY, "cmd_l+alt") in saved_values
        assert (Config.DEFAULTS_KEY_SECONDARY_HOTKEY, "ctrl+shift+space") in saved_values

    def test_change_secondary_hotkey_can_disable_it(self, make_app, patched_app_module, monkeypatch):
        """Пустое значение должно отключать дополнительный хоткей."""
        app, *_ = make_app(languages=["ru"], secondary_key_combination="ctrl+shift+space")
        calls = []

        class ListenerStub:
            def update_hotkeys(self, primary, secondary, llm):
                calls.append((primary, secondary, llm))

        app.app.hotkey_management_use_cases.capture_hotkey_combination = lambda *args, **kwargs: ""
        app.key_listener = ListenerStub()

        app.change_secondary_hotkey(None)

        assert app._secondary_key_combination == ""
        assert "не задан" in app.secondary_hotkey_item.title
        assert calls == [("cmd_l+alt", "", "")]

    def test_change_llm_hotkey_persists_value(self, make_app, patched_app_module, monkeypatch):
        """Изменение LLM-хоткея должно сохраняться."""
        saved_values = []
        app, *_ = make_app(languages=["ru"])
        app.app.hotkey_management_use_cases.capture_hotkey_combination = lambda *args, **kwargs: "ctrl+shift+l"

        class ListenerStub:
            def update_hotkeys(self, _primary, _secondary, _llm):
                return None

        app.key_listener = ListenerStub()
        monkeypatch.setattr(app.app.settings_store, "save_str", lambda key, value: saved_values.append((key, value)))

        app.change_llm_hotkey(None)

        assert (Config.DEFAULTS_KEY_LLM_HOTKEY, "ctrl+shift+l") in saved_values


class TestCancelRecording:
    """Тесты отмены записи через Escape и cancel_recording."""

    def test_cancel_recording_resets_state_to_idle(self, make_app, patched_app_module):
        """cancel_recording должен переключить состояние в idle."""
        app, *_ = make_app(languages=["ru"])
        app.start_app(None)

        app.cancel_recording()

        assert app.state == Config.STATUS_IDLE
        assert app.started is False

    def test_cancel_recording_calls_recorder_cancel(self, make_app):
        """cancel_recording должен вызвать recorder.cancel()."""
        app, recorder, _ = make_app(languages=["ru"])
        app.start_app(None)

        app.cancel_recording()

        assert recorder.cancelled is True

    def test_cancel_recording_ignored_when_not_started(self, make_app, patched_app_module):
        """cancel_recording не должен ничего делать, если запись не запущена."""
        app, recorder, _ = make_app(languages=["ru"])

        app.cancel_recording()

        assert app.state == Config.STATUS_IDLE
        assert recorder.cancelled is False

    def test_cancel_recording_updates_menu_items(self, make_app):
        """cancel_recording должен переключить доступность пунктов меню."""
        app, *_ = make_app(languages=["ru"])
        app.start_app(None)

        app.cancel_recording()

        # После отмены «Начать запись» снова доступна, а «Остановить запись» — нет
        start_item = app._menu_item("Начать запись")
        stop_item = app._menu_item("Остановить запись")
        assert start_item.callback is not None
        assert stop_item.callback is None

    def test_cancel_recording_sets_idle_title(self, make_app, patched_app_module):
        """cancel_recording должен вернуть иконку ⏯ в строке меню."""
        app, *_ = make_app(languages=["ru"])
        app.start_app(None)

        app.cancel_recording()
        app._refresh_title_and_status()

        assert app.title == "⏯"

    def test_escape_key_triggers_cancel_when_recording(self, make_app):
        """Нажатие Escape должно отменить запись, если она запущена."""
        app, recorder, _ = make_app(languages=["ru"])
        app.start_app(None)

        app.app.handle_escape_keycode(53)

        assert app.started is False
        assert recorder.cancelled is True

    def test_escape_key_ignored_when_not_recording(self, make_app, patched_app_module):
        """Нажатие Escape не должно ничего делать, если запись не запущена."""
        app, recorder, _ = make_app(languages=["ru"])

        app.app.handle_escape_keycode(53)

        assert app.state == Config.STATUS_IDLE
        assert recorder.cancelled is False

    def test_non_escape_key_ignored(self, make_app):
        """Нажатие не-Escape клавиши не должно отменять запись."""
        app, recorder, _ = make_app(languages=["ru"])
        app.start_app(None)

        app.app.handle_escape_keycode(0)

        assert app.started is True
        assert recorder.cancelled is False


class TestRecordingOverlay:
    """Тесты RecordingOverlay — всплывающего индикатора записи у курсора."""

    def test_initial_state_not_visible(self, patched_app_module):
        """После создания overlay не показан."""
        ov = overlay.RecordingOverlay()
        assert ov.is_visible is False
        assert ov._window is None
        assert ov._label is None

    def test_hide_when_not_visible(self, patched_app_module):
        """Повторный hide без show не вызывает ошибок."""
        ov = overlay.RecordingOverlay()
        ov.hide()
        assert ov.is_visible is False

    def test_update_time_without_label(self, patched_app_module):
        """update_time без показа окна не вызывает ошибок."""
        ov = overlay.RecordingOverlay()
        ov.update_time(42)
        assert ov.is_visible is False


class TestRecordingOverlayIntegration:
    """Тесты интеграции RecordingOverlay в StatusBarApp."""

    def test_overlay_initialized_in_app(self, make_app, patched_app_module):
        """StatusBarApp создаёт экземпляр RecordingOverlay."""
        app, *_ = make_app(languages=["ru"])
        assert hasattr(app, "recording_overlay")
        assert isinstance(app.recording_overlay, overlay.RecordingOverlay)

    def test_overlay_enabled_by_default(self, make_app):
        """По умолчанию индикатор записи у курсора включён."""
        app, *_ = make_app(languages=["ru"])
        assert app.show_recording_overlay is True
        assert app.recording_overlay_item.state == 1

    def test_overlay_menu_item_exists(self, make_app):
        """В меню есть пункт для переключения индикатора записи."""
        app, *_ = make_app(languages=["ru"])
        assert "🎯 Индикатор записи у курсора" in app.recording_overlay_item.title

    def test_toggle_recording_overlay_off(self, make_app, monkeypatch):
        """toggle_recording_overlay выключает индикатор."""
        saved = {}
        app, *_ = make_app(languages=["ru"])
        monkeypatch.setattr(app.app.settings_store, "save_bool", lambda k, v: saved.update({k: v}))
        assert app.show_recording_overlay is True

        app.toggle_recording_overlay(app.recording_overlay_item)

        assert app.show_recording_overlay is False
        assert app.recording_overlay_item.state == 0
        assert saved.get(Config.DEFAULTS_KEY_RECORDING_OVERLAY) is False

    def test_toggle_recording_overlay_on(self, make_app, monkeypatch):
        """toggle_recording_overlay включает индикатор обратно."""
        saved = {}
        app, *_ = make_app(languages=["ru"])
        monkeypatch.setattr(app.app.settings_store, "save_bool", lambda k, v: saved.update({k: v}))
        app.show_recording_overlay = False

        app.toggle_recording_overlay(app.recording_overlay_item)

        assert app.show_recording_overlay is True
        assert app.recording_overlay_item.state == 1

    def test_start_app_shows_overlay_when_enabled(self, make_app, monkeypatch):
        """start_app вызывает overlay.show(), когда индикатор включён."""
        app, *_ = make_app(languages=["ru"])
        app.show_recording_overlay = True

        show_called = []
        monkeypatch.setattr(app.recording_overlay, "show", lambda: show_called.append(True))

        app.start_app(None)

        assert len(show_called) == 1

    def test_start_app_does_not_show_overlay_when_disabled(self, make_app, monkeypatch):
        """start_app не вызывает overlay.show(), когда индикатор выключен."""
        app, *_ = make_app(languages=["ru"])
        app.show_recording_overlay = False

        show_called = []
        monkeypatch.setattr(app.recording_overlay, "show", lambda: show_called.append(True))

        app.start_app(None)

        assert len(show_called) == 0

    def test_stop_app_hides_overlay(self, make_app, monkeypatch):
        """stop_app вызывает overlay.hide()."""
        app, *_ = make_app(languages=["ru"])
        app.start_app(None)

        hide_called = []
        monkeypatch.setattr(app.recording_overlay, "hide", lambda: hide_called.append(True))

        app.stop_app(None)

        assert len(hide_called) == 1

    def test_cancel_recording_hides_overlay(self, make_app, monkeypatch):
        """cancel_recording вызывает overlay.hide()."""
        app, *_ = make_app(languages=["ru"])
        app.start_app(None)

        hide_called = []
        monkeypatch.setattr(app.recording_overlay, "hide", lambda: hide_called.append(True))

        app.cancel_recording()

        assert len(hide_called) == 1

    def test_on_status_tick_updates_overlay_time(self, make_app, monkeypatch):
        """on_status_tick вызывает overlay.update_time() при записи."""
        app, *_ = make_app(languages=["ru"])
        app.start_app(None)

        updated_times: list[object] = []
        monkeypatch.setattr(app.recording_overlay, "update_time", updated_times.append)

        app.on_status_tick(None)

        assert len(updated_times) == 1


class TestStatusBarWithFakeController:
    """Проверяет, что UI работает через snapshot и команды контроллера."""

    def test_initial_menu_builds_from_fake_snapshot(self):
        """StatusBarApp должен читать исходное состояние только из snapshot/controller."""
        controller = FakeDictationController(make_snapshot(model_name="custom-whisper", total_tokens=456))

        app = ui_module.StatusBarApp(cast("Any", controller))

        assert "custom-whisper" in app.model_item.title
        assert "456" in app.token_usage_item.title
        assert "ru" in app.language_item.title

    def test_subscription_updates_menu_from_new_snapshot(self):
        """При новом snapshot UI должен обновить статус и заголовки без знания runtime."""
        controller = FakeDictationController(make_snapshot())
        app = ui_module.StatusBarApp(cast("Any", controller))

        controller.emit(
            make_snapshot(
                state=Config.STATUS_TRANSCRIBING,
                model_name="small",
                total_tokens=789,
                show_recording_overlay=False,
            )
        )

        assert app.title == "🧠"
        assert "small" in app.model_item.title
        assert "789" in app.token_usage_item.title
        assert app.recording_overlay_item.state == 0

    def test_ui_commands_delegate_to_fake_controller(self):
        """UI должен вызывать команды контроллера, а не runtime-модули напрямую."""
        controller = FakeDictationController(make_snapshot())
        app = ui_module.StatusBarApp(cast("Any", controller))

        app.change_language(ui_module.rumps.MenuItem("en"))
        app.toggle_recording_overlay(app.recording_overlay_item)
        app.start_app(None)
        app.stop_app(None)

        assert controller.calls == [
            ("change_language", "en"),
            ("toggle_recording_overlay", None),
            ("start_recording", None),
            ("stop_recording", None),
        ]
