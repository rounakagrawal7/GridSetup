$repo = Split-Path -Parent $PSScriptRoot
Set-Location $repo
$Host.UI.RawUI.WindowTitle = "GRID pilot 15"
$env:PYTHONIOENCODING = "utf-8"
& (Join-Path $repo ".venv\Scripts\python.exe") (Join-Path $PSScriptRoot "pilot_session.py") --count 15 --reply-timeout 360
