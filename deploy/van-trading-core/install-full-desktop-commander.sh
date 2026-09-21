#!/usr/bin/env bash
set -euo pipefail

EXPECTED_HOST="${VAN_TRADING_HOST_ID:-van-trading-core}"
ADMIN_USER="${VAN_TRADING_ADMIN_USER:-ubuntu}"
HOME_DIR="$(getent passwd "$ADMIN_USER" | cut -d: -f6)"
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SPEC="$HERE/desktop-commander-runtime"
PREFIX="${VAN_DESKTOP_COMMANDER_PREFIX:-$HOME_DIR/.local/share/van/desktop-commander}"
BIN_DIR="$HOME_DIR/.local/bin"
WRAPPER="$BIN_DIR/van-local-commander-mcp"

fail(){ echo "ERROR: $*" >&2; exit 1; }

[[ "$(hostname)" == "$EXPECTED_HOST" ]] || fail "must run on $EXPECTED_HOST; got $(hostname)"
[[ "$(id -u)" -eq 0 ]] || fail "run with sudo/root"
command -v npm >/dev/null 2>&1 || fail "npm is required"
command -v node >/dev/null 2>&1 || fail "node is required"
[[ -f "$SPEC/package.json" && -f "$SPEC/package-lock.json" ]] || fail "pinned Desktop Commander lock files are missing"

locked_version="$(node -e 'const p=require(process.argv[1]);process.stdout.write(p.packages["node_modules/@wonderwhy-er/desktop-commander"]?.version||"")' "$SPEC/package-lock.json")"
[[ "$locked_version" == "0.2.50" ]] || fail "expected Desktop Commander 0.2.50; got $locked_version"

install -d -m 0755 -o "$ADMIN_USER" -g "$ADMIN_USER" "$PREFIX" "$BIN_DIR"
install -m 0644 -o "$ADMIN_USER" -g "$ADMIN_USER" "$SPEC/package.json" "$PREFIX/package.json"
install -m 0644 -o "$ADMIN_USER" -g "$ADMIN_USER" "$SPEC/package-lock.json" "$PREFIX/package-lock.json"
lock_hash="$(sha256sum "$SPEC/package-lock.json" | awk '{print $1}')"
marker="$PREFIX/.package-lock.sha256"

if [[ ! -x "$PREFIX/node_modules/.bin/desktop-commander" || ! -f "$marker" || "$(cat "$marker" 2>/dev/null || true)" != "$lock_hash" ]]; then
  sudo -u "$ADMIN_USER" npm --prefix "$PREFIX" ci --ignore-scripts --no-fund --no-audit
  printf '%s' "$lock_hash" > "$marker"
  chown "$ADMIN_USER:$ADMIN_USER" "$marker"
  chmod 0644 "$marker"
fi

cat > "$WRAPPER" <<WRAP
#!/usr/bin/env bash
set -euo pipefail
exec "$PREFIX/node_modules/.bin/desktop-commander" "\$@"
WRAP
chown "$ADMIN_USER:$ADMIN_USER" "$WRAPPER"
chmod 0755 "$WRAPPER"

echo "VAN_FULL_DESKTOP_COMMANDER=GREEN"
echo "host=$EXPECTED_HOST"
echo "version=$locked_version"
echo "wrapper=$WRAPPER"
