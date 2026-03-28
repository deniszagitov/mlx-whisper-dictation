"""Тесты методов вставки текста: CGEvent Unicode, AX API и буфер обмена."""

from __future__ import annotations

import sys
from typing import Any

import pytest
import src.infrastructure.text_input as text_input_module
import src.use_cases.transcription as transcriber_module
from src.domain.constants import Config


class FakeSettingsStore:
    """Простое in-memory хранилище настроек для тестов методов вставки."""

    def load_bool(self, _key, fallback):
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


def make_transcriber(app_module, diagnostics_enabled=False):
    """Создает transcriber с отключённой диагностикой для тестов."""
    diagnostics_store = app_module.DiagnosticsStore(root_dir=Config.LOG_DIR, enabled=diagnostics_enabled)
    return app_module.SpeechTranscriber(
        "dummy-model",
        settings_store=FakeSettingsStore(),
        diagnostics_store=diagnostics_store,
        type_text_via_cgevent=text_input_module.type_text_via_cgevent,
        insert_text_via_ax=text_input_module.insert_text_via_ax,
        send_cmd_v=text_input_module.send_cmd_v,
        clipboard_reader=text_input_module.read_clipboard,
        clipboard_writer=text_input_module.copy_to_clipboard,
    )


# ---------------------------------------------------------------------------
# CGEvent Unicode
# ---------------------------------------------------------------------------


@pytest.mark.skipif(sys.platform != "darwin", reason="CGEvent только на macOS")
class TestCGEventUnicode:
    """Тесты _type_text_via_cgevent."""

    def _setup_quartz_mocks(self, app_module, monkeypatch):
        """Подменяет все вызовы Quartz и возвращает списки для инспекции."""
        posted_events: list[object] = []
        sleep_calls: list[object] = []

        monkeypatch.setattr(text_input_module.time, "sleep", sleep_calls.append)  # type: ignore[attr-defined]
        monkeypatch.setattr(text_input_module.Quartz, "CGEventSourceCreate", lambda *_: object())  # type: ignore[attr-defined]

        def fake_create_keyboard(_source, keycode, is_key_down):
            return {"keycode": keycode, "is_key_down": is_key_down, "unicode": None}

        monkeypatch.setattr(text_input_module.Quartz, "CGEventCreateKeyboardEvent", fake_create_keyboard)  # type: ignore[attr-defined]

        def fake_set_unicode(event, length, string):
            event["unicode"] = string[:length]

        monkeypatch.setattr(text_input_module.Quartz, "CGEventKeyboardSetUnicodeString", fake_set_unicode)  # type: ignore[attr-defined]
        monkeypatch.setattr(
            text_input_module.Quartz,
            "CGEventPost",
            lambda tap, event: posted_events.append((tap, dict(event))),
        )
        return posted_events, sleep_calls

    def test_short_text_single_chunk(self, app_module, monkeypatch):
        """Текст короче CGEVENT_UNICODE_CHUNK_SIZE отправляется одним пакетом (down+up)."""
        transcriber = make_transcriber(app_module)
        posted, sleeps = self._setup_quartz_mocks(app_module, monkeypatch)

        transcriber._type_text_via_cgevent("Привет")

        assert len(posted) == 2  # 1 keyDown + 1 keyUp
        assert posted[0][1]["is_key_down"] is True
        assert posted[0][1]["unicode"] == "Привет"
        assert posted[1][1]["is_key_down"] is False
        assert posted[1][1]["unicode"] == "Привет"
        # Между чанками задержки нет — чанк один
        chunk_delays = [s for s in sleeps if s == Config.CGEVENT_CHUNK_DELAY]
        assert chunk_delays == []

    def test_exact_chunk_size_no_inter_delay(self, app_module, monkeypatch):
        """Текст длиной ровно CGEVENT_UNICODE_CHUNK_SIZE — один чанк, без межчанковых задержек."""
        transcriber = make_transcriber(app_module)
        posted, sleeps = self._setup_quartz_mocks(app_module, monkeypatch)
        text = "A" * Config.CGEVENT_UNICODE_CHUNK_SIZE

        transcriber._type_text_via_cgevent(text)

        assert len(posted) == 2
        chunk_delays = [s for s in sleeps if s == Config.CGEVENT_CHUNK_DELAY]
        assert chunk_delays == []

    def test_multi_chunk_events_and_delays(self, app_module, monkeypatch):
        """Длинный текст разбивается на несколько чанков с задержками между ними."""
        transcriber = make_transcriber(app_module)
        posted, sleeps = self._setup_quartz_mocks(app_module, monkeypatch)
        chunk_size = Config.CGEVENT_UNICODE_CHUNK_SIZE
        text = "X" * (chunk_size * 3 + 5)  # 3 полных чанка + хвост

        transcriber._type_text_via_cgevent(text)

        expected_chunks = 4  # ceil(65 / 20) = 4
        assert len(posted) == expected_chunks * 2  # down + up для каждого чанка
        # Задержки между чанками (не после последнего)
        chunk_delays = [s for s in sleeps if s == Config.CGEVENT_CHUNK_DELAY]
        assert len(chunk_delays) == expected_chunks - 1

    def test_unicode_content_in_chunks(self, app_module, monkeypatch):
        """Кириллический текст корректно разбивается по чанкам."""
        transcriber = make_transcriber(app_module)
        posted, _ = self._setup_quartz_mocks(app_module, monkeypatch)
        chunk_size = Config.CGEVENT_UNICODE_CHUNK_SIZE
        text = "Б" * (chunk_size + 3)

        transcriber._type_text_via_cgevent(text)

        # Первый чанк — полный, второй — хвост из 3 символов
        assert posted[0][1]["unicode"] == "Б" * chunk_size
        assert posted[2][1]["unicode"] == "Б" * 3

    def test_raises_when_event_source_is_none(self, app_module, monkeypatch):
        """RuntimeError при невозможности создать CGEventSource."""
        transcriber = make_transcriber(app_module)
        monkeypatch.setattr(transcriber_module.time, "sleep", lambda *_: None)  # type: ignore[attr-defined]
        monkeypatch.setattr(text_input_module.Quartz, "CGEventSourceCreate", lambda *_: None)  # type: ignore[attr-defined]

        with pytest.raises(RuntimeError, match="источник"):
            transcriber._type_text_via_cgevent("тест")

    def test_raises_when_keydown_event_is_none(self, app_module, monkeypatch):
        """RuntimeError при невозможности создать keyDown event."""
        transcriber = make_transcriber(app_module)
        monkeypatch.setattr(text_input_module.time, "sleep", lambda *_: None)  # type: ignore[attr-defined]
        monkeypatch.setattr(text_input_module.Quartz, "CGEventSourceCreate", lambda *_: object())  # type: ignore[attr-defined]

        def fail_on_keydown(_source, _keycode, is_key_down):
            if is_key_down:
                return None
            return {}

        monkeypatch.setattr(text_input_module.Quartz, "CGEventCreateKeyboardEvent", fail_on_keydown)  # type: ignore[attr-defined]

        with pytest.raises(RuntimeError, match="keyDown"):
            transcriber._type_text_via_cgevent("тест")

    def test_raises_when_keyup_event_is_none(self, app_module, monkeypatch):
        """RuntimeError при невозможности создать keyUp event."""
        transcriber = make_transcriber(app_module)
        monkeypatch.setattr(text_input_module.time, "sleep", lambda *_: None)  # type: ignore[attr-defined]
        monkeypatch.setattr(text_input_module.Quartz, "CGEventSourceCreate", lambda *_: object())  # type: ignore[attr-defined]

        def fail_on_keyup(_source, _keycode, is_key_down):
            if not is_key_down:
                return None
            return {}

        monkeypatch.setattr(text_input_module.Quartz, "CGEventCreateKeyboardEvent", fail_on_keyup)  # type: ignore[attr-defined]
        monkeypatch.setattr(text_input_module.Quartz, "CGEventKeyboardSetUnicodeString", lambda *_: None)  # type: ignore[attr-defined]
        monkeypatch.setattr(text_input_module.Quartz, "CGEventPost", lambda *_: None)  # type: ignore[attr-defined]

        with pytest.raises(RuntimeError, match="keyUp"):
            transcriber._type_text_via_cgevent("тест")

    def test_all_events_posted_to_correct_tap(self, app_module, monkeypatch):
        """Все события публикуются в kCGHIDEventTap."""
        transcriber = make_transcriber(app_module)
        posted, _ = self._setup_quartz_mocks(app_module, monkeypatch)

        transcriber._type_text_via_cgevent("AB")

        for tap, _event in posted:
            assert tap == text_input_module.Quartz.kCGHIDEventTap  # type: ignore[attr-defined]


# ---------------------------------------------------------------------------
# Accessibility (AX) API
# ---------------------------------------------------------------------------


@pytest.mark.skipif(sys.platform != "darwin", reason="AX API только на macOS")
class TestAXAPI:
    """Тесты _insert_text_via_ax."""

    def test_successful_insertion(self, app_module, monkeypatch):
        """Текст вставляется через AX API при успешном сценарии."""
        transcriber = make_transcriber(app_module)
        set_calls = []

        mock_hi: Any = type(sys)("HIServices")
        mock_hi.AXUIElementCreateSystemWide = lambda: "system_wide"
        mock_hi.kAXFocusedUIElementAttribute = "AXFocusedUIElement"
        mock_hi.kAXSelectedTextAttribute = "AXSelectedText"
        mock_hi.AXUIElementCopyAttributeValue = lambda _sw, _attr, _none: (0, "focused_el")
        mock_hi.AXUIElementSetAttributeValue = lambda _el, _attr, text: (set_calls.append(text), 0)[1]  # type: ignore[func-returns-value, attr-defined]
        monkeypatch.setitem(sys.modules, "HIServices", mock_hi)

        transcriber._insert_text_via_ax("Привет мир")

        assert set_calls == ["Привет мир"]

    def test_raises_when_focused_element_error(self, app_module, monkeypatch):
        """RuntimeError при ошибке получения сфокусированного элемента."""
        transcriber = make_transcriber(app_module)

        mock_hi: Any = type(sys)("HIServices")
        mock_hi.AXUIElementCreateSystemWide = lambda: "system_wide"
        mock_hi.kAXFocusedUIElementAttribute = "AXFocusedUIElement"
        mock_hi.AXUIElementCopyAttributeValue = lambda _sw, _attr, _none: (-25204, None)
        monkeypatch.setitem(sys.modules, "HIServices", mock_hi)

        with pytest.raises(RuntimeError, match="сфокусированный UI-элемент"):
            transcriber._insert_text_via_ax("тест")

    def test_raises_when_focused_element_is_none(self, app_module, monkeypatch):
        """RuntimeError когда AXUIElementCopyAttributeValue вернул err=0, но элемент=None."""
        transcriber = make_transcriber(app_module)

        mock_hi: Any = type(sys)("HIServices")
        mock_hi.AXUIElementCreateSystemWide = lambda: "system_wide"
        mock_hi.kAXFocusedUIElementAttribute = "AXFocusedUIElement"
        mock_hi.AXUIElementCopyAttributeValue = lambda _sw, _attr, _none: (0, None)
        monkeypatch.setitem(sys.modules, "HIServices", mock_hi)

        with pytest.raises(RuntimeError, match="сфокусированный UI-элемент"):
            transcriber._insert_text_via_ax("тест")

    def test_raises_when_set_attribute_fails(self, app_module, monkeypatch):
        """RuntimeError при ошибке записи текста через AX API."""
        transcriber = make_transcriber(app_module)

        mock_hi: Any = type(sys)("HIServices")
        mock_hi.AXUIElementCreateSystemWide = lambda: "system_wide"
        mock_hi.kAXFocusedUIElementAttribute = "AXFocusedUIElement"
        mock_hi.kAXSelectedTextAttribute = "AXSelectedText"
        mock_hi.AXUIElementCopyAttributeValue = lambda _sw, _attr, _none: (0, "focused_el")
        mock_hi.AXUIElementSetAttributeValue = lambda _el, _attr, _text: -25211
        monkeypatch.setitem(sys.modules, "HIServices", mock_hi)

        with pytest.raises(RuntimeError, match="AX API"):
            transcriber._insert_text_via_ax("тест")

    def test_does_not_touch_clipboard(self, app_module, monkeypatch):
        """AX-метод не должен затрагивать буфер обмена."""
        transcriber = make_transcriber(app_module)
        clipboard_calls = []
        monkeypatch.setattr(
            transcriber,
            "_copy_to_clipboard",
            lambda *_args: clipboard_calls.append(True),
        )

        mock_hi: Any = type(sys)("HIServices")
        mock_hi.AXUIElementCreateSystemWide = lambda: "system_wide"
        mock_hi.kAXFocusedUIElementAttribute = "AXFocusedUIElement"
        mock_hi.kAXSelectedTextAttribute = "AXSelectedText"
        mock_hi.AXUIElementCopyAttributeValue = lambda _sw, _attr, _none: (0, "focused_el")
        mock_hi.AXUIElementSetAttributeValue = lambda _el, _attr, _text: 0
        monkeypatch.setitem(sys.modules, "HIServices", mock_hi)

        transcriber._insert_text_via_ax("тест")

        assert clipboard_calls == []


# ---------------------------------------------------------------------------
# Clipboard с сохранением/восстановлением
# ---------------------------------------------------------------------------


@pytest.mark.skipif(sys.platform != "darwin", reason="Буфер обмена только на macOS")
class TestPasteViaClipboard:
    """Тесты _paste_via_clipboard."""

    def test_saves_and_restores_clipboard(self, app_module, monkeypatch):
        """Предыдущее содержимое буфера обмена должно восстанавливаться после вставки."""
        transcriber = make_transcriber(app_module)
        clipboard_writes: list[object] = []

        monkeypatch.setattr(transcriber, "_read_clipboard", lambda: "старый текст")
        monkeypatch.setattr(transcriber, "_copy_to_clipboard", clipboard_writes.append)
        monkeypatch.setattr(transcriber, "_send_cmd_v", lambda: None)
        monkeypatch.setattr(transcriber_module.time, "sleep", lambda *_: None)  # type: ignore[attr-defined]

        transcriber._paste_via_clipboard("новый текст")

        # Должно быть два вызова: 1) запись нового текста, 2) восстановление старого
        assert clipboard_writes == ["новый текст", "старый текст"]

    def test_no_restore_when_clipboard_was_empty(self, app_module, monkeypatch):
        """Если буфер обмена был пуст, восстановление не выполняется."""
        transcriber = make_transcriber(app_module)
        clipboard_writes: list[object] = []

        monkeypatch.setattr(transcriber, "_read_clipboard", lambda: None)
        monkeypatch.setattr(transcriber, "_copy_to_clipboard", clipboard_writes.append)
        monkeypatch.setattr(transcriber, "_send_cmd_v", lambda: None)
        monkeypatch.setattr(transcriber_module.time, "sleep", lambda *_: None)  # type: ignore[attr-defined]

        transcriber._paste_via_clipboard("текст")

        # Только одна запись — нового текста; восстановления нет
        assert clipboard_writes == ["текст"]

    def test_restores_clipboard_even_on_cmd_v_failure(self, app_module, monkeypatch):
        """Буфер обмена восстанавливается даже при ошибке _send_cmd_v."""
        transcriber = make_transcriber(app_module)
        clipboard_writes: list[object] = []

        monkeypatch.setattr(transcriber, "_read_clipboard", lambda: "сохранённый")
        monkeypatch.setattr(transcriber, "_copy_to_clipboard", clipboard_writes.append)
        monkeypatch.setattr(transcriber_module.time, "sleep", lambda *_: None)  # type: ignore[attr-defined]

        def failing_cmd_v():
            raise RuntimeError("Cmd+V failed")

        monkeypatch.setattr(transcriber, "_send_cmd_v", failing_cmd_v)

        with pytest.raises(RuntimeError, match="Cmd\\+V"):
            transcriber._paste_via_clipboard("текст")

        # Несмотря на исключение, старый текст восстановлен
        assert "сохранённый" in clipboard_writes

    def test_clipboard_restore_delay(self, app_module, monkeypatch):
        """После Cmd+V выдерживается задержка CLIPBOARD_RESTORE_DELAY."""
        transcriber = make_transcriber(app_module)
        sleep_calls: list[object] = []

        monkeypatch.setattr(transcriber, "_read_clipboard", lambda: None)
        monkeypatch.setattr(transcriber, "_copy_to_clipboard", lambda *_: None)
        monkeypatch.setattr(transcriber, "_send_cmd_v", lambda: None)
        monkeypatch.setattr(transcriber_module.time, "sleep", sleep_calls.append)  # type: ignore[attr-defined]

        transcriber._paste_via_clipboard("текст")

        assert Config.CLIPBOARD_RESTORE_DELAY in sleep_calls

    def test_calls_send_cmd_v(self, app_module, monkeypatch):
        """_paste_via_clipboard вызывает _send_cmd_v для имитации Cmd+V."""
        transcriber = make_transcriber(app_module)
        cmd_v_calls = []

        monkeypatch.setattr(transcriber, "_read_clipboard", lambda: None)
        monkeypatch.setattr(transcriber, "_copy_to_clipboard", lambda *_: None)
        monkeypatch.setattr(transcriber, "_send_cmd_v", lambda: cmd_v_calls.append(True))
        monkeypatch.setattr(transcriber_module.time, "sleep", lambda *_: None)  # type: ignore[attr-defined]

        transcriber._paste_via_clipboard("текст")

        assert cmd_v_calls == [True]

    def test_restore_failure_does_not_propagate(self, app_module, monkeypatch):
        """Ошибка восстановления буфера обмена не должна выбрасываться наружу."""
        transcriber = make_transcriber(app_module)
        call_count = [0]

        def failing_copy(text):
            call_count[0] += 1
            if call_count[0] > 1:
                raise OSError("restore failed")

        monkeypatch.setattr(transcriber, "_read_clipboard", lambda: "old")
        monkeypatch.setattr(transcriber, "_copy_to_clipboard", failing_copy)
        monkeypatch.setattr(transcriber, "_send_cmd_v", lambda: None)
        monkeypatch.setattr(transcriber_module.time, "sleep", lambda *_: None)  # type: ignore[attr-defined]

        # Не должно выбрасывать исключение
        transcriber._paste_via_clipboard("новый")


# ---------------------------------------------------------------------------
# _send_cmd_v — RuntimeError при невозможности создать события
# ---------------------------------------------------------------------------


@pytest.mark.skipif(sys.platform != "darwin", reason="CGEvent только на macOS")
class TestSendCmdV:
    """Тесты _send_cmd_v."""

    def test_raises_when_event_source_is_none(self, app_module, monkeypatch):
        """RuntimeError при невозможности создать CGEventSource."""
        transcriber = make_transcriber(app_module)
        monkeypatch.setattr(text_input_module.time, "sleep", lambda *_: None)  # type: ignore[attr-defined]
        monkeypatch.setattr(text_input_module.Quartz, "CGEventSourceCreate", lambda *_: None)  # type: ignore[attr-defined]

        with pytest.raises(RuntimeError, match="источник"):
            transcriber._send_cmd_v()

    def test_raises_when_keyboard_events_are_none(self, app_module, monkeypatch):
        """RuntimeError при невозможности создать keyboard events."""
        transcriber = make_transcriber(app_module)
        monkeypatch.setattr(text_input_module.time, "sleep", lambda *_: None)  # type: ignore[attr-defined]
        monkeypatch.setattr(text_input_module.Quartz, "CGEventSourceCreate", lambda *_: object())  # type: ignore[attr-defined]
        monkeypatch.setattr(
            text_input_module.Quartz,
            "CGEventCreateKeyboardEvent",
            lambda *_: None,
        )

        with pytest.raises(RuntimeError, match="keyboard events"):
            transcriber._send_cmd_v()
