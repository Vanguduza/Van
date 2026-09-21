#!/usr/bin/env bash
set -euo pipefail

EXPECTED_HOST="${VAN_TRADING_HOST_ID:-van-trading-core}"
SERVICE_USER="${VAN_DESKTOP_COMMANDER_USER:-vancommander}"
HOME_DIR="${VAN_DESKTOP_COMMANDER_HOME:-/var/lib/van-commander}"
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$HERE/../.." && pwd)"
SPEC="$HERE/desktop-commander-runtime"
PREFIX="${VAN_DESKTOP_COMMANDER_PREFIX:-$HOME_DIR/.local/share/van/desktop-commander}"
BIN_DIR="$HOME_DIR/.local/bin"
WRAPPER="$BIN_DIR/van-local-commander-mcp"
WORKSPACE="${VAN_DESKTOP_COMMANDER_WORKSPACE:-$HOME_DIR/work/Van}"
KEY_INSTALLER="/usr/local/sbin/van-install-commander-key"

fail(){ echo "ERROR: $*" >&2; exit 1; }

[[ "$(hostname)" == "$EXPECTED_HOST" ]] || fail "must run on $EXPECTED_HOST; got $(hostname)"
[[ "$(id -u)" -eq 0 ]] || fail "run with sudo/root"
command -v npm >/dev/null 2>&1 || fail "npm is required"
command -v node >/dev/null 2>&1 || fail "node is required"
command -v git >/dev/null 2>&1 || fail "git is required"
[[ -f "$SPEC/package.json" && -f "$SPEC/package-lock.json" ]] || fail "pinned Desktop Commander lock files are missing"

locked_version="$(node -e 'const p=require(process.argv[1]);process.stdout.write(p.packages["node_modules/@wonderwhy-er/desktop-commander"]?.version||"")' "$SPEC/package-lock.json")"
[[ "$locked_version" == "0.2.50" ]] || fail "expected Desktop Commander 0.2.50; got $locked_version"

# P0 isolation: the full machine/session actuator does not run as ubuntu or vati.
# It has no sudo/docker/vati group membership and cannot read /opt/van-trading/secrets.
if ! id "$SERVICE_USER" >/dev/null 2>&1; then
  useradd --system --create-home --home-dir "$HOME_DIR" --shell /bin/bash "$SERVICE_USER"
fi
[[ "$(getent passwd "$SERVICE_USER" | cut -d: -f6)" == "$HOME_DIR" ]] || fail "$SERVICE_USER home must be $HOME_DIR"
for forbidden in sudo docker vati; do
  if id -nG "$SERVICE_USER" | tr ' ' '\n' | grep -Fxq "$forbidden"; then
    fail "$SERVICE_USER must not belong to privileged group $forbidden"
  fi
done
passwd -l "$SERVICE_USER" >/dev/null 2>&1 || true

install -d -m 0750 -o "$SERVICE_USER" -g "$SERVICE_USER" "$HOME_DIR" "$PREFIX" "$BIN_DIR" "$HOME_DIR/work"
install -m 0644 -o "$SERVICE_USER" -g "$SERVICE_USER" "$SPEC/package.json" "$PREFIX/package.json"
install -m 0644 -o "$SERVICE_USER" -g "$SERVICE_USER" "$SPEC/package-lock.json" "$PREFIX/package-lock.json"
lock_hash="$(sha256sum "$SPEC/package-lock.json" | awk '{print $1}')"
marker="$PREFIX/.package-lock.sha256"

if [[ ! -x "$PREFIX/node_modules/.bin/desktop-commander" || ! -f "$marker" || "$(cat "$marker" 2>/dev/null || true)" != "$lock_hash" ]]; then
  sudo -H -u "$SERVICE_USER" npm --prefix "$PREFIX" ci --ignore-scripts --no-fund --no-audit
  printf '%s' "$lock_hash" > "$marker"
  chown "$SERVICE_USER:$SERVICE_USER" "$marker"
  chmod 0644 "$marker"
fi

# Isolated working copy. The actuator may edit/review this workspace, but the live
# /opt/van-trading tree and its 0700 secret directory are not its authority surface.
if [[ ! -d "$WORKSPACE/.git" ]]; then
  origin="$(git -C "$REPO_ROOT" config --get remote.origin.url || true)"
  [[ -n "$origin" ]] || origin="https://github.com/Vanguduza/Van.git"
  sudo -H -u "$SERVICE_USER" git clone --quiet "$origin" "$WORKSPACE"
fi

cat > "$WRAPPER" <<WRAP
#!/usr/bin/env bash
set -euo pipefail
export HOME="$HOME_DIR"
cd "$WORKSPACE"
exec "$PREFIX/node_modules/.bin/desktop-commander" "\$@"
WRAP
chown "$SERVICE_USER:$SERVICE_USER" "$WRAPPER"
chmod 0755 "$WRAPPER"

# Root-owned key enrollment helper. The Hermes bootstrap can submit only a public
# key; the server chooses the forced command and target account.
cat > "$KEY_INSTALLER" <<'KEYHELPER'
#!/usr/bin/env bash
set -euo pipefail
USER_NAME="${VAN_DESKTOP_COMMANDER_USER:-vancommander}"
HOME_DIR="${VAN_DESKTOP_COMMANDER_HOME:-/var/lib/van-commander}"
WRAPPER="$HOME_DIR/.local/bin/van-local-commander-mcp"
read -r pubkey
case "$pubkey" in
  ssh-ed25519\ *|ssh-rsa\ *) ;;
  *) echo "REFUSE: expected one SSH public key" >&2; exit 2 ;;
esac
[[ -x "$WRAPPER" ]] || { echo "REFUSE: Commander wrapper missing" >&2; exit 3; }
install -d -m 0700 -o "$USER_NAME" -g "$USER_NAME" "$HOME_DIR/.ssh"
touch "$HOME_DIR/.ssh/authorized_keys"
chown "$USER_NAME:$USER_NAME" "$HOME_DIR/.ssh/authorized_keys"
chmod 0600 "$HOME_DIR/.ssh/authorized_keys"
line="restrict,command=\"$WRAPPER\" $pubkey"
grep -Fqx "$line" "$HOME_DIR/.ssh/authorized_keys" || printf '%s\n' "$line" >> "$HOME_DIR/.ssh/authorized_keys"
KEYHELPER
chown root:root "$KEY_INSTALLER"
chmod 0755 "$KEY_INSTALLER"

# The security property is tested here too, not only documented.
if sudo -u "$SERVICE_USER" test -r /opt/van-trading/secrets/commander.token; then
  fail "$SERVICE_USER can read VATI Commander secrets"
fi

echo "VAN_FULL_DESKTOP_COMMANDER=GREEN"
echo "host=$EXPECTED_HOST"
echo "user=$SERVICE_USER"
echo "version=$locked_version"
echo "wrapper=$WRAPPER"
echo "workspace=$WORKSPACE"
