"""Тесты истории распознанного текста: добавление, лимит, persistence, callback."""

import sys

import pytest

import transcriber as transcriber_module


def make_transcriber(app_module, diagnostics_enabled=False):
    """Создает transcriber с отключённой диагностикой для тестов."""
    diagnostics_store = app_module.DiagnosticsStore(root_dir=app_module.LOG_DIR, enabled=diagnostics_enabled)
    return app_module.SpeechTranscriber("dummy-model", diagnostics_store=diagnostics_store)


# ---------------------------------------------------------------------------
# _add_to_history
# ---------------------------------------------------------------------------


@pytest.mark.skipif(sys.platform != "darwin", reason="NSUserDefaults только на macOS")
class TestAddToHistory:
    """Тесты _add_to_history."""

    def test_inserts_at_front(self, app_module, monkeypatch):
        """Новый текст добавляется в начало списка."""
        transcriber = make_transcriber(app_module)
        transcriber.history = ["первый"]
        monkeypatch.setattr(transcriber_module, "_save_defaults_list", lambda *_: None)

        transcriber._add_to_history("второй")

        assert transcriber.history[0] == "второй"
        assert transcriber.history[1] == "первый"

    def test_caps_at_max_size(self, app_module, monkeypatch):
        """История не превышает MAX_HISTORY_SIZE записей."""
        transcriber = make_transcriber(app_module)
        transcriber.history = [f"text_{i}" for i in range(app_module.MAX_HISTORY_SIZE)]
        monkeypatch.setattr(transcriber_module, "_save_defaults_list", lambda *_: None)

        transcriber._add_to_history("overflow")

        assert len(transcriber.history) == app_module.MAX_HISTORY_SIZE
        assert transcriber.history[0] == "overflow"
        # Последний элемент старого списка должен быть вытеснен
        assert f"text_{app_module.MAX_HISTORY_SIZE - 1}" not in transcriber.history

    def test_persists_to_nsuserdefaults(self, app_module, monkeypatch):
        """История сохраняется через _save_defaults_list с правильным ключом."""
        transcriber = make_transcriber(app_module)
        transcriber.history = []
        saved = []

        monkeypatch.setattr(
            transcriber_module,
            "_save_defaults_list",
            lambda key, value: saved.append((key, list(value))),
        )

        transcriber._add_to_history("тест")

        assert len(saved) == 1
        assert saved[0][0] == app_module.DEFAULTS_KEY_HISTORY
        assert saved[0][1] == ["тест"]

    def test_does_not_persist_history_in_private_mode(self, app_module, monkeypatch):
        """В private mode история остаётся только в памяти текущей сессии."""
        transcriber = make_transcriber(app_module)
        transcriber.history = []
        transcriber.private_mode_enabled = True
        saved = []

        monkeypatch.setattr(
            transcriber_module,
            "_save_defaults_list",
            lambda key, value: saved.append((key, list(value))),
        )

        transcriber._add_to_history("секрет")

        assert transcriber.history == ["секрет"]
        assert saved == []

    def test_private_mode_starts_with_empty_history(self, app_module, monkeypatch):
        """При активном private mode история не должна подниматься из defaults."""
        monkeypatch.setattr(
            transcriber_module,
            "_load_defaults_bool",
            lambda key, fallback: True if key == app_module.DEFAULTS_KEY_PRIVATE_MODE else fallback,
        )
        monkeypatch.setattr(transcriber_module, "_load_defaults_list", lambda *_args: ["старый текст"])

        transcriber = make_transcriber(app_module)

        assert transcriber.private_mode_enabled is True
        assert transcriber.history == []

    def test_set_private_mode_reloads_persisted_history_when_disabled(self, app_module, monkeypatch):
        """После выключения private mode история снова загружается из defaults."""
        transcriber = make_transcriber(app_module)
        transcriber.history = ["секрет"]
        callback_calls = []
        saved_flags = []
        transcriber.history_callback = lambda: callback_calls.append(True)

        monkeypatch.setattr(transcriber_module, "_save_defaults_bool", lambda key, value: saved_flags.append((key, value)))
        monkeypatch.setattr(transcriber_module, "_load_defaults_list", lambda *_args: ["обычная история"])

        transcriber.set_private_mode(True)
        assert transcriber.history == []

        transcriber.set_private_mode(False)

        assert transcriber.history == ["обычная история"]
        assert saved_flags == [
            (app_module.DEFAULTS_KEY_PRIVATE_MODE, True),
            (app_module.DEFAULTS_KEY_PRIVATE_MODE, False),
        ]
        assert callback_calls == [True, True]

    def test_calls_callback(self, app_module, monkeypatch):
        """history_callback вызывается при добавлении записи."""
        transcriber = make_transcriber(app_module)
        transcriber.history = []
        callback_calls = []
        transcriber.history_callback = lambda: callback_calls.append(True)
        monkeypatch.setattr(transcriber_module, "_save_defaults_list", lambda *_: None)

        transcriber._add_to_history("тест")

        assert callback_calls == [True]

    def test_callback_not_called_when_none(self, app_module, monkeypatch):
        """Если history_callback не задан, исключения не возникает."""
        transcriber = make_transcriber(app_module)
        transcriber.history = []
        transcriber.history_callback = None
        monkeypatch.setattr(transcriber_module, "_save_defaults_list", lambda *_: None)

        # Не должно выбрасывать исключение
        transcriber._add_to_history("тест")

    def test_callback_exception_does_not_propagate(self, app_module, monkeypatch):
        """Исключение в history_callback не прерывает работу."""
        transcriber = make_transcriber(app_module)
        transcriber.history = []
        monkeypatch.setattr(transcriber_module, "_save_defaults_list", lambda *_: None)

        def failing_callback():
            raise ValueError("callback error")

        transcriber.history_callback = failing_callback

        # Не должно выбрасывать исключение
        transcriber._add_to_history("тест")
        assert transcriber.history == ["тест"]

    def test_multiple_additions_maintain_order(self, app_module, monkeypatch):
        """Несколько добавлений сохраняют порядок: новейшее первым."""
        transcriber = make_transcriber(app_module)
        transcriber.history = []
        monkeypatch.setattr(transcriber_module, "_save_defaults_list", lambda *_: None)

        transcriber._add_to_history("первый")
        transcriber._add_to_history("второй")
        transcriber._add_to_history("третий")

        assert transcriber.history == ["третий", "второй", "первый"]

    def test_empty_string_added_to_history(self, app_module, monkeypatch):
        """Пустая строка тоже добавляется в историю (без фильтрации)."""
        transcriber = make_transcriber(app_module)
        transcriber.history = []
        monkeypatch.setattr(transcriber_module, "_save_defaults_list", lambda *_: None)

        transcriber._add_to_history("")

        assert transcriber.history == [""]


@pytest.mark.skipif(sys.platform != "darwin", reason="NSUserDefaults только на macOS")
class TestTokenUsage:
    """Тесты накопительного счётчика токенов."""

    def test_add_token_usage_persists_and_calls_callback(self, app_module, monkeypatch):
        """Добавление токенов сохраняет счётчик и уведомляет UI."""
        transcriber = make_transcriber(app_module)
        transcriber.total_tokens = 10
        saved = []
        callback_calls = []
        transcriber.token_usage_callback = lambda: callback_calls.append(True)

        monkeypatch.setattr(transcriber_module, "_save_defaults_int", lambda key, value: saved.append((key, value)))

        transcriber._add_token_usage(7)

        assert transcriber.total_tokens == 17
        assert saved == [(app_module.DEFAULTS_KEY_TOTAL_TOKENS, 17)]
        assert callback_calls == [True]

    def test_add_token_usage_ignores_zero_and_negative(self, app_module, monkeypatch):
        """Нулевые и отрицательные значения не меняют счётчик."""
        transcriber = make_transcriber(app_module)
        transcriber.total_tokens = 10
        monkeypatch.setattr(transcriber_module, "_save_defaults_int", lambda *_: pytest.fail("save should not be called"))

        transcriber._add_token_usage(0)
        transcriber._add_token_usage(-5)

        assert transcriber.total_tokens == 10


# ---------------------------------------------------------------------------
# _format_history_title (метод StatusBarApp, тестируем как утилиту)
# ---------------------------------------------------------------------------


@pytest.mark.skipif(sys.platform != "darwin", reason="rumps только на macOS")
class TestFormatHistoryTitle:
    """Тесты форматирования заголовка для подменю истории."""

    def _make_app_instance(self, app_module, monkeypatch):
        """Создаёт минимальный экземпляр StatusBarApp для тестов _format_history_title.

        Поскольку StatusBarApp наследует от rumps.App и требует полной инициализации,
        мы вызываем метод напрямую с self=None через unbound вызов.
        """

        # _format_history_title не обращается к self, поэтому подходит duck typing
        class FakeApp:
            pass

        fake = FakeApp()
        fake._format_history_title = app_module.StatusBarApp._format_history_title.__get__(fake)
        return fake

    def test_short_text_unchanged(self, app_module, monkeypatch):
        """Короткий текст возвращается без изменений."""
        fake = self._make_app_instance(app_module, monkeypatch)
        assert fake._format_history_title("Привет") == "Привет"

    def test_newlines_replaced_with_spaces(self, app_module, monkeypatch):
        """Переносы строк заменяются пробелами."""
        fake = self._make_app_instance(app_module, monkeypatch)
        result = fake._format_history_title("Строка 1\nСтрока 2\rСтрока 3")
        assert "\n" not in result
        assert "\r" not in result
        assert result == "Строка 1 Строка 2 Строка 3"

    def test_long_text_truncated_with_ellipsis(self, app_module, monkeypatch):
        """Длинный текст обрезается до HISTORY_DISPLAY_LENGTH с многоточием."""
        fake = self._make_app_instance(app_module, monkeypatch)
        long_text = "А" * (app_module.HISTORY_DISPLAY_LENGTH + 50)

        result = fake._format_history_title(long_text)

        assert len(result) == app_module.HISTORY_DISPLAY_LENGTH + 1  # +1 для "…"
        assert result.endswith("…")
        assert result[:-1] == "А" * app_module.HISTORY_DISPLAY_LENGTH

    def test_exact_length_no_truncation(self, app_module, monkeypatch):
        """Текст ровно HISTORY_DISPLAY_LENGTH символов не обрезается."""
        fake = self._make_app_instance(app_module, monkeypatch)
        exact_text = "Б" * app_module.HISTORY_DISPLAY_LENGTH

        result = fake._format_history_title(exact_text)

        assert result == exact_text
        assert "…" not in result
