"""Диагностический скрипт для поиска зависания."""
import importlib.util
import unittest.mock as mock

spec = importlib.util.spec_from_file_location("wda", "whisper-dictation.py")
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
print("Module loaded")


class FakeRecorder:
    def __init__(self):
        self.transcriber = type("T", (), {"model_name": "x"})()

    def set_status_callback(self, cb):
        pass

    def set_permission_callback(self, cb):
        pass

    def set_input_device(self, d):
        pass

    def start(self, l=None):
        pass

    def stop(self):
        pass


devices = [{"index": 0, "name": "M", "max_input_channels": 1, "default_sample_rate": 48000.0, "is_default": True}]

with mock.patch.object(mod, "list_input_devices", return_value=devices):
    with mock.patch.object(mod, "get_accessibility_status", return_value=True):
        with mock.patch.object(mod, "get_input_monitoring_status", return_value=True):
            with mock.patch.object(mod, "notify_user", return_value=None):
                print("Creating StatusBarApp...")
                app = mod.StatusBarApp(
                    recorder=FakeRecorder(),
                    model_name="test/model",
                    hotkey_status="test",
                    languages=["ru"],
                    max_time=30,
                    key_combination="cmd_l+alt",
                    secondary_hotkey_status="not set",
                    secondary_key_combination=None,
                )
                print(f"StatusBarApp created: {app.title}")
