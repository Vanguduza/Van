#!/usr/bin/env bash
# Converge the private Hermes -> VAN Trading Core Browser Fabric transport.
#
# This runs on the Hermes/Gateway host. Browser workers remain loopback-only on
# van-trading-core; SSH is the transport, not an authority boundary.
set -euo pipefail

TRADING_HOST="${VAN_TRADING_CORE_SSH_HOST:-van-trading-core}"
GATEWAY_ENV="${VAN_GATEWAY_ENV:-$HOME/.config/van/gateway.env}"
REPO="${VAN_REPO:-$HOME/work/van-google-runtime-closure}"
UNIT_DIR="$HOME/.config/systemd/user"
UNIT="$UNIT_DIR/van-trading-core-browser-tunnel.service"

STAGEHAND_LOCAL_PORT="${VAN_TRADING_STAGEHAND_LOCAL_PORT:-19140}"
HARNESS_LOCAL_PORT="${VAN_TRADING_HARNESS_LOCAL_PORT:-19141}"
JEV_LOCAL_PORT="${VAN_TRADING_JEV_LOCAL_PORT:-19142}"

die(){ printf '[browser-transport] ERROR: %s\n' "$*" >&2; exit 1; }
log(){ printf '[browser-transport] %s\n' "$*"; }

[[ -f "$GATEWAY_ENV" ]] || die "gateway env missing: $GATEWAY_ENV"
[[ -d "$REPO/.git" ]] || die "VAN repository missing: $REPO"
ssh -o BatchMode=yes -o ConnectTimeout=10 "$TRADING_HOST" true >/dev/null

for spec in   "$STAGEHAND_LOCAL_PORT:9140"   "$HARNESS_LOCAL_PORT:9141"   "$JEV_LOCAL_PORT:9142"
do
  local_port="${spec%%:*}"
  [[ "$local_port" =~ ^[0-9]+$ ]] || die "invalid local port: $local_port"
  (( local_port >= 1024 && local_port <= 65535 )) || die "local port outside unprivileged range: $local_port"
done

mkdir -p "$UNIT_DIR"
cat >"$UNIT" <<UNIT
[Unit]
Description=VAN private Browser Fabric transport to Trading Core
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
ExecStart=/usr/bin/ssh -NT \
  -o BatchMode=yes \
  -o ExitOnForwardFailure=yes \
  -o ServerAliveInterval=30 \
  -o ServerAliveCountMax=3 \
  -o ClearAllForwardings=yes \
  -L 127.0.0.1:$STAGEHAND_LOCAL_PORT:127.0.0.1:9140 \
  -L 127.0.0.1:$HARNESS_LOCAL_PORT:127.0.0.1:9141 \
  -L 127.0.0.1:$JEV_LOCAL_PORT:127.0.0.1:9142 \
  $TRADING_HOST
Restart=always
RestartSec=3
TimeoutStartSec=20
TimeoutStopSec=10
NoNewPrivileges=yes
PrivateTmp=yes
ProtectSystem=strict
ProtectHome=read-only
RestrictSUIDSGID=yes
LockPersonality=yes

[Install]
WantedBy=default.target
UNIT
chmod 0644 "$UNIT"

# Patch only the keys this transport owns. Preserve all other Gateway configuration.
python3 - "$GATEWAY_ENV" \
  "$STAGEHAND_LOCAL_PORT" "$HARNESS_LOCAL_PORT" "$JEV_LOCAL_PORT" <<'PY'
from pathlib import Path
import re
import sys

path = Path(sys.argv[1])
stagehand, harness, jev = sys.argv[2:]
values = {
    "VAN_BROWSER_ENABLED": "true",
    "VAN_BROWSER_STAGEHAND_BASE_URL": f"http://127.0.0.1:{stagehand}",
    "VAN_BROWSER_HARNESS_BASE_URL": f"http://127.0.0.1:{harness}",
    "VAN_BROWSER_JEV_ENABLED": "true",
    "VAN_BROWSER_JEV_BASE_URL": f"http://127.0.0.1:{jev}",
    "VAN_BROWSER_JEV_EXPECTED_VERSION": "0.1.0",
    "VAN_BROWSER_JEV_MODEL": "jev-1.13.0",
    "VAN_BROWSER_JEV_MIN_CONFIDENCE": "0.80",
    # Canonical VAN/Hermes model policy. The worker still fails closed until its
    # own Stagehand model secret is present and live-certified.
    "VAN_BROWSER_STAGEHAND_MODEL_PROVIDER": "anthropic",
    "VAN_BROWSER_STAGEHAND_MODEL_NAME": "claude-sonnet-5",
}
text = path.read_text(encoding="utf-8")
for key, value in values.items():
    line = f"{key}={value}"
    pattern = rf"(?m)^{re.escape(key)}=.*$"
    if re.search(pattern, text):
        text = re.sub(pattern, line, text)
    else:
        if text and not text.endswith("\n"):
            text += "\n"
        text += line + "\n"
tmp = path.with_name(path.name + ".browser.tmp")
tmp.write_text(text, encoding="utf-8")
tmp.chmod(0o600)
tmp.replace(path)
PY
chmod 0600 "$GATEWAY_ENV"

systemctl --user daemon-reload
systemctl --user enable --now van-trading-core-browser-tunnel.service >/dev/null

# Prove all three private workers are reachable over the exact loopback forwards.
for attempt in 1 2 3 4 5 6 7 8 9 10; do
  if curl -fsS --max-time 3 "http://127.0.0.1:$HARNESS_LOCAL_PORT/health" >/tmp/van-browser-harness-health.json 2>/dev/null \
     && curl -fsS --max-time 3 "http://127.0.0.1:$STAGEHAND_LOCAL_PORT/health" >/tmp/van-stagehand-health.json 2>/dev/null \
     && curl -fsS --max-time 3 "http://127.0.0.1:$JEV_LOCAL_PORT/health" >/tmp/van-jev-health.json 2>/dev/null; then
    break
  fi
  [[ "$attempt" != 10 ]] || {
    systemctl --user --no-pager --full status van-trading-core-browser-tunnel.service >&2 || true
    die "browser worker forwards did not become reachable"
  }
  sleep 1
done

python3 - "$HARNESS_LOCAL_PORT" "$STAGEHAND_LOCAL_PORT" "$JEV_LOCAL_PORT" <<'PY'
import json
from pathlib import Path
import sys

h = json.loads(Path("/tmp/van-browser-harness-health.json").read_text())
s = json.loads(Path("/tmp/van-stagehand-health.json").read_text())
j = json.loads(Path("/tmp/van-jev-health.json").read_text())
assert h["ok"] is True and h["runtime_version"] == "0.1.13"
assert s["ok"] is True and s["runtime_version"] == "4.1.0"
assert s["direct_agent_loop"] is False and s["model_self_selection"] is False
assert j["ok"] is True and j["runtime_version"] == "0.1.0"
assert j["model"] == "jev-1.13.0"
assert float(j["min_confidence"]) == 0.80
assert j["text_generation"] is False and j["executes_actions"] is False
assert j["autonomous_loop"] is False
PY

# Re-read browser coordinates in the production Gateway.
systemctl --user restart van-gateway.service
systemctl --user is-active --quiet van-gateway.service

# Readiness evidence belongs to the Gateway state store, so canaries run HERE, not on
# Trading Core. Harness is deterministic and is certified immediately. Jev/Stagehand
# are certified only when their dedicated worker credential is actually present.
set -a
# shellcheck disable=SC1090
. "$GATEWAY_ENV"
set +a
export PYTHONPATH="$REPO/backend"
PYTHON="$HOME/.local/share/van/venv/bin/python"
[[ -x "$PYTHON" ]] || die "Gateway Python runtime missing: $PYTHON"

"$PYTHON" "$REPO/tools/certification/certify_browser_fabric.py" \
  --canary harness --target notebooklm.google.com

if python3 - <<'PY' >/dev/null 2>&1
import json
d=json.load(open("/tmp/van-jev-health.json"))
assert d.get("model_key_present") is True
PY
then
  "$PYTHON" "$REPO/tools/certification/certify_browser_fabric.py" \
    --canary jev --target muse.ai \
    && log "JEV_GATEWAY_READINESS_GREEN" \
    || log "JEV_GATEWAY_READINESS_DEGRADED_STAGEHAND_FALLBACK"
else
  log "JEV_GATEWAY_READINESS_DEGRADED_NO_PROVIDER_KEY"
fi

if python3 - <<'PY' >/dev/null 2>&1
import json
d=json.load(open("/tmp/van-stagehand-health.json"))
assert d.get("model_key_present") is True
PY
then
  "$PYTHON" "$REPO/tools/certification/certify_browser_fabric.py" \
    --canary stagehand --target notebooklm.google.com \
    && log "STAGEHAND_GATEWAY_READINESS_GREEN" \
    || log "STAGEHAND_GATEWAY_READINESS_DEGRADED"
else
  log "STAGEHAND_GATEWAY_READINESS_DEGRADED_NO_PROVIDER_KEY"
fi

log "BROWSER_RUNTIME_TRANSPORT_GREEN harness=127.0.0.1:$HARNESS_LOCAL_PORT stagehand=127.0.0.1:$STAGEHAND_LOCAL_PORT jev=127.0.0.1:$JEV_LOCAL_PORT"
