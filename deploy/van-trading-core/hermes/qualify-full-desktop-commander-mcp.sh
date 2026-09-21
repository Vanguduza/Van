#!/usr/bin/env bash
set -euo pipefail

HERMES_CONFIG="${HERMES_CONFIG:-$HOME/.hermes/config.yaml}"
VAN_REPO="${VAN_REPO:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)}"
DIAL_REPO="${DIAL_REPO:-$HOME/dial-new}"
[[ -f "$DIAL_REPO/agent-system/orchestration/probe-commander-authority-gateway.mjs" ]] || DIAL_REPO="/opt/dial/dial-new"
WRAPPER="$VAN_REPO/deploy/van-trading-core/hermes/van-trading-full-commander-stdio.sh"

fail(){ echo "QUALIFICATION RED: $*" >&2; exit 1; }
pass(){ echo "✓ $*"; }

[[ "$(hostname)" == "${DIAL_HERMES_HOST_ID:-dial-hermes-control}" ]] || fail "wrong host"
[[ -f "$HERMES_CONFIG" ]] || fail "Hermes config missing"
[[ -x "$WRAPPER" ]] || fail "Trading Commander SSH stdio wrapper missing"

python3 - "$HERMES_CONFIG" "$DIAL_REPO" "$WRAPPER" <<'PY' || exit 1
import sys,yaml,os
cfg=yaml.safe_load(open(sys.argv[1],encoding='utf-8')) or {}
server=(cfg.get('mcp_servers') or {}).get('van_trading_local_commander') or {}
gateway=os.path.join(sys.argv[2],'agent-system/orchestration/hermes-commander-gateway.mjs')
assert server.get('command')=='node',server
assert server.get('args')==[gateway,'--commander-id','van_trading_local_commander'],server
assert (server.get('env') or {}).get('DIAL_LOCAL_COMMANDER_WRAPPER')==sys.argv[3],server
assert server.get('enabled') is True,server
assert server.get('supports_parallel_tool_calls') is False,server
assert server.get('timeout')==600,server
assert server.get('tools') in (None,{}),'full Commander must not carry a tool filter'
bounded=(cfg.get('mcp_servers') or {}).get('van_trading_commander') or {}
assert bounded,'bounded VATI commander must continue to coexist'
PY
pass "Full Trading Commander and bounded VATI commander coexist"

CAP="$(DIAL_LOCAL_COMMANDER_WRAPPER="$WRAPPER" node "$DIAL_REPO/deploy/oracle/hermes-codex/probe-full-local-commander.mjs" 2>&1)" || { echo "$CAP" >&2; fail "full Trading Commander capability probe failed"; }
grep -q '"status": "GREEN"' <<<"$CAP" || { echo "$CAP" >&2; fail "Trading Commander capability surface incomplete"; }
pass "Trading Commander exposes full process/file/config/session tool surface"

AUTH="$(DIAL_LOCAL_COMMANDER_WRAPPER="$WRAPPER" DIAL_COMMANDER_PROBE_COMMANDER_ID=van_trading_local_commander node "$DIAL_REPO/agent-system/orchestration/probe-commander-authority-gateway.mjs" 2>&1)" || { echo "$AUTH" >&2; fail "Trading Commander authority probe failed"; }
grep -q '"status": "GREEN"' <<<"$AUTH" || { echo "$AUTH" >&2; fail "Trading Commander authority gate not GREEN"; }
pass "Trading Commander is full-capability but fail-closed outside owner/automation authority"

echo '{"status":"GREEN","commander":"van_trading_local_commander","capability_surface":"FULL","transport":"PRIVATE_FORCED_COMMAND_SSH_STDIO","domain_commander":"van_trading_commander","authority":"HERMES"}'
