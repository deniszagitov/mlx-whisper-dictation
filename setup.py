"""Конфигурация сборки macOS-приложения через py2app."""

import os
import sys
from pathlib import Path
from typing import Any, cast

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
            distribution = cast("Any", self.distribution)
            distribution.install_requires = []
            distribution.extras_require = {}
            super().finalize_options()

        def build_executable(self, target, arcname, pkgexts, copyexts, script, extra_scripts):
            """Пропускает копирование zlib как файла, если модуль встроен в Python."""
            appdir, resdir, plist = self.create_bundle(target, script)
            self.appdir = appdir
            self.resdir = resdir
            self.plist = plist

            for fn in extra_scripts:
                if fn.endswith(".py"):
                    fn = fn[:-3]
                elif fn.endswith(".pyw"):
                    fn = fn[:-4]

                src_fn = py2app_build_app.script_executable(
                    arch=self.arch,
                    secondary=False,
                    use_old_sdk=self.use_old_sdk,
                )
                tgt_fn = os.path.join(self.appdir, "Contents", "MacOS", os.path.basename(fn))
                py2app_build_app.mergecopy(src_fn, tgt_fn)
                py2app_build_app.make_exec(tgt_fn)

            site_path = os.path.join(resdir, "site.py")
            py2app_build_app.byte_compile(
                [py2app_build_app.SourceModule("site", site_path)],
                target_dir=resdir,
                optimize=self.optimize,
                force=self.force,
                verbose=self.verbose,
                dry_run=self.dry_run,
            )
            if not self.dry_run:
                os.unlink(site_path)

            includedir = py2app_build_app.get_config_var("CONFINCLUDEPY")
            configdir = py2app_build_app.get_config_var("LIBPL")

            if includedir is None:
                includedir = "python%d.%d" % (sys.version_info[:2])
            else:
                includedir = os.path.basename(includedir)

            if configdir is None:
                configdir = "config"
            else:
                configdir = os.path.basename(configdir)

            self.compile_datamodels(resdir)
            self.compile_mappingmodels(resdir)

            bootfn = "__boot__"
            bootfile = open(os.path.join(resdir, bootfn + ".py"), "w")
            for fn in target.prescripts:
                bootfile.write(self.get_bootstrap_data(fn))
                bootfile.write("\n\n")

            bootfile.write("DEFAULT_SCRIPT=%r\n" % (os.path.basename(script),))

            script_map = {}
            for fn in extra_scripts:
                fn = os.path.basename(fn)
                if fn.endswith(".py"):
                    script_map[fn[:-3]] = fn
                elif fn.endswith(".py"):
                    script_map[fn[:-4]] = fn
                else:
                    script_map[fn] = fn

            bootfile.write("SCRIPT_MAP=%r\n" % (script_map,))
            bootfile.write("_run()\n")
            bootfile.close()

            self.copy_file(script, resdir)
            for fn in extra_scripts:
                self.copy_file(fn, resdir)

            pydir = os.path.join(resdir, "lib", "python%s.%s" % (sys.version_info[:2]))

            if sys.version_info[0] == 2 or self.semi_standalone:
                arcdir = os.path.join(resdir, "lib", "python%d.%d" % (sys.version_info[:2]))
            else:
                arcdir = os.path.join(resdir, "lib")
            realhome = os.path.join(sys.prefix, "lib", "python%d.%d" % (sys.version_info[:2]))
            self.mkpath(pydir)

            if self.optimize:
                py2app_build_app.make_symlink("../../site.pyo", os.path.join(pydir, "site.pyo"))
            else:
                py2app_build_app.make_symlink("../../site.pyc", os.path.join(pydir, "site.pyc"))
            cfgdir = os.path.join(pydir, configdir)
            realcfg = os.path.join(realhome, configdir)
            real_include = os.path.join(sys.prefix, "include")
            if self.semi_standalone:
                py2app_build_app.make_symlink(realcfg, cfgdir)
                py2app_build_app.make_symlink(real_include, os.path.join(resdir, "include"))
            else:
                self.mkpath(cfgdir)
                if "_sysconfigdata" not in sys.modules:
                    for fn in "Makefile", "Setup", "Setup.local", "Setup.config":
                        rfn = os.path.join(realcfg, fn)
                        if os.path.exists(rfn):
                            self.copy_file(rfn, os.path.join(cfgdir, fn))

                inc_dir = os.path.join(resdir, "include", includedir)
                self.mkpath(inc_dir)
                self.copy_file(
                    py2app_build_app.get_config_h_filename(),
                    os.path.join(inc_dir, "pyconfig.h"),
                )

            self.copy_file(arcname, arcdir)
            if sys.version_info[0] != 2:
                import zlib

                zlib_file = getattr(zlib, "__file__", None)
                if zlib_file:
                    self.copy_file(zlib_file, os.path.dirname(arcdir))

            ext_dir = os.path.join(pydir, os.path.basename(self.ext_dir))
            self.copy_tree(self.ext_dir, ext_dir, preserve_symlinks=True)
            self.copy_tree(
                self.framework_dir,
                os.path.join(appdir, "Contents", "Frameworks"),
                preserve_symlinks=True,
            )
            for pkg_name in self.packages:
                pkg = self.get_bootstrap(pkg_name)

                if self.semi_standalone:
                    p = py2app_build_app.Package(pkg_name, pkg)
                    if not py2app_build_app.not_stdlib_filter(p):
                        continue

                dst = os.path.join(pydir, pkg_name)
                if os.path.isdir(pkg):
                    self.mkpath(dst)
                    self.copy_tree(pkg, dst)
                else:
                    self.copy_file(pkg, dst + ".py")

            for copyext in copyexts:
                fn = os.path.join(
                    ext_dir,
                    copyext.identifier.replace(".", os.sep) + os.path.splitext(copyext.filename)[1],
                )
                self.mkpath(os.path.dirname(fn))
                py2app_build_app.copy_file(copyext.filename, fn, dry_run=self.dry_run)
                self.copy_loader_paths(copyext.filename, fn)

            for src, dest in self.iter_data_files():
                dest = os.path.join(resdir, dest)
                if src == dest:
                    continue
                py2app_build_app.makedirs(os.path.dirname(dest))
                py2app_build_app.copy_resource(src, dest, dry_run=self.dry_run)

            plugindir = os.path.join(appdir, "Contents", "Library")
            for src, dest in self.iter_extra_plugins():
                dest = os.path.join(plugindir, dest)
                if src == dest:
                    continue

                py2app_build_app.makedirs(os.path.dirname(dest))
                py2app_build_app.copy_resource(src, dest, dry_run=self.dry_run)

            target.appdir = appdir
            return appdir


APP = ["whisper-dictation.py"]
ROOT = Path(__file__).parent
README = (ROOT / "README.md").read_text(encoding="utf-8")

_PY2APP_PACKAGES = ["mlx", "mlx_whisper", "numpy", "pyaudio", "pynput", "rumps", "tqdm"]

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
