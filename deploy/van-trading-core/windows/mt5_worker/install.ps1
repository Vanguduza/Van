# install.ps1 — MT5 bridge worker on the Windows host (run as the account that owns the MT5 terminal).
# Prereqs: MetaTrader 5 terminal installed and logged in once; Python 3.12 x64 from python.org.
# Files copied from van-trading-core (/opt/van-trading/secrets/pki): ca.crt, mt5-worker.crt, mt5-worker.key
param([string]$Root = "C:\van-mt5", [int]$Port = 9443)
$ErrorActionPreference = "Stop"
New-Item -ItemType Directory -Force -Path $Root | Out-Null
Copy-Item "$PSScriptRoot\mt5_bridge_worker.py" "$Root\mt5_bridge_worker.py" -Force
if (-not (Test-Path "$Root\venv")) { py -3.12 -m venv "$Root\venv" }
& "$Root\venv\Scripts\pip.exe" install --quiet "MetaTrader5==5.0.4874"
foreach ($f in "ca.crt","mt5-worker.crt","mt5-worker.key") { if (-not (Test-Path "$Root\$f")) { throw "missing $Root\$f — copy it from van-trading-core pki" } }
if (-not (Test-Path "$Root\bridge.key")) { $bytes = New-Object byte[] 32; [Security.Cryptography.RandomNumberGenerator]::Fill($bytes); [Convert]::ToHexString($bytes).ToLower() | Set-Content -NoNewline "$Root\bridge.key"; Write-Host "bridge.key created — copy its value into the account secrets file on van-trading-core as BRIDGE_SIGNING_KEY" }
if (-not (Test-Path "$Root\worker.json")) {
  @{ listen="0.0.0.0"; port=$Port; cert="$Root\mt5-worker.crt"; key="$Root\mt5-worker.key"; ca="$Root\ca.crt"; signing_key_file="$Root\bridge.key"; accounts=@{} } | ConvertTo-Json -Depth 4 | Set-Content "$Root\worker.json"
  Write-Host "worker.json created — add accounts: {alias: {login, server, password_file}}"
}
# Owner-only ACLs on secrets (equivalent of 0600)
foreach ($f in "bridge.key","mt5-worker.key","worker.json") { icacls "$Root\$f" /inheritance:r /grant:r "$env:USERNAME:(R,W)" | Out-Null }
# Windows firewall: only van-trading-core may reach the worker port
netsh advfirewall firewall delete rule name="VAN MT5 bridge" | Out-Null
netsh advfirewall firewall add rule name="VAN MT5 bridge" dir=in action=allow protocol=TCP localport=$Port remoteip=10.0.1.233 | Out-Null
# Scheduled task keeps the worker running at logon (the MT5 terminal needs an interactive session)
$action = New-ScheduledTaskAction -Execute "$Root\venv\Scripts\python.exe" -Argument "$Root\mt5_bridge_worker.py --config $Root\worker.json" -WorkingDirectory $Root
$trigger = New-ScheduledTaskTrigger -AtLogOn
Register-ScheduledTask -TaskName "VAN MT5 Bridge Worker" -Action $action -Trigger $trigger -RunLevel Limited -Force | Out-Null
Write-Host "installed. Start now: Start-ScheduledTask -TaskName 'VAN MT5 Bridge Worker'"
