#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

LABEL="com.deniszagitov.whisper-dictation"
AGENT_DIR="$HOME/Library/LaunchAgents"
PLIST_PATH="$AGENT_DIR/$LABEL.plist"
LOG_DIR="$HOME/Library/Logs/whisper-dictation"
RUN_SCRIPT="$SCRIPT_DIR/run.sh"
TEMPLATE_PATH="$SCRIPT_DIR/launch-agent.plist.template"
UID_VALUE="$(id -u)"

mkdir -p "$AGENT_DIR" "$LOG_DIR"

"$SCRIPT_DIR/bootstrap.sh"

sed \
    -e "s|__RUN_SCRIPT__|$RUN_SCRIPT|g" \
    -e "s|__WORKING_DIRECTORY__|$SCRIPT_DIR|g" \
    -e "s|__STDOUT_LOG__|$LOG_DIR/stdout.log|g" \
    -e "s|__STDERR_LOG__|$LOG_DIR/stderr.log|g" \
    "$TEMPLATE_PATH" > "$PLIST_PATH"

launchctl bootout "gui/$UID_VALUE" "$PLIST_PATH" >/dev/null 2>&1 || true
launchctl bootstrap "gui/$UID_VALUE" "$PLIST_PATH"
launchctl enable "gui/$UID_VALUE/$LABEL" >/dev/null 2>&1 || true
launchctl kickstart -k "gui/$UID_VALUE/$LABEL"

echo "LaunchAgent installed: $PLIST_PATH"
echo "Logs: $LOG_DIR"