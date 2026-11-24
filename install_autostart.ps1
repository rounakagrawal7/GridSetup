# Install GRID in the current user's Startup folder.
# Installs the tray icon and the always-on GRID Life resident.
$ErrorActionPreference = "Stop"
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$pythonw = Join-Path $here ".venv\Scripts\pythonw.exe"
if (-not (Test-Path $pythonw)) {
    $cmd = Get-Command pythonw.exe -ErrorAction SilentlyContinue
    if (-not $cmd) {
        Write-Host "pythonw.exe not found. Create .venv first or install Python." -ForegroundColor Red
        exit 1
    }
    $pythonw = $cmd.Source
}
$startup = [Environment]::GetFolderPath("Startup")
$shell = New-Object -ComObject WScript.Shell

$trayPath = Join-Path $startup "GRID Tray.lnk"
$tray = $shell.CreateShortcut($trayPath)
$tray.TargetPath = $pythonw
$tray.Arguments = "`"$here\grid_tray.py`""
$tray.WorkingDirectory = $here
$tray.Description = "GRID v3 tray"
$tray.Save()
Write-Host "Installed: $trayPath" -ForegroundColor Green

$residentPath = Join-Path $startup "GRID Life.lnk"
$resident = $shell.CreateShortcut($residentPath)
$resident.TargetPath = $pythonw
$resident.Arguments = "`"$here\grid_agent.py`" --no-input --no-banner --resident"
$resident.WorkingDirectory = $here
$resident.Description = "GRID Life - always-on resident"
$resident.Save()
Write-Host "Installed: $residentPath" -ForegroundColor Green
Write-Host "GRID Life will wake at your next login and keep its own clock."
Write-Host "Logs: $here\logs\resident-YYYYMMDD.log"
Write-Host "To relaunch the resident after the app exits, set life.resident_autostart=true in config.json."
