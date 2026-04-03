"""Persistence-обёртка над NSUserDefaults."""

from __future__ import annotations

from Foundation import NSUserDefaults

from ...domain.constants import Config


class Defaults:
    """Синглтон-фабрика для чтения и записи NSUserDefaults."""

    _instance: Defaults | None = None

    def __new__(cls) -> Defaults:
        """Гарантирует единственный экземпляр Defaults."""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def load_bool(self, key: str, fallback: bool) -> bool:
        """Читает булево значение из NSUserDefaults."""
        defaults = NSUserDefaults.standardUserDefaults()
        if defaults.objectForKey_(key) is None:
            return fallback
        return bool(defaults.boolForKey_(key))

    def contains_key(self, key: str) -> bool:
        """Проверяет наличие ключа в NSUserDefaults."""
        return NSUserDefaults.standardUserDefaults().objectForKey_(key) is not None

    def save_bool(self, key: str, value: bool) -> None:
        """Сохраняет булево значение в NSUserDefaults."""
        NSUserDefaults.standardUserDefaults().setBool_forKey_(bool(value), key)

    def load_list(self, key: str) -> list[str]:
        """Читает список строк из NSUserDefaults."""
        defaults = NSUserDefaults.standardUserDefaults()
        value = defaults.arrayForKey_(key)
        if value is None:
            return []
        return [str(item) for item in value]

    def save_list(self, key: str, value: list[str]) -> None:
        """Сохраняет список строк в NSUserDefaults."""
        NSUserDefaults.standardUserDefaults().setObject_forKey_(list(value), key)

    def load_int(self, key: str, fallback: int) -> int:
        """Читает целое значение из NSUserDefaults."""
        defaults = NSUserDefaults.standardUserDefaults()
        if defaults.objectForKey_(key) is None:
            return int(fallback)
        return int(defaults.integerForKey_(key))

    def save_int(self, key: str, value: int) -> None:
        """Сохраняет целое значение в NSUserDefaults."""
        NSUserDefaults.standardUserDefaults().setInteger_forKey_(int(value), key)

    def load_str(self, key: str, fallback: str | None = None) -> str | None:
        """Читает строковое значение из NSUserDefaults."""
        defaults = NSUserDefaults.standardUserDefaults()
        value = defaults.objectForKey_(key)
        if value is None:
            return fallback
        return str(value)

    def save_str(self, key: str, value: object) -> None:
        """Сохраняет строковое значение в NSUserDefaults."""
        NSUserDefaults.standardUserDefaults().setObject_forKey_(str(value), key)

    def load_max_time(self, fallback: int | float | None) -> int | float | None:
        """Читает лимит записи из NSUserDefaults."""
        value = self.load_str(Config.DEFAULTS_KEY_MAX_TIME, fallback=None)
        if value is None:
            return fallback
        if value == "none":
            return None
        parsed = float(value)
        if parsed.is_integer():
            return int(parsed)
        return parsed

    def save_max_time(self, value: int | float | None) -> None:
        """Сохраняет лимит записи в NSUserDefaults."""
        if value is None:
            self.save_str(Config.DEFAULTS_KEY_MAX_TIME, "none")
            return
        self.save_str(Config.DEFAULTS_KEY_MAX_TIME, value)

    def load_input_device_index(self) -> int | None:
        """Читает индекс сохранённого микрофона из NSUserDefaults."""
        defaults = NSUserDefaults.standardUserDefaults()
        value = defaults.objectForKey_(Config.DEFAULTS_KEY_INPUT_DEVICE_INDEX)
        if value is None:
            return None
        index = int(defaults.integerForKey_(Config.DEFAULTS_KEY_INPUT_DEVICE_INDEX))
        return None if index < 0 else index

    def load_input_device_name(self) -> str | None:
        """Читает имя сохранённого микрофона из NSUserDefaults."""
        defaults = NSUserDefaults.standardUserDefaults()
        value = defaults.objectForKey_(Config.DEFAULTS_KEY_INPUT_DEVICE_NAME)
        if value is None:
            return None
        normalized = str(value).strip()
        return normalized or None

    def save_input_device_index(self, value: int | None) -> None:
        """Сохраняет индекс выбранного микрофона в NSUserDefaults."""
        self.save_int(Config.DEFAULTS_KEY_INPUT_DEVICE_INDEX, -1 if value is None else value)

    def save_input_device_name(self, value: str | None) -> None:
        """Сохраняет имя выбранного микрофона в NSUserDefaults."""
        if value is None:
            self.remove_key(Config.DEFAULTS_KEY_INPUT_DEVICE_NAME)
            return
        normalized = str(value).strip()
        if not normalized:
            self.remove_key(Config.DEFAULTS_KEY_INPUT_DEVICE_NAME)
            return
        self.save_str(Config.DEFAULTS_KEY_INPUT_DEVICE_NAME, normalized)

    def remove_key(self, key: str) -> None:
        """Удаляет ключ из NSUserDefaults."""
        NSUserDefaults.standardUserDefaults().removeObjectForKey_(key)
