"""Тесты переключения LLM-моделей и Obsidian-интеграции."""

from __future__ import annotations

import tempfile
from pathlib import Path
from unittest.mock import MagicMock

from src.domain.constants import Config
from src.domain.llm_processing import detect_obsidian_action
from src.infrastructure.llm_runtime import LlmGateway, _is_vlm_model
from src.infrastructure.obsidian import (
    _sanitize_filename,
    get_default_vault_path,
    search_obsidian_notes,
    write_obsidian_note,
)


class TestLlmModelDetection:
    """Тесты определения типа LLM-модели (VLM vs LM)."""

    def test_gemma4_detected_as_vlm(self):
        """Gemma 4 должна определяться как VLM-модель."""
        assert _is_vlm_model("mlx-community/gemma-4-26b-a4b-it-4bit") is True

    def test_qwen_detected_as_lm(self):
        """Qwen 3.5 должна определяться как обычная LM-модель."""
        assert _is_vlm_model("mlx-community/Huihui-Qwen3.5-4B-Claude-4.6-Opus-abliterated-6bit") is False

    def test_unknown_model_detected_as_lm(self):
        """Неизвестная модель по умолчанию считается LM."""
        assert _is_vlm_model("some-other-model") is False

    def test_vision_model_detected_as_vlm(self):
        """Модель с 'vision' в имени определяется как VLM."""
        assert _is_vlm_model("mlx-community/some-vision-model") is True


class TestLlmGatewayChangeModel:
    """Тесты переключения модели через LlmGateway."""

    def test_change_model_updates_name(self):
        """change_model должен обновить model_name."""
        lm_loader = MagicMock(return_value=(MagicMock(), MagicMock()))
        vlm_loader = MagicMock(return_value=(MagicMock(), MagicMock()))
        gw = LlmGateway(
            "mlx-community/Huihui-Qwen3.5-4B-Claude-4.6-Opus-abliterated-6bit",
            runtime_loader=lm_loader,
            generation_runner=MagicMock(return_value="ok"),
            vlm_runtime_loader=vlm_loader,
            vlm_generation_runner=MagicMock(return_value="ok"),
        )
        assert gw.model_name == "mlx-community/Huihui-Qwen3.5-4B-Claude-4.6-Opus-abliterated-6bit"

        gw.change_model("mlx-community/gemma-4-26b-a4b-it-4bit")
        assert gw.model_name == "mlx-community/gemma-4-26b-a4b-it-4bit"

    def test_change_model_same_name_is_noop(self):
        """change_model с тем же именем ничего не делает."""
        cleanup = MagicMock()
        gw = LlmGateway(
            "model-a",
            runtime_loader=MagicMock(return_value=(MagicMock(), MagicMock())),
            generation_runner=MagicMock(return_value="ok"),
            memory_cleanup=cleanup,
        )
        gw.change_model("model-a")
        cleanup.assert_not_called()

    def test_change_model_unloads_cached(self):
        """change_model выгружает ранее кэшированную модель."""
        cleanup = MagicMock()
        lm_loader = MagicMock(return_value=(MagicMock(), MagicMock()))
        gw = LlmGateway(
            "model-a",
            runtime_loader=lm_loader,
            generation_runner=MagicMock(return_value="ok"),
            memory_cleanup=cleanup,
        )
        gw.performance_mode = "fast"
        gw._load_runtime_objects()
        assert gw._cached_model is not None

        gw.change_model("model-b")
        assert gw._cached_model is None
        cleanup.assert_called_once()

    def test_change_model_switches_to_vlm_backend(self):
        """Переключение на VLM-модель должно выбрать VLM backend."""
        lm_loader = MagicMock(return_value=(MagicMock(), MagicMock()))
        vlm_loader = MagicMock(return_value=(MagicMock(), MagicMock()))
        gw = LlmGateway(
            "regular-model",
            runtime_loader=lm_loader,
            generation_runner=MagicMock(return_value="ok"),
            vlm_runtime_loader=vlm_loader,
            vlm_generation_runner=MagicMock(return_value="ok"),
            memory_cleanup=MagicMock(),
        )
        assert gw._runtime_loader is lm_loader

        gw.change_model("mlx-community/gemma-4-26b-a4b-it-4bit")
        assert gw._runtime_loader is vlm_loader


class TestLlmModelPresets:
    """Тесты конфигурации пресетов LLM-моделей."""

    def test_default_llm_model_is_gemma4(self):
        """Модель по умолчанию — Gemma 4."""
        assert "gemma-4" in Config.DEFAULT_LLM_MODEL_NAME

    def test_presets_contain_both_models(self):
        """Пресеты содержат Gemma 4 и Qwen."""
        assert len(Config.LLM_MODEL_PRESETS) >= 2
        names = " ".join(Config.LLM_MODEL_PRESETS).lower()
        assert "gemma" in names
        assert "qwen" in names

    def test_obsidian_prompt_presets_exist(self):
        """В пресетах промптов есть Obsidian-пресеты."""
        assert "📝 Obsidian: заметка" in Config.LLM_PROMPT_PRESETS
        assert "📝 Obsidian: напомни" in Config.LLM_PROMPT_PRESETS

    def test_obsidian_prompt_names_match_presets(self):
        """OBSIDIAN_PROMPT_NAMES совпадают с ключами пресетов."""
        for name in Config.OBSIDIAN_PROMPT_NAMES:
            assert name in Config.LLM_PROMPT_PRESETS


class TestObsidianActionDetection:
    """Тесты определения Obsidian-действий по тексту."""

    def test_write_action_detected(self):
        """'запиши' определяется как действие 'write'."""
        assert detect_obsidian_action("запиши что мне нужно настроить бакеты для прода") == "write"

    def test_remind_action_detected(self):
        """'напомни' определяется как действие 'remind'."""
        assert detect_obsidian_action("напомни что мне нужно сделать по поводу налогов") == "remind"

    def test_task_action_detected(self):
        """'задачу' определяется как действие 'write'."""
        assert detect_obsidian_action("добавь задачу проверить конфиг") == "write"

    def test_empty_text_returns_none(self):
        """Пустой текст возвращает None."""
        assert detect_obsidian_action("") is None


class TestObsidianVault:
    """Тесты записи и поиска заметок в Obsidian vault."""

    def test_write_note_creates_file(self, tmp_path):
        """Заметка записывается в файл в vault."""
        content = "# Тестовая заметка\nТело заметки."
        path = write_obsidian_note(tmp_path, content)
        assert path.exists()
        assert path.read_text(encoding="utf-8") == content
        assert "Тестовая заметка" in path.name

    def test_write_note_avoids_collision(self, tmp_path):
        """При коллизии имён добавляется суффикс."""
        content = "# Заметка\nСодержимое."
        path1 = write_obsidian_note(tmp_path, content)
        path2 = write_obsidian_note(tmp_path, content)
        assert path1 != path2
        assert path2.exists()

    def test_write_note_creates_directory(self):
        """Vault-директория создаётся при необходимости."""
        with tempfile.TemporaryDirectory() as tmp:
            vault = Path(tmp) / "nested" / "vault"
            path = write_obsidian_note(vault, "# Test\nBody")
            assert path.exists()
            assert vault.is_dir()

    def test_search_notes_finds_matching(self, tmp_path):
        """Поиск находит заметку по ключевым словам."""
        (tmp_path / "note1.md").write_text("Настроить бакеты для прода", encoding="utf-8")
        (tmp_path / "note2.md").write_text("Купить молоко", encoding="utf-8")
        result = search_obsidian_notes(tmp_path, "бакеты прод")
        assert "бакеты" in result.lower()
        assert "молоко" not in result

    def test_search_notes_empty_vault(self, tmp_path):
        """Поиск в пустом vault возвращает пустую строку."""
        result = search_obsidian_notes(tmp_path, "что-нибудь")
        assert result == ""

    def test_search_notes_nonexistent_path(self):
        """Поиск по несуществующему пути возвращает пустую строку."""
        result = search_obsidian_notes("/nonexistent/path", "запрос")
        assert result == ""

    def test_default_vault_path_is_in_home(self):
        """Путь по умолчанию находится в домашней директории."""
        path = get_default_vault_path()
        assert path == Path.home() / "Repositories" / "obsidian-vault"


class TestSanitizeFilename:
    """Тесты очистки имён файлов."""

    def test_removes_unsafe_characters(self):
        """Убирает небезопасные символы из имени файла."""
        assert _sanitize_filename("file<>name") == "filename"

    def test_truncates_long_names(self):
        """Обрезает слишком длинные имена до 100 символов."""
        long_name = "a" * 200
        assert len(_sanitize_filename(long_name)) == 100

    def test_empty_string_returns_default(self):
        """Пустая строка заменяется на 'заметка'."""
        assert _sanitize_filename("") == "заметка"
