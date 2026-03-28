"""Тесты StatusBarApp — menu bar приложения.

Проверяет корректность инициализации, обновления состояний,
переключения записи и отображения статусов в меню.
"""

import time

import pytest
import src.ui as ui_module


class FakeRecorder:
    """Фейковый Recorder для тестов StatusBarApp."""

    def __init__(self):
        """Инициализирует фейковый рекордер."""
        self.started = False
        self.stopped = False
        self.cancelled = False
        self.last_language = None
        self.input_device = None
        self.performance_mode = None
        self.transcriber = type(
            "TranscriberStub",
            (),
            {
                "model_name": "mlx-community/whisper-large-v3-turbo",
                "paste_cgevent_enabled": True,
                "paste_ax_enabled": False,
                "paste_clipboard_enabled": False,
                "llm_clipboard_enabled": True,
                "private_mode_enabled": False,
                "history": [],
                "history_callback": None,
                "total_tokens": 0,
                "token_usage_callback": None,
                "set_private_mode": lambda self, enabled: setattr(self, "private_mode_enabled", bool(enabled)),
            },
        )()
        self.llm_processor = type(
            "LLMProcessorStub",
            (),
            {"is_model_cached": lambda self: True, "set_performance_mode": lambda self, mode: setattr(self, "performance_mode", mode)},
        )()

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
        self.llm_processor.set_performance_mode(performance_mode)

    def start(self, language=None):
        """Имитирует начало записи."""
        self.started = True
        self.last_language = language

    def stop(self):
        """Имитирует остановку записи."""
        self.stopped = True

    def cancel(self):
        """Имитирует отмену записи."""
        self.cancelled = True


@pytest.fixture
def patched_app_module(app_module, monkeypatch):
    """Подготавливает модуль приложения с замоканными системными вызовами."""
    import src.ui as ui_module

    monkeypatch.setattr(
        ui_module,
        "list_input_devices",
        lambda: [
            {"index": 0, "name": "Built-in Microphone", "max_input_channels": 1, "default_sample_rate": 48000.0, "is_default": True},
        ],
    )
    monkeypatch.setattr(ui_module, "get_accessibility_status", lambda: True)
    monkeypatch.setattr(ui_module, "get_input_monitoring_status", lambda: True)
    monkeypatch.setattr(ui_module, "_load_microphone_profiles", lambda: [])
    monkeypatch.setattr(ui_module, "notify_user", lambda *args: None)
    return app_module


@pytest.fixture
def make_app(patched_app_module):
    """Фабрика для создания StatusBarApp с фейковым рекордером."""

    def _make(languages=None, max_time=30, secondary_key_combination=None):
        recorder = FakeRecorder()
        app = patched_app_module.StatusBarApp(
            recorder=recorder,
            model_name="mlx-community/whisper-large-v3-turbo",
            hotkey_status="левая ⌘ + ⌥",
            languages=languages,
            max_time=max_time,
            key_combination="cmd_l+alt",
            secondary_hotkey_status=(
                patched_app_module.format_hotkey_status(secondary_key_combination) if secondary_key_combination else "не задан"
            ),
            secondary_key_combination=secondary_key_combination,
        )
        return app, recorder

    return _make


class TestStatusBarInit:
    """Тесты инициализации StatusBarApp."""

    def test_initial_state_is_idle(self, make_app, patched_app_module):
        """После создания приложение в состоянии ожидания."""
        app, _ = make_app(languages=["ru"])
        assert app.state == patched_app_module.STATUS_IDLE

    def test_initial_title_is_pause_icon(self, make_app):
        """Начальная иконка — ⏯."""
        app, _ = make_app(languages=["ru"])
        assert app.title == "⏯"

    def test_model_name_in_menu(self, make_app):
        """Имя модели отображается в меню."""
        app, _ = make_app(languages=["ru"])
        assert "whisper-large-v3-turbo" in app.model_item.title

    def test_hotkey_in_menu(self, make_app):
        """Хоткей отображается в меню."""
        app, _ = make_app(languages=["ru"])
        assert "⌘" in app.hotkey_item.title

    def test_secondary_hotkey_in_menu_when_missing(self, make_app):
        """Если дополнительный хоткей не задан, это явно видно в меню."""
        app, _ = make_app(languages=["ru"])
        assert "не задан" in app.secondary_hotkey_item.title

    def test_max_time_in_menu(self, make_app):
        """Лимит длительности отображается в меню."""
        app, _ = make_app(languages=["ru"], max_time=30)
        assert "30 с" in app.max_time_item.title

    def test_language_in_menu(self, make_app):
        """Текущий язык отображается в меню."""
        app, _ = make_app(languages=["ru"])
        assert "ru" in app.language_item.title

    def test_auto_language_when_none(self, make_app):
        """Без языков показывается автоопределение."""
        app, _ = make_app(languages=None)
        assert "автоопределение" in app.language_item.title

    def test_permission_items_present(self, make_app):
        """Статусы разрешений отображаются в меню."""
        app, _ = make_app(languages=["ru"])
        assert "Accessibility" in app.accessibility_item.title
        assert "Input Monitoring" in app.input_monitoring_item.title
        assert "Microphone" in app.microphone_item.title

    def test_token_usage_item_present(self, make_app):
        """В меню отображается общий счётчик токенов."""
        app, _ = make_app(languages=["ru"])
        assert "Токены" in app.token_usage_item.title

    def test_started_is_false(self, make_app):
        """Запись не запущена при инициализации."""
        app, _ = make_app(languages=["ru"])
        assert app.started is False

    def test_input_device_in_menu(self, make_app):
        """Микрофон отображается в меню."""
        app, _ = make_app(languages=["ru"])
        assert "Built-in Microphone" in app.input_device_item.title

    def test_input_device_submenu_contains_microphones(self, make_app):
        """Полный список микрофонов вынесен в подменю выбора устройства."""
        app, _ = make_app(languages=["ru"])
        assert app.input_device_menu["[0] Built-in Microphone"].state == 1

    def test_microphone_profiles_menu_is_present(self, make_app):
        """Быстрые профили микрофона доступны отдельным подменю."""
        app, _ = make_app(languages=["ru"])
        assert app.microphone_profiles_menu["➕ Добавить текущий профиль…"].title == "➕ Добавить текущий профиль…"

    def test_recording_notification_enabled_by_default(self, make_app):
        """Уведомление о старте записи включено по умолчанию."""
        app, _ = make_app(languages=["ru"])
        assert app.show_recording_notification is True
        assert app.recording_notification_item.state == 1

    def test_llm_clipboard_enabled_by_default(self, make_app):
        """Буфер обмена для LLM включён по умолчанию."""
        app, recorder = make_app(languages=["ru"])
        assert recorder.transcriber.llm_clipboard_enabled is True
        assert app.llm_clipboard_item.state == 1


class TestStatusBarStateTransitions:
    """Тесты переключения состояний записи."""

    def test_start_sets_recording_state(self, make_app, patched_app_module):
        """Начало записи переключает состояние в recording."""
        app, recorder = make_app(languages=["ru"])
        app.start_app(None)
        assert app.state == patched_app_module.STATUS_RECORDING
        assert app.started is True
        assert recorder.started is True

    def test_start_passes_language_to_recorder(self, make_app):
        """Язык передаётся рекордеру при старте."""
        app, recorder = make_app(languages=["ru"])
        app.start_app(None)
        assert recorder.last_language == "ru"

    def test_stop_sets_transcribing_state(self, make_app, patched_app_module):
        """Остановка записи переключает состояние в transcribing."""
        app, recorder = make_app(languages=["ru"])
        app.start_app(None)
        app.stop_app(None)
        assert app.state == patched_app_module.STATUS_TRANSCRIBING
        assert app.started is False
        assert recorder.stopped is True

    def test_stop_without_start_does_nothing(self, make_app, patched_app_module):
        """Остановка без старта не меняет состояние."""
        app, recorder = make_app(languages=["ru"])
        app.stop_app(None)
        assert app.state == patched_app_module.STATUS_IDLE
        assert recorder.stopped is False

    def test_toggle_starts_when_idle(self, make_app, patched_app_module):
        """Toggle запускает запись из состояния ожидания."""
        app, recorder = make_app(languages=["ru"])
        app.toggle()
        assert app.started is True
        assert recorder.started is True

    def test_toggle_stops_when_recording(self, make_app):
        """Toggle останавливает запись из состояния записи."""
        app, recorder = make_app(languages=["ru"])
        app.toggle()
        app.toggle()
        assert app.started is False
        assert recorder.stopped is True

    def test_start_shows_notification_when_enabled(self, make_app, patched_app_module, monkeypatch):
        """При включенном флаге старт записи показывает уведомление."""
        notifications = []
        monkeypatch.setattr(ui_module, "notify_user", lambda *args: notifications.append(args))

        app, _ = make_app(languages=["ru"])
        app.show_recording_notification = True
        app.start_app(None)

        assert len(notifications) == 1
        assert notifications[0][0] == "MLX Whisper Dictation"
        assert "Запись началась" in notifications[0][1]

    def test_start_skips_notification_when_disabled(self, make_app, patched_app_module, monkeypatch):
        """При выключенном флаге старт записи не показывает уведомление."""
        notifications = []
        monkeypatch.setattr(ui_module, "notify_user", lambda *args: notifications.append(args))

        app, _ = make_app(languages=["ru"])
        app.show_recording_notification = False
        app.start_app(None)

        assert notifications == []

    def test_toggle_recording_notification_updates_flag_and_state(self, make_app):
        """Переключатель уведомления меняет флаг и состояние пункта меню."""
        app, _ = make_app(languages=["ru"])

        app.toggle_recording_notification(app.recording_notification_item)
        assert app.show_recording_notification is False
        assert app.recording_notification_item.state == 0

        app.toggle_recording_notification(app.recording_notification_item)
        assert app.show_recording_notification is True
        assert app.recording_notification_item.state == 1

    def test_toggle_recording_notification_persists_flag(self, make_app, patched_app_module, monkeypatch):
        """Флаг уведомления о записи должен сохраняться."""
        saved_values = []
        monkeypatch.setattr(ui_module, "_save_defaults_bool", lambda key, value: saved_values.append((key, value)))
        app, _ = make_app(languages=["ru"])

        app.toggle_recording_notification(app.recording_notification_item)

        assert (patched_app_module.DEFAULTS_KEY_RECORDING_NOTIFICATION, False) in saved_values


class TestStatusBarDisplay:
    """Тесты отображения иконки и статуса."""

    def test_recording_title_shows_timer(self, make_app):
        """Во время записи в заголовке показывается таймер."""
        app, _ = make_app(languages=["ru"])
        app.start_app(None)
        app.on_status_tick(None)
        assert "🔴" in app.title

    def test_transcribing_title_shows_brain(self, make_app, patched_app_module):
        """Во время распознавания отображается мозг."""
        app, _ = make_app(languages=["ru"])
        app.state = patched_app_module.STATUS_TRANSCRIBING
        app._refresh_title_and_status()
        assert app.title == "🧠"

    def test_idle_title_shows_pause(self, make_app, patched_app_module):
        """В состоянии ожидания отображается пауза."""
        app, _ = make_app(languages=["ru"])
        app.state = patched_app_module.STATUS_IDLE
        app._refresh_title_and_status()
        assert app.title == "⏯"

    def test_state_label_idle(self, make_app, patched_app_module):
        """Метка idle → ожидание."""
        app, _ = make_app(languages=["ru"])
        app.state = patched_app_module.STATUS_IDLE
        assert app._state_label() == "ожидание"

    def test_state_label_recording(self, make_app, patched_app_module):
        """Метка recording → запись."""
        app, _ = make_app(languages=["ru"])
        app.state = patched_app_module.STATUS_RECORDING
        assert app._state_label() == "запись"

    def test_state_label_transcribing(self, make_app, patched_app_module):
        """Метка transcribing → распознавание."""
        app, _ = make_app(languages=["ru"])
        app.state = patched_app_module.STATUS_TRANSCRIBING
        assert app._state_label() == "распознавание"

    def test_refresh_token_usage_item_updates_number(self, make_app):
        """Пункт меню со счётчиком токенов обновляется из transcriber."""
        app, recorder = make_app(languages=["ru"])
        recorder.transcriber.total_tokens = 12345

        app._refresh_token_usage_item()

        assert app.token_usage_item.title == "🔢 Токены: 12 345"


class TestStatusBarMaxTime:
    """Тесты автоматической остановки по лимиту."""

    def test_auto_stop_on_max_time(self, make_app, monkeypatch):
        """Запись автоматически останавливается по лимиту."""
        app, recorder = make_app(languages=["ru"], max_time=5)
        app.start_app(None)
        app.start_time = time.time() - 6
        app.on_status_tick(None)
        assert app.started is False
        assert recorder.stopped is True

    def test_no_auto_stop_before_max_time(self, make_app):
        """Запись не останавливается до лимита."""
        app, _recorder = make_app(languages=["ru"], max_time=30)
        app.start_app(None)
        app.on_status_tick(None)
        assert app.started is True

    def test_no_limit_means_no_auto_stop(self, make_app):
        """Без лимита запись не останавливается автоматически."""
        app, _recorder = make_app(languages=["ru"], max_time=None)
        app.start_app(None)
        app.start_time = time.time() - 999
        app.on_status_tick(None)
        assert app.started is True


class TestStatusBarSetState:
    """Тесты set_state и set_permission_status."""

    def test_set_state_updates_state(self, make_app, patched_app_module):
        """set_state обновляет текущее состояние."""
        app, _ = make_app(languages=["ru"])
        app.set_state(patched_app_module.STATUS_RECORDING)
        assert app.state == patched_app_module.STATUS_RECORDING

    def test_set_permission_status_updates_microphone(self, make_app):
        """set_permission_status обновляет статус микрофона."""
        app, _ = make_app(languages=["ru"])
        app.set_permission_status("microphone", True)
        assert app.permission_status["microphone"] is True

    def test_set_permission_status_updates_accessibility(self, make_app):
        """set_permission_status обновляет статус accessibility."""
        app, _ = make_app(languages=["ru"])
        app.set_permission_status("accessibility", False)
        assert app.permission_status["accessibility"] is False


class TestStatusBarMenuSelections:
    """Тесты выбора параметров через пункты меню."""

    def test_change_max_time_from_menu_updates_state(self, make_app):
        """Выбор лимита записи из меню должен обновлять max_time и заголовок."""
        app, _ = make_app(languages=["ru"], max_time=30)
        item = app._menu_item("Лимит: 60 с")

        app.change_max_time(item)

        assert app.max_time == 60
        assert "60 с" in app.max_time_item.title
        assert item.state == 1

    def test_change_max_time_persists_selection(self, make_app, patched_app_module, monkeypatch):
        """Лимит записи должен сохраняться между перезапусками."""
        saved_values = []

        def save_defaults_max_time(value):
            saved_values.append(value)

        monkeypatch.setattr(ui_module, "_save_defaults_max_time", save_defaults_max_time)
        app, _ = make_app(languages=["ru"], max_time=30)

        app.change_max_time(app._menu_item("Лимит: 60 с"))

        assert saved_values == [60]

    def test_change_model_from_menu_updates_transcriber(self, make_app):
        """Выбор модели из меню должен переключать модель в transcriber."""
        app, recorder = make_app(languages=["ru"], max_time=30)
        item = app._menu_item("Модель: whisper-turbo")

        app.change_model(item)

        assert app.model_name == "whisper-turbo"
        assert recorder.transcriber.model_name == "mlx-community/whisper-turbo"
        assert "whisper-turbo" in app.model_item.title
        assert item.state == 1

    def test_change_model_persists_selection(self, make_app, patched_app_module, monkeypatch):
        """Выбранная модель должна сохраняться в NSUserDefaults."""
        saved_values = []
        monkeypatch.setattr(ui_module, "_save_defaults_str", lambda key, value: saved_values.append((key, value)))
        app, _ = make_app(languages=["ru"], max_time=30)

        app.change_model(app._menu_item("Модель: whisper-turbo"))

        assert (patched_app_module.DEFAULTS_KEY_MODEL, "mlx-community/whisper-turbo") in saved_values

    def test_change_input_device_persists_selection(self, patched_app_module, monkeypatch):
        """Выбранный микрофон должен сохраняться в настройках."""
        saved_values = []

        def save_defaults_input_device_index(value):
            saved_values.append(value)

        monkeypatch.setattr(ui_module, "_save_defaults_input_device_index", save_defaults_input_device_index)
        monkeypatch.setattr(
            ui_module,
            "list_input_devices",
            lambda: [
                {"index": 0, "name": "Built-in Microphone", "max_input_channels": 1, "default_sample_rate": 48000.0, "is_default": True},
                {"index": 4, "name": "USB Mic", "max_input_channels": 1, "default_sample_rate": 44100.0, "is_default": False},
            ],
        )
        recorder = FakeRecorder()
        app = patched_app_module.StatusBarApp(
            recorder=recorder,
            model_name="mlx-community/whisper-large-v3-turbo",
            hotkey_status="левая ⌘ + ⌥",
            languages=["ru"],
            max_time=30,
            key_combination="cmd_l+alt",
        )

        app.change_input_device(app._menu_item("[4] USB Mic"))

        assert saved_values == [4]
        assert recorder.input_device["index"] == 4

    def test_add_current_microphone_profile_saves_current_settings(self, make_app, patched_app_module, monkeypatch):
        """Текущие настройки можно сохранить как быстрый профиль микрофона."""
        saved_profiles = []
        monkeypatch.setattr(ui_module, "prompt_text", lambda *args, **kwargs: "Звонки")
        monkeypatch.setattr(
            ui_module,
            "_save_microphone_profiles",
            lambda profiles: saved_profiles.append([dict(profile) for profile in profiles]),
        )
        app, recorder = make_app(languages=["ru"], max_time=30)
        recorder.transcriber.paste_ax_enabled = True
        recorder.transcriber.paste_clipboard_enabled = True
        recorder.transcriber.llm_clipboard_enabled = False

        app.add_current_microphone_profile(None)

        assert app.microphone_profiles[0]["name"] == "Звонки"
        assert app.microphone_profiles_menu["Звонки"].state == 1
        assert saved_profiles[-1][0]["input_device_index"] == 0
        assert saved_profiles[-1][0]["paste_ax"] is True
        assert saved_profiles[-1][0]["paste_clipboard"] is True
        assert saved_profiles[-1][0]["llm_clipboard"] is False

    def test_apply_microphone_profile_updates_basic_settings(self, patched_app_module, monkeypatch):
        """Профиль микрофона должен применять устройство и базовые настройки."""
        saved_device_indexes = []
        saved_strings = []
        saved_bools = []
        saved_max_times = []

        def save_defaults_str(key, value):
            saved_strings.append((key, value))

        def save_defaults_bool(key, value):
            saved_bools.append((key, value))

        monkeypatch.setattr(
            ui_module,
            "list_input_devices",
            lambda: [
                {"index": 0, "name": "Built-in Microphone", "max_input_channels": 1, "default_sample_rate": 48000.0, "is_default": True},
                {"index": 4, "name": "USB Mic", "max_input_channels": 1, "default_sample_rate": 44100.0, "is_default": False},
            ],
        )
        monkeypatch.setattr(
            ui_module,
            "_load_microphone_profiles",
            lambda: [
                {
                    "name": "Встречи",
                    "input_device_index": 4,
                    "input_device_name": "USB Mic",
                    "model_repo": "mlx-community/whisper-turbo",
                    "language": "ru",
                    "max_time": 60,
                    "performance_mode": patched_app_module.PERFORMANCE_MODE_FAST,
                    "private_mode": True,
                    "paste_cgevent": False,
                    "paste_ax": True,
                    "paste_clipboard": True,
                    "llm_clipboard": False,
                },
            ],
        )
        monkeypatch.setattr(ui_module, "_save_defaults_input_device_index", saved_device_indexes.append)
        monkeypatch.setattr(ui_module, "_save_defaults_str", save_defaults_str)
        monkeypatch.setattr(ui_module, "_save_defaults_bool", save_defaults_bool)
        monkeypatch.setattr(ui_module, "_save_defaults_max_time", saved_max_times.append)

        recorder = FakeRecorder()
        app = patched_app_module.StatusBarApp(
            recorder=recorder,
            model_name="mlx-community/whisper-large-v3-turbo",
            hotkey_status="левая ⌘ + ⌥",
            languages=["ru"],
            max_time=30,
            key_combination="cmd_l+alt",
        )

        app.apply_microphone_profile(app.microphone_profiles_menu["Встречи"])

        assert recorder.input_device["index"] == 4
        assert app.model_name == "whisper-turbo"
        assert app.max_time == 60
        assert app.performance_mode == patched_app_module.PERFORMANCE_MODE_FAST
        assert recorder.transcriber.private_mode_enabled is True
        assert recorder.transcriber.paste_cgevent_enabled is False
        assert recorder.transcriber.paste_ax_enabled is True
        assert recorder.transcriber.paste_clipboard_enabled is True
        assert recorder.transcriber.llm_clipboard_enabled is False
        assert saved_device_indexes == [4]
        assert (patched_app_module.DEFAULTS_KEY_MODEL, "mlx-community/whisper-turbo") in saved_strings
        assert (patched_app_module.DEFAULTS_KEY_PERFORMANCE_MODE, patched_app_module.PERFORMANCE_MODE_FAST) in saved_strings
        assert saved_max_times == [60]
        assert (patched_app_module.DEFAULTS_KEY_PASTE_CGEVENT, False) in saved_bools
        assert (patched_app_module.DEFAULTS_KEY_PASTE_AX, True) in saved_bools
        assert (patched_app_module.DEFAULTS_KEY_PASTE_CLIPBOARD, True) in saved_bools
        assert (patched_app_module.DEFAULTS_KEY_LLM_CLIPBOARD, False) in saved_bools

    def test_toggle_llm_clipboard_updates_transcriber_and_defaults(self, make_app, patched_app_module, monkeypatch):
        """Переключатель LLM-буфера должен менять runtime-state и сохраняться."""
        saved_bools = []
        monkeypatch.setattr(ui_module, "_save_defaults_bool", lambda key, value: saved_bools.append((key, value)))
        app, recorder = make_app(languages=["ru"])

        app.toggle_llm_clipboard(app.llm_clipboard_item)

        assert recorder.transcriber.llm_clipboard_enabled is False
        assert app.llm_clipboard_item.state == 0
        assert (patched_app_module.DEFAULTS_KEY_LLM_CLIPBOARD, False) in saved_bools

    def test_delete_microphone_profile_removes_it(self, patched_app_module, monkeypatch):
        """Сохранённый профиль можно удалить из подменю быстрых профилей."""
        saved_profiles = []
        monkeypatch.setattr(
            ui_module,
            "_load_microphone_profiles",
            lambda: [
                {
                    "name": "Встречи",
                    "input_device_index": 0,
                    "input_device_name": "Built-in Microphone",
                    "model_repo": "mlx-community/whisper-large-v3-turbo",
                    "language": "ru",
                    "max_time": 30,
                    "performance_mode": patched_app_module.PERFORMANCE_MODE_NORMAL,
                    "private_mode": False,
                    "paste_cgevent": True,
                    "paste_ax": False,
                    "paste_clipboard": False,
                },
            ],
        )
        monkeypatch.setattr(
            ui_module,
            "_save_microphone_profiles",
            lambda profiles: saved_profiles.append([dict(profile) for profile in profiles]),
        )

        recorder = FakeRecorder()
        app = patched_app_module.StatusBarApp(
            recorder=recorder,
            model_name="mlx-community/whisper-large-v3-turbo",
            hotkey_status="левая ⌘ + ⌥",
            languages=["ru"],
            max_time=30,
            key_combination="cmd_l+alt",
        )

        app.delete_microphone_profile(app.microphone_profiles_menu["🗑 Удалить профиль"]["Встречи"])

        assert app.microphone_profiles == []
        assert saved_profiles[-1] == []

    def test_change_performance_mode_updates_recorder_and_menu(self, make_app, patched_app_module, monkeypatch):
        """Смена режима должна обновлять рекордер и сохраняться."""
        saved_values = []
        monkeypatch.setattr(ui_module, "_save_defaults_str", lambda key, value: saved_values.append((key, value)))
        app, recorder = make_app(languages=["ru"], max_time=30)

        app.change_performance_mode(app.performance_menu["Быстрый"])

        assert app.performance_mode == patched_app_module.PERFORMANCE_MODE_FAST
        assert recorder.performance_mode == patched_app_module.PERFORMANCE_MODE_FAST
        assert "Быстрый" in app.performance_menu.title
        assert (patched_app_module.DEFAULTS_KEY_PERFORMANCE_MODE, patched_app_module.PERFORMANCE_MODE_FAST) in saved_values

    def test_change_llm_prompt_persists_selection(self, make_app, patched_app_module, monkeypatch):
        """Выбор LLM-промпта должен сохраняться и применяться к рекордеру."""
        saved_values = []
        monkeypatch.setattr(ui_module, "_save_defaults_str", lambda key, value: saved_values.append((key, value)))
        app, recorder = make_app(languages=["ru"], max_time=30)

        app._change_llm_prompt(app.llm_prompt_menu["Исправь текст"])

        assert app.llm_prompt_name == "Исправь текст"
        assert recorder.llm_system_prompt == patched_app_module.LLM_PROMPT_PRESETS["Исправь текст"]
        assert (patched_app_module.DEFAULTS_KEY_LLM_PROMPT, "Исправь текст") in saved_values


class TestStatusBarHotkeys:
    """Тесты изменения основного и дополнительного хоткеев."""

    def test_change_secondary_hotkey_updates_menu_and_listener(self, make_app, patched_app_module, monkeypatch):
        """Изменение дополнительного хоткея должно обновить меню и runtime listener."""
        app, _ = make_app(languages=["ru"])
        calls = []

        class ListenerStub:
            def update_key_combinations(self, combinations):
                calls.append(combinations)

        monkeypatch.setattr(ui_module, "capture_hotkey_combination", lambda *args, **kwargs: "ctrl+shift+space")
        monkeypatch.setattr(ui_module, "notify_user", lambda *args: None)
        app.key_listener = ListenerStub()

        app.change_secondary_hotkey(None)

        assert app._secondary_key_combination == "ctrl+shift+space"
        assert "Space" in app.secondary_hotkey_item.title
        assert calls == [["cmd_l+alt", "ctrl+shift+space"]]

    def test_change_secondary_hotkey_persists_value(self, make_app, patched_app_module, monkeypatch):
        """Изменение дополнительного хоткея должно сохраняться."""
        saved_values = []

        class ListenerStub:
            def update_key_combinations(self, _combinations):
                return None

        monkeypatch.setattr(ui_module, "capture_hotkey_combination", lambda *args, **kwargs: "ctrl+shift+space")
        monkeypatch.setattr(ui_module, "notify_user", lambda *args: None)
        monkeypatch.setattr(ui_module, "_save_defaults_str", lambda key, value: saved_values.append((key, value)))
        app, _ = make_app(languages=["ru"])
        app.key_listener = ListenerStub()

        app.change_secondary_hotkey(None)

        assert (patched_app_module.DEFAULTS_KEY_PRIMARY_HOTKEY, "cmd_l+alt") in saved_values
        assert (patched_app_module.DEFAULTS_KEY_SECONDARY_HOTKEY, "ctrl+shift+space") in saved_values

    def test_change_secondary_hotkey_can_disable_it(self, make_app, patched_app_module, monkeypatch):
        """Пустое значение должно отключать дополнительный хоткей."""
        app, _ = make_app(languages=["ru"], secondary_key_combination="ctrl+shift+space")
        calls = []

        class ListenerStub:
            def update_key_combinations(self, combinations):
                calls.append(combinations)

        monkeypatch.setattr(ui_module, "capture_hotkey_combination", lambda *args, **kwargs: "")
        monkeypatch.setattr(ui_module, "notify_user", lambda *args: None)
        app.key_listener = ListenerStub()

        app.change_secondary_hotkey(None)

        assert app._secondary_key_combination == ""
        assert "не задан" in app.secondary_hotkey_item.title
        assert calls == [["cmd_l+alt"]]

    def test_change_llm_hotkey_persists_value(self, make_app, patched_app_module, monkeypatch):
        """Изменение LLM-хоткея должно сохраняться."""
        saved_values = []
        monkeypatch.setattr(ui_module, "capture_hotkey_combination", lambda *args, **kwargs: "ctrl+shift+l")
        monkeypatch.setattr(ui_module, "notify_user", lambda *args: None)
        monkeypatch.setattr(
            ui_module,
            "GlobalKeyListener",
            lambda *_args, **_kwargs: type("Listener", (), {"start": lambda self: None, "stop": lambda self: None})(),
        )
        monkeypatch.setattr(ui_module, "_save_defaults_str", lambda key, value: saved_values.append((key, value)))
        app, _ = make_app(languages=["ru"])

        app.change_llm_hotkey(None)

        assert (patched_app_module.DEFAULTS_KEY_LLM_HOTKEY, "ctrl+shift+l") in saved_values


class TestCancelRecording:
    """Тесты отмены записи через Escape и cancel_recording."""

    def test_cancel_recording_resets_state_to_idle(self, make_app, patched_app_module):
        """cancel_recording должен переключить состояние в idle."""
        app, _ = make_app(languages=["ru"])
        app.start_app(None)

        app.cancel_recording()

        assert app.state == patched_app_module.STATUS_IDLE
        assert app.started is False

    def test_cancel_recording_calls_recorder_cancel(self, make_app):
        """cancel_recording должен вызвать recorder.cancel()."""
        app, recorder = make_app(languages=["ru"])
        app.start_app(None)

        app.cancel_recording()

        assert recorder.cancelled is True

    def test_cancel_recording_ignored_when_not_started(self, make_app, patched_app_module):
        """cancel_recording не должен ничего делать, если запись не запущена."""
        app, recorder = make_app(languages=["ru"])

        app.cancel_recording()

        assert app.state == patched_app_module.STATUS_IDLE
        assert recorder.cancelled is False

    def test_cancel_recording_updates_menu_items(self, make_app):
        """cancel_recording должен переключить доступность пунктов меню."""
        app, _ = make_app(languages=["ru"])
        app.start_app(None)

        app.cancel_recording()

        # После отмены «Начать запись» снова доступна, а «Остановить запись» — нет
        start_item = app._menu_item("Начать запись")
        stop_item = app._menu_item("Остановить запись")
        assert start_item.callback is not None
        assert stop_item.callback is None

    def test_cancel_recording_sets_idle_title(self, make_app, patched_app_module):
        """cancel_recording должен вернуть иконку ⏯ в строке меню."""
        app, _ = make_app(languages=["ru"])
        app.start_app(None)

        app.cancel_recording()
        app._refresh_title_and_status()

        assert app.title == "⏯"

    def test_escape_key_triggers_cancel_when_recording(self, make_app):
        """Нажатие Escape должно отменить запись, если она запущена."""
        app, recorder = make_app(languages=["ru"])
        app.start_app(None)

        class FakeEvent:
            def keyCode(self):
                return 53  # _KEYCODE_ESCAPE

        app._handle_escape_key(FakeEvent())

        assert app.started is False
        assert recorder.cancelled is True

    def test_escape_key_ignored_when_not_recording(self, make_app, patched_app_module):
        """Нажатие Escape не должно ничего делать, если запись не запущена."""
        app, recorder = make_app(languages=["ru"])

        class FakeEvent:
            def keyCode(self):
                return 53  # _KEYCODE_ESCAPE

        app._handle_escape_key(FakeEvent())

        assert app.state == patched_app_module.STATUS_IDLE
        assert recorder.cancelled is False

    def test_non_escape_key_ignored(self, make_app):
        """Нажатие не-Escape клавиши не должно отменять запись."""
        app, recorder = make_app(languages=["ru"])
        app.start_app(None)

        class FakeEvent:
            def keyCode(self):
                return 0  # not Escape

        app._handle_escape_key(FakeEvent())

        assert app.started is True
        assert recorder.cancelled is False


class TestRecordingOverlay:
    """Тесты RecordingOverlay — всплывающего индикатора записи у курсора."""

    def test_initial_state_not_visible(self, patched_app_module):
        """После создания overlay не показан."""
        overlay = patched_app_module.RecordingOverlay()
        assert overlay.is_visible is False
        assert overlay._window is None
        assert overlay._label is None

    def test_hide_when_not_visible(self, patched_app_module):
        """Повторный hide без show не вызывает ошибок."""
        overlay = patched_app_module.RecordingOverlay()
        overlay.hide()
        assert overlay.is_visible is False

    def test_update_time_without_label(self, patched_app_module):
        """update_time без показа окна не вызывает ошибок."""
        overlay = patched_app_module.RecordingOverlay()
        overlay.update_time(42)
        assert overlay.is_visible is False


class TestRecordingOverlayIntegration:
    """Тесты интеграции RecordingOverlay в StatusBarApp."""

    def test_overlay_initialized_in_app(self, make_app, patched_app_module):
        """StatusBarApp создаёт экземпляр RecordingOverlay."""
        app, _ = make_app(languages=["ru"])
        assert hasattr(app, "recording_overlay")
        assert isinstance(app.recording_overlay, patched_app_module.RecordingOverlay)

    def test_overlay_enabled_by_default(self, make_app):
        """По умолчанию индикатор записи у курсора включён."""
        app, _ = make_app(languages=["ru"])
        assert app.show_recording_overlay is True
        assert app.recording_overlay_item.state == 1

    def test_overlay_menu_item_exists(self, make_app):
        """В меню есть пункт для переключения индикатора записи."""
        app, _ = make_app(languages=["ru"])
        assert "🎯 Индикатор записи у курсора" in app.recording_overlay_item.title

    def test_toggle_recording_overlay_off(self, make_app, monkeypatch):
        """toggle_recording_overlay выключает индикатор."""
        import src.config as config_module

        saved = {}
        monkeypatch.setattr(ui_module, "_save_defaults_bool", lambda k, v: saved.update({k: v}))

        app, _ = make_app(languages=["ru"])
        assert app.show_recording_overlay is True

        app.toggle_recording_overlay(app.recording_overlay_item)

        assert app.show_recording_overlay is False
        assert app.recording_overlay_item.state == 0
        assert saved.get(config_module.DEFAULTS_KEY_RECORDING_OVERLAY) is False

    def test_toggle_recording_overlay_on(self, make_app, monkeypatch):
        """toggle_recording_overlay включает индикатор обратно."""
        import src.config as config_module

        saved = {}
        monkeypatch.setattr(config_module, "_save_defaults_bool", lambda k, v: saved.update({k: v}))

        app, _ = make_app(languages=["ru"])
        app.show_recording_overlay = False

        app.toggle_recording_overlay(app.recording_overlay_item)

        assert app.show_recording_overlay is True
        assert app.recording_overlay_item.state == 1

    def test_start_app_shows_overlay_when_enabled(self, make_app, monkeypatch):
        """start_app вызывает overlay.show(), когда индикатор включён."""
        app, _ = make_app(languages=["ru"])
        app.show_recording_overlay = True

        show_called = []
        monkeypatch.setattr(app.recording_overlay, "show", lambda: show_called.append(True))

        app.start_app(None)

        assert len(show_called) == 1

    def test_start_app_does_not_show_overlay_when_disabled(self, make_app, monkeypatch):
        """start_app не вызывает overlay.show(), когда индикатор выключен."""
        app, _ = make_app(languages=["ru"])
        app.show_recording_overlay = False

        show_called = []
        monkeypatch.setattr(app.recording_overlay, "show", lambda: show_called.append(True))

        app.start_app(None)

        assert len(show_called) == 0

    def test_stop_app_hides_overlay(self, make_app, monkeypatch):
        """stop_app вызывает overlay.hide()."""
        app, _ = make_app(languages=["ru"])
        app.start_app(None)

        hide_called = []
        monkeypatch.setattr(app.recording_overlay, "hide", lambda: hide_called.append(True))

        app.stop_app(None)

        assert len(hide_called) == 1

    def test_cancel_recording_hides_overlay(self, make_app, monkeypatch):
        """cancel_recording вызывает overlay.hide()."""
        app, _ = make_app(languages=["ru"])
        app.start_app(None)

        hide_called = []
        monkeypatch.setattr(app.recording_overlay, "hide", lambda: hide_called.append(True))

        app.cancel_recording()

        assert len(hide_called) == 1

    def test_on_status_tick_updates_overlay_time(self, make_app, monkeypatch):
        """on_status_tick вызывает overlay.update_time() при записи."""
        app, _ = make_app(languages=["ru"])
        app.start_app(None)

        updated_times = []
        monkeypatch.setattr(app.recording_overlay, "update_time", updated_times.append)

        app.on_status_tick(None)

        assert len(updated_times) == 1
