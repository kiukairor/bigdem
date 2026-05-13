#!/bin/bash
# One-time setup: install and enable the demo2 trigger watcher as a user systemd service.
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SERVICE_FILE="$SCRIPT_DIR/demo2-watcher.service"
DEST="$HOME/.config/systemd/user/demo2-watcher.service"

mkdir -p "$HOME/.config/systemd/user"
cp "$SERVICE_FILE" "$DEST"
systemctl --user daemon-reload
systemctl --user enable demo2-watcher
systemctl --user start  demo2-watcher
systemctl --user status demo2-watcher

echo ""
echo "NOTE: run 'loginctl enable-linger $USER' once so the service"
echo "survives after logout (required for headless Pi runs)."
