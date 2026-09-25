#!/usr/bin/env bash
# Turn on the phone's direct mutual-TLS link to the VAN gateway on this (the Hermes) host.
#
#   tools/runtime/enable_van_mtls.sh --san IP:203.0.113.7[,DNS:van.example] [--port 8443]
#
# Idempotent. On first run it creates the VAN device CA and a server certificate for --san;
# later runs keep the CA (re-creating it would strand every enrolled phone) and only re-issue
# the server certificate when --san changes. It then points gateway.env at the directory,
# opens the port in ufw, restarts the gateway, and proves from outside the app what a
# network client sees: TLS 1.3 only, and 403 without a client certificate.
#
# It prints the CA certificate in base64 at the end. That is public material: the app build
# pins it as VAN_GATEWAY_CA_PEM_B64. The CA *key* never leaves $MTLS_DIR and is never printed.
set -euo pipefail

SAN=""
PORT="8443"
while [[ $# -gt 0 ]]; do
  case "$1" in
    --san) SAN="$2"; shift 2 ;;
    --port) PORT="$2"; shift 2 ;;
    *) echo "FAIL unknown_argument:$1" >&2; exit 2 ;;
  esac
done
[[ -n "$SAN" ]] || { echo "FAIL missing --san" >&2; exit 2; }
[[ "$PORT" =~ ^[0-9]+$ ]] && (( PORT >= 1024 )) || { echo "FAIL port_must_be_unprivileged:$PORT" >&2; exit 2; }

STATE_ROOT="${VAN_STATE_ROOT:-$HOME/.local/share/van}"
CONFIG_ROOT="${VAN_CONFIG_ROOT:-$HOME/.config/van}"
GATEWAY_ENV="$CONFIG_ROOT/gateway.env"
VENV_PY="$STATE_ROOT/venv/bin/python"
RUNTIME_BACKEND="$STATE_ROOT/runtime/backend"
MTLS_DIR="$STATE_ROOT/mtls"

for required in "$GATEWAY_ENV" "$VENV_PY" "$RUNTIME_BACKEND/van_gateway/mtls/serve.py"; do
  [[ -e "$required" ]] || { echo "FAIL missing:$required (run install_van_gateway_service.sh first)" >&2; exit 2; }
done

pki() { PYTHONPATH="$RUNTIME_BACKEND" "$VENV_PY" -m van_gateway.mtls.pki "$@"; }

umask 077
mkdir -p "$MTLS_DIR"
chmod 700 "$MTLS_DIR"
if [[ ! -f "$MTLS_DIR/ca.crt" ]]; then
  pki init --dir "$MTLS_DIR"
  echo "PASS van_device_ca_created"
else
  echo "PASS van_device_ca_kept"
fi
if [[ ! -f "$MTLS_DIR/server.crt" || "$(cat "$MTLS_DIR/server.san" 2>/dev/null)" != "$SAN" ]]; then
  pki issue-server --dir "$MTLS_DIR" --san "$SAN"
  printf '%s\n' "$SAN" > "$MTLS_DIR/server.san"
  echo "PASS van_server_certificate_issued san=$SAN"
fi

set_env() {
  local key="$1" value="$2" tmp
  tmp="$(mktemp "$CONFIG_ROOT/gateway.env.XXXXXX")"
  grep -Ev "^${key}=" "$GATEWAY_ENV" > "$tmp" || true
  printf '%s=%s\n' "$key" "$value" >> "$tmp"
  install -m 0600 "$tmp" "$GATEWAY_ENV"
  rm -f "$tmp"
}
set_env VAN_MTLS_ENABLED true
set_env VAN_MTLS_DIR "$MTLS_DIR"
set_env VAN_MTLS_PORT "$PORT"

if command -v ufw >/dev/null && sudo -n ufw status 2>/dev/null | grep -q '^Status: active'; then
  sudo -n ufw allow "$PORT/tcp" comment 'van direct mtls' >/dev/null
  echo "PASS ufw_allows:$PORT/tcp"
fi

systemctl --user daemon-reload
systemctl --user restart van-gateway.service

PROBE_HOST="127.0.0.1"
for _ in {1..30}; do
  if (exec 3<>"/dev/tcp/$PROBE_HOST/$PORT") 2>/dev/null; then break; fi
  sleep 1
done

# What a network client sees, checked with a client that is not the app.
MTLS_DIR="$MTLS_DIR" PORT="$PORT" HOST="$PROBE_HOST" "$VENV_PY" - <<'PROBE'
import json, os, socket, ssl, sys

d, port, host = os.environ["MTLS_DIR"], int(os.environ["PORT"]), os.environ["HOST"]
def ctx(tls12=False):
    c = ssl.create_default_context(cafile=f"{d}/ca.crt")
    c.check_hostname = False  # the SAN is the public name; this probe dials loopback
    if tls12:
        c.maximum_version = ssl.TLSVersion.TLSv1_2
    return c

try:
    with socket.create_connection((host, port), 5) as raw, ctx(True).wrap_socket(raw):
        sys.exit("FAIL tls12_accepted")
except ssl.SSLError:
    print("PASS tls12_refused")

with socket.create_connection((host, port), 5) as raw, ctx().wrap_socket(raw) as tls:
    assert tls.version() == "TLSv1.3", tls.version()
    tls.sendall(f"GET /health HTTP/1.1\r\nHost: {host}\r\nConnection: close\r\n\r\n".encode())
    reply = b""
    while chunk := tls.recv(4096):
        reply += chunk
head, _, body = reply.partition(b"\r\n\r\n")
status = head.split(b" ", 2)[1]
if status != b"403" or json.loads(body)["detail"] != "client_certificate_required":
    sys.exit(f"FAIL no_certificate_not_refused status={status!r}")
print("PASS tls13_only_and_no_certificate_refused")
PROBE

systemctl --user is-active --quiet van-gateway.service
echo "PASS van_direct_mtls_enabled port=$PORT san=$SAN"
echo "VAN_GATEWAY_CA_PEM_B64=$(base64 -w0 "$MTLS_DIR/ca.crt")"
