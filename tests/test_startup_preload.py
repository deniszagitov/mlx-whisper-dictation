from types import SimpleNamespace


class FakeStartupModelManager:
    def __init__(self):
        self.calls = []

    def preload_selected_models(self, **kwargs):
        self.calls.append(("selected", kwargs))

    def preload_asr_model(self, model_name):
        self.calls.append(("asr", model_name))

    def preload_llm_model(self, model_name):
        self.calls.append(("llm", model_name))

    def preload_tts_model(self, model_name):
        self.calls.append(("tts", model_name))


def test_startup_preload_loads_only_configured_tts_model(app_module):
    manager = FakeStartupModelManager()
    app_controller = SimpleNamespace(reader_tts_mlx_model="mlx-community/Qwen3-TTS")

    app_module._preload_startup_models(model_manager=manager, app_controller=app_controller)

    assert manager.calls == [("tts", "mlx-community/Qwen3-TTS")]
