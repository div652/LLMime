#!/bin/bash
set -e

DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
SERVICE_TEMPLATE="llm-bridge.service.template"
SERVICE_DEST="$HOME/.config/systemd/user/llm-bridge.service"

echo "Activating virtual environment..."
source "$DIR/venv/bin/activate"

echo "Installing pyinstaller..."
pip install pyinstaller

echo "Building standalone executable..."
pyinstaller --onefile --noconsole daemon.py

echo "Creating systemd directory if it doesn't exist..."
mkdir -p "$HOME/.config/systemd/user"

echo "Generating exact systemd service file..."
cat << EOF > "$SERVICE_DEST"
[Unit]
Description=LLM-to-Notion Universal Clipboard Bridge
After=graphical-session.target

[Service]
ExecStart=$DIR/dist/daemon
Restart=always
RestartSec=5
Environment=DISPLAY=:0

[Install]
WantedBy=default.target
EOF

echo "Reloading systemd user daemon..."
systemctl --user daemon-reload
echo "Enabling and starting llm-bridge service..."
# systemctl --user enable --now llm-bridge.service

echo "Build complete. The binary is at dist/daemon"
echo "To start the background service, run: systemctl --user start llm-bridge.service"
