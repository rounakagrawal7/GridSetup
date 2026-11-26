param(
    [string]$BaseUrl = "http://127.0.0.1:8771"
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$tokenPath = Join-Path $root "run\api_token"
if (-not (Test-Path $tokenPath)) {
    throw "Token file not found: $tokenPath. Start the host first."
}

$token = (Get-Content $tokenPath -Raw).Trim()
$headers = @{ Authorization = "Bearer $token" }
$pair = Invoke-RestMethod -Uri "$BaseUrl/api/v1/pair/code" -Headers $headers -TimeoutSec 8

Write-Host ""
Write-Host "GRID phone pairing" -ForegroundColor Green
Write-Host "  Host URL: $($pair.url)"
Write-Host "  Code:     $($pair.code)" -ForegroundColor Yellow
Write-Host "  Valid:    $([math]::Floor($pair.expires_in / 60))m $($pair.expires_in % 60)s"
Write-Host ""
Write-Host "On the phone: Find GRID, choose the host, enter the code."
if ($pair.url -match '127\.0\.0\.1|localhost') {
    Write-Host ""
    Write-Host "WARNING: the host is loopback-only. Set api.host to 0.0.0.0 in config.json and restart." -ForegroundColor Red
}
