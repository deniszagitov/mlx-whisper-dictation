#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

if ! command -v brew >/dev/null 2>&1; then
	echo "Homebrew is required. Install it first: https://brew.sh/" >&2
	exit 1
fi

if command -v python3.12 >/dev/null 2>&1; then
	PYTHON_BIN="$(command -v python3.12)"
elif command -v python3.11 >/dev/null 2>&1; then
	PYTHON_BIN="$(command -v python3.11)"
else
	echo "Python 3.12 or 3.11 is required." >&2
	exit 1
fi

if ! brew list --versions portaudio >/dev/null 2>&1; then
	brew install portaudio
fi

if [ -d "$SCRIPT_DIR/venv" ] && [ ! -d "$SCRIPT_DIR/.venv" ]; then
	mv "$SCRIPT_DIR/venv" "$SCRIPT_DIR/.venv"
fi

RECREATE_VENV=0
if [ ! -x "$SCRIPT_DIR/.venv/bin/python" ]; then
	RECREATE_VENV=1
else
	VENV_VERSION="$($SCRIPT_DIR/.venv/bin/python -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')"
	TARGET_VERSION="$($PYTHON_BIN -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')"
	if [ "$VENV_VERSION" != "$TARGET_VERSION" ]; then
		RECREATE_VENV=1
	fi
fi

if [ "$RECREATE_VENV" -eq 1 ]; then
	rm -rf "$SCRIPT_DIR/.venv"
	"$PYTHON_BIN" -m venv "$SCRIPT_DIR/.venv"
fi

source "$SCRIPT_DIR/.venv/bin/activate"
python -m pip install --upgrade pip
python -m pip install -r "$SCRIPT_DIR/requirements.txt"

exec python "$SCRIPT_DIR/whisper-dictation.py" "$@"
