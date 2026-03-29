"""Чистые типы доменного слоя приложения Dictator."""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import TYPE_CHECKING, TypedDict

from .constants import Config
from .hotkeys import format_hotkey_status, normalize_key_combination

if TYPE_CHECKING:
    from collections.abc import Collection

    from .ports import SettingsStoreProtocol


class HistoryRecord(TypedDict):
    """Запись истории распознанного текста."""

    text: str
    created_at: float


class AudioDeviceInfo(TypedDict):
    """Информация об устройстве ввода PyAudio."""

    index: int
    name: str
    max_input_channels: int
    default_sample_rate: float
    is_default: bool


class AudioDiagnostics(TypedDict):
    """Диагностика входного аудиосигнала."""

    language: str | None
    duration_seconds: float
    rms_energy: float
    peak_amplitude: float
    silence_threshold: float
    hallucination_threshold: float
    sample_rate: int
    samples: int
    first_samples: list[float]


def _coerce_bool(value: object, *, fallback: bool) -> bool:
    """Приводит произвольное значение к bool по предсказуемым правилам."""
    if value is None:
        return fallback
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"1", "true", "yes", "on"}:
            return True
        if normalized in {"0", "false", "no", "off", ""}:
            return False
        return fallback
    return bool(value)


def _coerce_optional_str(value: object) -> str | None:
    """Преобразует значение в строку или отсутствие значения."""
    if value is None:
        return None
    normalized = str(value).strip()
    return normalized or None


def _coerce_optional_int(value: object) -> int | None:
    """Преобразует значение в int или возвращает None."""
    if value is None:
        return None
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError:
            return None
    return None


def _coerce_max_time(value: object, *, fallback: int | float | None) -> int | float | None:
    """Нормализует лимит записи из сырого значения."""
    if value is None:
        return None
    if isinstance(value, str):
        normalized = value.strip().lower()
        if not normalized:
            return fallback
        if normalized == "none":
            return None
        try:
            parsed = float(normalized)
        except ValueError:
            return fallback
    elif isinstance(value, (int, float)):
        parsed = float(value)
    else:
        return fallback
    if parsed.is_integer():
        return int(parsed)
    return parsed


def _coerce_languages(value: object) -> tuple[str, ...] | None:
    """Преобразует входной язык или список языков в нормализованный tuple."""
    if value is None:
        return None
    candidates: tuple[object, ...]
    if isinstance(value, str):
        candidates = tuple(value.split(","))
    elif isinstance(value, (list, tuple, set, frozenset)):
        candidates = tuple(value)
    else:
        candidates = (value,)

    normalized = tuple(
        part
        for item in candidates
        if (part := str(item).strip())
    )
    return normalized or None


def _coerce_model_name(value: object, *, fallback: str) -> str:
    """Возвращает валидное имя модели или fallback."""
    normalized = _coerce_optional_str(value)
    return normalized or fallback


def _coerce_optional_hotkey(value: object) -> str | None:
    """Нормализует хоткей или возвращает None."""
    normalized = _coerce_optional_str(value)
    if normalized is None:
        return None
    return normalize_key_combination(normalized)


@dataclass(frozen=True, slots=True)
class HotkeyConfig:
    """Нормализованные настройки хоткеев приложения."""

    primary_key_combination: str | None
    secondary_key_combination: str | None
    llm_key_combination: str | None
    use_double_command_hotkey: bool = False

    @classmethod
    def from_values(
        cls,
        *,
        primary_key_combination: object,
        secondary_key_combination: object,
        llm_key_combination: object,
        use_double_command_hotkey: object = False,
        secondary_hotkey_explicitly_set: bool = False,
    ) -> HotkeyConfig:
        """Создаёт конфиг хоткеев из сырых значений."""
        use_double = _coerce_bool(use_double_command_hotkey, fallback=False)
        primary = None if use_double else _coerce_optional_hotkey(primary_key_combination)
        secondary = _coerce_optional_hotkey(secondary_key_combination)
        llm = _coerce_optional_hotkey(llm_key_combination)

        if use_double:
            if secondary_hotkey_explicitly_set and secondary is not None:
                raise ValueError("Параметр --secondary_key_combination нельзя использовать вместе с --k_double_cmd.")
            secondary = None
        elif primary is None:
            raise ValueError("Основной хоткей должен быть задан.")

        if primary is not None and secondary is not None and primary == secondary:
            raise ValueError("Дополнительный хоткей должен отличаться от основного.")

        return cls(
            primary_key_combination=primary,
            secondary_key_combination=secondary,
            llm_key_combination=llm,
            use_double_command_hotkey=use_double,
        )

    @property
    def active_key_combinations(self) -> tuple[str, ...]:
        """Возвращает все включённые комбинации основных хоткеев."""
        if self.use_double_command_hotkey:
            return ()
        return tuple(
            combination
            for combination in (self.primary_key_combination, self.secondary_key_combination)
            if combination is not None
        )

    @property
    def hotkey_status(self) -> str:
        """Возвращает display-строку основного хоткея."""
        return format_hotkey_status(self.primary_key_combination, use_double_cmd=self.use_double_command_hotkey)

    @property
    def secondary_hotkey_status(self) -> str:
        """Возвращает display-строку дополнительного хоткея."""
        if self.secondary_key_combination is None:
            return "не задан"
        return format_hotkey_status(self.secondary_key_combination)

    @property
    def llm_hotkey_status(self) -> str:
        """Возвращает display-строку LLM-хоткея."""
        if self.llm_key_combination is None:
            return "не задан"
        return format_hotkey_status(self.llm_key_combination)

    @property
    def primary_store_value(self) -> str:
        """Возвращает значение для хранения основного хоткея."""
        return "" if self.primary_key_combination is None else self.primary_key_combination

    @property
    def secondary_store_value(self) -> str:
        """Возвращает значение для хранения дополнительного хоткея."""
        return "" if self.secondary_key_combination is None else self.secondary_key_combination

    @property
    def llm_store_value(self) -> str:
        """Возвращает значение для хранения LLM-хоткея."""
        return "" if self.llm_key_combination is None else self.llm_key_combination

    def with_primary(self, value: object) -> HotkeyConfig:
        """Возвращает новый конфиг с обновлённым основным хоткеем."""
        return self.from_values(
            primary_key_combination=value,
            secondary_key_combination=self.secondary_key_combination,
            llm_key_combination=self.llm_key_combination,
            use_double_command_hotkey=self.use_double_command_hotkey,
        )

    def with_secondary(self, value: object) -> HotkeyConfig:
        """Возвращает новый конфиг с обновлённым дополнительным хоткеем."""
        return self.from_values(
            primary_key_combination=self.primary_key_combination,
            secondary_key_combination=value,
            llm_key_combination=self.llm_key_combination,
            use_double_command_hotkey=self.use_double_command_hotkey,
        )

    def with_llm(self, value: object) -> HotkeyConfig:
        """Возвращает новый конфиг с обновлённым LLM-хоткеем."""
        return self.from_values(
            primary_key_combination=self.primary_key_combination,
            secondary_key_combination=self.secondary_key_combination,
            llm_key_combination=value,
            use_double_command_hotkey=self.use_double_command_hotkey,
        )


@dataclass(frozen=True, slots=True)
class LaunchConfig:
    """Итоговая конфигурация запуска приложения."""

    model: str
    languages: tuple[str, ...] | None
    max_time: int | float | None
    llm_model: str
    hotkeys: HotkeyConfig

    @classmethod
    def from_sources(
        cls,
        *,
        model: object,
        language: object,
        max_time: object,
        llm_model: object,
        key_combination: object,
        secondary_key_combination: object,
        llm_key_combination: object,
        k_double_cmd: object,
        settings_store: SettingsStoreProtocol | None = None,
        cli_overrides: Collection[str] = (),
    ) -> LaunchConfig:
        """Собирает итоговую конфигурацию из CLI и сохранённых настроек."""
        if settings_store is not None and "-m" not in cli_overrides and "--model" not in cli_overrides:
            saved_model = settings_store.load_str(Config.DEFAULTS_KEY_MODEL, fallback=None)
            if saved_model:
                model = saved_model

        if settings_store is not None and "-l" not in cli_overrides and "--language" not in cli_overrides:
            saved_language = settings_store.load_str(Config.DEFAULTS_KEY_LANGUAGE, fallback=None)
            if saved_language:
                language = saved_language

        if settings_store is not None and "-t" not in cli_overrides and "--max_time" not in cli_overrides:
            saved_max_time = settings_store.load_str(Config.DEFAULTS_KEY_MAX_TIME, fallback=None)
            if saved_max_time is not None:
                max_time = saved_max_time

        use_double = _coerce_bool(k_double_cmd, fallback=False)
        if settings_store is not None and not use_double and "-k" not in cli_overrides and "--key_combination" not in cli_overrides:
            saved_primary = settings_store.load_str(Config.DEFAULTS_KEY_PRIMARY_HOTKEY, fallback=None)
            if saved_primary:
                key_combination = saved_primary

        if (
            settings_store is not None
            and not use_double
            and "--secondary_key_combination" not in cli_overrides
            and settings_store.contains_key(Config.DEFAULTS_KEY_SECONDARY_HOTKEY)
        ):
            secondary_key_combination = settings_store.load_str(Config.DEFAULTS_KEY_SECONDARY_HOTKEY, fallback="")

        if (
            settings_store is not None
            and "--llm_key_combination" not in cli_overrides
            and settings_store.contains_key(Config.DEFAULTS_KEY_LLM_HOTKEY)
        ):
            llm_key_combination = settings_store.load_str(Config.DEFAULTS_KEY_LLM_HOTKEY, fallback="")

        normalized_model = _coerce_model_name(model, fallback=Config.DEFAULT_MODEL_NAME)
        normalized_languages = _coerce_languages(language)
        normalized_max_time = _coerce_max_time(max_time, fallback=30)
        normalized_llm_model = _coerce_model_name(llm_model, fallback=Config.DEFAULT_LLM_MODEL_NAME)
        hotkeys = HotkeyConfig.from_values(
            primary_key_combination=key_combination,
            secondary_key_combination=secondary_key_combination,
            llm_key_combination=llm_key_combination,
            use_double_command_hotkey=use_double,
            secondary_hotkey_explicitly_set="--secondary_key_combination" in cli_overrides,
        )

        if normalized_model.endswith(".en") and normalized_languages is not None and any(lang != "en" for lang in normalized_languages):
            raise ValueError("Для модели с суффиксом .en нельзя указывать язык, отличный от английского.")

        return cls(
            model=normalized_model,
            languages=normalized_languages,
            max_time=normalized_max_time,
            llm_model=normalized_llm_model,
            hotkeys=hotkeys,
        )

    @property
    def language(self) -> list[str] | None:
        """Возвращает список языков в совместимом с текущим кодом формате."""
        if self.languages is None:
            return None
        return list(self.languages)

    @property
    def key_combination(self) -> str | None:
        """Возвращает основной хоткей."""
        return self.hotkeys.primary_key_combination

    @property
    def secondary_key_combination(self) -> str | None:
        """Возвращает дополнительный хоткей."""
        return self.hotkeys.secondary_key_combination

    @property
    def llm_key_combination(self) -> str | None:
        """Возвращает LLM-хоткей."""
        return self.hotkeys.llm_key_combination

    @property
    def k_double_cmd(self) -> bool:
        """Возвращает флаг режима двойной Command."""
        return self.hotkeys.use_double_command_hotkey

    @property
    def max_time_store_value(self) -> str:
        """Возвращает сериализованное значение лимита записи для persistence."""
        if self.max_time is None:
            return "none"
        return str(self.max_time)

    def with_model(self, model: object) -> LaunchConfig:
        """Возвращает новый конфиг с обновлённой моделью."""
        return replace(self, model=_coerce_model_name(model, fallback=self.model))

    def with_max_time(self, max_time: object) -> LaunchConfig:
        """Возвращает новый конфиг с обновлённым лимитом записи."""
        return replace(self, max_time=_coerce_max_time(max_time, fallback=self.max_time))

    def with_hotkeys(self, hotkeys: HotkeyConfig) -> LaunchConfig:
        """Возвращает новый конфиг с обновлёнными хоткеями."""
        return replace(self, hotkeys=hotkeys)


@dataclass(frozen=True, slots=True)
class AppPreferences:
    """Сохранённые пользовательские настройки верхнего уровня."""

    llm_prompt_name: str
    performance_mode: str
    selected_language: str | None
    selected_input_device_index: int | None
    show_recording_notification: bool
    show_recording_overlay: bool

    @classmethod
    def from_store(cls, settings_store: SettingsStoreProtocol) -> AppPreferences:
        """Читает настройки приложения из persistence-слоя."""
        llm_prompt_name = settings_store.load_str(Config.DEFAULTS_KEY_LLM_PROMPT, Config.DEFAULT_LLM_PROMPT_NAME)
        if llm_prompt_name not in Config.LLM_PROMPT_PRESETS:
            llm_prompt_name = Config.DEFAULT_LLM_PROMPT_NAME

        selected_input_device_index = None
        if settings_store.contains_key(Config.DEFAULTS_KEY_INPUT_DEVICE_INDEX):
            stored_index = settings_store.load_int(Config.DEFAULTS_KEY_INPUT_DEVICE_INDEX, fallback=-1)
            if stored_index >= 0:
                selected_input_device_index = stored_index

        return cls(
            llm_prompt_name=llm_prompt_name or Config.DEFAULT_LLM_PROMPT_NAME,
            performance_mode=Config.normalize_performance_mode(
                settings_store.load_str(Config.DEFAULTS_KEY_PERFORMANCE_MODE, Config.DEFAULT_PERFORMANCE_MODE),
            ),
            selected_language=_coerce_optional_str(settings_store.load_str(Config.DEFAULTS_KEY_LANGUAGE, fallback=None)),
            selected_input_device_index=selected_input_device_index,
            show_recording_notification=settings_store.load_bool(Config.DEFAULTS_KEY_RECORDING_NOTIFICATION, fallback=True),
            show_recording_overlay=settings_store.load_bool(Config.DEFAULTS_KEY_RECORDING_OVERLAY, fallback=True),
        )

    def with_llm_prompt_name(self, prompt_name: object) -> AppPreferences:
        """Возвращает новый набор настроек с обновлённым LLM-промптом."""
        normalized = _coerce_optional_str(prompt_name)
        if normalized not in Config.LLM_PROMPT_PRESETS:
            normalized = Config.DEFAULT_LLM_PROMPT_NAME
        return replace(self, llm_prompt_name=normalized)

    def with_performance_mode(self, performance_mode: object) -> AppPreferences:
        """Возвращает новый набор настроек с обновлённым performance mode."""
        return replace(self, performance_mode=Config.normalize_performance_mode(performance_mode))

    def with_selected_language(self, language: object) -> AppPreferences:
        """Возвращает новый набор настроек с обновлённым языком."""
        return replace(self, selected_language=_coerce_optional_str(language))

    def with_selected_input_device_index(self, device_index: object) -> AppPreferences:
        """Возвращает новый набор настроек с обновлённым микрофоном."""
        return replace(self, selected_input_device_index=_coerce_optional_int(device_index))

    def with_recording_notification(self, enabled: object) -> AppPreferences:
        """Возвращает новый набор настроек с обновлённым флагом уведомления."""
        return replace(self, show_recording_notification=_coerce_bool(enabled, fallback=self.show_recording_notification))

    def with_recording_overlay(self, enabled: object) -> AppPreferences:
        """Возвращает новый набор настроек с обновлённым флагом overlay."""
        return replace(self, show_recording_overlay=_coerce_bool(enabled, fallback=self.show_recording_overlay))


@dataclass(frozen=True, slots=True)
class TranscriberPreferences:
    """Сохранённые настройки транскрайбера и методов вставки."""

    paste_cgevent_enabled: bool
    paste_ax_enabled: bool
    paste_clipboard_enabled: bool
    llm_clipboard_enabled: bool
    private_mode_enabled: bool
    total_tokens: int

    @classmethod
    def from_store(cls, settings_store: SettingsStoreProtocol) -> TranscriberPreferences:
        """Читает настройки транскрайбера из persistence-слоя."""
        return cls(
            paste_cgevent_enabled=settings_store.load_bool(Config.DEFAULTS_KEY_PASTE_CGEVENT, fallback=True),
            paste_ax_enabled=settings_store.load_bool(Config.DEFAULTS_KEY_PASTE_AX, fallback=False),
            paste_clipboard_enabled=settings_store.load_bool(Config.DEFAULTS_KEY_PASTE_CLIPBOARD, fallback=False),
            llm_clipboard_enabled=settings_store.load_bool(Config.DEFAULTS_KEY_LLM_CLIPBOARD, fallback=True),
            private_mode_enabled=settings_store.load_bool(Config.DEFAULTS_KEY_PRIVATE_MODE, fallback=False),
            total_tokens=max(settings_store.load_int(Config.DEFAULTS_KEY_TOTAL_TOKENS, fallback=0), 0),
        )

    def with_private_mode(self, enabled: object) -> TranscriberPreferences:
        """Возвращает новый набор настроек с обновлённым private mode."""
        return replace(self, private_mode_enabled=_coerce_bool(enabled, fallback=self.private_mode_enabled))

    def with_paste_cgevent_enabled(self, enabled: object) -> TranscriberPreferences:
        """Возвращает новый набор настроек с обновлённым CGEvent-режимом."""
        return replace(self, paste_cgevent_enabled=_coerce_bool(enabled, fallback=self.paste_cgevent_enabled))

    def with_paste_ax_enabled(self, enabled: object) -> TranscriberPreferences:
        """Возвращает новый набор настроек с обновлённым AX-режимом."""
        return replace(self, paste_ax_enabled=_coerce_bool(enabled, fallback=self.paste_ax_enabled))

    def with_paste_clipboard_enabled(self, enabled: object) -> TranscriberPreferences:
        """Возвращает новый набор настроек с обновлённым clipboard-режимом."""
        return replace(self, paste_clipboard_enabled=_coerce_bool(enabled, fallback=self.paste_clipboard_enabled))

    def with_llm_clipboard_enabled(self, enabled: object) -> TranscriberPreferences:
        """Возвращает новый набор настроек с обновлённым LLM clipboard."""
        return replace(self, llm_clipboard_enabled=_coerce_bool(enabled, fallback=self.llm_clipboard_enabled))

    def with_total_tokens(self, token_count: object) -> TranscriberPreferences:
        """Возвращает новый набор настроек с обновлённым счётчиком токенов."""
        normalized = _coerce_optional_int(token_count)
        return replace(self, total_tokens=max(normalized or 0, 0))


@dataclass(frozen=True, slots=True)
class MicrophoneProfile:
    """Быстрый профиль настроек микрофона."""

    name: str
    input_device_index: int
    input_device_name: str
    model_repo: str
    language: str | None
    max_time: int | float | None
    performance_mode: str
    private_mode: bool
    paste_cgevent: bool
    paste_ax: bool
    paste_clipboard: bool
    llm_clipboard: bool

    @classmethod
    def from_payload(cls, raw_profile: object) -> MicrophoneProfile | None:
        """Создаёт профиль микрофона из сырого JSON-представления."""
        if not isinstance(raw_profile, dict):
            return None

        name = " ".join(str(raw_profile.get("name") or "").split())
        input_device_index = _coerce_optional_int(raw_profile.get("input_device_index"))
        if not name or input_device_index is None:
            return None

        return cls(
            name=name,
            input_device_index=input_device_index,
            input_device_name=str(raw_profile.get("input_device_name") or ""),
            model_repo=_coerce_model_name(raw_profile.get("model_repo"), fallback=Config.DEFAULT_MODEL_NAME),
            language=_coerce_optional_str(raw_profile.get("language")),
            max_time=_coerce_max_time(raw_profile.get("max_time"), fallback=None),
            performance_mode=Config.normalize_performance_mode(raw_profile.get("performance_mode")),
            private_mode=_coerce_bool(raw_profile.get("private_mode", False), fallback=False),
            paste_cgevent=_coerce_bool(raw_profile.get("paste_cgevent", True), fallback=True),
            paste_ax=_coerce_bool(raw_profile.get("paste_ax", False), fallback=False),
            paste_clipboard=_coerce_bool(raw_profile.get("paste_clipboard", False), fallback=False),
            llm_clipboard=_coerce_bool(raw_profile.get("llm_clipboard", True), fallback=True),
        )

    @classmethod
    def from_runtime(
        cls,
        profile_name: object,
        *,
        input_device_index: object,
        input_device_name: object,
        model_repo: object,
        language: object,
        max_time: object,
        performance_mode: object,
        private_mode: object,
        paste_cgevent: object,
        paste_ax: object,
        paste_clipboard: object,
        llm_clipboard: object,
    ) -> MicrophoneProfile:
        """Создаёт профиль из текущего runtime-состояния приложения."""
        payload = {
            "name": profile_name,
            "input_device_index": input_device_index,
            "input_device_name": input_device_name,
            "model_repo": model_repo,
            "language": language,
            "max_time": max_time,
            "performance_mode": performance_mode,
            "private_mode": private_mode,
            "paste_cgevent": paste_cgevent,
            "paste_ax": paste_ax,
            "paste_clipboard": paste_clipboard,
            "llm_clipboard": llm_clipboard,
        }
        profile = cls.from_payload(payload)
        if profile is None:
            raise ValueError("Некорректный профиль микрофона.")
        return profile

    def to_payload(self) -> dict[str, object]:
        """Возвращает JSON-совместимое представление профиля."""
        return {
            "name": self.name,
            "input_device_index": self.input_device_index,
            "input_device_name": self.input_device_name,
            "model_repo": self.model_repo,
            "language": self.language,
            "max_time": self.max_time,
            "performance_mode": self.performance_mode,
            "private_mode": self.private_mode,
            "paste_cgevent": self.paste_cgevent,
            "paste_ax": self.paste_ax,
            "paste_clipboard": self.paste_clipboard,
            "llm_clipboard": self.llm_clipboard,
        }

    def matches_runtime(
        self,
        *,
        input_device_index: int | None,
        model_repo: str,
        language: str | None,
        max_time: int | float | None,
        performance_mode: str,
        private_mode: bool,
        paste_cgevent: bool,
        paste_ax: bool,
        paste_clipboard: bool,
        llm_clipboard: bool,
    ) -> bool:
        """Сравнивает профиль с текущими runtime-настройками."""
        return (
            self.input_device_index == input_device_index
            and self.model_repo == model_repo
            and self.language == language
            and self.max_time == max_time
            and self.performance_mode == performance_mode
            and self.private_mode == private_mode
            and self.paste_cgevent == paste_cgevent
            and self.paste_ax == paste_ax
            and self.paste_clipboard == paste_clipboard
            and self.llm_clipboard == llm_clipboard
        )


@dataclass(slots=True)
class AppSnapshot:
    """Снимок состояния контроллера диктовки для UI и тестов."""

    state: str
    started: bool
    elapsed_time: int
    model_repo: str
    model_name: str
    hotkey_status: str
    secondary_hotkey_status: str
    llm_hotkey_status: str
    primary_key_combination: str
    secondary_key_combination: str
    llm_key_combination: str
    llm_prompt_name: str
    performance_mode: str
    max_time: float | None
    max_time_options: list[float | None]
    model_options: list[str]
    languages: list[str] | None
    current_language: str | None
    input_devices: list[AudioDeviceInfo]
    current_input_device: AudioDeviceInfo | None
    permission_status: dict[str, bool | None]
    microphone_profiles: list[MicrophoneProfile]
    show_recording_notification: bool
    show_recording_overlay: bool
    private_mode_enabled: bool
    paste_cgevent_enabled: bool
    paste_ax_enabled: bool
    paste_clipboard_enabled: bool
    llm_clipboard_enabled: bool
    history: list[str]
    total_tokens: int
    llm_download_title: str
    llm_download_interactive: bool
    use_double_command_hotkey: bool
