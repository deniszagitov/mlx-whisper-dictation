"""Константы и настройки приложения Dictator.

Содержит все конфигурационные значения, пресеты и хелперы для работы
с NSUserDefaults.
"""

from pathlib import Path

from Foundation import NSUserDefaults

DEFAULT_MODEL_NAME = "mlx-community/whisper-large-v3-turbo"
MODEL_PRESETS = [
    "mlx-community/whisper-large-v3-turbo",
    "mlx-community/whisper-large-v3-mlx",
    "mlx-community/whisper-turbo",
]
MAX_TIME_PRESETS = [15, 30, 45, 60, 90, None]
MIN_HOTKEY_PARTS = 2
DOUBLE_COMMAND_PRESS_INTERVAL = 0.5
STATUS_IDLE = "idle"
STATUS_RECORDING = "recording"
STATUS_TRANSCRIBING = "transcribing"
PERMISSION_GRANTED = "есть"
PERMISSION_DENIED = "нет"
PERMISSION_UNKNOWN = "неизвестно"
SILENCE_RMS_THRESHOLD = 0.0005
HALLUCINATION_RMS_THRESHOLD = 0.002
SHORT_AUDIO_WARNING_SECONDS = 0.3
MAX_DEBUG_ARTIFACTS = 10
LOG_DIR = Path.home() / "Library/Logs/whisper-dictation"
ARTIFACT_TTL_SECONDS = 24 * 60 * 60
ACCESSIBILITY_SETTINGS_URL = "x-apple.systempreferences:com.apple.preference.security?Privacy_Accessibility"
INPUT_MONITORING_SETTINGS_URL = "x-apple.systempreferences:com.apple.preference.security?Privacy_ListenEvent"
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
DEFAULT_LLM_MODEL_NAME = "mlx-community/Huihui-Qwen3.5-4B-Claude-4.6-Opus-abliterated-6bit"
LLM_MAX_TOKENS = 150
LLM_RESPONSE_CHAR_LIMIT = 180
LLM_NOTIFICATION_CHAR_LIMIT = LLM_RESPONSE_CHAR_LIMIT
DOWNLOAD_COMPLETE_PCT = 100
DEFAULTS_KEY_MODEL = "selected_model"
DEFAULTS_KEY_LANGUAGE = "selected_language"
DEFAULTS_KEY_INPUT_DEVICE_INDEX = "input_device_index"
DEFAULTS_KEY_MAX_TIME = "max_recording_seconds"
DEFAULTS_KEY_PRIMARY_HOTKEY = "primary_hotkey"
DEFAULTS_KEY_SECONDARY_HOTKEY = "secondary_hotkey"
DEFAULTS_KEY_LLM_HOTKEY = "llm_hotkey"
DEFAULTS_KEY_LLM_PROMPT = "llm_prompt_preset"
DEFAULTS_KEY_LLM_CLIPBOARD = "llm_clipboard_enabled"
DEFAULTS_KEY_RECORDING_NOTIFICATION = "show_recording_notification"
DEFAULTS_KEY_PERFORMANCE_MODE = "performance_mode"
DEFAULTS_KEY_MICROPHONE_PROFILES = "microphone_profiles"
MAX_MICROPHONE_PROFILES = 10
STATUS_LLM_PROCESSING = "llm_processing"
PERFORMANCE_MODE_NORMAL = "normal"
PERFORMANCE_MODE_FAST = "fast"
DEFAULT_PERFORMANCE_MODE = PERFORMANCE_MODE_NORMAL
PERFORMANCE_MODE_LABELS = {
    PERFORMANCE_MODE_NORMAL: "Обычный",
    PERFORMANCE_MODE_FAST: "Быстрый",
}
LLM_PROMPT_PRESETS = {
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
        "ПРАВИЛА: верни ТОЛЬКО перевод на русский, ничего больше. БЕЗ комментариев, БЕЗ markdown. Максимум 180 символов. Только plain text."
    ),
    "Резюме": (
        "ПРАВИЛА: сделай резюме ОДНИМ предложением, максимум 180 символов. БЕЗ markdown, БЕЗ списков, БЕЗ заголовков. Только plain text."
    ),
}
DEFAULT_LLM_PROMPT_NAME = "Универсальный помощник"
KNOWN_HALLUCINATIONS = {
    "thank you",
    "thank you.",
    "продолжение следует",
    "продолжение следует...",
    "спасибо за внимание",
    "спасибо за просмотр",
}


def _load_defaults_bool(key, fallback):
    """Читает булево значение из NSUserDefaults.

    Если ключ ещё не был записан, возвращает fallback.

    Args:
        key: Строковый ключ в NSUserDefaults.
        fallback: Значение по умолчанию, если ключ отсутствует.

    Returns:
        Сохранённое значение или fallback.
    """
    defaults = NSUserDefaults.standardUserDefaults()
    if defaults.objectForKey_(key) is None:
        return fallback
    return bool(defaults.boolForKey_(key))


def _save_defaults_bool(key, value):
    """Сохраняет булево значение в NSUserDefaults.

    Args:
        key: Строковый ключ.
        value: Булево значение для сохранения.
    """
    NSUserDefaults.standardUserDefaults().setBool_forKey_(bool(value), key)


def _load_defaults_list(key):
    """Читает список строк из NSUserDefaults.

    Args:
        key: Строковый ключ.

    Returns:
        Список строк или пустой список, если ключ отсутствует.
    """
    defaults = NSUserDefaults.standardUserDefaults()
    value = defaults.arrayForKey_(key)
    if value is None:
        return []
    return [str(item) for item in value]


def _save_defaults_list(key, value):
    """Сохраняет список строк в NSUserDefaults.

    Args:
        key: Строковый ключ.
        value: Список строк для сохранения.
    """
    NSUserDefaults.standardUserDefaults().setObject_forKey_(list(value), key)


def _load_defaults_int(key, fallback):
    """Читает целое значение из NSUserDefaults.

    Args:
        key: Строковый ключ в NSUserDefaults.
        fallback: Значение по умолчанию, если ключ отсутствует.

    Returns:
        Сохранённое целое значение или fallback.
    """
    defaults = NSUserDefaults.standardUserDefaults()
    if defaults.objectForKey_(key) is None:
        return int(fallback)
    return int(defaults.integerForKey_(key))


def _save_defaults_int(key, value):
    """Сохраняет целое значение в NSUserDefaults.

    Args:
        key: Строковый ключ.
        value: Целое значение для сохранения.
    """
    NSUserDefaults.standardUserDefaults().setInteger_forKey_(int(value), key)


def _load_defaults_str(key, fallback=None):
    """Читает строковое значение из NSUserDefaults."""
    defaults = NSUserDefaults.standardUserDefaults()
    value = defaults.objectForKey_(key)
    if value is None:
        return fallback
    return str(value)


def _save_defaults_str(key, value):
    """Сохраняет строковое значение в NSUserDefaults."""
    NSUserDefaults.standardUserDefaults().setObject_forKey_(str(value), key)


def _load_defaults_max_time(fallback):
    """Читает лимит записи из NSUserDefaults."""
    value = _load_defaults_str(DEFAULTS_KEY_MAX_TIME, fallback=None)
    if value is None:
        return fallback
    if value == "none":
        return None
    parsed = float(value)
    if parsed.is_integer():
        return int(parsed)
    return parsed


def _save_defaults_max_time(value):
    """Сохраняет лимит записи в NSUserDefaults."""
    if value is None:
        _save_defaults_str(DEFAULTS_KEY_MAX_TIME, "none")
        return
    _save_defaults_str(DEFAULTS_KEY_MAX_TIME, value)


def _load_defaults_input_device_index():
    """Читает индекс сохранённого микрофона из NSUserDefaults."""
    defaults = NSUserDefaults.standardUserDefaults()
    value = defaults.objectForKey_(DEFAULTS_KEY_INPUT_DEVICE_INDEX)
    if value is None:
        return None
    index = int(defaults.integerForKey_(DEFAULTS_KEY_INPUT_DEVICE_INDEX))
    return None if index < 0 else index


def _save_defaults_input_device_index(value):
    """Сохраняет индекс выбранного микрофона в NSUserDefaults."""
    _save_defaults_int(DEFAULTS_KEY_INPUT_DEVICE_INDEX, -1 if value is None else value)


def _remove_defaults_key(key):
    """Удаляет ключ из NSUserDefaults."""
    NSUserDefaults.standardUserDefaults().removeObjectForKey_(key)


def _performance_mode_label(performance_mode):
    """Возвращает человекочитаемое имя режима работы."""
    return PERFORMANCE_MODE_LABELS.get(performance_mode, PERFORMANCE_MODE_LABELS[DEFAULT_PERFORMANCE_MODE])


def _normalize_performance_mode(performance_mode):
    """Нормализует идентификатор режима работы."""
    return performance_mode if performance_mode in PERFORMANCE_MODE_LABELS else DEFAULT_PERFORMANCE_MODE


def format_max_time_status(max_time):
    """Преобразует лимит длительности записи в строку для меню."""
    if max_time is None:
        return "без лимита"
    if float(max_time).is_integer():
        return f"{int(max_time)} с"
    return f"{max_time} с"
