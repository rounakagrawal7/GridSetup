# Create a project-local opencode.jsonc that connects OpenCode to GRID.
# Run from the GridSetup folder:
#   .\install_opencode_mcp.ps1
# Then start OpenCode in this folder:
#   opencode
$ErrorActionPreference = "Stop"
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$python = Join-Path $here ".venv\Scripts\python.exe"
if (-not (Test-Path $python)) {
    $cmd = Get-Command python.exe -ErrorAction SilentlyContinue
    if (-not $cmd) {
        Write-Host "Python not found. Create .venv first." -ForegroundColor Red
        exit 1
    }
    $python = $cmd.Source
}
$server = Join-Path $here "grid_mcp_server.py"
if (-not (Test-Path $server)) {
    Write-Host "grid_mcp_server.py not found next to this script." -ForegroundColor Red
    exit 1
}
$template = Get-Content (Join-Path $here "opencode.example.jsonc") -Raw
$escapedHome = $here.Replace('\', '\\')
$escapedPython = $python.Replace('\', '\\')
$config = $template.Replace('{{GRID_HOME}}', $escapedHome).Replace('{{GRID_PYTHON}}', $escapedPython)
$dest = Join-Path $here "opencode.jsonc"
$utf8NoBom = New-Object System.Text.UTF8Encoding($false)
[System.IO.File]::WriteAllText($dest, $config, $utf8NoBom)
Write-Host "Created: $dest" -ForegroundColor Green
Write-Host "Start OpenCode from this folder: opencode"
Write-Host "Then check: opencode mcp list   (expect: grid connected)"
