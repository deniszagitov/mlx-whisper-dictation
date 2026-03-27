"""Unit-тесты setup.py без запуска реальной сборки."""

from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path

import setuptools

SETUP_PATH = Path(__file__).resolve().parent.parent / "setup.py"


def load_setup_module(monkeypatch, argv, with_fake_py2app=False):
    """Загружает setup.py с перехватом вызова setuptools.setup."""
    captured_kwargs = {}

    monkeypatch.setattr(sys, "argv", list(argv))
    monkeypatch.setattr(setuptools, "setup", lambda **kwargs: captured_kwargs.update(kwargs))

    if with_fake_py2app:

        class FakeBasePy2App:
            def __init__(self, distribution=None):
                self.distribution = distribution
                self.copy_calls = []

                def _copy(source, *_args, **_kwargs):
                    self.copy_calls.append(source)
                    return source

                self.copy_file = _copy

            def finalize_options(self):
                self.finalized = True

            def build_executable(self, target, arcname, pkgexts, copyexts, script, extra_scripts):
                self.copy_file(None)
                self.copy_file("payload")
                return {
                    "target": target,
                    "arcname": arcname,
                    "pkgexts": pkgexts,
                    "copyexts": copyexts,
                    "script": script,
                    "extra_scripts": extra_scripts,
                }

        def failing_imp_find_module(_name, _path=None):
            raise ImportError("not found")

        fake_py2app_package = types.ModuleType("py2app")
        fake_py2app_build = types.ModuleType("py2app.build_app")
        fake_py2app_build.py2app = FakeBasePy2App
        fake_py2app_build.imp_find_module = failing_imp_find_module
        fake_py2app_package.build_app = fake_py2app_build

        fake_modulegraph_package = types.ModuleType("modulegraph")
        fake_modulegraph_util = types.ModuleType("modulegraph.util")
        fake_modulegraph_util.imp_find_module = failing_imp_find_module
        fake_modulegraph_package.util = fake_modulegraph_util

        monkeypatch.setitem(sys.modules, "py2app", fake_py2app_package)
        monkeypatch.setitem(sys.modules, "py2app.build_app", fake_py2app_build)
        monkeypatch.setitem(sys.modules, "modulegraph", fake_modulegraph_package)
        monkeypatch.setitem(sys.modules, "modulegraph.util", fake_modulegraph_util)

        class FakeSpec:
            def __init__(self):
                self.submodule_search_locations = ["/tmp/demo-pkg"]

        monkeypatch.setattr(importlib.util, "find_spec", lambda name: FakeSpec() if name == "demo_pkg" else None)

    module_name = f"dictator_setup_{'_'.join(argv)}"
    spec = importlib.util.spec_from_file_location(module_name, SETUP_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module, captured_kwargs


def test_setup_registers_expected_metadata(monkeypatch):
    """setup.py должен передавать в setuptools основные метаданные сборки."""
    module, captured_kwargs = load_setup_module(monkeypatch, ["setup.py"])

    assert captured_kwargs["app"] == ["main.py"]
    assert captured_kwargs["distclass"] is module.Py2AppDistribution
    assert captured_kwargs["name"] == "Dictator"
    assert captured_kwargs["options"]["py2app"]["plist"]["CFBundleIdentifier"] == "com.deniszagitov.dictator"
    assert "cmdclass" not in captured_kwargs


def test_distribution_clears_dependencies_on_init_and_finalize(monkeypatch):
    """Py2AppDistribution должен очищать install_requires и extras_require."""
    module, _captured_kwargs = load_setup_module(monkeypatch, ["setup.py"])
    distribution = module.Py2AppDistribution({"install_requires": ["demo"], "extras_require": {"dev": ["x"]}})

    monkeypatch.setattr(module.Distribution, "finalize_options", lambda self: setattr(self, "base_finalized", True))
    distribution.install_requires = ["another"]
    distribution.extras_require = {"test": ["y"]}

    distribution.finalize_options()

    assert distribution.install_requires == []
    assert distribution.extras_require == {}
    assert distribution.base_finalized is True


def test_setup_enables_fixed_py2app_and_patches_imp_find_module(monkeypatch):
    """При запуске с py2app setup.py должен регистрировать FixedPy2App и fallback для uv env."""
    module, captured_kwargs = load_setup_module(monkeypatch, ["setup.py", "py2app"], with_fake_py2app=True)

    assert captured_kwargs["cmdclass"]["py2app"] is module.FixedPy2App
    assert module.py2app_build_app.imp_find_module("demo_pkg")[1] == "/tmp/demo-pkg"


def test_fixed_py2app_clears_distribution_and_restores_zlib(monkeypatch):
    """FixedPy2App должен очистить зависимости и безопасно обработать отсутствие zlib.__file__."""
    module, _captured_kwargs = load_setup_module(monkeypatch, ["setup.py", "py2app"], with_fake_py2app=True)
    distribution = types.SimpleNamespace(install_requires=["demo"], extras_require={"dev": ["x"]})
    command = module.FixedPy2App(distribution=distribution)

    monkeypatch.delattr(module.zlib, "__file__", raising=False)

    command.finalize_options()
    result = command.build_executable("target", "arc", ["pkg"], ["ext"], "script.py", ["extra.py"])

    assert distribution.install_requires == []
    assert distribution.extras_require == {}
    assert command.finalized is True
    assert result["target"] == "target"
    assert command.copy_calls == ["payload"]
    assert hasattr(module.zlib, "__file__") is False
