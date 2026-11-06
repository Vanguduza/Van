#!/usr/bin/env bash
set -euo pipefail
OUT=/var/lib/van-muse-sandbox/qualification-latest.json

fail_closed() {
  local rc="$1"
  logger -t van-muse-sandbox "FAIL_CLOSED sandbox qualification failed rc=$rc"
  systemctl --no-block stop van-muse-cdp-bridge.service van-muse-sandbox.service van-muse-sandbox-proxy.service >/dev/null 2>&1 || true
  exit "$rc"
}

/usr/local/bin/qualify-muse-sandbox >"$OUT" || fail_closed $?
jq -e '.status=="GREEN" and .required_failures==0' "$OUT" >/dev/null || fail_closed 90
