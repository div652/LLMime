#!/bin/bash
set -e

echo "=== LLMime v3 Build ==="

# Activate virtual environment
source venv/bin/activate
echo "✅ Virtual environment activated"

# Install Python dependencies
pip install -r requirements.txt --quiet
pip install pyinstaller --quiet
echo "✅ Python dependencies installed"

# Build standalone executable
echo "🔨 Building standalone binary..."
pyinstaller -y --onefile --noconsole daemon.py
echo "✅ Binary built at dist/daemon"

# Clean up old systemd service if present
echo "🧹 Cleaning up old systemd service..."
systemctl --user stop llm-bridge.service 2>/dev/null || true
systemctl --user disable llm-bridge.service 2>/dev/null || true
rm -f ~/.config/systemd/user/llm-bridge.service
systemctl --user daemon-reload || true
echo "✅ Old systemd service removed"

# Create launcher and autostart directories
mkdir -p ~/.local/share/applications
mkdir -p ~/.config/autostart

DAEMON_PATH="$(pwd)/dist/daemon"

# Generate desktop file
DESKTOP_FILE="[Desktop Entry]
Type=Application
Name=LLMime Clipboard Bridge
Comment=LLMime Clipboard Bridge for native Slite AST injection
Exec=\"${DAEMON_PATH}\"
Icon=preferences-desktop-keyboard
Terminal=false
Categories=Utility;
X-GNOME-Autostart-enabled=true
"

echo "${DESKTOP_FILE}" > ~/.local/share/applications/llmime.desktop
echo "${DESKTOP_FILE}" > ~/.config/autostart/llmime.desktop

echo "✅ Desktop launcher registered: ~/.local/share/applications/llmime.desktop"
echo "✅ Autostart launcher registered: ~/.config/autostart/llmime.desktop"

# Prompt user to restart the daemon
echo ""
echo "=== Build Complete ==="
echo "You can search for 'LLMime Clipboard Bridge' in your Application Menu to start it,"
echo "or it will start automatically on your next login."
echo ""
echo "Starting the daemon now..."
# Launch in the background
"${DAEMON_PATH}" &
echo "✅ Daemon started in background (PID: $!)"
