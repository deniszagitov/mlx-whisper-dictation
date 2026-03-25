"""Конфигурация сборки macOS-приложения через py2app."""

import sys
from pathlib import Path
from typing import Any, cast

from setuptools import setup
from setuptools.dist import Distribution

sys.setrecursionlimit(10000)

if "py2app" in sys.argv:
    from py2app.build_app import py2app as build_py2app
else:
    build_py2app = None


class Py2AppDistribution(Distribution):
    """Distribution, совместимый с py2app и PEP 621 метаданными."""

    def __init__(self, attrs=None):
        """Создает distribution и очищает install_requires для py2app."""
        super().__init__(attrs)
        self.install_requires = []
        self.extras_require = {}

    def finalize_options(self):
        """Повторно очищает зависимости после финализации setuptools."""
        super().finalize_options()
        self.install_requires = []
        self.extras_require = {}


if build_py2app is not None:

    class FixedPy2App(build_py2app):
        """Команда py2app, совместимая с зависимостями из pyproject.toml."""

        def finalize_options(self):
            """Очищает install_requires до внутренней проверки py2app."""
            distribution = cast("Any", self.distribution)
            distribution.install_requires = []
            distribution.extras_require = {}
            super().finalize_options()


APP = ["whisper-dictation.py"]
ROOT = Path(__file__).parent
README = (ROOT / "README.md").read_text(encoding="utf-8")

_PY2APP_PACKAGES = ["mlx", "mlx_whisper", "numpy", "pyaudio", "pynput", "rumps", "tqdm"]

if "py2app" in sys.argv:
    # py2app внутри использует устаревший imp.find_module, который может не
    # обнаружить пакеты в venv, созданном uv. Предварительно импортируем каждый
    # пакет через importlib и добавляем его родительскую директорию в sys.path.
    import importlib

    for _pkg_name in _PY2APP_PACKAGES:
        try:
            _mod = importlib.import_module(_pkg_name)
        except ImportError:
            continue
        for _loc in getattr(_mod, "__path__", []):
            _parent = str(Path(_loc).parent)
            if _parent not in sys.path:
                sys.path.insert(0, _parent)

OPTIONS = {
    "argv_emulation": False,
    "site_packages": False,
    "packages": _PY2APP_PACKAGES,
    "includes": ["AppKit", "Foundation", "PyObjCTools", "Quartz", "objc", "pynput.keyboard._darwin"],
    "plist": {
        "CFBundleDisplayName": "Dictator",
        "CFBundleName": "Dictator",
        "CFBundleIdentifier": "com.deniszagitov.dictator",
        "CFBundleShortVersionString": "0.1.0",
        "CFBundleVersion": "0.1.0",
        "LSUIElement": True,
        "NSMicrophoneUsageDescription": ("Приложение записывает звук с микрофона для офлайн-диктовки."),
    },
}


setup_kwargs = {
    "app": APP,
    "distclass": Py2AppDistribution,
    "name": "Dictator",
    "version": "0.1.0",
    "description": "Офлайн-приложение диктовки для macOS на базе mlx_whisper.",
    "long_description": README,
    "long_description_content_type": "text/markdown",
    "options": {"py2app": OPTIONS},
}

if build_py2app is not None:
    setup_kwargs["cmdclass"] = {"py2app": FixedPy2App}

setup(
    **setup_kwargs,
)
