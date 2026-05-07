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
        "mlx-community/Qwen3-ASR-1.7B-8bit",
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
    AUDIO_SAMPLE_RATE = 16000
    AUDIO_CHANNELS_MONO = 1
    AUDIO_PROFILE_GENERIC = "generic"
    AUDIO_PROFILE_MACBOOK_BUILTIN_HIGH_QUALITY = "macbook_builtin_high_quality"
    AUDIO_PROFILE_LABELS: ClassVar[dict[str, str]] = {
        AUDIO_PROFILE_GENERIC: "обычный",
        AUDIO_PROFILE_MACBOOK_BUILTIN_HIGH_QUALITY: "MacBook HQ",
    }
    AUDIO_POST_ROLL_MS_DEFAULT = 300
    AUDIO_POST_ROLL_MS_MIN = 100
    AUDIO_POST_ROLL_MS_MAX = 800
    AUDIO_NO_SPEECH_RMS_THRESHOLD = 0.0003
    AUDIO_NO_SPEECH_PEAK_THRESHOLD = 0.003
    AUDIO_MIN_RECORDING_DURATION_FOR_SKIP_S = 0.5
    AUDIO_VAD_FRAME_MS = 30
    AUDIO_VAD_MODE = 1
    AUDIO_TARGET_SPEECH_RMS = 0.05
    AUDIO_MAX_GAIN_DB = 9.0
    AUDIO_PEAK_LIMIT = 0.95
    AUDIO_DO_NOT_NORMALIZE_IF_PEAK_ABOVE = 0.80
    AUDIO_DO_NOT_NORMALIZE_IF_RMS_BELOW_WITHOUT_VAD_SPEECH = 0.0005
    AUDIO_CLIPPING_THRESHOLD = 0.98
    AUDIO_CLIPPING_WARNING_RATIO = 0.005
    MAX_DEBUG_ARTIFACTS = 10
    LOG_DIR = Path.home() / "Library/Logs/whisper-dictation"
    ARTIFACT_TTL_SECONDS = 24 * 60 * 60
    DISPLAY_SLEEP_RELEASE_GRACE_SECONDS = 0
    POWER_DIAGNOSTICS_COMMAND_TIMEOUT_SECONDS = 2.0
    POWER_DIAGNOSTICS_ENV = "DICTATOR_POWER_DIAGNOSTICS"
    SYSTEM_DIAGNOSTICS_ENV = "DICTATOR_SYSTEM_DIAGNOSTICS"
    ACCESSIBILITY_SETTINGS_URL = "x-apple.systempreferences:com.apple.preference.security?Privacy_Accessibility"
    INPUT_MONITORING_SETTINGS_URL = "x-apple.systempreferences:com.apple.preference.security?Privacy_ListenEvent"
    KEYCODE_COMMAND = 0x37
    KEYCODE_V = 0x09
    DEFAULTS_KEY_PASTE_CGEVENT = "paste_method_cgevent"
    DEFAULTS_KEY_PASTE_AX = "paste_method_ax"
    DEFAULTS_KEY_PASTE_CLIPBOARD = "paste_method_clipboard"
    DEFAULTS_KEY_CAPITALIZE_FIRST_LETTER = "capitalize_first_letter_enabled"
    DEFAULTS_KEY_REMOVE_TRAILING_PERIOD_FOR_SINGLE_SENTENCE = "remove_trailing_period_for_single_sentence_enabled"
    DEFAULTS_KEY_RESTORE_TRAILING_PERIOD_ON_NEXT_DICTATION = "restore_trailing_period_on_next_dictation_enabled"
    DEFAULTS_KEY_HISTORY = "transcription_history"
    DEFAULTS_KEY_PRIVATE_MODE = "private_mode"
    DEFAULTS_KEY_TOTAL_TOKENS = "total_token_usage"
    DEFAULTS_KEY_RECORDING_TIME_IN_MENU_BAR = "recording_time_in_menu_bar"
    MAX_HISTORY_SIZE = 20
    HISTORY_DISPLAY_LENGTH = 100
    CGEVENT_UNICODE_CHUNK_SIZE = 20
    CGEVENT_CHUNK_DELAY = 0.005
    CLIPBOARD_RESTORE_DELAY = 0.15
    DEFAULT_LLM_MODEL_NAME = "mlx-community/gemma-4-26b-a4b-it-4bit"
    LLM_MODEL_PRESETS: ClassVar[list[str]] = [
        "mlx-community/gemma-4-26b-a4b-it-4bit",
        "mlx-community/Huihui-Qwen3.5-4B-Claude-4.6-Opus-abliterated-6bit",
    ]
    LLM_MAX_TOKENS = 500
    LLM_RESPONSE_CHAR_LIMIT = 180
    LLM_NOTIFICATION_CHAR_LIMIT = 180
    LLM_OBSIDIAN_MAX_TOKENS = 1000
    LLM_OBSIDIAN_RESPONSE_CHAR_LIMIT = 2000
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
    DEFAULTS_KEY_LLM_MODEL = "llm_model"
    DEFAULTS_KEY_READER_RSVP_HOTKEY = "reader.rsvp.hotkey"
    DEFAULTS_KEY_READER_TTS_HOTKEY = "reader.tts.hotkey"
    DEFAULTS_KEY_READER_RSVP_WPM = "reader.rsvp.wpm"
    DEFAULTS_KEY_READER_RSVP_CHUNK_SIZE = "reader.rsvp.chunk_size"
    DEFAULTS_KEY_READER_RSVP_FONT_SIZE = "reader.rsvp.font_size"
    DEFAULTS_KEY_READER_TTS_RATE_MULTIPLIER = "reader.tts.rate_multiplier"
    DEFAULTS_KEY_READER_TTS_RATE_DEFAULT_V2 = "reader.tts.rate_multiplier.default_v2"
    DEFAULTS_KEY_READER_TTS_VOICE_ID = "reader.tts.voice_id"
    DEFAULTS_KEY_READER_TTS_MAX_MINUTES = "reader.tts.max_minutes"
    DEFAULTS_KEY_READER_TTS_ENGINE = "reader.tts.engine"
    DEFAULTS_KEY_READER_TTS_MLX_MODEL = "reader.tts.mlx_model"
    DEFAULTS_KEY_READER_TTS_MLX_VOICE_DESCRIPTION = "reader.tts.mlx_voice_description"
    DEFAULTS_KEY_READER_PREPROCESS_MODEL = "reader.preprocess.model"
    DEFAULTS_KEY_READER_PREPROCESS_ENABLED = "reader.preprocess.enabled"
    DEFAULTS_KEY_OBSIDIAN_VAULT = "obsidian_vault_path"
    DEFAULTS_KEY_RECORDING_NOTIFICATION = "show_recording_notification"
    DEFAULTS_KEY_RECORDING_OVERLAY = "recording_overlay"
    DEFAULTS_KEY_PERFORMANCE_MODE = "performance_mode"
    DEFAULTS_KEY_HIGH_QUALITY_MAC_BUILTIN = "audio_high_quality_mac_builtin"
    DEFAULTS_KEY_GAIN_NORMALIZATION = "audio_gain_normalization"
    DEFAULTS_KEY_AUDIO_ARTIFACT_CLEANUP = "audio_artifact_cleanup_enabled"
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
        "📝 Obsidian: заметка": (
            "Ты помощник для создания заметок в Obsidian. "
            "Пользователь диктует голосом заметку или задачу. "
            "Если это задача — верни её в формате '- [ ] описание задачи'. "
            "Если это заметка — верни аккуратно отформатированный текст. "
            "Добавь заголовок '# ' с кратким названием на первой строке. "
            "НЕ добавляй объяснений, только саму заметку. "
            "Используй markdown."
        ),
        "📝 Obsidian: напомни": (
            "Ты помощник для поиска заметок в Obsidian. "
            "Пользователь голосом описывает, что хочет вспомнить. "
            "В контексте ты получишь содержимое релевантных заметок из хранилища. "
            "Верни краткий ответ с ключевой информацией из найденных заметок. "
            "Если ничего не найдено — скажи что заметок по этой теме нет. "
            "Максимум 300 символов, plain text."
        ),
    }
    OBSIDIAN_PROMPT_NAMES: ClassVar[frozenset[str]] = frozenset(
        {
            "📝 Obsidian: заметка",
            "📝 Obsidian: напомни",
        }
    )
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

    @staticmethod
    def audio_profile_label(profile_name: str) -> str:
        """Возвращает человекочитаемую подпись аудиопрофиля."""
        return Config.AUDIO_PROFILE_LABELS.get(profile_name, Config.AUDIO_PROFILE_LABELS[Config.AUDIO_PROFILE_GENERIC])
