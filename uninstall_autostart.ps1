# Remove GRID from the current user's Startup folder.
$ErrorActionPreference = "Stop"
$startup = [Environment]::GetFolderPath("Startup")
foreach ($name in @("GRID Tray.lnk", "GRID Life.lnk")) {
    $shortcutPath = Join-Path $startup $name
    if (Test-Path $shortcutPath) {
        Remove-Item $shortcutPath -Force
        Write-Host "Removed: $shortcutPath" -ForegroundColor Green
    } else {
        Write-Host "$name was not installed." -ForegroundColor Yellow
    }
}
