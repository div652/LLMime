# LLMime v3 — Windows build & install script (PowerShell)
# Mirrors build.sh, but produces a Windows .exe and registers autostart via
# the user's Startup folder. Run from the repo root:  .\build_windows.ps1

$ErrorActionPreference = "Stop"

Write-Host "=== LLMime v3 Windows Build ==="

# 1. Resolve a Python interpreter (prefer the 'py' launcher).
$py = "py"
if (-not (Get-Command $py -ErrorAction SilentlyContinue)) { $py = "python" }

# 2. Create / reuse a Windows virtual environment.
if (-not (Test-Path "venv-win\Scripts\python.exe")) {
    Write-Host "Creating virtual environment (venv-win)..."
    & $py -m venv venv-win
}
$venvPy = ".\venv-win\Scripts\python.exe"
Write-Host "OK Virtual environment ready"

# 3. Install dependencies + PyInstaller.
& $venvPy -m pip install --quiet --upgrade pip
& $venvPy -m pip install --quiet -r requirements-windows.txt
& $venvPy -m pip install --quiet pyinstaller
Write-Host "OK Python dependencies installed"

# 4. Build the standalone windowed executable.
#    --noconsole: no console window.  compiler.py and daemon.py are pulled in
#    automatically because daemon_windows.py imports them.
Write-Host "Building standalone binary..."
& $venvPy -m PyInstaller -y --onefile --noconsole --name LLMime daemon_windows.py
$exePath = Join-Path (Get-Location) "dist\LLMime.exe"
Write-Host "OK Binary built at $exePath"

# 5. Register autostart via a shortcut in the user's Startup folder.
$startup = [System.Environment]::GetFolderPath("Startup")
$lnkPath = Join-Path $startup "LLMime.lnk"
$wsh = New-Object -ComObject WScript.Shell
$shortcut = $wsh.CreateShortcut($lnkPath)
$shortcut.TargetPath = $exePath
$shortcut.WorkingDirectory = (Split-Path $exePath)
$shortcut.Description = "LLMime Clipboard Bridge (native Slite AST injection)"
$shortcut.Save()
Write-Host "OK Autostart shortcut registered: $lnkPath"

# 6. Launch it now.
Write-Host ""
Write-Host "=== Build Complete ==="
Write-Host "LLMime will start automatically on login. Starting it now..."
Start-Process -FilePath $exePath
Write-Host "OK Daemon started (look for the indigo 'L' icon in your system tray)."
