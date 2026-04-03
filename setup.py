"""Конфигурация сборки macOS-приложения через py2app."""

import sys
import zlib
from pathlib import Path

from setuptools import setup
from setuptools.dist import Distribution

sys.setrecursionlimit(10000)

if "py2app" in sys.argv:
    import py2app.build_app as py2app_build_app
    from py2app.build_app import py2app as build_py2app
else:
    py2app_build_app = None
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
            self.distribution.install_requires = []
            self.distribution.extras_require = {}
            super().finalize_options()

        def build_executable(self, target, arcname, pkgexts, copyexts, script, extra_scripts):
            """Подкладывает py2app безопасный zlib.__file__ для uv Python без shared-модуля."""
            sentinel = object()
            original_zlib_file = getattr(zlib, "__file__", sentinel)
            original_copy_file = self.copy_file  # type: ignore[has-type]

            def _copy_file(source, *args, **kwargs):
                if not source:
                    return None
                return original_copy_file(source, *args, **kwargs)

            try:
                if original_zlib_file is sentinel:
                    zlib.__file__ = ""
                self.copy_file = _copy_file
                return super().build_executable(target, arcname, pkgexts, copyexts, script, extra_scripts)
            finally:
                self.copy_file = original_copy_file
                if original_zlib_file is sentinel:
                    del zlib.__file__


APP = ["main.py"]
ROOT = Path(__file__).parent
README = (ROOT / "README.md").read_text(encoding="utf-8")

_PY2APP_PACKAGES = ["mlx", "mlx_audio", "mlx_whisper", "numpy", "pyaudio", "pynput", "rumps", "src", "tqdm"]

if "py2app" in sys.argv:
    # py2app (через modulegraph) использует устаревший imp.find_module, который
    # не всегда находит пакеты в venv, созданном uv. Патчим imp_find_module
    # и в modulegraph.util, и в py2app.build_app (куда он уже скопирован
    # через «from modulegraph.util import imp_find_module»).
    import imp
    import importlib.util

    import modulegraph.util
    import py2app.build_app

    _original_imp_find_module = modulegraph.util.imp_find_module

    def _patched_imp_find_module(name, path=None):
        try:
            return _original_imp_find_module(name, path)
        except ImportError:
            spec = importlib.util.find_spec(name)
            if spec is None or not spec.submodule_search_locations:
                raise
            pkg_dir = spec.submodule_search_locations[0]
            return (None, pkg_dir, ("", "", imp.PKG_DIRECTORY))

    modulegraph.util.imp_find_module = _patched_imp_find_module
    py2app.build_app.imp_find_module = _patched_imp_find_module

OPTIONS = {
    "argv_emulation": False,
    "site_packages": False,
    "iconfile": "assets/icons/Dictator.icns",
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
    "description": "Офлайн-приложение диктовки для macOS на базе локальных MLX ASR-моделей.",
    "long_description": README,
    "long_description_content_type": "text/markdown",
    "options": {"py2app": OPTIONS},
}

if build_py2app is not None:
    setup_kwargs["cmdclass"] = {"py2app": FixedPy2App}

setup(
    **setup_kwargs,
)
