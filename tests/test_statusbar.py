"""Тесты StatusBarApp — menu bar приложения.

Проверяет корректность инициализации, обновления состояний,
переключения записи и отображения статусов в меню.
"""

import time

import pytest


class FakeRecorder:
    """Фейковый Recorder для тестов StatusBarApp."""

    def __init__(self):
        """Инициализирует фейковый рекордер."""
        self.started = False
        self.stopped = False
        self.last_language = None
        self.input_device = None
        self.transcriber = type(
            "TranscriberStub",
            (),
            {
                "model_name": "mlx-community/whisper-large-v3-turbo",
                "paste_cgevent_enabled": True,
                "paste_ax_enabled": False,
                "paste_clipboard_enabled": False,
                "history": [],
                "history_callback": None,
            },
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

    def start(self, language=None):
        """Имитирует начало записи."""
        self.started = True
        self.last_language = language

    def stop(self):
        """Имитирует остановку записи."""
        self.stopped = True


@pytest.fixture
def patched_app_module(app_module, monkeypatch):
    """Подготавливает модуль приложения с замоканными системными вызовами."""
    monkeypatch.setattr(
        app_module,
        "list_input_devices",
        lambda: [
            {"index": 0, "name": "Built-in Microphone", "max_input_channels": 1, "default_sample_rate": 48000.0, "is_default": True},
        ],
    )
    monkeypatch.setattr(app_module, "get_accessibility_status", lambda: True)
    monkeypatch.setattr(app_module, "get_input_monitoring_status", lambda: True)
    monkeypatch.setattr(app_module, "notify_user", lambda *args: None)
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

    def test_started_is_false(self, make_app):
        """Запись не запущена при инициализации."""
        app, _ = make_app(languages=["ru"])
        assert app.started is False

    def test_input_device_in_menu(self, make_app):
        """Микрофон отображается в меню."""
        app, _ = make_app(languages=["ru"])
        assert "Built-in Microphone" in app.input_device_item.title

    def test_recording_notification_enabled_by_default(self, make_app):
        """Уведомление о старте записи включено по умолчанию."""
        app, _ = make_app(languages=["ru"])
        assert app.show_recording_notification is True
        assert app.recording_notification_item.state == 1


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
        monkeypatch.setattr(patched_app_module, "notify_user", lambda *args: notifications.append(args))

        app, _ = make_app(languages=["ru"])
        app.show_recording_notification = True
        app.start_app(None)

        assert len(notifications) == 1
        assert notifications[0][0] == "MLX Whisper Dictation"
        assert "Запись началась" in notifications[0][1]

    def test_start_skips_notification_when_disabled(self, make_app, patched_app_module, monkeypatch):
        """При выключенном флаге старт записи не показывает уведомление."""
        notifications = []
        monkeypatch.setattr(patched_app_module, "notify_user", lambda *args: notifications.append(args))

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

    def test_change_model_from_menu_updates_transcriber(self, make_app):
        """Выбор модели из меню должен переключать модель в transcriber."""
        app, recorder = make_app(languages=["ru"], max_time=30)
        item = app._menu_item("Модель: whisper-turbo")

        app.change_model(item)

        assert app.model_name == "whisper-turbo"
        assert recorder.transcriber.model_name == "mlx-community/whisper-turbo"
        assert "whisper-turbo" in app.model_item.title
        assert item.state == 1


class TestStatusBarHotkeys:
    """Тесты изменения основного и дополнительного хоткеев."""

    def test_change_secondary_hotkey_updates_menu_and_listener(self, make_app, patched_app_module, monkeypatch):
        """Изменение дополнительного хоткея должно обновить меню и runtime listener."""
        app, _ = make_app(languages=["ru"])
        calls = []

        class ListenerStub:
            def update_key_combinations(self, combinations):
                calls.append(combinations)

        monkeypatch.setattr(patched_app_module, "capture_hotkey_combination", lambda *args, **kwargs: "ctrl+shift+space")
        monkeypatch.setattr(patched_app_module, "notify_user", lambda *args: None)
        app.key_listener = ListenerStub()

        app.change_secondary_hotkey(None)

        assert app._secondary_key_combination == "ctrl+shift+space"
        assert "Space" in app.secondary_hotkey_item.title
        assert calls == [["cmd_l+alt", "ctrl+shift+space"]]

    def test_change_secondary_hotkey_can_disable_it(self, make_app, patched_app_module, monkeypatch):
        """Пустое значение должно отключать дополнительный хоткей."""
        app, _ = make_app(languages=["ru"], secondary_key_combination="ctrl+shift+space")
        calls = []

        class ListenerStub:
            def update_key_combinations(self, combinations):
                calls.append(combinations)

        monkeypatch.setattr(patched_app_module, "capture_hotkey_combination", lambda *args, **kwargs: "")
        monkeypatch.setattr(patched_app_module, "notify_user", lambda *args: None)
        app.key_listener = ListenerStub()

        app.change_secondary_hotkey(None)

        assert app._secondary_key_combination == ""
        assert "не задан" in app.secondary_hotkey_item.title
        assert calls == [["cmd_l+alt"]]
