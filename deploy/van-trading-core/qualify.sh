#!/usr/bin/env bash
# Qualification report for van-trading-core. Exit 0 only when every REQUIRED check is GREEN.
# Machine-readable JSON on stdout; run after bootstrap and after every change.
set -uo pipefail
BASE=/opt/van-trading; DATA=/var/lib/van-trading
ENVF="$BASE/config/van-trading-core.env"; [[ -f "$ENVF" ]] && set -a && . "$ENVF" && set +a
checks=(); fails=0
add() {
  local name="$1" status="$2" detail="$3" required="${4:-1}"
  checks+=("{\"check\":\"$name\",\"status\":\"$status\",\"required\":$required,\"detail\":$(printf '%s' "$detail" | jq -Rs .)}")
  if [[ "$status" != "GREEN" && "$required" == "1" ]]; then fails=$((fails+1)); fi
  return 0
}
unit() { local u="$1" req="${2:-1}"; if systemctl is-active --quiet "$u"; then add "unit:$u" GREEN "active" "$req"; else add "unit:$u" RED "$(systemctl is-active "$u" 2>&1)" "$req"; fi; }
[[ "$(uname -m)" == "aarch64" || "$(uname -m)" == "x86_64" ]] && add arch GREEN "$(uname -m)" || add arch RED "$(uname -m)"
command -v python3.12 >/dev/null && add python GREEN "$(python3.12 --version)" || add python RED "python3.12 missing"
command -v node >/dev/null && [[ "$(node -v | cut -c2- | cut -d. -f1)" -ge 20 ]] && add node GREEN "$(node -v)" || add node RED "node ≥ 20 missing"
command -v docker >/dev/null && docker compose version >/dev/null 2>&1 && add docker GREEN "$(docker --version)" || add docker RED "docker/compose missing"
id vati >/dev/null 2>&1 && add user GREEN vati || add user RED "vati missing"
for f in "$BASE/secrets/commander.token" "$BASE/secrets/vekl.token" "$BASE/secrets/pki/ca.crt"; do
  if [[ -f "$f" ]]; then m=$(stat -c %a "$f"); [[ "$m" =~ ^600$|^400$ ]] && add "secret:$(basename "$f")" GREEN "mode $m" || add "secret:$(basename "$f")" RED "mode $m (need 0600)"; else add "secret:$(basename "$f")" RED missing; fi
done
unit vati-vekl.service; unit vati-commander.service; unit vati-automation.service; unit vati-supabase.service 0; unit docker.service 0
curl -fsS --max-time 5 "${VAN_VEKL_URL:-http://127.0.0.1:9134}/health" >/tmp/vekl.json 2>/dev/null && jq -e '.ok==true' /tmp/vekl.json >/dev/null && add vekl_health GREEN "$(jq -c '.registry|{resources,sources}' /tmp/vekl.json)" || add vekl_health RED "VEKL health not ok"
curl -fsSk --max-time 5 "https://127.0.0.1:${VAN_COMMANDER_PORT:-9133}/health" >/tmp/cmd.json 2>/dev/null && jq -e '.ok==true' /tmp/cmd.json >/dev/null && add commander_health GREEN "$(jq -c '.commands|length' /tmp/cmd.json) commands" || add commander_health RED "commander health not ok"
if "$BASE/automation/qualify-automation-runtime.sh" >/tmp/automation-qualify.log 2>&1; then add automation_fabric GREEN "$(tail -n 1 /tmp/automation-qualify.log)"; else add automation_fabric RED "$(tail -c 500 /tmp/automation-qualify.log)"; fi
if "$BASE/app/deploy/van-trading-core/supabase/qualify-supabase-runtime.sh" >/tmp/supabase-qualify.log 2>&1; then add supabase_runtime GREEN "$(tail -n 1 /tmp/supabase-qualify.log)"; else add supabase_runtime RED "$(tail -c 500 /tmp/supabase-qualify.log)"; fi
if [[ -f "$DATA/evidence/browser/runtime-manifest.json" ]] && jq -e '.stagehand=="4.1.0" and .playwright=="1.63.0" and .temporalio=="1.33.0"' "$DATA/evidence/browser/runtime-manifest.json" >/dev/null; then add browser_runtime GREEN "Stagehand 4.1.0 / Playwright 1.63.0 / Temporal 1.33.0"; else add browser_runtime RED "browser runtime manifest missing or mismatched"; fi
if [[ -n "${VAN_COMMANDER_LEDGER:-}" ]]; then PYTHONPATH="$BASE/app/trading" "$BASE/venv/bin/python" - <<PY >/tmp/ledger.json 2>/tmp/ledger.err && add ledger GREEN "$(cat /tmp/ledger.json)" || add ledger RED "$(tail -c 300 /tmp/ledger.err)"
import json
from vati.core.ledger_pg import open_ledger
l = open_ledger("${VAN_COMMANDER_LEDGER}"); ok, n = l.verify_chain(); print(json.dumps({"backend": type(l).__name__, "chain_ok": ok, "events": n})); l.close()
PY
fi
if ufw status 2>/dev/null | grep -q "Status: active"; then ufw status | grep -q "9133" && add firewall GREEN "ufw active, 9133 scoped" || add firewall RED "9133 rule missing"; else add firewall RED "ufw inactive"; fi
listeners="$(ss -ltnH 2>/dev/null | awk '{print $4}' | grep -E ':(3000|5432|5433|6543|8000)$' || true)"
bad_listeners="$(printf '%s
' "$listeners" | grep -Ev '^(127\.0\.0\.1|\[::1\]):' || true)"
missing_ports=""
for p in 3000 5432 5433 6543 8000; do printf '%s
' "$listeners" | grep -Eq ":${p}$" || missing_ports="$missing_ports $p"; done
if [[ -z "$bad_listeners" && -z "$missing_ports" ]]; then add supabase_loopback GREEN "ports 3000,5432,5433,6543,8000 loopback-only"; else add supabase_loopback RED "non-loopback=${bad_listeners:-none}; missing=${missing_ports:-none}"; fi
shopt -s nullglob; hb=("$DATA"/heartbeats/*.json); if (( ${#hb[@]} )); then for f in "${hb[@]}"; do age=$(( $(date +%s) - $(jq -r '.updated_ms' "$f")/1000 )); [[ $age -lt 300 ]] && add "session:$(basename "$f" .json)" GREEN "$(jq -c '{status,cycles,kill_switch}' "$f") age=${age}s" 0 || add "session:$(basename "$f" .json)" AMBER "stale heartbeat ${age}s" 0; done; else add sessions AMBER "no session heartbeats yet (no account enabled)" 0; fi
[[ "$(uname -m)" == "x86_64" ]] && add mt5_native AMBER "x86_64: MT5 could run here, but the design keeps MT5 on the Windows worker" 0 || add mt5_native AMBER "ARM64 host: MT5 runs on the Windows bridge worker; this VM holds only the mTLS client" 0
status=GREEN; (( fails )) && status=RED
printf '{"host":"%s","status":"%s","required_failures":%d,"at":"%s","checks":[%s]}\n' "$(hostname)" "$status" "$fails" "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$(IFS=,; echo "${checks[*]}")" | jq .
(( fails == 0 ))
