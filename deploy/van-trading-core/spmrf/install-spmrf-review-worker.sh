#!/usr/bin/env bash
set -euo pipefail

EXPECTED_HOST="${VAN_TRADING_HOST_ID:-van-trading-core}"
ADMIN_USER="${VAN_TRADING_ADMIN_USER:-ubuntu}"
ADMIN_HOME="$(getent passwd "$ADMIN_USER" | cut -d: -f6)"
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PREFIX="$ADMIN_HOME/.local/share/van/spmrf/codex"
BIN_DIR="$ADMIN_HOME/.local/bin"
WORKER="$BIN_DIR/van-spmrf-review-worker"
PIN_VERSION="0.153.1"
PIN_INTEGRITY="sha512-d5txIVzNIkZnAmCiqxksAACqm+xUvq83YGKd3YYAF9ISXWkC7hsiPXpSD24ypKOqpvbZiScMSq0e0p4TycczNw=="

fail(){ echo "ERROR: $*" >&2; exit 1; }
[[ "$(hostname)" == "$EXPECTED_HOST" ]] || fail "must run on $EXPECTED_HOST"
[[ "$(id -u)" -eq 0 ]] || fail "run with sudo/root"
command -v npm >/dev/null 2>&1 || fail "npm is required"
command -v jq >/dev/null 2>&1 || fail "jq is required"

observed_integrity="$(npm view "@openai/codex@$PIN_VERSION" dist.integrity --json | jq -r '.')"
[[ "$observed_integrity" == "$PIN_INTEGRITY" ]] || fail "Codex registry integrity mismatch for $PIN_VERSION"

install -d -m 0755 -o "$ADMIN_USER" -g "$ADMIN_USER" "$PREFIX" "$BIN_DIR" "$ADMIN_HOME/.cache/van-spmrf"
cat > "$PREFIX/package.json" <<JSON
{"private":true,"dependencies":{"@openai/codex":"$PIN_VERSION"}}
JSON
chown "$ADMIN_USER:$ADMIN_USER" "$PREFIX/package.json"
sudo -u "$ADMIN_USER" npm --prefix "$PREFIX" install --ignore-scripts --no-fund --no-audit --package-lock-only
sudo -u "$ADMIN_USER" npm --prefix "$PREFIX" ci --ignore-scripts --no-fund --no-audit

actual="$(node -e 'process.stdout.write(require(process.argv[1]).version)' "$PREFIX/node_modules/@openai/codex/package.json")"
[[ "$actual" == "$PIN_VERSION" ]] || fail "installed Codex version mismatch: $actual"

install -m 0755 -o "$ADMIN_USER" -g "$ADMIN_USER" "$HERE/van-spmrf-review-worker.mjs" "$ADMIN_HOME/.local/share/van/spmrf/van-spmrf-review-worker.mjs"
cat > "$WORKER" <<WRAP
#!/usr/bin/env bash
set -euo pipefail
unset OPENAI_API_KEY CODEX_API_KEY
export VAN_SPMRF_CODEX_BIN="$PREFIX/node_modules/.bin/codex"
exec node "$ADMIN_HOME/.local/share/van/spmrf/van-spmrf-review-worker.mjs" "\$@"
WRAP
chown "$ADMIN_USER:$ADMIN_USER" "$WORKER"
chmod 0755 "$WORKER"

status="$(sudo -u "$ADMIN_USER" env HOME="$ADMIN_HOME" "$PREFIX/node_modules/.bin/codex" login status 2>&1 || true)"
if grep -q 'Logged in using ChatGPT' <<<"$status"; then
  echo "VAN_SPMRF_CHATGPT_AUTH=GREEN"
else
  echo "VAN_SPMRF_CHATGPT_AUTH=PAIRING_REQUIRED"
  echo "Run once as ubuntu: $PREFIX/node_modules/.bin/codex login"
fi
echo "VAN_SPMRF_REVIEW_WORKER=INSTALLED"
echo "worker=$WORKER"
echo "codex_version=$actual"
