"""Тест сборки .app через py2app.

Проверяет, что alias-сборка приложения завершается без ошибок
и создаёт корректный .app bundle.
"""

import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
pytestmark = pytest.mark.build


class TestBuildApp:
    """Тесты сборки Dictator.app."""

    def test_py2app_alias_build_succeeds(self):
        """Alias-сборка py2app завершается без ошибок и создаёт .app."""
        dist_dir = ROOT / "dist"
        app_path = dist_dir / "Dictator.app"

        # Чистим предыдущую сборку, чтобы убедиться, что .app создаётся заново
        if app_path.exists():
            shutil.rmtree(app_path)

        result = subprocess.run(
            ["uv", "run", "python", "setup.py", "py2app", "-A"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )

        assert result.returncode == 0, f"py2app завершился с ошибкой:\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"
        assert app_path.is_dir(), f"Dictator.app не создан в {dist_dir}"

    def test_app_bundle_has_required_structure(self):
        """Собранный .app содержит обязательные файлы bundle."""
        app_path = ROOT / "dist" / "Dictator.app"
        if not app_path.exists():
            pytest.skip("Dictator.app не найден — сначала запустите тест сборки")

        contents = app_path / "Contents"
        assert (contents / "Info.plist").is_file(), "Info.plist отсутствует"
        assert (contents / "MacOS").is_dir(), "MacOS/ отсутствует"

        # Ищем исполняемый файл в MacOS/
        executables = list((contents / "MacOS").iterdir())
        assert executables, "Нет исполняемого файла в Contents/MacOS/"

    def test_info_plist_has_correct_bundle_id(self):
        """Info.plist содержит правильный bundle identifier."""
        import plistlib

        plist_path = ROOT / "dist" / "Dictator.app" / "Contents" / "Info.plist"
        if not plist_path.exists():
            pytest.skip("Info.plist не найден — сначала запустите тест сборки")

        with plist_path.open("rb") as plist_file:
            plist = plistlib.load(plist_file)

        assert plist.get("CFBundleIdentifier") == "com.deniszagitov.dictator"
        assert plist.get("CFBundleName") == "Dictator"
        assert plist.get("LSUIElement") is True, "LSUIElement должен быть True для menubar-приложения"
