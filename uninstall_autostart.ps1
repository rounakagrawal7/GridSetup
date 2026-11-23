# Remove GRID from the current user's Startup folder.
$ErrorActionPreference = "Stop"
$startup = [Environment]::GetFolderPath("Startup")
$shortcutPath = Join-Path $startup "GRID Tray.lnk"
if (Test-Path $shortcutPath) {
    Remove-Item $shortcutPath -Force
    Write-Host "Removed: $shortcutPath" -ForegroundColor Green
} else {
    Write-Host "GRID Tray shortcut was not installed." -ForegroundColor Yellow
}
