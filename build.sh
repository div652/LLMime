#!/bin/bash
set -e

echo "=== LLMime v2 Build ==="

# Activate virtual environment
source venv/bin/activate
echo "✅ Virtual environment activated"

# Install Python dependencies
pip install -r requirements.txt --quiet
pip install pyinstaller --quiet
echo "✅ Python dependencies installed"

# Verify local KaTeX is available
if [ ! -f "node_modules/.bin/katex" ]; then
    echo "❌ Local KaTeX CLI not found. Install with: npm install katex"
    exit 1
fi
echo "✅ Local KaTeX CLI found"

# Build standalone executable
echo "🔨 Building standalone binary..."
pyinstaller -y --onefile --noconsole daemon.py
echo "✅ Binary built at dist/daemon"

# Create systemd service directory
mkdir -p ~/.config/systemd/user

# Generate systemd service file
# IMPORTANT: ExecStart path MUST be quoted to handle spaces in path (v1 lesson)
DAEMON_PATH="$(pwd)/dist/daemon"
cat > ~/.config/systemd/user/llm-bridge.service << EOF
[Unit]
Description=LLMime Clipboard Bridge

[Service]
ExecStart="${DAEMON_PATH}"
Restart=always
RestartSec=5
Environment=DISPLAY=:0
Environment=HOME=${HOME}
Environment=PATH=${HOME}/.nvm/versions/node/$(node -v 2>/dev/null || echo "v0")/bin:/usr/local/bin:/usr/bin:/bin:${HOME}/.local/bin:${HOME}/.npm-global/bin

[Install]
WantedBy=default.target
EOF

echo "✅ Systemd service file generated"

# Reload and restart
systemctl --user daemon-reload
systemctl --user enable --now llm-bridge.service
echo "✅ Service started"

echo ""
echo "=== Build Complete ==="
echo "Binary: dist/daemon"
echo "Service: systemctl --user status llm-bridge.service"
