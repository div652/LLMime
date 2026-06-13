# Installation Guide: LLM-to-Notion Universal Clipboard Bridge

This guide covers how to install the Universal Clipboard Bridge on a Linux environment.

## Prerequisites
- A Linux environment with Python 3 installed.
- A functional X11 or Wayland clipboard system.
- `pip` for Python package management.

## 1. Clone or Copy the Repository
Ensure you have the following files in your project directory (e.g., `~/Projects/LLMime`):
- `daemon.py`
- `build.sh`
- `requirements.txt`

## 2. Execute the Build Script
The build script automatically creates an isolated Python Virtual Environment, installs the required `PyQt6` bindings and PyInstaller, generates a standalone executable, and configures a systemd user daemon.

1. Navigate to your project folder in your terminal:
   ```bash
   cd ~/Projects/LLMime
   ```

2. Make sure the build script is executable:
   ```bash
   chmod +x build.sh
   ```

3. Run the complete build pipeline:
   ```bash
   ./build.sh
   ```

## 3. Verify Systemd Configuration
Once the build completes, the daemon will be installed under your local system resources (`~/.config/systemd/user/llm-bridge.service`). 

To manually start the systemd daemon right away:
```bash
systemctl --user start llm-bridge.service
```

To enable the daemon to automatically start on every boot:
```bash
systemctl --user enable llm-bridge.service
```

To check whether the daemon is actively running:
```bash
systemctl --user status llm-bridge.service
```

You are now fully installed and ready to go!
