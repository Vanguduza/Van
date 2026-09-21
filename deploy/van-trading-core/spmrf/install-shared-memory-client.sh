#!/usr/bin/env bash
set -euo pipefail

EXPECTED_HOST="${VAN_TRADING_HOST_ID:-van-trading-core}"
ADMIN_USER="${VAN_TRADING_ADMIN_USER:-ubuntu}"
HOME_DIR="$(getent passwd "$ADMIN_USER" | cut -d: -f6)"
HERMES_HOST="${DIAL_HERMES_CONTROL_HOST:-dial-hermes-control}"
HERMES_USER="${DIAL_HERMES_CONTROL_USER:-ubuntu}"
SSH_DIR="$HOME_DIR/.ssh"
BIN_DIR="$HOME_DIR/.local/bin"
CODEX_BIN="${VAN_SPMRF_CODEX_BIN:-$HOME_DIR/.local/share/van/spmrf/codex/node_modules/.bin/codex}"

fail(){ echo "ERROR: $*" >&2; exit 1; }
[[ "$(hostname)" == "$EXPECTED_HOST" ]] || fail "must run on $EXPECTED_HOST"
[[ "$(id -u)" -eq 0 ]] || fail "run with sudo/root"

install -d -m 0700 -o "$ADMIN_USER" -g "$ADMIN_USER" "$SSH_DIR"
install -d -m 0755 -o "$ADMIN_USER" -g "$ADMIN_USER" "$BIN_DIR"

for harness in chatgpt claude; do
  key="$SSH_DIR/van-spmrf-$harness"
  if [[ ! -f "$key" ]]; then
    sudo -u "$ADMIN_USER" ssh-keygen -q -t ed25519 -N '' -C "van-spmrf-$harness" -f "$key"
  fi
  chmod 600 "$key"; chmod 644 "$key.pub"
  chown "$ADMIN_USER:$ADMIN_USER" "$key" "$key.pub"

  wrapper="$BIN_DIR/dial-shared-memory-$harness-stdio"
  cat > "$wrapper" <<WRAP
#!/usr/bin/env bash
set -euo pipefail
exec ssh -T \
  -o BatchMode=yes \
  -o IdentitiesOnly=yes \
  -o StrictHostKeyChecking=yes \
  -o UserKnownHostsFile="$SSH_DIR/known_hosts" \
  -o ConnectTimeout=10 \
  -i "$key" \
  "$HERMES_USER@$HERMES_HOST"
WRAP
  chmod 0755 "$wrapper"; chown "$ADMIN_USER:$ADMIN_USER" "$wrapper"
done

if [[ -x "$CODEX_BIN" ]]; then
  sudo -u "$ADMIN_USER" env HOME="$HOME_DIR" "$CODEX_BIN" mcp remove dial-shared-project-memory >/dev/null 2>&1 || true
  sudo -u "$ADMIN_USER" env HOME="$HOME_DIR" "$CODEX_BIN" mcp add dial-shared-project-memory     -- "$BIN_DIR/dial-shared-memory-chatgpt-stdio" >/dev/null
fi

if command -v claude >/dev/null 2>&1; then
  sudo -u "$ADMIN_USER" env HOME="$HOME_DIR" claude mcp remove --scope user dial-shared-project-memory >/dev/null 2>&1 || true
  sudo -u "$ADMIN_USER" env HOME="$HOME_DIR" claude mcp add --scope user dial-shared-project-memory     -- "$BIN_DIR/dial-shared-memory-claude-stdio" >/dev/null
fi

if sudo -u "$ADMIN_USER" ssh-keygen -F "$HERMES_HOST" -f "$SSH_DIR/known_hosts" >/dev/null 2>&1; then
  echo "SPMRF_HERMES_HOST_KEY=READY"
else
  echo "SPMRF_HERMES_HOST_KEY=PENDING"
  echo "Seed $HERMES_HOST into $SSH_DIR/known_hosts from trusted Oracle host-key evidence before first use."
fi

echo "SPMRF_TRADING_MEMORY_CLIENT=INSTALLED"
echo "chatgpt_public_key=$SSH_DIR/van-spmrf-chatgpt.pub"
echo "claude_public_key=$SSH_DIR/van-spmrf-claude.pub"
