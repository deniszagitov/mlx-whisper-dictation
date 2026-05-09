"""Тесты спецификации нативного окна настроек."""

from src.adapters.settings_window import NAVIGATION_ITEMS, build_settings_screens

from .test_statusbar import make_downloadable_model_statuses, make_snapshot


def _screen_by_id(screens, identifier):
    """Возвращает экран по идентификатору."""
    return next(screen for screen in screens if screen.identifier == identifier)


def _row_titles(screen):
    """Возвращает все заголовки рядов на экране."""
    return {row.title for section in screen.sections for row in section.rows}


def test_settings_window_uses_design_navigation_sections():
    """Окно настроек должно повторять разделы из design-макета в toolbar-навигации."""
    screens = build_settings_screens(make_snapshot())

    assert [screen.identifier for screen in screens] == [
        "home",
        "recognition",
        "llm",
        "tts",
        "rsvp",
        "input",
        "hotkeys",
        "audio",
        "history",
        "permissions",
        "about",
    ]
    assert [item.identifier for item in NAVIGATION_ITEMS] == [screen.identifier for screen in screens]


def test_tts_screen_exposes_required_reader_controls():
    """Экран TTS должен содержать все критичные reader-настройки."""
    tts_screen = _screen_by_id(build_settings_screens(make_snapshot()), "tts")
    titles = _row_titles(tts_screen)

    assert {
        "Запустить TTS",
        "LLM-предобработка",
        "Backend",
        "MLX-модель",
        "Состояние MLX TTS-модели",
        "Описание MLX-голоса",
        "Голос",
        "Скорость речи",
        "Максимальная длительность",
    } <= titles


def test_rsvp_screen_exposes_required_reader_controls():
    """Экран RSVP должен содержать запуск и параметры чтения."""
    rsvp_screen = _screen_by_id(build_settings_screens(make_snapshot()), "rsvp")
    titles = _row_titles(rsvp_screen)

    assert {
        "Запустить RSVP",
        "LLM-предобработка",
        "Скорость чтения",
        "Размер chunk-а",
        "Размер шрифта",
    } <= titles


def test_permissions_screen_keeps_all_macos_permissions_visible():
    """Экран доступов должен показывать все критичные разрешения macOS."""
    permissions_screen = _screen_by_id(
        build_settings_screens(
            make_snapshot(permission_status={"accessibility": False, "input_monitoring": True, "microphone": None})
        ),
        "permissions",
    )
    rows = {row.title: row for section in permissions_screen.sections for row in section.rows}

    assert rows["Accessibility"].value == "Не предоставлено"
    assert rows["Input Monitoring"].value == "Предоставлено"
    assert rows["Microphone"].value == "Неизвестно"


def test_history_screen_exposes_obsidian_archive_search():
    """Экран истории должен давать доступ к поиску по Obsidian-архиву."""
    history_screen = _screen_by_id(build_settings_screens(make_snapshot()), "history")
    titles = _row_titles(history_screen)

    assert {"Спросить историю", "Obsidian vault", "Папка архива", "Открыть архив в Finder", "Бакеты", "Прод"} <= titles


def test_downloadable_models_have_markers_and_delete_action():
    """Скачиваемые модели должны показывать статус и действие удаления."""
    model_statuses = make_downloadable_model_statuses("mlx-community/whisper-turbo", downloaded=False)
    snapshot = make_snapshot(
        model_repo="mlx-community/whisper-turbo",
        model_options=["mlx-community/whisper-turbo"],
        downloadable_models=model_statuses,
    )
    recognition_screen = _screen_by_id(build_settings_screens(snapshot), "recognition")
    rows = {row.title: row for section in recognition_screen.sections for row in section.rows}

    model_row = rows["Whisper-модель"]
    status_row = rows["Состояние Whisper-модели"]

    assert "не загружено" in model_row.options[0].title
    assert status_row.control == "model_status"
    assert status_row.value.can_download is True
    assert status_row.secondary_action == "delete_downloaded_model"


def test_settings_screens_explain_domain_terms():
    """Внутренние экраны должны раскрывать STT, LLM, TTS и RSVP."""
    screens = {screen.identifier: screen for screen in build_settings_screens(make_snapshot())}

    assert "Speech-to-Text" in screens["recognition"].description
    assert "Large Language Model" in screens["llm"].description
    assert "Text-to-Speech" in screens["tts"].description
    assert "Rapid Serial Visual Presentation" in screens["rsvp"].description
