"""Тесты генерации MkDocs-страниц из Python-модулей проекта."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


def _load_generate_docs_module(project_root: Path):
    script_path = project_root / "scripts" / "generate_docs.py"
    spec = importlib.util.spec_from_file_location("generate_docs", script_path)
    module = importlib.util.module_from_spec(spec)
    assert spec is not None
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_generate_docs_builds_runtime_pages_from_modular_sources(tmp_path):
    """Генератор строит overview и модульные страницы по актуальной структуре src/."""
    project_root = tmp_path / "project"
    docs_dir = project_root / "docs"
    src_dir = project_root / "src"
    scripts_dir = project_root / "scripts"
    docs_dir.mkdir(parents=True)
    src_dir.mkdir(parents=True)
    scripts_dir.mkdir(parents=True)

    source_script = Path(__file__).resolve().parent.parent / "scripts" / "generate_docs.py"
    (scripts_dir / "generate_docs.py").write_text(source_script.read_text(encoding="utf-8"), encoding="utf-8")

    (project_root / "main.py").write_text(
        '"""Точка входа приложения.\n\nЗапускает menu bar и CLI.\n"""\n\n\n'
        'def parse_args():\n    """Разбирает CLI-аргументы."""\n    return None\n',
        encoding="utf-8",
    )
    (project_root / "setup.py").write_text(
        '"""Сборка приложения."""\n\nAPP = ["main.py"]\n',
        encoding="utf-8",
    )

    module_sources = {
        "config.py": '"""Конфигурация приложения.\n\nХранит константы и defaults.\n"""\n\nFLAG = True\n',
        "audio.py": (
            '"""Работа с микрофоном.\n\nСодержит Recorder.\n"""\n\n\n'
            'class Recorder:\n    """Записывает звук."""\n\n'
            '    def start(self):\n        """Начинает запись."""\n'
        ),
        "diagnostics.py": '"""Диагностика приложения."""\n',
        "hotkeys.py": '"""Глобальные хоткеи."""\n',
        "permissions.py": '"""Разрешения macOS."""\n',
        "transcriber.py": (
            '"""Распознавание и вставка.\n\nСодержит SpeechTranscriber.\n"""\n\n\ndef transcribe():\n    """Возвращает текст."""\n'
        ),
        "llm.py": '"""LLM-обработка текста."""\n',
        "ui.py": '"""Menu bar интерфейс."""\n',
    }
    for filename, content in module_sources.items():
        (src_dir / filename).write_text(content, encoding="utf-8")

    module = _load_generate_docs_module(project_root)
    module.ROOT = project_root
    module.DOCS_DIR = docs_dir
    module.RUNTIME_TARGETS = (
        module.ModuleTarget("CLI и запуск", project_root / "main.py", "api/entrypoint.md"),
        module.ModuleTarget("Конфигурация", src_dir / "config.py", "api/modules/config.md"),
        module.ModuleTarget("Аудио и микрофон", src_dir / "audio.py", "api/modules/audio.md"),
        module.ModuleTarget("Диагностика", src_dir / "diagnostics.py", "api/modules/diagnostics.md"),
        module.ModuleTarget("Глобальные хоткеи", src_dir / "hotkeys.py", "api/modules/hotkeys.md"),
        module.ModuleTarget("Разрешения macOS", src_dir / "permissions.py", "api/modules/permissions.md"),
        module.ModuleTarget("Распознавание и вставка", src_dir / "transcriber.py", "api/modules/transcriber.md"),
        module.ModuleTarget("LLM-обработка", src_dir / "llm.py", "api/modules/llm.md"),
        module.ModuleTarget("Menu bar UI", src_dir / "ui.py", "api/modules/ui.md"),
    )
    module.SETUP_TARGET = module.ModuleTarget("API сборки", project_root / "setup.py", "api/setup.md")

    module.main()

    runtime_overview = (docs_dir / "api" / "runtime.md").read_text(encoding="utf-8")
    assert "Этот раздел собирается автоматически из docstring entrypoint-файла и модулей в каталоге `src/`." in runtime_overview
    assert "[Распознавание и вставка](modules/transcriber.md)" in runtime_overview

    entrypoint_page = (docs_dir / "api" / "entrypoint.md").read_text(encoding="utf-8")
    assert "Исходный файл: `main.py`" in entrypoint_page
    assert "Разбирает CLI-аргументы" in entrypoint_page

    module_page = (docs_dir / "api" / "modules" / "transcriber.md").read_text(encoding="utf-8")
    assert "Исходный файл: `src/transcriber.py`" in module_page
    assert "Возвращает текст" in module_page

    index_page = (docs_dir / "index.md").read_text(encoding="utf-8")
    assert "обзор runtime-слоя" in index_page
    assert "[Точка входа и CLI](api/entrypoint.md)" in index_page
