#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

if [ ! -x "$SCRIPT_DIR/.venv/bin/python" ]; then
	echo "Virtual environment is missing. Run ./bootstrap.sh first." >&2
	exit 1
fi

source "$SCRIPT_DIR/.venv/bin/activate"

exec python "$SCRIPT_DIR/whisper-dictation.py" "$@"
