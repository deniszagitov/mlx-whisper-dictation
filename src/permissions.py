"""Разрешения macOS и системные утилиты приложения Dictator.

Проверка и запрос Accessibility, Input Monitoring, уведомления,
открытие System Settings и информация об активном приложении.
"""

import ctypes
import logging
import platform

import AppKit
import objc
import Quartz
import rumps
from Foundation import NSURL, NSDictionary

from config import (
    ACCESSIBILITY_SETTINGS_URL,
    INPUT_MONITORING_SETTINGS_URL,
    PERMISSION_DENIED,
    PERMISSION_GRANTED,
    PERMISSION_UNKNOWN,
)

LOGGER = logging.getLogger(__name__)


def notify_user(title, message):
    """Показывает системное уведомление macOS.

    Args:
        title: Заголовок уведомления.
        message: Основной текст уведомления.
    """
    try:
        rumps.notification(title, "", message)
    except Exception:
        LOGGER.exception("❌ Не удалось показать системное уведомление macOS")


def open_system_settings(url):
    """Открывает нужный раздел System Settings по специальной ссылке macOS."""
    if platform.system() != "Darwin":
        return False

    try:
        settings_url = NSURL.URLWithString_(url)
        return bool(AppKit.NSWorkspace.sharedWorkspace().openURL_(settings_url))
    except Exception:
        LOGGER.exception("❌ Не удалось открыть System Settings: %s", url)
        return False


def frontmost_application_info():
    """Возвращает краткую информацию о текущем активном приложении."""
    try:
        workspace = AppKit.NSWorkspace.sharedWorkspace()
        application = workspace.frontmostApplication()
        if application is None:
            return None

        return {
            "name": str(application.localizedName() or ""),
            "bundle_id": str(application.bundleIdentifier() or ""),
            "pid": int(application.processIdentifier()),
        }
    except Exception:
        LOGGER.exception("❌ Не удалось определить активное приложение")
        return None


def is_accessibility_trusted():
    """Проверяет, выдан ли процессу доступ к Accessibility на macOS.

    Returns:
        True, если приложение может использовать глобальные события клавиатуры,
        иначе False.
    """
    if platform.system() != "Darwin":
        return True

    try:
        return permission_preflight_status("AXIsProcessTrusted") is not False
    except Exception:
        LOGGER.exception("❌ Не удалось проверить статус Accessibility")
        return True


def permission_preflight_status(function_name):
    """Вызывает preflight-функцию из ApplicationServices, если она доступна.

    Args:
        function_name: Имя C-функции из ApplicationServices.

    Returns:
        True, False или None, если статус нельзя определить.
    """
    if platform.system() != "Darwin":
        return True

    try:
        application_services = ctypes.CDLL("/System/Library/Frameworks/ApplicationServices.framework/ApplicationServices")
        preflight_function = getattr(application_services, function_name, None)
        if preflight_function is None:
            return None
        preflight_function.restype = ctypes.c_bool
        return bool(preflight_function())
    except Exception:
        LOGGER.exception("❌ Не удалось проверить статус разрешения %s", function_name)
        return None


def get_accessibility_status():
    """Возвращает статус доступа к Accessibility."""
    return permission_preflight_status("AXIsProcessTrusted")


def get_input_monitoring_status():
    """Возвращает статус доступа к Input Monitoring."""
    return permission_preflight_status("CGPreflightListenEventAccess")


def request_accessibility_permission():
    """Запрашивает Accessibility через системный диалог macOS.

    Вызывает AXIsProcessTrustedWithOptions с kAXTrustedCheckOptionPrompt=True,
    чтобы macOS показала пользователю диалог с предложением открыть настройки.

    Returns:
        True, если разрешение уже выдано, False если нужно выдать вручную.
    """
    if platform.system() != "Darwin":
        return True

    try:
        application_services = ctypes.CDLL("/System/Library/Frameworks/ApplicationServices.framework/ApplicationServices")
        options = NSDictionary.dictionaryWithObject_forKey_(True, "AXTrustedCheckOptionPrompt")
        request_function = getattr(application_services, "AXIsProcessTrustedWithOptions", None)
        if request_function is None:
            LOGGER.warning("⚠️ AXIsProcessTrustedWithOptions не найдена")
            return False

        request_function.restype = ctypes.c_bool
        request_function.argtypes = [ctypes.c_void_p]
        result = bool(request_function(objc.pyobjc_id(options)))
    except Exception:
        LOGGER.exception("❌ Не удалось запросить Accessibility")
        return False
    else:
        return result


def request_input_monitoring_permission():
    """Запрашивает Input Monitoring через системный диалог macOS.

    Вызывает CGRequestListenEventAccess, чтобы macOS показала пользователю
    диалог с предложением открыть настройки Input Monitoring.

    Returns:
        True, если разрешение уже выдано, False если нужно выдать вручную.
    """
    if platform.system() != "Darwin":
        return True

    try:
        request_function = getattr(Quartz, "CGRequestListenEventAccess", None)
        if request_function is None:
            LOGGER.warning("⚠️ CGRequestListenEventAccess не найдена")
            return False
        return bool(request_function())
    except Exception:
        LOGGER.exception("❌ Не удалось запросить Input Monitoring")
        return False


def permission_label(status):
    """Преобразует булев статус разрешения в строку для меню.

    Args:
        status: True, False или None.

    Returns:
        Строковое значение статуса.
    """
    if status is True:
        return PERMISSION_GRANTED
    if status is False:
        return PERMISSION_DENIED
    return PERMISSION_UNKNOWN


def warn_missing_accessibility_permission():
    """Показывает пользователю предупреждение об отсутствии Accessibility-доступа."""
    message = (
        "Нет доступа к Accessibility для MLX Whisper Dictation. "
        "Без него не будут работать глобальный хоткей и вставка текста. "
        "Откройте System Settings -> Privacy & Security -> Accessibility и включите приложение заново."
    )
    LOGGER.error("🔐 %s", message)
    open_system_settings(ACCESSIBILITY_SETTINGS_URL)
    notify_user("MLX Whisper Dictation", message)


def warn_missing_input_monitoring_permission():
    """Показывает пользователю предупреждение об отсутствии Input Monitoring."""
    message = (
        "Нет доступа к Input Monitoring для MLX Whisper Dictation. "
        "Без него macOS может блокировать глобальный хоткей или синтетический ввод. "
        "Откройте System Settings -> Privacy & Security -> Input Monitoring и включите приложение заново."
    )
    LOGGER.error("🔐 %s", message)
    open_system_settings(INPUT_MONITORING_SETTINGS_URL)
    notify_user("MLX Whisper Dictation", message)
