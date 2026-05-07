"""Интеграционные тесты reader wiring через hotkey dispatcher."""

from typing import Any, cast

import src.app as app_module
from src.domain.constants import Config
from src.domain.reader_types import ClipboardContent
from src.domain.types import LaunchConfig
from src.infrastructure.hotkeys import MODIFIER_FLAG_MASKS, HotkeyDispatcher


class FakeRecorder:
    """Минимальный recorder для DictationApp."""

    def set_status_callback(self, _callback):
        return None

    def set_permission_callback(self, _callback):
        return None

    def set_input_device(self, _device_info):
        return None

    def start(self, language=None, on_audio_ready=None):
        return None

    def stop(self):
        return None

    def cancel(self):
        return None


class FakeTranscriber:
    """Минимальный transcriber для DictationApp."""

    def __init__(self):
        self.model_name = Config.DEFAULT_MODEL_NAME
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


class FakeLLM:
    """Фейковый LLM gateway для reader."""

    last_token_usage = 0
    download_progress_callback = None

    def __init__(self):
        self.performance_mode = None
        self.calls = []

    def is_model_cached(self):
        return True

    def set_performance_mode(self, mode):
        self.performance_mode = mode

    def process_text(self, text, system_prompt, *, context=None, max_tokens=None):
        self.calls.append((text, system_prompt, context, max_tokens))
        return "один два"

    def ensure_model_downloaded(self):
        return None

    def change_model(self, model_name):
        self.model_name = model_name


class FakeReaderClipboard:
    """Фейковый reader clipboard."""

    def read_content(self):
        return ClipboardContent("сырой текст", has_text_type=True)


class FakeRSVPDisplay:
    """Фейковый RSVP display."""

    def __init__(self):
        self.frames = []
        self.running = False

    def show_frames(self, frames, _config):
        self.frames = frames
        self.running = True

    def close(self):
        self.running = False

    def is_running(self):
        return self.running

    def handle_key(self, key_name):
        if key_name == "esc":
            self.close()
            return True
        return False


class FakeTTS:
    """Фейковый TTS."""

    def speak(self, _text, _config):
        return None

    def stop(self):
        return None

    def is_speaking(self):
        return False

    def available_voices(self):
        return []

    def set_keep_model_loaded(self, _enabled):
        return None


class ImmediateThread:
    """Тестовый Thread, сразу выполняющий target."""

    def __init__(self, *, target: Any, daemon: bool) -> None:
        self._target = target
        self.daemon = daemon
        self._alive = False

    def start(self):
        self._alive = True
        try:
            self._target()
        finally:
            self._alive = False

    def is_alive(self):
        return self._alive


class FakeEvent:
    """Фейковый NSEvent."""

    def __init__(self, key_code, characters="", modifier_flags=0):
        self._key_code = key_code
        self._characters = characters
        self._modifier_flags = modifier_flags

    def keyCode(self):
        return self._key_code

    def charactersIgnoringModifiers(self):
        return self._characters

    def modifierFlags(self):
        return self._modifier_flags


def test_rsvp_hotkey_dispatches_to_reader_use_case(monkeypatch):
    monkeypatch.setattr(app_module.threading, "Thread", ImmediateThread)
    settings_store = app_module._InMemorySettingsStore()
    notifications = []
    display = FakeRSVPDisplay()
    llm = FakeLLM()
    controller = app_module.DictationApp(
        recorder=cast("Any", FakeRecorder()),
        transcriber=cast("Any", FakeTranscriber()),
        llm_processor=cast("Any", llm),
        launch_config=LaunchConfig.from_sources(
            model=Config.DEFAULT_MODEL_NAME,
            language=["ru"],
            max_time=30,
            llm_model=Config.DEFAULT_LLM_MODEL_NAME,
            key_combination="ctrl+shift+d",
            secondary_key_combination=None,
            llm_key_combination=None,
        ),
        system_integration_service=app_module.SystemIntegrationService(
            notify=lambda title, message: notifications.append((title, message)),
            get_accessibility_status=lambda: True,
            get_input_monitoring_status=lambda: True,
            request_accessibility_permission=lambda: True,
            request_input_monitoring_permission=lambda: True,
            warn_missing_accessibility_permission=lambda: None,
            warn_missing_input_monitoring_permission=lambda: None,
            open_path=lambda _path: True,
        ),
        reader_clipboard=FakeReaderClipboard(),
        rsvp_display=cast("Any", display),
        tts_speaker=cast("Any", FakeTTS()),
        settings_store=cast("Any", settings_store),
    )
    dispatcher = HotkeyDispatcher(controller)
    dispatcher.pressed_modifier_names = {"cmd_l", "alt_l"}

    handled = dispatcher._handle_key_down(
        FakeEvent(
            15,
            "r",
            modifier_flags=MODIFIER_FLAG_MASKS["cmd_l"] | MODIFIER_FLAG_MASKS["alt_l"],
        )
    )

    assert handled is True
    assert [frame.text for frame in display.frames] == ["один два"]
    assert llm.calls
    assert notifications == []


def test_rsvp_hotkey_with_primary_modifier_prefix_does_not_start_dictation(monkeypatch):
    monkeypatch.setattr(app_module.threading, "Thread", ImmediateThread)
    settings_store = app_module._InMemorySettingsStore()
    display = FakeRSVPDisplay()
    llm = FakeLLM()
    controller = app_module.DictationApp(
        recorder=cast("Any", FakeRecorder()),
        transcriber=cast("Any", FakeTranscriber()),
        llm_processor=cast("Any", llm),
        launch_config=LaunchConfig.from_sources(
            model=Config.DEFAULT_MODEL_NAME,
            language=["ru"],
            max_time=30,
            llm_model=Config.DEFAULT_LLM_MODEL_NAME,
            key_combination="cmd_l+alt",
            secondary_key_combination=None,
            llm_key_combination=None,
        ),
        reader_clipboard=FakeReaderClipboard(),
        rsvp_display=cast("Any", display),
        tts_speaker=cast("Any", FakeTTS()),
        settings_store=cast("Any", settings_store),
    )
    dispatcher = HotkeyDispatcher(controller)
    dispatcher.pressed_modifier_names = {"cmd_l"}

    modifier_handled = dispatcher._handle_flags_changed(
        FakeEvent(
            58,
            modifier_flags=MODIFIER_FLAG_MASKS["cmd_l"] | MODIFIER_FLAG_MASKS["alt_l"],
        )
    )
    key_handled = dispatcher._handle_key_down(
        FakeEvent(
            15,
            "r",
            modifier_flags=MODIFIER_FLAG_MASKS["cmd_l"] | MODIFIER_FLAG_MASKS["alt_l"],
        )
    )

    assert modifier_handled is True
    assert key_handled is True
    assert display.frames
    assert controller.started is False
