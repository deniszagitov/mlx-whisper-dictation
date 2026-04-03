"""Чистые константы и helper-функции приложения Dictator."""

from __future__ import annotations

from pathlib import Path
from typing import ClassVar


class Config:
    """Константы и пресеты приложения Dictator."""

    DEFAULT_MODEL_NAME = "mlx-community/whisper-large-v3-turbo"
    MODEL_PRESETS: ClassVar[list[str]] = [
        "mlx-community/whisper-large-v3-turbo",
        "mlx-community/whisper-large-v3-mlx",
        "mlx-community/whisper-turbo",
    ]
    MAX_TIME_PRESETS: ClassVar[list[int | None]] = [15, 30, 45, 60, 90, None]
    MIN_HOTKEY_PARTS = 2
    DOUBLE_COMMAND_PRESS_INTERVAL = 0.5
    STATUS_IDLE = "idle"
    STATUS_RECORDING = "recording"
    STATUS_TRANSCRIBING = "transcribing"
    STATUS_LLM_PROCESSING = "llm_processing"
    PERMISSION_GRANTED = "есть"
    PERMISSION_DENIED = "нет"
    PERMISSION_UNKNOWN = "неизвестно"
    SILENCE_RMS_THRESHOLD = 0.0005
    HALLUCINATION_RMS_THRESHOLD = 0.002
    SHORT_AUDIO_WARNING_SECONDS = 0.3
    MAX_DEBUG_ARTIFACTS = 10
    LOG_DIR = Path.home() / "Library/Logs/whisper-dictation"
    ARTIFACT_TTL_SECONDS = 24 * 60 * 60
    ACCESSIBILITY_SETTINGS_URL = (
        "x-apple.systempreferences:com.apple.preference.security?Privacy_Accessibility"
    )
    INPUT_MONITORING_SETTINGS_URL = (
        "x-apple.systempreferences:com.apple.preference.security?Privacy_ListenEvent"
    )
    KEYCODE_COMMAND = 0x37
    KEYCODE_V = 0x09
    DEFAULTS_KEY_PASTE_CGEVENT = "paste_method_cgevent"
    DEFAULTS_KEY_PASTE_AX = "paste_method_ax"
    DEFAULTS_KEY_PASTE_CLIPBOARD = "paste_method_clipboard"
    DEFAULTS_KEY_HISTORY = "transcription_history"
    DEFAULTS_KEY_PRIVATE_MODE = "private_mode"
    DEFAULTS_KEY_TOTAL_TOKENS = "total_token_usage"
    MAX_HISTORY_SIZE = 20
    HISTORY_DISPLAY_LENGTH = 100
    CGEVENT_UNICODE_CHUNK_SIZE = 20
    CGEVENT_CHUNK_DELAY = 0.005
    CLIPBOARD_RESTORE_DELAY = 0.15
    DEFAULT_LLM_MODEL_NAME = (
        "mlx-community/Huihui-Qwen3.5-4B-Claude-4.6-Opus-abliterated-6bit"
    )
    LLM_MAX_TOKENS = 500
    LLM_RESPONSE_CHAR_LIMIT = 180
    LLM_NOTIFICATION_CHAR_LIMIT = 180
    DOWNLOAD_COMPLETE_PCT = 100
    DEFAULTS_KEY_MODEL = "selected_model"
    DEFAULTS_KEY_LANGUAGE = "selected_language"
    DEFAULTS_KEY_INPUT_DEVICE_INDEX = "input_device_index"
    DEFAULTS_KEY_INPUT_DEVICE_NAME = "input_device_name"
    DEFAULTS_KEY_MAX_TIME = "max_recording_seconds"
    DEFAULTS_KEY_PRIMARY_HOTKEY = "primary_hotkey"
    DEFAULTS_KEY_SECONDARY_HOTKEY = "secondary_hotkey"
    DEFAULTS_KEY_LLM_HOTKEY = "llm_hotkey"
    DEFAULTS_KEY_LLM_PROMPT = "llm_prompt_preset"
    DEFAULTS_KEY_LLM_CLIPBOARD = "llm_clipboard_enabled"
    DEFAULTS_KEY_RECORDING_NOTIFICATION = "show_recording_notification"
    DEFAULTS_KEY_RECORDING_OVERLAY = "recording_overlay"
    DEFAULTS_KEY_PERFORMANCE_MODE = "performance_mode"
    DEFAULTS_KEY_MICROPHONE_PROFILES = "microphone_profiles"
    MAX_MICROPHONE_PROFILES = 10
    PERFORMANCE_MODE_NORMAL = "normal"
    PERFORMANCE_MODE_FAST = "fast"
    DEFAULT_PERFORMANCE_MODE = "normal"
    PERFORMANCE_MODE_LABELS: ClassVar[dict[str, str]] = {
        "normal": "Обычный",
        "fast": "Быстрый",
    }
    LLM_PROMPT_PRESETS: ClassVar[dict[str, str]] = {
        "Универсальный помощник": (
            "ПРАВИЛА: отвечай ОДНИМ предложением, максимум 180 символов. "
            "НЕ используй markdown, списки, нумерацию, заголовки. "
            "НЕ показывай анализ, рассуждения, черновик, ограничения или служебные шаги. "
            "Верни только готовое красивое сообщение plain text; можно добавить 1 уместный эмодзи."
        ),
        "Исправь текст": (
            "ПРАВИЛА: верни ТОЛЬКО исправленный текст, ничего больше. "
            "НЕ добавляй комментариев, пояснений, markdown. Максимум 180 символов. "
            "Если текст корректен — верни его как есть."
        ),
        "Переведи на English": (
            "RULES: return ONLY the English translation, nothing else. "
            "NO comments, NO markdown, NO explanations. Max 180 characters. Plain text only."
        ),
        "Переведи на русский": (
            "ПРАВИЛА: верни ТОЛЬКО перевод на русский, ничего больше. "
            "БЕЗ комментариев, БЕЗ markdown. Максимум 180 символов. Только plain text."
        ),
        "Резюме": (
            "ПРАВИЛА: сделай резюме ОДНИМ предложением, максимум 180 символов. "
            "БЕЗ markdown, БЕЗ списков, БЕЗ заголовков. Только plain text."
        ),
    }
    DEFAULT_LLM_PROMPT_NAME = "Универсальный помощник"
    KNOWN_HALLUCINATIONS: ClassVar[set[str]] = {
        "thank you",
        "thank you.",
        "продолжение следует",
        "продолжение следует...",
        "спасибо за внимание",
        "спасибо за просмотр",
    }

    @staticmethod
    def format_max_time_status(max_time: int | float | None) -> str:
        """Преобразует лимит длительности записи в строку для меню."""
        if max_time is None:
            return "без лимита"
        if float(max_time).is_integer():
            return f"{int(max_time)} с"
        return f"{max_time} с"

    @staticmethod
    def performance_mode_label(performance_mode: str) -> str:
        """Возвращает человекочитаемое имя режима работы."""
        return Config.PERFORMANCE_MODE_LABELS.get(
            performance_mode,
            Config.PERFORMANCE_MODE_LABELS[Config.DEFAULT_PERFORMANCE_MODE],
        )

    @staticmethod
    def normalize_performance_mode(performance_mode: object) -> str:
        """Нормализует идентификатор режима работы."""
        if performance_mode in Config.PERFORMANCE_MODE_LABELS:
            return str(performance_mode)
        return Config.DEFAULT_PERFORMANCE_MODE
