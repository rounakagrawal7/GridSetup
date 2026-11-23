# GRID launcher: check the setup, then start without the wizard.
$ErrorActionPreference = "Stop"
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $here

$python = Join-Path $here ".venv\Scripts\python.exe"
if (-not (Test-Path $python)) {
    Write-Host "No .venv found; using system Python. For an isolated setup, see the Clean start section in README.md." -ForegroundColor Yellow
    $python = "python"
}

& $python grid_agent.py --check
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

& $python grid_agent.py --no-input @args
