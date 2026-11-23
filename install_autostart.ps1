# Install GRID in the current user's Startup folder.
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
$shortcutPath = Join-Path $startup "GRID Tray.lnk"
$shell = New-Object -ComObject WScript.Shell
$shortcut = $shell.CreateShortcut($shortcutPath)
$shortcut.TargetPath = $pythonw
$shortcut.Arguments = "`"$here\grid_tray.py`""
$shortcut.WorkingDirectory = $here
$shortcut.Description = "GRID v3 tray"
$shortcut.Save()
Write-Host "Installed: $shortcutPath" -ForegroundColor Green
Write-Host "GRID will appear in the notification area at your next login."
