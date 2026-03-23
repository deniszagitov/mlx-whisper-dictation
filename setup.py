"""Конфигурация сборки macOS-приложения через py2app."""

import sys
from pathlib import Path

from setuptools import setup

sys.setrecursionlimit(10000)


APP = ["whisper-dictation.py"]
ROOT = Path(__file__).parent
README = (ROOT / "README.md").read_text(encoding="utf-8")

OPTIONS = {
    "argv_emulation": False,
    "site_packages": False,
    "packages": ["mlx", "mlx_whisper", "numpy", "pyaudio", "pynput", "rumps", "tqdm"],
    "includes": ["AppKit", "Foundation", "PyObjCTools", "pynput.keyboard._darwin"],
    "plist": {
        "CFBundleDisplayName": "MLX Whisper Dictation",
        "CFBundleName": "MLX Whisper Dictation",
        "CFBundleIdentifier": "com.deniszagitov.mlx-whisper-dictation",
        "CFBundleShortVersionString": "0.1.0",
        "CFBundleVersion": "0.1.0",
        "LSUIElement": True,
        "NSMicrophoneUsageDescription": ("Приложение записывает звук с микрофона для офлайн-диктовки."),
    },
}


setup(
    app=APP,
    name="MLX Whisper Dictation",
    version="0.1.0",
    description="Офлайн-приложение диктовки для macOS на базе mlx_whisper.",
    long_description=README,
    long_description_content_type="text/markdown",
    options={"py2app": OPTIONS},
)
