# API сборки

Исходный файл: `setup.py`

Конфигурация сборки macOS-приложения через py2app.

## Константы

- `APP` = `['whisper-dictation.py']`
- `ROOT` = `Path(__file__).parent`
- `README` = `(ROOT / 'README.md').read_text(encoding='utf-8')`
- `_PY2APP_PACKAGES` = `['mlx', 'mlx_whisper', 'numpy', 'pyaudio', 'pynput', 'rumps', 'tqdm']`
- `OPTIONS` = `{'argv_emulation': False, 'site_packages': False, 'packages': _PY2APP_PACKAGES, 'includes': ['AppKit', 'Foundation', 'PyObjCTools', 'Quartz', 'objc', 'pynput.keyboard._darwin'], 'plist': {'CFBundleDisplayName': 'Dictator', 'CFBundleName': 'Dictator', 'CFBundleIdentifier': 'com.deniszagitov.dictator', 'CFBundleShortVersionString': '0.1.0', 'CFBundleVersion': '0.1.0', 'LSUIElement': True, 'NSMicrophoneUsageDescription': 'Приложение записывает звук с микрофона для офлайн-диктовки.'}}`

## Классы

## `Py2AppDistribution`

Distribution, совместимый с py2app и PEP 621 метаданными.

### Методы

#### `__init__`

```python
__init__(attrs = None)
```

Создает distribution и очищает install_requires для py2app.

#### `finalize_options`

```python
finalize_options()
```

Повторно очищает зависимости после финализации setuptools.
