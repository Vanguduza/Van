#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
CONFIG_ROOT="${VAN_CONFIG_ROOT:-$HOME/.config/van}"
TOKEN_FILE="$CONFIG_ROOT/cloudflare-tunnel.token"
PUBLIC_ENV="$CONFIG_ROOT/public-gateway.env"
GATEWAY_ENV="$CONFIG_ROOT/gateway.env"
CLOUDFLARED="${VAN_CLOUDFLARED_BIN:-$HOME/bin/cloudflared}"
UNIT_SRC="$ROOT/deploy/systemd/van-cloudflare-tunnel.service"
UNIT_DST="$HOME/.config/systemd/user/van-cloudflare-tunnel.service"

for required in "$TOKEN_FILE" "$PUBLIC_ENV" "$GATEWAY_ENV" "$UNIT_SRC"; do
  if [[ ! -f "$required" ]]; then
    echo "FAIL missing_required_file:$required" >&2
    exit 2
  fi
done
if [[ ! -x "$CLOUDFLARED" ]]; then
  echo "FAIL cloudflared_missing:$CLOUDFLARED" >&2
  exit 2
fi
chmod 700 "$CONFIG_ROOT"
chmod 600 "$TOKEN_FILE" "$GATEWAY_ENV" "$PUBLIC_ENV"

PUBLIC_URL="$(sed -n 's/^VAN_PUBLIC_GATEWAY_URL=//p' "$PUBLIC_ENV" | tail -1)"
if [[ "$PUBLIC_URL" != https://* ]] || [[ "$PUBLIC_URL" == *trycloudflare.com* ]]; then
  echo "FAIL stable_https_public_gateway_required" >&2
  exit 3
fi
mkdir -p "$HOME/.config/systemd/user"
install -m 0644 "$UNIT_SRC" "$UNIT_DST"
systemctl --user daemon-reload
systemctl --user enable van-cloudflare-tunnel.service >/dev/null
systemctl --user restart van-cloudflare-tunnel.service

for _ in {1..20}; do
  if systemctl --user is-active --quiet van-cloudflare-tunnel.service; then
    break
  fi
  sleep 1
done
if ! systemctl --user is-active --quiet van-cloudflare-tunnel.service; then
  systemctl --user --no-pager --full status van-cloudflare-tunnel.service >&2 || true
  echo "FAIL van_cloudflare_tunnel_not_active" >&2
  exit 4
fi

VAN_GATEWAY_ENV="$GATEWAY_ENV" VAN_PUBLIC_URL="$PUBLIC_URL" python3 - <<'PY'
import os
import urllib.request
from pathlib import Path

token = ""
for line in Path(os.environ["VAN_GATEWAY_ENV"]).read_text(encoding="utf-8").splitlines():
    if line.startswith("VAN_INGRESS_TOKEN="):
        token = line.split("=", 1)[1].strip()
        break
if not token:
    raise SystemExit("ingress_token_missing")
request = urllib.request.Request(
    os.environ["VAN_PUBLIC_URL"].rstrip("/") + "/health",
    headers={"X-Van-Ingress-Token": token},
)
with urllib.request.urlopen(request, timeout=15) as response:
    if response.status != 200:
        raise SystemExit(f"public_health_http_{response.status}")
PY

echo "PASS van_named_tunnel_ready"
echo "public_gateway=$PUBLIC_URL"
echo "service=van-cloudflare-tunnel.service"
