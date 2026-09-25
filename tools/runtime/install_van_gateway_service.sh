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

# Public tunnel access is gated again at the VAN application boundary.
# Generate the owner ingress bearer once and keep it out of logs/process args.
if ! grep -Eq '^VAN_INGRESS_TOKEN=.{32,}$' "$GATEWAY_ENV"; then
  INGRESS_TOKEN="$(python3 - <<'INGRESSPY'
import secrets
print(secrets.token_urlsafe(48))
INGRESSPY
)"
  TMP_ENV="$(mktemp "$CONFIG_ROOT/gateway.env.XXXXXX")"
  grep -Ev '^VAN_INGRESS_TOKEN=' "$GATEWAY_ENV" > "$TMP_ENV" || true
  printf 'VAN_INGRESS_TOKEN=%s\n' "$INGRESS_TOKEN" >> "$TMP_ENV"
  install -m 0600 "$TMP_ENV" "$GATEWAY_ENV"
  rm -f "$TMP_ENV"
  unset INGRESS_TOKEN
fi

STAGE="$(mktemp -d "$STATE_ROOT/runtime.stage.XXXXXX")"
trap 'rm -rf "$STAGE"' EXIT
mkdir -p "$STAGE/backend"
cp -a "$ROOT/backend/van_gateway" "$STAGE/backend/"
cp "$ROOT/backend/requirements.txt" "$STAGE/backend/requirements.txt"
cp "$ROOT/backend/requirements.lock" "$STAGE/backend/requirements.lock"
cp -a "$ROOT/registries" "$STAGE/registries"
# `van_gateway.trading.accounts` puts <runtime>/trading on sys.path and imports `commander`
# from it. Without this copy the gateway crashes at startup; runtimes that worked had it
# placed by hand. The trading test suite is not runtime code.
tar -C "$ROOT" --exclude='trading/tests' --exclude='__pycache__' -cf - trading | tar -C "$STAGE" -xf -
# GAP-F-018/021 — `qualify_gateway_host.sh` reports the deployed commit on a GREEN
# qualification. The staged runtime is a plain `cp -a`, not a git checkout, so the SHA has
# to be captured here, at the one point that still has the source tree's git metadata.
git -C "$ROOT" rev-parse HEAD > "$STAGE/DEPLOYED_SHA" 2>/dev/null || echo "unknown" > "$STAGE/DEPLOYED_SHA"

if [[ ! -x "$VENV/bin/python" ]]; then
  python3 -m venv "$VENV"
fi
# GAP-F-017 — install from the exact-pinned lock, not the floating spec. Two installs of
# the same commit must resolve to the same bytes; requirements.txt alone cannot promise
# that once any dependency ships a new release between them.
if [[ "${VAN_INSTALL_STAGE_ONLY:-}" != "1" ]]; then
  "$VENV/bin/python" -m pip install --quiet -r "$STAGE/backend/requirements.lock"
fi

# Pre-flight: the staged runtime must build the app with this host's real environment
# *before* it replaces the running one. A runtime that cannot start never takes the
# gateway down; the old one keeps serving and this install fails instead.
if ! (cd "$STAGE/backend" && PYTHONPATH="$STAGE/backend" \
      VAN_ENV_FILES="$GOOGLE_ENV:$GATEWAY_ENV:$CONFIG_ROOT/trading-commander.env" \
      timeout 120 "$VENV/bin/python" - <<'PREFLIGHT'
import os, sys
from pathlib import Path

# systemd EnvironmentFile semantics, as far as these files use them.
for name in os.environ.pop("VAN_ENV_FILES").split(":"):
    path = Path(name)
    if not path.is_file():
        continue
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "'\"":
            value = value[1:-1]
        os.environ[key.strip()] = value
import van_gateway.app  # noqa: F401  builds the app exactly as the unit's process does
import van_gateway.mtls.serve  # noqa: F401
PREFLIGHT
    ); then
  echo "FAIL van_gateway_preflight: the staged runtime cannot build the app; the running gateway was not touched" >&2
  exit 4
fi
echo "PASS van_gateway_preflight"
if [[ "${VAN_INSTALL_STAGE_ONLY:-}" == "1" ]]; then
  # Never the live runtime: stage-only must be safe to run on a serving host.
  rm -rf "$STATE_ROOT/runtime.staged"
  mv "$STAGE" "$STATE_ROOT/runtime.staged"
  trap - EXIT
  echo "staged=$STATE_ROOT/runtime.staged (the running runtime and unit were not touched)"
  exit 0
fi

rm -rf "$RUNTIME_ROOT.previous"
if [[ -d "$RUNTIME_ROOT" ]]; then
  mv "$RUNTIME_ROOT" "$RUNTIME_ROOT.previous"
fi
mv "$STAGE" "$RUNTIME_ROOT"
trap - EXIT

install -m 0644 "$UNIT_SRC" "$UNIT_DST"
systemctl --user daemon-reload
systemctl --user enable van-gateway.service >/dev/null
systemctl --user restart van-gateway.service

for _ in {1..20}; do
  if VAN_GATEWAY_ENV="$GATEWAY_ENV" "$VENV/bin/python" - <<'HEALTH'
import os
import urllib.request
from pathlib import Path

env_path = Path(os.environ["VAN_GATEWAY_ENV"])
token = ""
for line in env_path.read_text(encoding="utf-8").splitlines():
    if line.startswith("VAN_INGRESS_TOKEN="):
        token = line.split("=", 1)[1].strip()
        break
if not token:
    raise SystemExit(1)
request = urllib.request.Request(
    "http://127.0.0.1:8787/health",
    headers={"X-Van-Ingress-Token": token},
)
try:
    with urllib.request.urlopen(request, timeout=2) as r:
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
