# MLX Whisper Dictation

Offline dictation for macOS that records from the microphone, transcribes with MLX Whisper, and types into the currently focused input field.

This repository is tuned for Apple Silicon Macs and packaged as a menu bar application. The transcription path stays close to the MLX examples approach: the app calls `mlx_whisper.transcribe(...)` directly and passes the selected `path_or_hf_repo` model identifier.

## What It Does

- Runs as a menu bar app.
- Listens for a global hotkey.
- Records microphone input.
- Transcribes speech with `mlx_whisper.transcribe(...)`.
- Types the recognized text into the active app.

## Requirements

- macOS on Apple Silicon.
- Homebrew Python 3.11.
- Homebrew.
- `py2app==0.28.10` and `modulegraph` for local application builds.
- Accessibility permission.
- Microphone permission.

## Build The App Locally

For local use on your own Mac, the reliable path is an alias app build. This produces a normal `.app` bundle, but it uses the project environment in place instead of trying to fully freeze every dependency into a standalone distributable bundle.

```bash
brew install portaudio
pyenv local 3.11.14
/opt/homebrew/bin/python3.11 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip setuptools wheel
pip install py2app==0.28.10 modulegraph
pip install -r requirements.txt
python setup.py py2app -A
```

The built app bundle will appear at:

```bash
dist/MLX Whisper Dictation.app
```

Then launch it with one of these commands:

```bash
open "dist/MLX Whisper Dictation.app"
```

or

```bash
./dist/MLX\ Whisper\ Dictation.app/Contents/MacOS/MLX\ Whisper\ Dictation
```

The second form is useful for debugging because logs stay in the Terminal.

## Why Python 3.11

- The repository now pins `.python-version` to `3.11.14`.
- Your Homebrew Python 3.11 is a framework build, which is much better suited for `py2app` on macOS.
- Your previous `pyenv` Python 3.12 build was not a framework build, and `py2app` did not produce a usable app bundle from it.

If `.venv` already exists from another Python version, recreate it before building.

## Run During Development

If you want to run the script directly before packaging:

```bash
source .venv/bin/activate
python whisper-dictation.py
```

## Hotkeys

Default on macOS:

```bash
cmd_l+alt
```

The app now accepts combinations with more than two keys. Examples:

```bash
python whisper-dictation.py -k cmd_l+shift+space
python whisper-dictation.py -k cmd_r+shift
python whisper-dictation.py -k ctrl+alt
```

You can also use right command as a dictation trigger:

```bash
python whisper-dictation.py --k_double_cmd
```

That mode uses:

- double right command to start recording
- single right command to stop recording

If you use this mode, disable the built-in macOS Dictation shortcut first.

## Model Selection

Default:

```bash
mlx-community/whisper-large-v3-turbo
```

Recommended on M3:

- `mlx-community/whisper-large-v3-turbo` for a stronger latency and quality balance
- `mlx-community/whisper-large-v3-mlx` if quality matters more than responsiveness
- `mlx-community/whisper-turbo` if you prefer lower latency over quality

Example:

```bash
python whisper-dictation.py -m mlx-community/whisper-large-v3-mlx -l ru
```

## Permissions

Grant these permissions to the built app:

- `Microphone`
- `Accessibility`

If global hotkeys still do not react, also check `Input Monitoring` for the built app.

## Start At Login

After building, add the app bundle to `Login Items` in macOS:

1. Open `System Settings`
2. Open `General`
3. Open `Login Items & Extensions`
4. Add `dist/MLX Whisper Dictation.app`

## GitHub Actions Build

The repository includes a GitHub Actions workflow at [.github/workflows/build-macos-app.yml](.github/workflows/build-macos-app.yml).

It:

- runs on `macos-14`
- installs `portaudio`
- installs Python dependencies and `py2app`
- builds the `.app`
- uploads a zipped app artifact

## Reference

This repository uses the MLX Whisper approach shown in the MLX examples project:

- `mlx_whisper.transcribe(audio, path_or_hf_repo=...)`
- MLX Community Whisper models hosted on Hugging Face
- model selection via direct repo or local model path, similar to the MLX examples CLI and API
