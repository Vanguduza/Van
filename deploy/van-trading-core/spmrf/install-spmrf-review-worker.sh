#!/usr/bin/env bash
set -euo pipefail

EXPECTED_HOST="${VAN_TRADING_HOST_ID:-van-trading-core}"
REVIEW_USER="${VAN_SPMRF_REVIEW_USER:-vanreviewer}"
REVIEW_HOME="${VAN_SPMRF_REVIEW_HOME:-/var/lib/van-reviewer}"
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PREFIX="$REVIEW_HOME/.local/share/van/spmrf/codex"
BIN_DIR="$REVIEW_HOME/.local/bin"
WORKER="$BIN_DIR/van-spmrf-review-worker"
PIN_VERSION="0.153.1"
PIN_INTEGRITY="sha512-d5txIVzNIkZnAmCiqxksAACqm+xUvq83YGKd3YYAF9ISXWkC7hsiPXpSD24ypKOqpvbZiScMSq0e0p4TycczNw=="

fail(){ echo "ERROR: $*" >&2; exit 1; }
[[ "$(hostname)" == "$EXPECTED_HOST" ]] || fail "must run on $EXPECTED_HOST"
[[ "$(id -u)" -eq 0 ]] || fail "run with sudo/root"
command -v npm >/dev/null 2>&1 || fail "npm is required"
command -v jq >/dev/null 2>&1 || fail "jq is required"

# The independent model reviewer is intentionally not the VM administrator. It has
# no sudo/docker/vati group membership and therefore cannot turn a read-only model
# session into access to broker/VATI secrets by invoking the administrator's sudo.
if ! id "$REVIEW_USER" >/dev/null 2>&1; then
  useradd --system --create-home --home-dir "$REVIEW_HOME" --shell /bin/bash "$REVIEW_USER"
fi
[[ "$(getent passwd "$REVIEW_USER" | cut -d: -f6)" == "$REVIEW_HOME" ]] || fail "$REVIEW_USER home must be $REVIEW_HOME"
for forbidden in sudo docker vati; do
  if id -nG "$REVIEW_USER" | tr ' ' '\n' | grep -Fxq "$forbidden"; then
    fail "$REVIEW_USER must not belong to privileged group $forbidden"
  fi
done
passwd -l "$REVIEW_USER" >/dev/null 2>&1 || true

observed_integrity="$(npm view "@openai/codex@$PIN_VERSION" dist.integrity --json | jq -r '.')"
[[ "$observed_integrity" == "$PIN_INTEGRITY" ]] || fail "Codex registry integrity mismatch for $PIN_VERSION"

install -d -m 0755 -o "$REVIEW_USER" -g "$REVIEW_USER" "$PREFIX" "$BIN_DIR" "$REVIEW_HOME/.cache/van-spmrf"
cat > "$PREFIX/package.json" <<JSON
{"private":true,"dependencies":{"@openai/codex":"$PIN_VERSION"}}
JSON
chown "$REVIEW_USER:$REVIEW_USER" "$PREFIX/package.json"
sudo -u "$REVIEW_USER" npm --prefix "$PREFIX" install --ignore-scripts --no-fund --no-audit --package-lock-only
sudo -u "$REVIEW_USER" npm --prefix "$PREFIX" ci --ignore-scripts --no-fund --no-audit

actual="$(node -e 'process.stdout.write(require(process.argv[1]).version)' "$PREFIX/node_modules/@openai/codex/package.json")"
[[ "$actual" == "$PIN_VERSION" ]] || fail "installed Codex version mismatch: $actual"

install -m 0755 -o "$REVIEW_USER" -g "$REVIEW_USER" "$HERE/van-spmrf-review-worker.mjs" "$REVIEW_HOME/.local/share/van/spmrf/van-spmrf-review-worker.mjs"
cat > "$WORKER" <<WRAP
#!/usr/bin/env bash
set -euo pipefail
unset OPENAI_API_KEY CODEX_API_KEY
export VAN_SPMRF_CODEX_BIN="$PREFIX/node_modules/.bin/codex"
exec node "$REVIEW_HOME/.local/share/van/spmrf/van-spmrf-review-worker.mjs" "\$@"
WRAP
chown "$REVIEW_USER:$REVIEW_USER" "$WORKER"
chmod 0755 "$WORKER"

status="$(sudo -u "$REVIEW_USER" env HOME="$REVIEW_HOME" "$PREFIX/node_modules/.bin/codex" login status 2>&1 || true)"
if grep -q 'Logged in using ChatGPT' <<<"$status"; then
  echo "VAN_SPMRF_CHATGPT_AUTH=GREEN"
else
  echo "VAN_SPMRF_CHATGPT_AUTH=PAIRING_REQUIRED"
  echo "Run once as the isolated reviewer: sudo -u $REVIEW_USER -H $PREFIX/node_modules/.bin/codex login"
fi
echo "VAN_SPMRF_REVIEW_WORKER=INSTALLED"
echo "worker=$WORKER"
echo "review_user=$REVIEW_USER"
echo "codex_version=$actual"
