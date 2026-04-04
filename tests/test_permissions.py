"""Тесты разрешений macOS (Accessibility, Input Monitoring, Microphone).

Проверяет, что функции проверки разрешений возвращают корректные типы
и что вспомогательная логика приложения правильно обрабатывает все возможные
значения разрешений.
"""


class TestPermissionLabel:
    """Тесты преобразования статуса разрешения в строку для меню."""

    def test_granted(self, app_module):
        """True должен стать 'есть'."""
        assert app_module.permission_label(True) == "есть"

    def test_denied(self, app_module):
        """False должен стать 'нет'."""
        assert app_module.permission_label(False) == "нет"

    def test_unknown(self, app_module):
        """None должен стать 'неизвестно'."""
        assert app_module.permission_label(None) == "неизвестно"


class TestPermissionPreflightStatus:
    """Тесты вызова preflight-функций разрешений."""

    def test_accessibility_returns_bool_or_none(self, app_module):
        """get_accessibility_status должен вернуть True, False или None."""
        result = app_module.get_accessibility_status()
        assert result is True or result is False or result is None

    def test_input_monitoring_returns_bool_or_none(self, app_module):
        """get_input_monitoring_status должен вернуть True, False или None."""
        result = app_module.get_input_monitoring_status()
        assert result is True or result is False or result is None

    def test_nonexistent_function_returns_none(self, app_module):
        """Несуществующая функция должна вернуть None."""
        result = app_module.permission_preflight_status("NonExistentFunction12345")
        assert result is None

    def test_is_accessibility_trusted_returns_bool(self, app_module):
        """is_accessibility_trusted должен вернуть True или False."""
        result = app_module.is_accessibility_trusted()
        assert isinstance(result, bool)


class TestWakeObserver:
    """Тесты регистрации observer пробуждения macOS."""

    def test_register_wake_observer_subscribes_notification_center(self, app_module, monkeypatch):
        """register_wake_observer должен подписаться на NSWorkspaceDidWakeNotification."""
        import src.infrastructure.permissions as permissions_module

        added_calls = []

        def shared_workspace():
            return FakeWorkspace()

        class FakeCenter:
            def addObserver_selector_name_object_(self, observer, selector, name, obj):
                added_calls.append((observer, selector, name, obj))

        class FakeWorkspace:
            def notificationCenter(self):
                return FakeCenter()

        monkeypatch.setattr(permissions_module.platform, "system", lambda: "Darwin")
        monkeypatch.setattr(
            permissions_module.AppKit,
            "NSWorkspace",
            type("WorkspaceStub", (), {"sharedWorkspace": staticmethod(shared_workspace)}),
        )
        monkeypatch.setattr(permissions_module.AppKit, "NSWorkspaceDidWakeNotification", "wake")

        observer = permissions_module.register_wake_observer(lambda: None)

        assert observer is not None
        assert len(added_calls) == 1
        assert added_calls[0][1] == b"handleWake:"
        assert added_calls[0][2] == "wake"

    def test_workspace_observer_calls_python_callback(self, app_module):
        """Objective-C observer должен пробрасывать wake в Python callback."""
        import src.infrastructure.permissions as permissions_module

        calls = []
        observer = permissions_module._WorkspaceWakeObserver.observerWithCallback_(lambda: calls.append(True))

        observer.handleWake_(None)

        assert calls == [True]


class TestApplicationActivationObserver:
    """Тесты регистрации observer смены активного приложения."""

    def test_register_application_activation_observer_subscribes_notification_center(self, app_module, monkeypatch):
        """Observer смены приложения должен подписаться на NSWorkspaceDidActivateApplicationNotification."""
        import src.infrastructure.permissions as permissions_module

        added_calls = []

        def shared_workspace():
            return FakeWorkspace()

        class FakeCenter:
            def addObserver_selector_name_object_(self, observer, selector, name, obj):
                added_calls.append((observer, selector, name, obj))

        class FakeWorkspace:
            def notificationCenter(self):
                return FakeCenter()

        monkeypatch.setattr(permissions_module.platform, "system", lambda: "Darwin")
        monkeypatch.setattr(
            permissions_module.AppKit,
            "NSWorkspace",
            type("WorkspaceStub", (), {"sharedWorkspace": staticmethod(shared_workspace)}),
        )
        monkeypatch.setattr(
            permissions_module.AppKit,
            "NSWorkspaceDidActivateApplicationNotification",
            "activate",
        )

        observer = permissions_module.register_application_activation_observer(lambda _info: None)

        assert observer is not None
        assert len(added_calls) == 1
        assert added_calls[0][1] == b"handleApplicationActivate:"
        assert added_calls[0][2] == "activate"

    def test_application_observer_calls_python_callback_with_frontmost_app(self, app_module, monkeypatch):
        """Objective-C observer должен пробрасывать текущее активное приложение в Python callback."""
        import src.infrastructure.permissions as permissions_module

        calls: list[dict[str, str | int] | None] = []
        monkeypatch.setattr(
            permissions_module,
            "frontmost_application_info",
            lambda: {"name": "Notes", "bundle_id": "com.apple.Notes", "pid": 42},
        )
        observer = permissions_module._WorkspaceApplicationObserver.observerWithCallback_(calls.append)

        observer.handleApplicationActivate_(None)

        assert calls == [{"name": "Notes", "bundle_id": "com.apple.Notes", "pid": 42}]
