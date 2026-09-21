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
COMMANDER_USER="${VAN_DESKTOP_COMMANDER_USER:-vancommander}"
COMMANDER_HOME="${VAN_DESKTOP_COMMANDER_HOME:-/var/lib/van-commander}"
if id "$COMMANDER_USER" >/dev/null 2>&1; then
  groups="$(id -nG "$COMMANDER_USER" | tr ' ' '\n')"
  if grep -Eq '^(vati|sudo|docker)$' <<<"$groups"; then
    add full_desktop_commander_identity RED "$COMMANDER_USER belongs to a forbidden privileged group"
  else
    add full_desktop_commander_identity GREEN "$COMMANDER_USER isolated from vati/sudo/docker"
  fi
else
  add full_desktop_commander_identity RED "$COMMANDER_USER missing"
fi
if [[ -x "$COMMANDER_HOME/.local/bin/van-local-commander-mcp" && -f "$COMMANDER_HOME/.local/share/van/desktop-commander/node_modules/@wonderwhy-er/desktop-commander/package.json" ]]; then
  dcver="$(node -e 'const p=require(process.argv[1]);process.stdout.write(String(p.version||""))' "$COMMANDER_HOME/.local/share/van/desktop-commander/node_modules/@wonderwhy-er/desktop-commander/package.json" 2>/dev/null || true)"
  [[ "$dcver" == "0.2.50" ]] && add full_desktop_commander GREEN "Desktop Commander $dcver; isolated stdio wrapper installed" || add full_desktop_commander RED "unexpected Desktop Commander version: ${dcver:-missing}"
else
  add full_desktop_commander RED "isolated full Desktop Commander stdio runtime missing"
fi
if id "$COMMANDER_USER" >/dev/null 2>&1 && sudo -u "$COMMANDER_USER" test -r "$BASE/secrets/commander.token" 2>/dev/null; then
  add full_desktop_commander_secret_boundary RED "$COMMANDER_USER can read VATI Commander secrets"
else
  add full_desktop_commander_secret_boundary GREEN "$COMMANDER_USER cannot read VATI Commander secrets"
fi
[[ -d "$COMMANDER_HOME/work/Van/.git" ]] && add full_desktop_commander_workspace GREEN "isolated Git workspace present" || add full_desktop_commander_workspace RED "isolated Git workspace missing"
[[ -x /usr/local/sbin/van-install-commander-key && "$(stat -c '%U:%G:%a' /usr/local/sbin/van-install-commander-key 2>/dev/null)" == "root:root:755" ]] && add full_desktop_commander_key_enrolment GREEN "root-owned forced-key installer present" || add full_desktop_commander_key_enrolment RED "root-owned key installer missing or wrong mode"
[[ -x /usr/local/bin/van-github-recovery ]] && add github_recovery_command GREEN "bounded recovery entrypoint installed" || add github_recovery_command RED "van-github-recovery missing"
if sudo -n -u "$COMMANDER_USER" sudo -n /usr/local/bin/van-github-recovery probe >/dev/null 2>&1; then
  add full_desktop_commander_recovery_sudo GREEN "enumerated recovery helper is callable"
else
  add full_desktop_commander_recovery_sudo RED "bounded recovery sudo rule missing or unusable"
fi
if sudo -n -u "$COMMANDER_USER" sudo -n true >/dev/null 2>&1; then
  add full_desktop_commander_no_generic_sudo RED "$COMMANDER_USER can invoke generic sudo"
else
  add full_desktop_commander_no_generic_sudo GREEN "$COMMANDER_USER has no generic sudo"
fi
REVIEW_USER="${VAN_SPMRF_REVIEW_USER:-vanreviewer}"
REVIEW_HOME="${VAN_SPMRF_REVIEW_HOME:-/var/lib/van-reviewer}"
if id "$REVIEW_USER" >/dev/null 2>&1; then
  review_groups="$(id -nG "$REVIEW_USER" | tr ' ' '\n')"
  if grep -Eq '^(vati|sudo|docker)$' <<<"$review_groups"; then
    add spmrf_reviewer_identity RED "$REVIEW_USER belongs to a forbidden privileged group"
  else
    add spmrf_reviewer_identity GREEN "$REVIEW_USER isolated from vati/sudo/docker"
  fi
else
  add spmrf_reviewer_identity RED "$REVIEW_USER missing"
fi
if [[ -x "$REVIEW_HOME/.local/bin/van-spmrf-review-worker" && -x "$REVIEW_HOME/.local/share/van/spmrf/codex/node_modules/.bin/codex" ]]; then
  cv="$("$REVIEW_HOME/.local/share/van/spmrf/codex/node_modules/.bin/codex" --version 2>/dev/null || true)"
  [[ "$cv" == *"0.153.1"* ]] && add spmrf_review_worker GREEN "$cv; isolated worker installed" || add spmrf_review_worker RED "unexpected Codex version: ${cv:-missing}"
else
  add spmrf_review_worker RED "isolated SPMRF review worker/Codex runtime missing"
fi
if id "$REVIEW_USER" >/dev/null 2>&1 && sudo -u "$REVIEW_USER" test -r "$BASE/secrets/commander.token" 2>/dev/null; then
  add spmrf_secret_boundary RED "$REVIEW_USER can read VATI Commander secrets"
else
  add spmrf_secret_boundary GREEN "$REVIEW_USER cannot read VATI Commander secrets"
fi
auth="$(sudo -u "$REVIEW_USER" env HOME="$REVIEW_HOME" "$REVIEW_HOME/.local/share/van/spmrf/codex/node_modules/.bin/codex" login status 2>&1 || true)"
grep -q 'Logged in using ChatGPT' <<<"$auth" && add spmrf_chatgpt_auth GREEN "secondary ChatGPT subscription OAuth active under isolated reviewer" || add spmrf_chatgpt_auth RED "isolated reviewer must run codex login once"
if [[ -x "$REVIEW_HOME/.local/bin/dial-shared-memory-chatgpt-stdio" && -x "$REVIEW_HOME/.local/bin/dial-shared-memory-claude-stdio" ]]; then
  add spmrf_memory_clients GREEN "ChatGPT and Claude forced-SSH stdio clients installed under isolated reviewer"
else
  add spmrf_memory_clients RED "isolated shared-memory stdio clients missing"
fi
if sudo -u "$REVIEW_USER" ssh-keygen -F "${DIAL_HERMES_CONTROL_HOST:-dial-hermes-control}" -f "$REVIEW_HOME/.ssh/known_hosts" >/dev/null 2>&1; then
  add spmrf_hermes_host_key GREEN "trusted Hermes host key present for isolated reviewer"
else
  add spmrf_hermes_host_key RED "trusted dial-hermes-control host key missing for isolated reviewer"
fi
declare -A commander_token_hashes=()
for f in "$BASE/secrets/commander.token" "$BASE/secrets/commander.token.hermes" "$BASE/secrets/commander.token.van-gateway"; do
  name="$(basename "$f")"
  if [[ ! -f "$f" ]]; then add "secret:$name" RED missing; continue; fi
  m="$(stat -c %a "$f")"
  if [[ "$m" != "600" && "$m" != "400" ]]; then add "secret:$name" RED "mode $m (need 0600)"; continue; fi
  value="$(tr -d '\r\n' < "$f")"
  if (( ${#value} < 32 )); then add "secret:$name" RED "token shorter than 32 characters"; continue; fi
  h="$(sha256sum "$f" | awk '{print $1}')"
  if [[ -n "${commander_token_hashes[$h]:-}" ]]; then
    add "secret:$name" RED "duplicates ${commander_token_hashes[$h]}"
  else
    commander_token_hashes[$h]="$name"
    add "secret:$name" GREEN "mode $m; distinct principal credential"
  fi
done
for f in "$BASE/secrets/vekl.token" "$BASE/secrets/pki/ca.crt"; do
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
if VAN_ADMIN_CIDRS="${VAN_ADMIN_CIDRS:-10.0.0.123/32,10.0.0.184/32}" VAN_PUBLIC_HOST="${VAN_PUBLIC_HOST:-}" bash "$BASE/app/deploy/van-trading-core/oci/harden-oracle-image-firewall.sh" --verify >/tmp/oracle-firewall.log 2>&1; then add oracle_image_firewall GREEN "$(tail -n 1 /tmp/oracle-firewall.log)"; else add oracle_image_firewall RED "$(tail -c 500 /tmp/oracle-firewall.log)"; fi
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
