"""Тесты истории распознанного текста: TTL, persistence, callback."""

import sys

import pytest
from src.domain.constants import Config
from src.domain.transcription import normalize_history_record


class FakeSettingsStore:
    """Простое in-memory хранилище настроек для тестов истории."""

    def __init__(self) -> None:
        self.private_mode_enabled = False

    def load_bool(self, key, fallback):
        if key == Config.DEFAULTS_KEY_PRIVATE_MODE:
            return self.private_mode_enabled
        return fallback

    def save_bool(self, _key, _value):
        return None

    def load_list(self, _key):
        return []

    def save_list(self, _key, _value):
        return None

    def load_int(self, _key, fallback):
        return fallback

    def save_int(self, _key, _value):
        return None

    def load_str(self, _key, fallback=None):
        return fallback

    def save_str(self, _key, _value):
        return None

    def load_max_time(self, fallback):
        return fallback

    def save_max_time(self, _value):
        return None

    def load_input_device_index(self):
        return None

    def save_input_device_index(self, _value):
        return None

    def remove_key(self, _key):
        return None


def make_transcriber(app_module, diagnostics_enabled=False, settings_store=None):
    """Создает transcriber с отключённой диагностикой для тестов."""
    diagnostics_store = app_module.DiagnosticsStore(root_dir=Config.LOG_DIR, enabled=diagnostics_enabled)
    return app_module.SpeechTranscriber(
        "dummy-model",
        settings_store=settings_store or FakeSettingsStore(),
        diagnostics_store=diagnostics_store,
    )


# ---------------------------------------------------------------------------
# add_to_history
# ---------------------------------------------------------------------------


@pytest.mark.skipif(sys.platform != "darwin", reason="NSUserDefaults только на macOS")
class TestAddToHistory:
    """Тесты add_to_history."""

    def test_inserts_at_front(self, app_module, monkeypatch):
        """Новый текст добавляется в начало списка."""
        transcriber = make_transcriber(app_module)
        transcriber.history = ["первый"]
        monkeypatch.setattr(transcriber, "_save_history_records", lambda *_: None)

        transcriber.add_to_history("второй")

        assert transcriber.history[0] == "второй"
        assert transcriber.history[1] == "первый"

    def test_drops_entries_older_than_24_hours(self, app_module, monkeypatch):
        """При добавлении история очищается от записей старше 24 часов."""
        transcriber = make_transcriber(app_module)
        now = 2_000_000.0
        transcriber._history_records = [
            {"text": "старый", "created_at": now - (24 * 60 * 60) - 1},
            {"text": "свежий", "created_at": now - 60},
        ]
        transcriber.history = ["старый", "свежий"]

        monkeypatch.setattr(transcriber, "_current_time", lambda: now)
        monkeypatch.setattr(transcriber, "_save_history_records", lambda *_: None)

        transcriber.add_to_history("новый")

        assert transcriber.history == ["новый", "свежий"]

    def test_persists_to_nsuserdefaults(self, app_module, monkeypatch):
        """История сохраняется через _save_defaults_list с правильным ключом."""
        transcriber = make_transcriber(app_module)
        transcriber.history = []
        saved = []

        monkeypatch.setattr(transcriber, "_save_history_records", lambda value: saved.append(list(value)))

        transcriber.add_to_history("тест")

        assert len(saved) == 1
        assert saved[0][0]["text"] == "тест"
        assert isinstance(saved[0][0]["created_at"], float)

    def test_does_not_persist_history_in_private_mode(self, app_module, monkeypatch):
        """В private mode история остаётся только в памяти текущей сессии."""
        transcriber = make_transcriber(app_module)
        transcriber.history = []
        transcriber.private_mode_enabled = True
        saved = []

        monkeypatch.setattr(transcriber, "_save_history_records", lambda value: saved.append(list(value)))

        transcriber.add_to_history("секрет")

        assert transcriber.history == ["секрет"]
        assert saved == []

    def test_private_mode_starts_with_empty_history(self, app_module, monkeypatch):
        """При активном private mode история не должна подниматься из defaults."""
        settings_store = FakeSettingsStore()
        settings_store.private_mode_enabled = True
        transcriber = make_transcriber(app_module, settings_store=settings_store)

        assert transcriber.private_mode_enabled is True
        assert transcriber.history == []

    def test_set_private_mode_reloads_persisted_history_when_disabled(self, app_module, monkeypatch):
        """После выключения private mode история снова загружается из defaults."""
        transcriber = make_transcriber(app_module)
        transcriber.history = ["секрет"]
        callback_calls = []
        saved_flags = []
        transcriber.history_callback = lambda: callback_calls.append(True)
        monkeypatch.setattr(transcriber, "_current_time", lambda: 2_000_000.0)

        monkeypatch.setattr(transcriber.settings_store, "save_bool", lambda key, value: saved_flags.append((key, value)))
        monkeypatch.setattr(
            transcriber,
            "_load_history_items",
            lambda: [{"text": "обычная история", "created_at": 2_000_000.0}],
        )
        monkeypatch.setattr(transcriber, "_save_history_records", lambda *_args: None)

        transcriber.set_private_mode(True)
        assert transcriber.history == []

        transcriber.set_private_mode(False)

        assert transcriber.history == ["обычная история"]
        assert saved_flags == [
            (Config.DEFAULTS_KEY_PRIVATE_MODE, True),
            (Config.DEFAULTS_KEY_PRIVATE_MODE, False),
        ]
        assert callback_calls == [True, True]

    def test_calls_callback(self, app_module, monkeypatch):
        """history_callback вызывается при добавлении записи."""
        transcriber = make_transcriber(app_module)
        transcriber.history = []
        callback_calls = []
        transcriber.history_callback = lambda: callback_calls.append(True)
        monkeypatch.setattr(transcriber, "_save_history_records", lambda *_: None)

        transcriber.add_to_history("тест")

        assert callback_calls == [True]

    def test_callback_not_called_when_none(self, app_module, monkeypatch):
        """Если history_callback не задан, исключения не возникает."""
        transcriber = make_transcriber(app_module)
        transcriber.history = []
        transcriber.history_callback = None
        monkeypatch.setattr(transcriber, "_save_history_records", lambda *_: None)

        # Не должно выбрасывать исключение
        transcriber.add_to_history("тест")

    def test_callback_exception_does_not_propagate(self, app_module, monkeypatch):
        """Исключение в history_callback не прерывает работу."""
        transcriber = make_transcriber(app_module)
        transcriber.history = []
        monkeypatch.setattr(transcriber, "_save_history_records", lambda *_: None)

        def failing_callback():
            raise ValueError("callback error")

        transcriber.history_callback = failing_callback

        # Не должно выбрасывать исключение
        transcriber.add_to_history("тест")
        assert transcriber.history == ["тест"]

    def test_multiple_additions_maintain_order(self, app_module, monkeypatch):
        """Несколько добавлений сохраняют порядок: новейшее первым."""
        transcriber = make_transcriber(app_module)
        transcriber.history = []
        monkeypatch.setattr(transcriber, "_save_history_records", lambda *_: None)

        transcriber.add_to_history("первый")
        transcriber.add_to_history("второй")
        transcriber.add_to_history("третий")

        assert transcriber.history == ["третий", "второй", "первый"]

    def test_empty_string_added_to_history(self, app_module, monkeypatch):
        """Пустая строка тоже добавляется в историю (без фильтрации)."""
        transcriber = make_transcriber(app_module)
        transcriber.history = []
        monkeypatch.setattr(transcriber, "_save_history_records", lambda *_: None)

        transcriber.add_to_history("")

        assert transcriber.history == [""]

    def test_prune_expired_history_removes_old_records(self, app_module, monkeypatch):
        """Явная очистка истории должна удалять записи старше 24 часов."""
        transcriber = make_transcriber(app_module)
        now = 2_000_000.0
        transcriber._history_records = [
            {"text": "старый", "created_at": now - (24 * 60 * 60) - 1},
            {"text": "свежий", "created_at": now - 10},
        ]
        transcriber.history = ["старый", "свежий"]
        saved = []

        monkeypatch.setattr(transcriber, "_current_time", lambda: now)
        monkeypatch.setattr(transcriber, "_save_history_records", lambda value: saved.append(list(value)))

        changed = transcriber.prune_expired_history()

        assert changed is True
        assert transcriber.history == ["свежий"]
        assert saved[0][0]["text"] == "свежий"

    def test_corrupted_nsdictionary_text_is_skipped(self, monkeypatch):
        """Повреждённая запись с NSDictionary вместо строки в поле text пропускается."""
        now = 2_000_000.0

        # Симулируем NSDictionary-подобный объект (hasattr objectForKey_)
        class FakeNSDict:
            """Объект, имитирующий NSDictionary из PyObjC."""

            def __init__(self, data):
                self._data = data

            def get(self, key, default=None):
                return self._data.get(key, default)

            def __getitem__(self, key):
                return self._data[key]

            def objectForKey_(self, key):
                return self._data.get(key)

        corrupted_item = FakeNSDict({
            "text": FakeNSDict({"text": "вложенный", "created_at": now - 10}),
            "created_at": now - 10,
        })

        result = normalize_history_record(corrupted_item, now)
        assert result is None

    def test_valid_nsdictionary_record_is_loaded(self, monkeypatch):
        """Корректная запись из NSDictionary-подобного объекта загружается нормально."""
        now = 2_000_000.0

        class FakeNSDict:
            """Объект, имитирующий NSDictionary из PyObjC."""

            def __init__(self, data):
                self._data = data

            def get(self, key, default=None):
                return self._data.get(key, default)

            def __getitem__(self, key):
                return self._data[key]

            def objectForKey_(self, key):
                return self._data.get(key)

        valid_item = FakeNSDict({"text": "нормальный текст", "created_at": now - 10})

        result = normalize_history_record(valid_item, now)
        assert result is not None
        assert result["text"] == "нормальный текст"


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

        monkeypatch.setattr(transcriber.settings_store, "save_int", lambda key, value: saved.append((key, value)))

        transcriber.add_token_usage(7)

        assert transcriber.total_tokens == 17
        assert saved == [(Config.DEFAULTS_KEY_TOTAL_TOKENS, 17)]
        assert callback_calls == [True]

    def test_add_token_usage_ignores_zero_and_negative(self, app_module, monkeypatch):
        """Нулевые и отрицательные значения не меняют счётчик."""
        transcriber = make_transcriber(app_module)
        transcriber.total_tokens = 10
        monkeypatch.setattr(transcriber.settings_store, "save_int", lambda *_: pytest.fail("save should not be called"))

        transcriber.add_token_usage(0)
        transcriber.add_token_usage(-5)

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

        fake: object = FakeApp()
        fake._format_history_title = app_module.StatusBarApp._format_history_title.__get__(fake)  # type: ignore[attr-defined]
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
        long_text = "А" * (Config.HISTORY_DISPLAY_LENGTH + 50)

        result = fake._format_history_title(long_text)

        assert len(result) == Config.HISTORY_DISPLAY_LENGTH + 1  # +1 для "…"
        assert result.endswith("…")
        assert result[:-1] == "А" * Config.HISTORY_DISPLAY_LENGTH

    def test_exact_length_no_truncation(self, app_module, monkeypatch):
        """Текст ровно HISTORY_DISPLAY_LENGTH символов не обрезается."""
        fake = self._make_app_instance(app_module, monkeypatch)
        exact_text = "Б" * Config.HISTORY_DISPLAY_LENGTH

        result = fake._format_history_title(exact_text)

        assert result == exact_text
        assert "…" not in result
