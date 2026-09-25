#!/usr/bin/env bash
# Configure VAN gateway access to the shared DIAL Jev service without exposing
# provider credentials to VAN or Android.
set -euo pipefail

CONFIG_ROOT="${VAN_CONFIG_ROOT:-$HOME/.config/van}"
GATEWAY_ENV="${VAN_GATEWAY_ENV_FILE:-$CONFIG_ROOT/gateway.env}"
SERVICE_URL="${DIAL_JEV_SERVICE_URL:-http://127.0.0.1:6791}"
PROJECTION_SOURCE="${DIAL_JEV_PROJECTION_TOKEN_SOURCE:-/etc/dial-control/secrets/jev-projection-token}"
CONTROL_SOURCE="${DIAL_JEV_CONTROL_TOKEN_SOURCE:-/etc/dial-control/secrets/jev-control-token}"
CONSUMER_SOURCE="${DIAL_JEV_CONSUMER_TOKEN_SOURCE:-/etc/dial-control/secrets/jev-consumer-token}"
OWNER="${VAN_CONFIG_OWNER:-}"

fail(){ echo "FAIL $*" >&2; exit 2; }
[[ -r "$PROJECTION_SOURCE" ]] || fail "projection token source is not readable: $PROJECTION_SOURCE"
[[ -r "$CONTROL_SOURCE" ]] || fail "control token source is not readable: $CONTROL_SOURCE"
[[ -r "$CONSUMER_SOURCE" ]] || fail "consumer token source is not readable: $CONSUMER_SOURCE"
[[ -f "$GATEWAY_ENV" ]] || fail "gateway env does not exist: $GATEWAY_ENV"

mkdir -p "$CONFIG_ROOT"
chmod 700 "$CONFIG_ROOT"
install -m 0600 "$PROJECTION_SOURCE" "$CONFIG_ROOT/jev-projection.token"
install -m 0600 "$CONTROL_SOURCE" "$CONFIG_ROOT/jev-control.token"
install -m 0600 "$CONSUMER_SOURCE" "$CONFIG_ROOT/jev-consumer.token"
if [[ -n "$OWNER" ]]; then
  chown "$OWNER" "$CONFIG_ROOT/jev-projection.token" "$CONFIG_ROOT/jev-control.token" "$CONFIG_ROOT/jev-consumer.token" "$GATEWAY_ENV"
fi

tmp="$(mktemp "$CONFIG_ROOT/gateway.env.XXXXXX")"
trap 'rm -f "$tmp"' EXIT
grep -Ev '^VAN_JEV_(ENABLED|BASE_URL|PROJECTION_TOKEN_FILE|CONTROL_TOKEN_FILE|CONSUMER_TOKEN_FILE|TIMEOUT_SECONDS)=' "$GATEWAY_ENV" > "$tmp" || true
cat >>"$tmp" <<ENV
VAN_JEV_ENABLED=true
VAN_JEV_BASE_URL=$SERVICE_URL
VAN_JEV_PROJECTION_TOKEN_FILE=$CONFIG_ROOT/jev-projection.token
VAN_JEV_CONTROL_TOKEN_FILE=$CONFIG_ROOT/jev-control.token
VAN_JEV_CONSUMER_TOKEN_FILE=$CONFIG_ROOT/jev-consumer.token
VAN_JEV_TIMEOUT_SECONDS=5
ENV
install -m 0600 "$tmp" "$GATEWAY_ENV"
if [[ -n "$OWNER" ]]; then chown "$OWNER" "$GATEWAY_ENV"; fi
rm -f "$tmp"; trap - EXIT

# Read-only projection token must be sufficient to inspect status.
projection_token="$(cat "$CONFIG_ROOT/jev-projection.token")"
code="$(curl --silent --output /dev/null --write-out '%{http_code}' \
  -H "X-Dial-Jev-Token: $projection_token" "$SERVICE_URL/v1/status" || true)"
unset projection_token
[[ "$code" == "200" ]] || fail "Jev projection canary returned HTTP $code"

if systemctl --user list-unit-files van-gateway.service >/dev/null 2>&1; then
  systemctl --user restart van-gateway.service
fi

echo "PASS van_jev_gateway_configured"
echo "service_url=$SERVICE_URL"
echo "projection_token=owner-file-only"
echo "control_token=owner-file-only"
echo "consumer_token=server-file-only"
