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

# 4. Generate the app icon from the in-app artwork (matches the tray icon).
& $venvPy make_icon.py
$icoPath = Join-Path (Get-Location) "llmime.ico"
Write-Host "OK Icon generated at $icoPath"

# 5. Build the standalone windowed executable.
#    --noconsole: no console window.  --icon embeds the LLMime icon.
#    compiler.py and daemon.py are pulled in automatically because
#    daemon_windows.py imports them.
Write-Host "Building standalone binary..."
& $venvPy -m PyInstaller -y --onefile --noconsole --icon $icoPath --name LLMime daemon_windows.py
$exePath = Join-Path (Get-Location) "dist\LLMime.exe"
Write-Host "OK Binary built at $exePath"

# 6. Register shortcuts.
#    - Startup folder  -> auto-launch on login.
#    - Start Menu      -> searchable / launchable from the Start menu.
$wsh = New-Object -ComObject WScript.Shell

function New-LLMimeShortcut($lnkPath) {
    $sc = $wsh.CreateShortcut($lnkPath)
    $sc.TargetPath = $exePath
    $sc.WorkingDirectory = (Split-Path $exePath)
    $sc.Description = "LLMime Clipboard Bridge (native Slite AST injection)"
    $sc.IconLocation = "$exePath,0"
    $sc.Save()
}

$startupLnk = Join-Path ([System.Environment]::GetFolderPath("Startup")) "LLMime.lnk"
New-LLMimeShortcut $startupLnk
Write-Host "OK Autostart shortcut registered: $startupLnk"

# "Programs" = the per-user Start Menu Programs folder; a .lnk here makes the
# app appear in Start-menu search as "LLMime".
$startMenuLnk = Join-Path ([System.Environment]::GetFolderPath("Programs")) "LLMime.lnk"
New-LLMimeShortcut $startMenuLnk
Write-Host "OK Start Menu shortcut registered: $startMenuLnk"

# 7. Launch it now.
Write-Host ""
Write-Host "=== Build Complete ==="
Write-Host "Search 'LLMime' in the Start menu to launch it, or it will auto-start on login."
Write-Host "Starting it now..."
Start-Process -FilePath $exePath
Write-Host "OK Daemon started (look for the indigo 'L' icon in your system tray)."
