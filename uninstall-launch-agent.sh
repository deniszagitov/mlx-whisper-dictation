#!/bin/bash
set -euo pipefail

LABEL="com.deniszagitov.whisper-dictation"
PLIST_PATH="$HOME/Library/LaunchAgents/$LABEL.plist"
UID_VALUE="$(id -u)"

launchctl bootout "gui/$UID_VALUE" "$PLIST_PATH" >/dev/null 2>&1 || true
rm -f "$PLIST_PATH"

echo "LaunchAgent removed: $PLIST_PATH"