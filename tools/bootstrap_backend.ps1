# Bootstrap Van gateway on Windows. Idempotent, fail-closed, secret-safe.
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location (Join-Path $Root "backend")
if (-not (Test-Path ".venv")) {
    python -m venv .venv
}
# GAP-F-017 - install from the exact-pinned lock so a local bootstrap resolves the same
# dependency set CI and the release host do.
& .\.venv\Scripts\python.exe -m pip install -r requirements.lock
& .\.venv\Scripts\python.exe -m pytest -q
Write-Host "VAN gateway bootstrap OK"
