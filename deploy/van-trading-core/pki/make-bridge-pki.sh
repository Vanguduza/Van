#!/usr/bin/env bash
# Private PKI for the two TLS seams of the trading estate:
#   1. commander.crt/key  — the commander service on van-trading-core (10.0.1.233:9133), CA-pinned by Hermes' shim
#   2. mt5-worker.crt/key — the Windows MT5 bridge worker, CA-pinned by vati-core; vati-core presents client.crt (mTLS)
# Output goes to $OUT (default /opt/van-trading/secrets/pki), mode 0600, owned by the caller. Idempotent.
set -euo pipefail
OUT="${OUT:-/opt/van-trading/secrets/pki}"
CORE_IP="${CORE_IP:-10.0.1.233}"
WORKER_HOST="${WORKER_HOST:-mt5-worker}"
WORKER_IP="${WORKER_IP:-}"
DAYS="${DAYS:-825}"
mkdir -p "$OUT"; chmod 700 "$OUT"; cd "$OUT"
umask 077
if [[ ! -f ca.key ]]; then
  openssl req -x509 -newkey rsa:4096 -nodes -keyout ca.key -out ca.crt -days 3650 -subj "/CN=van-trading-bridge-ca" -addext "basicConstraints=critical,CA:TRUE" -addext "keyUsage=critical,keyCertSign,cRLSign"
fi
issue() { # name, subject CN, SAN list
  local name="$1" cn="$2" san="$3"
  [[ -f "$name.crt" ]] && return 0
  openssl req -newkey rsa:2048 -nodes -keyout "$name.key" -out "$name.csr" -subj "/CN=$cn"
  printf 'subjectAltName=%s\nextendedKeyUsage=serverAuth,clientAuth\nbasicConstraints=CA:FALSE\n' "$san" > "$name.ext"
  openssl x509 -req -in "$name.csr" -CA ca.crt -CAkey ca.key -CAcreateserial -out "$name.crt" -days "$DAYS" -extfile "$name.ext"
  rm -f "$name.csr" "$name.ext"
}
issue commander "van-trading-core" "IP:${CORE_IP},DNS:van-trading-core,IP:127.0.0.1"
issue mt5-worker "$WORKER_HOST" "DNS:${WORKER_HOST}${WORKER_IP:+,IP:$WORKER_IP}"
issue client "vati-core-client" "DNS:vati-core-client"
chmod 600 ./*.key ./*.crt
echo "PKI ready in $OUT: ca.crt (pin on both sides), commander.{crt,key}, mt5-worker.{crt,key} (copy to the Windows worker), client.{crt,key} (vati-core → worker mTLS)"
