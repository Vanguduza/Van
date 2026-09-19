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
# P2-SEC-008 — `issue` used to return early whenever the certificate file existed, so an
# 825-day certificate was minted once and never looked at again. A private PKI with no
# renewal path expires silently and takes the trading estate's two TLS seams with it.
# RENEW_WITHIN_DAYS is how far ahead a re-issue happens; --check reports without changing
# anything, so a monitor can ask.
RENEW_WITHIN_DAYS="${RENEW_WITHIN_DAYS:-60}"
CHECK_ONLY=0
[[ "${1:-}" == "--check" ]] && CHECK_ONLY=1
mkdir -p "$OUT"; chmod 700 "$OUT"; cd "$OUT"
umask 077
if [[ ! -f ca.key ]]; then
  if (( CHECK_ONLY )); then echo "MISSING ca"; else
  openssl req -x509 -newkey rsa:4096 -nodes -keyout ca.key -out ca.crt -days 3650 -subj "/CN=van-trading-bridge-ca" -addext "basicConstraints=critical,CA:TRUE" -addext "keyUsage=critical,keyCertSign,cRLSign"
  fi
fi

expires_within() { # cert, days — true when the certificate expires inside that window
  local cert="$1" days="$2"
  [[ -f "$cert" ]] || return 0
  ! openssl x509 -in "$cert" -noout -checkend $(( days * 86400 )) >/dev/null 2>&1
}

renewal_report() {
  local name rc=0
  for name in ca commander mt5-worker client; do
    if [[ ! -f "$name.crt" ]]; then
      echo "MISSING $name"; rc=1; continue
    fi
    local until; until=$(openssl x509 -in "$name.crt" -noout -enddate | cut -d= -f2)
    if expires_within "$name.crt" "$RENEW_WITHIN_DAYS"; then
      echo "RENEW $name (expires $until)"; rc=1
    else
      echo "OK $name (expires $until)"
    fi
  done
  return $rc
}

if (( CHECK_ONLY )); then
  renewal_report
  exit $?
fi

issue() { # name, subject CN, SAN list
  local name="$1" cn="$2" san="$3"
  # Re-issue when the certificate is missing OR inside the renewal window. Returning
  # early on mere existence is what made this script a one-shot.
  if [[ -f "$name.crt" ]] && ! expires_within "$name.crt" "$RENEW_WITHIN_DAYS"; then
    return 0
  fi
  [[ -f "$name.crt" ]] && echo "renewing $name (inside ${RENEW_WITHIN_DAYS}-day window)"
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
renewal_report || true
echo "Run '$0 --check' from a monitor; it exits non-zero when anything is missing or inside the ${RENEW_WITHIN_DAYS}-day renewal window."
