# MLX Whisper Dictation

Offline dictation for macOS that records from the microphone, transcribes with MLX Whisper, and types into the currently focused input field.

This repository is tuned for Apple Silicon Macs. On a MacBook M3, the default model is `mlx-community/whisper-turbo` because it gives a better latency profile for interactive dictation than the old `large` default.

## What It Does

- Runs as a menu bar app.
- Listens for a global hotkey.
- Records microphone input.
- Transcribes speech with `mlx_whisper.transcribe(...)`.
- Types the recognized text into the active app.

## Requirements

- macOS on Apple Silicon.
- Python 3.11 or 3.12.
- Homebrew.
- Accessibility permission.
- Microphone permission.

## Run

```bash
./bootstrap.sh
./run.sh
```

`bootstrap.sh` is the one-time environment setup. It will:

- verify Homebrew
- ensure `portaudio` is installed
- prefer `python3.12`, otherwise `python3.11`
- recreate `.venv` automatically if it was built with the wrong Python version
- install or refresh Python dependencies

`run.sh` is the normal runtime entrypoint. It only activates `.venv` and starts the app.

If you want to run the Python file directly after bootstrap:

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
mlx-community/whisper-turbo
```

Recommended on M3:

- `mlx-community/whisper-turbo` for the lowest latency
- `mlx-community/whisper-large-v3-turbo` for a stronger latency and quality balance
- `mlx-community/whisper-large-v3-mlx` if quality matters more than responsiveness

Example:

```bash
python whisper-dictation.py -m mlx-community/whisper-large-v3-turbo -l ru
```

## Permissions

Grant these permissions to the app that launches the script:

- `Microphone`
- `Accessibility`

If you start the app from Terminal, grant permissions to Terminal.

## Autostart

Install the LaunchAgent:

```bash
./install-launch-agent.sh
```

Remove it later with:

```bash
./uninstall-launch-agent.sh
```

What this does:

- installs a user LaunchAgent in `~/Library/LaunchAgents`
- starts the app automatically after login
- writes logs to `~/Library/Logs/whisper-dictation`

The LaunchAgent uses [run.sh](run.sh) for startup, so it does not reinstall dependencies on every login.

If the environment is missing, `install-launch-agent.sh` runs [bootstrap.sh](bootstrap.sh) once before registering the agent.

## Reference

This repository uses the MLX Whisper approach shown in the MLX examples project:

- `mlx_whisper.transcribe(audio, path_or_hf_repo=...)`
- MLX Community Whisper models hosted on Hugging Face
- fast model variants such as `whisper-turbo` for interactive usage
