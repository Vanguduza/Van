# Sync Project Truth into a running local gateway (live PUT, not offline cache).
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
if (-not $env:VAN_INTERNAL_CONTROL_TOKEN) {
    Write-Error "Set VAN_INTERNAL_CONTROL_TOKEN before live Project Truth PUT"
}
Set-Location $Root
python tools/projects/sync_project_truth.py --from-mounts --gateway http://127.0.0.1:8787
