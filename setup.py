from pathlib import Path
import sys

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
        "NSMicrophoneUsageDescription": "This app records microphone audio for offline dictation.",
    },
}


setup(
    app=APP,
    name="MLX Whisper Dictation",
    version="0.1.0",
    description="Offline macOS dictation app built on mlx_whisper.",
    long_description=README,
    long_description_content_type="text/markdown",
    options={"py2app": OPTIONS},
)
