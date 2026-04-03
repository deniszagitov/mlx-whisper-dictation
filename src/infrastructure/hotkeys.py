"""Горячие клавиши и единый keyboard dispatcher приложения Dictator."""

from __future__ import annotations

import ctypes
import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

import AppKit
import Quartz

from ..domain.hotkeys import (
    MODIFIER_NAMES,
    hotkey_name_matches,
    is_modifier_only_combination,
    normalize_key_combination,
    normalize_key_name,
)

if TYPE_CHECKING:
    from ..domain.ports import ToggleableApp

LOGGER = logging.getLogger(__name__)

MODIFIER_KEYCODES_MAP = {
    54: "cmd_r",
    55: "cmd_l",
    56: "shift_l",
    58: "alt_l",
    59: "ctrl_l",
    60: "shift_r",
    61: "alt_r",
    62: "ctrl_r",
}

MODIFIER_FLAG_MASKS = {
    "alt_l": 0x00080000,
    "alt_r": 0x00080000,
    "ctrl_l": 0x00040000,
    "ctrl_r": 0x00040000,
    "shift_l": 0x00020000,
    "shift_r": 0x00020000,
    "cmd_l": 0x00100000,
    "cmd_r": 0x00100000,
}

_KEYCODE_ESCAPE = 53

NAMED_KEYCODES_MAP = {
    36: "enter",
    48: "tab",
    49: "space",
    51: "backspace",
    _KEYCODE_ESCAPE: "esc",
}

try:
    _carbon_lib = ctypes.cdll.LoadLibrary("/System/Library/Frameworks/Carbon.framework/Carbon")
    _cf_lib = ctypes.cdll.LoadLibrary(
        "/System/Library/Frameworks/CoreFoundation.framework/CoreFoundation"
    )

    _tis_unicode_key_layout_data = ctypes.c_void_p.in_dll(
        _carbon_lib, "kTISPropertyUnicodeKeyLayoutData"
    )

    _TISCopyCurrentASCIICapableKeyboardInputSource = (
        _carbon_lib.TISCopyCurrentASCIICapableKeyboardInputSource
    )
    _TISCopyCurrentASCIICapableKeyboardInputSource.argtypes = []
    _TISCopyCurrentASCIICapableKeyboardInputSource.restype = ctypes.c_void_p

    _TISGetInputSourceProperty = _carbon_lib.TISGetInputSourceProperty
    _TISGetInputSourceProperty.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
    _TISGetInputSourceProperty.restype = ctypes.c_void_p

    _CFDataGetBytePtr = _cf_lib.CFDataGetBytePtr
    _CFDataGetBytePtr.argtypes = [ctypes.c_void_p]
    _CFDataGetBytePtr.restype = ctypes.c_void_p

    _CFRelease = _cf_lib.CFRelease
    _CFRelease.argtypes = [ctypes.c_void_p]
    _CFRelease.restype = None

    _LMGetKbdType = _carbon_lib.LMGetKbdType
    _LMGetKbdType.argtypes = []
    _LMGetKbdType.restype = ctypes.c_uint8

    _UCKeyTranslate = _carbon_lib.UCKeyTranslate
    _UCKeyTranslate.argtypes = [
        ctypes.c_void_p,
        ctypes.c_uint16,
        ctypes.c_uint16,
        ctypes.c_uint32,
        ctypes.c_uint32,
        ctypes.c_uint32,
        ctypes.POINTER(ctypes.c_uint32),
        ctypes.c_ulong,
        ctypes.POINTER(ctypes.c_ulong),
        ctypes.c_wchar_p,
    ]
    _UCKeyTranslate.restype = ctypes.c_int32

    _CARBON_AVAILABLE = True
except Exception:
    _CARBON_AVAILABLE = False
    LOGGER.debug("⚠️ Carbon UCKeyTranslate недоступен, раскладко-независимый маппинг отключён")

_UC_KEY_ACTION_DOWN = 0
_UC_KEY_TRANSLATE_NO_DEAD_KEYS_BIT = 2


def _keycode_to_char(keycode: int) -> str | None:
    """Преобразует виртуальный keycode в символ через ASCII-совместимую раскладку."""
    if not _CARBON_AVAILABLE:
        return None
    try:
        source = _TISCopyCurrentASCIICapableKeyboardInputSource()
        if not source:
            return None
        try:
            layout_data_ref = _TISGetInputSourceProperty(
                source, _tis_unicode_key_layout_data
            )
            if not layout_data_ref:
                return None
            layout_ptr = _CFDataGetBytePtr(layout_data_ref)
            if not layout_ptr:
                return None

            dead_key_state = ctypes.c_uint32(0)
            max_length = ctypes.c_ulong(4)
            actual_length = ctypes.c_ulong(0)
            unicode_buf = ctypes.create_unicode_buffer(4)

            status = _UCKeyTranslate(
                layout_ptr,
                ctypes.c_uint16(keycode),
                ctypes.c_uint16(_UC_KEY_ACTION_DOWN),
                ctypes.c_uint32(0),
                ctypes.c_uint32(_LMGetKbdType()),
                ctypes.c_uint32(1 << _UC_KEY_TRANSLATE_NO_DEAD_KEYS_BIT),
                ctypes.byref(dead_key_state),
                max_length,
                ctypes.byref(actual_length),
                unicode_buf,
            )
            if status == 0 and actual_length.value > 0:
                return unicode_buf.value[0].lower()
        finally:
            _CFRelease(source)
    except Exception:
        LOGGER.debug("⚠️ _keycode_to_char(%s) — ошибка Carbon API", keycode, exc_info=True)
    return None


def parse_key(key_name: str) -> str:
    """Возвращает нормализованное строковое имя клавиши."""
    return normalize_key_name(key_name)


def parse_key_combination(key_combination: str) -> tuple[str, ...]:
    """Разбирает строку с комбинацией клавиш в tuple имён."""
    return tuple(normalize_key_combination(key_combination).split("+"))


def _event_key_name_static(event: Any) -> str:
    """Извлекает имя обычной клавиши из NSEvent."""
    key_code = int(event.keyCode())
    if key_code in NAMED_KEYCODES_MAP:
        return NAMED_KEYCODES_MAP[key_code]
    char = _keycode_to_char(key_code)
    if char:
        return char
    characters = str(event.charactersIgnoringModifiers() or "").lower()
    return characters[:1] if characters else ""


@dataclass(slots=True)
class _HotkeyBinding:
    """Скомпилированное правило хоткея для dispatcher-а."""

    name: str
    key_combination: str
    callback: Any
    required_modifiers: tuple[str, ...]
    required_key: str | None
    modifier_only: bool
    triggered: bool = False
    suppress_key_up: bool = False

    @classmethod
    def from_combination(cls, name: str, key_combination: str, callback: Any) -> _HotkeyBinding:
        normalized = normalize_key_combination(key_combination)
        parts = tuple(normalized.split("+"))
        required_modifiers = tuple(part for part in parts if part in MODIFIER_NAMES)
        required_key = next((part for part in parts if part not in MODIFIER_NAMES), None)
        return cls(
            name=name,
            key_combination=normalized,
            callback=callback,
            required_modifiers=required_modifiers,
            required_key=required_key,
            modifier_only=is_modifier_only_combination(normalized),
        )


class HotkeyDispatcher:
    """Единая точка обработки primary/secondary/LLM хоткеев и Escape."""

    def __init__(self, app: Any) -> None:
        self.app = app
        self.pressed_modifier_names: set[str] = set()
        self._bindings: list[_HotkeyBinding] = []
        self._event_tap: Any = None
        self._tap_source: Any = None
        self._tap_run_loop: Any = None
        self._escape_key_up_suppressed = False
        self.update_hotkeys(
            getattr(app, "primary_key_combination", ""),
            getattr(app, "secondary_key_combination", ""),
            getattr(app, "llm_key_combination", ""),
        )

    def start(self) -> None:
        """Запускает единый CGEventTap без leaky-fallback режима."""
        if self._event_tap is not None:
            return

        event_mask = (
            Quartz.CGEventMaskBit(Quartz.kCGEventFlagsChanged)
            | Quartz.CGEventMaskBit(Quartz.kCGEventKeyDown)
            | Quartz.CGEventMaskBit(Quartz.kCGEventKeyUp)
        )
        tap = Quartz.CGEventTapCreate(
            Quartz.kCGSessionEventTap,
            Quartz.kCGHeadInsertEventTap,
            Quartz.kCGEventTapOptionDefault,
            event_mask,
            self._cgevent_tap_callback,
            None,
        )
        if tap is None:
            LOGGER.warning(
                "⌨️ Не удалось создать единый CGEventTap. Глобальные хоткеи и Escape останутся отключены до выдачи Accessibility."
            )
            return

        self._event_tap = tap
        self._tap_source = Quartz.CFMachPortCreateRunLoopSource(None, tap, 0)
        self._tap_run_loop = Quartz.CFRunLoopGetCurrent()
        Quartz.CFRunLoopAddSource(
            self._tap_run_loop,
            self._tap_source,
            Quartz.kCFRunLoopCommonModes,
        )
        Quartz.CGEventTapEnable(tap, True)
        LOGGER.info("⌨️ Единый CGEventTap создан — все хоткеи и Escape идут через один dispatcher")

    def stop(self) -> None:
        """Останавливает единый keyboard dispatcher."""
        if self._event_tap is not None:
            Quartz.CGEventTapEnable(self._event_tap, False)
            if self._tap_source is not None and self._tap_run_loop is not None:
                Quartz.CFRunLoopRemoveSource(
                    self._tap_run_loop,
                    self._tap_source,
                    Quartz.kCFRunLoopCommonModes,
                )
        self._event_tap = None
        self._tap_source = None
        self._tap_run_loop = None
        self._reset_runtime_state()

    def on_system_wake(self) -> None:
        """Восстанавливает CGEventTap после выхода системы из sleep."""
        LOGGER.info("⌨️ Восстанавливаю CGEventTap после wake")
        self._reset_runtime_state()
        if self._event_tap is None:
            self.start()
            return

        try:
            Quartz.CGEventTapEnable(self._event_tap, True)
        except Exception:
            LOGGER.exception("⌨️ Не удалось включить старый CGEventTap, пересоздаю dispatcher")
            self.stop()
            self.start()

    def update_hotkeys(self, primary: str, secondary: str, llm: str) -> None:
        """Обновляет набор активных хоткеев без пересоздания dispatcher-а."""
        self._bindings = []
        if primary:
            self._bindings.append(_HotkeyBinding.from_combination("primary", primary, self.app.toggle))
        if secondary:
            self._bindings.append(_HotkeyBinding.from_combination("secondary", secondary, self.app.toggle))
        if llm:
            self._bindings.append(_HotkeyBinding.from_combination("llm", llm, self.app.toggle_llm))
        self._bindings.sort(
            key=lambda binding: (
                len(binding.required_modifiers),
                sum(1 for modifier in binding.required_modifiers if modifier.endswith("_l") or modifier.endswith("_r")),
                int(binding.required_key is not None),
            ),
            reverse=True,
        )
        self._reset_runtime_state()

    def _reset_runtime_state(self) -> None:
        self.pressed_modifier_names.clear()
        self._escape_key_up_suppressed = False
        for binding in self._bindings:
            binding.triggered = False
            binding.suppress_key_up = False

    def _required_modifiers_are_pressed(self, required_modifiers: tuple[str, ...]) -> bool:
        return all(
            any(
                hotkey_name_matches(expected_name, pressed_name)
                for pressed_name in self.pressed_modifier_names
            )
            for expected_name in required_modifiers
        )

    def _event_is_modifier_pressed(self, event: Any, modifier_name: str) -> bool:
        modifier_flags = int(event.modifierFlags())
        mask = MODIFIER_FLAG_MASKS.get(modifier_name, 0)
        return bool(modifier_flags & mask)

    def _handle_flags_changed(self, event: Any) -> bool:
        key_code = int(event.keyCode())
        modifier_name = MODIFIER_KEYCODES_MAP.get(key_code)
        if modifier_name is None:
            return False

        modifier_pressed = self._event_is_modifier_pressed(event, modifier_name)
        if modifier_pressed:
            self.pressed_modifier_names.add(modifier_name)
        else:
            self.pressed_modifier_names.discard(modifier_name)

        should_suppress = False
        for binding in self._bindings:
            required_pressed = self._required_modifiers_are_pressed(binding.required_modifiers)
            if binding.modifier_only:
                if required_pressed:
                    if not binding.triggered:
                        LOGGER.info("⌨️ Сработал глобальный хоткей: %s", binding.key_combination)
                        binding.triggered = True
                        binding.callback()
                        should_suppress = True
                else:
                    if binding.triggered and any(
                        hotkey_name_matches(expected_name, modifier_name)
                        for expected_name in binding.required_modifiers
                    ):
                        should_suppress = True
                    binding.triggered = False
            elif not required_pressed:
                binding.triggered = False

        return should_suppress

    def _handle_key_down(self, event: Any) -> bool:
        event_key_name = _event_key_name_static(event)
        if event_key_name == "esc" and getattr(self.app, "started", False):
            LOGGER.info("⌨️ Escape перехвачен dispatcher-ом — отменяю запись")
            self._escape_key_up_suppressed = True
            self.app.handle_escape_keycode(_KEYCODE_ESCAPE)
            return True

        for binding in self._bindings:
            if binding.required_key is None:
                continue
            if not self._required_modifiers_are_pressed(binding.required_modifiers):
                binding.triggered = False
                continue
            if hotkey_name_matches(binding.required_key, event_key_name) and not binding.triggered:
                LOGGER.info("⌨️ Сработал глобальный хоткей: %s", binding.key_combination)
                binding.triggered = True
                binding.suppress_key_up = True
                binding.callback()
                return True
            if event_key_name != binding.required_key:
                binding.triggered = False
        return False

    def _handle_key_up(self, event: Any) -> bool:
        event_key_name = _event_key_name_static(event)
        if event_key_name == "esc" and self._escape_key_up_suppressed:
            self._escape_key_up_suppressed = False
            return True

        for binding in self._bindings:
            if binding.required_key is None:
                continue
            if binding.suppress_key_up and hotkey_name_matches(binding.required_key, event_key_name):
                binding.suppress_key_up = False
                binding.triggered = False
                return True
            if hotkey_name_matches(binding.required_key, event_key_name):
                binding.triggered = False
        return False

    def _dispatch_nsevent(self, event: Any, event_type: int) -> bool:
        if event_type == Quartz.kCGEventFlagsChanged:
            return self._handle_flags_changed(event)
        if event_type == Quartz.kCGEventKeyDown:
            return self._handle_key_down(event)
        if event_type == Quartz.kCGEventKeyUp:
            return self._handle_key_up(event)
        return False

    def _ns_event_from_cgevent(self, cg_event: Any) -> Any | None:
        try:
            return AppKit.NSEvent.eventWithCGEvent_(cg_event)
        except Exception:
            return None

    def _cgevent_tap_callback(self, _proxy: Any, event_type: int, cg_event: Any, _refcon: Any) -> Any | None:
        if event_type == Quartz.kCGEventTapDisabledByTimeout:
            LOGGER.warning("⌨️ CGEventTap отключён по таймауту, включаем обратно")
            if self._event_tap is not None:
                Quartz.CGEventTapEnable(self._event_tap, True)
            return cg_event

        if event_type == Quartz.kCGEventTapDisabledByUserInput:
            return cg_event

        ns_event = self._ns_event_from_cgevent(cg_event)
        if ns_event is None:
            return cg_event

        if self._dispatch_nsevent(ns_event, event_type):
            return None
        return cg_event


class GlobalKeyListener:
    """Совместимый single-hotkey listener для unit-тестов."""

    def __init__(self, app: ToggleableApp, key_combination: str, callback: Any | None = None) -> None:
        self.app = app
        self.callback = callback or app.toggle
        self._binding = _HotkeyBinding.from_combination("compat", key_combination, self.callback)
        self.key_combination = self._binding.key_combination
        self.key_names = self.key_combination.split("+")
        self.modifier_names = set(MODIFIER_NAMES)
        self.required_modifiers = list(self._binding.required_modifiers)
        self.required_key = self._binding.required_key
        self.pressed_modifier_names: set[str] = set()
        self.triggered = False
        self._event_tap: Any = None

    def start(self) -> None:
        """Совместимый no-op запуск listener-а."""
        return None

    def stop(self) -> None:
        """Совместимая no-op остановка listener-а."""
        return None

    def update_key_combination(self, key_combination: str) -> None:
        """Обновляет одну тестовую комбинацию без системной регистрации."""
        self._binding = _HotkeyBinding.from_combination("compat", key_combination, self.callback)
        self.key_combination = self._binding.key_combination
        self.key_names = self.key_combination.split("+")
        self.required_modifiers = list(self._binding.required_modifiers)
        self.required_key = self._binding.required_key
        self.pressed_modifier_names.clear()
        self.triggered = False

    def _required_modifiers_are_pressed(self) -> bool:
        return all(
            any(hotkey_name_matches(expected_name, pressed_name) for pressed_name in self.pressed_modifier_names)
            for expected_name in self.required_modifiers
        )

    def _event_is_modifier_pressed(self, event: Any, modifier_name: str) -> bool:
        modifier_flags = int(event.modifierFlags())
        mask = MODIFIER_FLAG_MASKS.get(modifier_name, 0)
        return bool(modifier_flags & mask)

    def _handle_flags_changed(self, event: Any) -> None:
        key_code = int(event.keyCode())
        modifier_name = MODIFIER_KEYCODES_MAP.get(key_code)
        if modifier_name is None:
            return
        if self._event_is_modifier_pressed(event, modifier_name):
            self.pressed_modifier_names.add(modifier_name)
        else:
            self.pressed_modifier_names.discard(modifier_name)
            self.triggered = False
        if self.required_key is None and self._required_modifiers_are_pressed() and not self.triggered:
            self.triggered = True
            self.callback()

    def _event_key_name(self, event: Any) -> str:
        return _event_key_name_static(event)

    def _check_key_down(self, event: Any) -> bool:
        if self.required_key is None:
            if not self._required_modifiers_are_pressed():
                self.triggered = False
            return False
        event_key_name = self._event_key_name(event)
        if self._required_modifiers_are_pressed() and hotkey_name_matches(self.required_key, event_key_name) and not self.triggered:
            self.triggered = True
            self.callback()
            return True
        if event_key_name != self.required_key:
            self.triggered = False
        return False

    def _ns_event_from_cgevent(self, cg_event: Any) -> Any | None:
        try:
            return AppKit.NSEvent.eventWithCGEvent_(cg_event)
        except Exception:
            return None

    def _cgevent_tap_callback(self, _proxy: Any, event_type: int, cg_event: Any, _refcon: Any) -> Any | None:
        if event_type == Quartz.kCGEventTapDisabledByTimeout:
            if self._event_tap is not None:
                Quartz.CGEventTapEnable(self._event_tap, True)
            return cg_event
        if event_type == Quartz.kCGEventTapDisabledByUserInput:
            return cg_event
        ns_event = self._ns_event_from_cgevent(cg_event)
        if ns_event is None:
            return cg_event
        if self._check_key_down(ns_event):
            return None
        return cg_event


class MultiHotkeyListener:
    """Совместимый multi-listener для unit-тестов."""

    def __init__(self, app: ToggleableApp, key_combinations: list[str]) -> None:
        self.app = app
        self.key_combinations: list[str] = []
        self.listeners: list[GlobalKeyListener] = []
        self._build_listeners(key_combinations)

    def start(self) -> None:
        """Совместимо запускает вложенные listener-ы."""
        for listener in self.listeners:
            listener.start()

    def stop(self) -> None:
        """Совместимо останавливает вложенные listener-ы."""
        for listener in self.listeners:
            listener.stop()

    def _build_listeners(self, key_combinations: list[str]) -> None:
        normalized = []
        for key_combination in key_combinations:
            if not key_combination:
                continue
            normalized.append(normalize_key_combination(key_combination))
        if not normalized:
            raise ValueError("Нужно указать хотя бы один хоткей.")
        self.key_combinations = normalized
        self.listeners = [GlobalKeyListener(self.app, key_combination) for key_combination in self.key_combinations]

    def update_key_combinations(self, key_combinations: list[str]) -> None:
        """Пересобирает тестовый набор вложенных listener-ов."""
        self.stop()
        self._build_listeners(key_combinations)
        self.start()

    def on_system_wake(self) -> None:
        """Перезапускает тестовые listener-ы после выхода системы из sleep."""
        self.stop()
        self.start()
