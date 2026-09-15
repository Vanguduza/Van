# Start Van gateway (uvicorn) on Windows.
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$Backend = Join-Path $Root "backend"
$Python = Join-Path $Backend ".venv\Scripts\python.exe"
if (-not (Test-Path $Python)) {
    Write-Error "Missing backend/.venv — run tools/bootstrap_backend.ps1 first"
}
$env:PYTHONPATH = $Backend
if (-not $env:VAN_INTERNAL_CONTROL_TOKEN) {
    Write-Warning "VAN_INTERNAL_CONTROL_TOKEN unset; Project Truth PUT and Google control routes will fail closed."
}
Set-Location $Backend
& $Python -m uvicorn van_gateway.app:app --host 127.0.0.1 --port 8787
