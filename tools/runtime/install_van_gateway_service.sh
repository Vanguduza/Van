#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
STATE_ROOT="${VAN_STATE_ROOT:-$HOME/.local/share/van}"
RUNTIME_ROOT="$STATE_ROOT/runtime"
VENV="$STATE_ROOT/venv"
CONFIG_ROOT="${VAN_CONFIG_ROOT:-$HOME/.config/van}"
GOOGLE_ENV="$CONFIG_ROOT/google-workspace.env"
GATEWAY_ENV="$CONFIG_ROOT/gateway.env"
UNIT_SRC="$ROOT/deploy/systemd/van-gateway.service"
UNIT_DST="$HOME/.config/systemd/user/van-gateway.service"

for required in "$GOOGLE_ENV" "$GATEWAY_ENV" "$UNIT_SRC"; do
  if [[ ! -f "$required" ]]; then
    echo "FAIL missing_required_file:$required" >&2
    exit 2
  fi
done

mkdir -p "$STATE_ROOT" "$CONFIG_ROOT" "$HOME/.config/systemd/user"
chmod 700 "$STATE_ROOT" "$CONFIG_ROOT"
chmod 600 "$GOOGLE_ENV" "$GATEWAY_ENV"

# Device HMAC credentials must survive gateway restarts without being stored in plaintext.
# Generate the dedicated Fernet key once, keep it owner-readable only, and never print it.
if ! grep -Eq '^VAN_DEVICE_SECRET_FERNET_KEY=.+$' "$GATEWAY_ENV"; then
  DEVICE_KEY="$(python3 - <<'KEYPY'
import base64, secrets
print(base64.urlsafe_b64encode(secrets.token_bytes(32)).decode('ascii'))
KEYPY
)"
  TMP_ENV="$(mktemp "$CONFIG_ROOT/gateway.env.XXXXXX")"
  grep -Ev '^VAN_DEVICE_SECRET_FERNET_KEY=' "$GATEWAY_ENV" > "$TMP_ENV" || true
  printf 'VAN_DEVICE_SECRET_FERNET_KEY=%s\n' "$DEVICE_KEY" >> "$TMP_ENV"
  install -m 0600 "$TMP_ENV" "$GATEWAY_ENV"
  rm -f "$TMP_ENV"
  unset DEVICE_KEY
fi

STAGE="$(mktemp -d "$STATE_ROOT/runtime.stage.XXXXXX")"
trap 'rm -rf "$STAGE"' EXIT
mkdir -p "$STAGE/backend"
cp -a "$ROOT/backend/van_gateway" "$STAGE/backend/"
cp "$ROOT/backend/requirements.txt" "$STAGE/backend/requirements.txt"
cp -a "$ROOT/registries" "$STAGE/registries"

if [[ ! -x "$VENV/bin/python" ]]; then
  python3 -m venv "$VENV"
fi
"$VENV/bin/python" -m pip install --quiet -r "$STAGE/backend/requirements.txt"

rm -rf "$RUNTIME_ROOT.previous"
if [[ -d "$RUNTIME_ROOT" ]]; then
  mv "$RUNTIME_ROOT" "$RUNTIME_ROOT.previous"
fi
mv "$STAGE" "$RUNTIME_ROOT"
trap - EXIT

install -m 0644 "$UNIT_SRC" "$UNIT_DST"
systemctl --user daemon-reload
systemctl --user enable --now van-gateway.service

for _ in {1..20}; do
  if "$VENV/bin/python" - <<'HEALTH'
import urllib.request
try:
    with urllib.request.urlopen("http://127.0.0.1:8787/health", timeout=2) as r:
        raise SystemExit(0 if r.status == 200 else 1)
except Exception:
    raise SystemExit(1)
HEALTH
  then
    echo "PASS van_gateway_http_ready"
    echo "runtime=$RUNTIME_ROOT"
    echo "service=van-gateway.service"
    exit 0
  fi
  sleep 1
done

systemctl --user --no-pager --full status van-gateway.service >&2 || true
echo "FAIL van_gateway_health_timeout" >&2
exit 3
