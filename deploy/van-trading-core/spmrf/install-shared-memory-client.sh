#!/usr/bin/env bash
set -euo pipefail

EXPECTED_HOST="${VAN_TRADING_HOST_ID:-van-trading-core}"
REVIEW_USER="${VAN_SPMRF_REVIEW_USER:-vanreviewer}"
HOME_DIR="${VAN_SPMRF_REVIEW_HOME:-/var/lib/van-reviewer}"
HERMES_HOST="${DIAL_HERMES_CONTROL_HOST:-dial-hermes-control}"
HERMES_USER="${DIAL_HERMES_CONTROL_USER:-ubuntu}"
SSH_DIR="$HOME_DIR/.ssh"
BIN_DIR="$HOME_DIR/.local/bin"
CODEX_BIN="${VAN_SPMRF_CODEX_BIN:-$HOME_DIR/.local/share/van/spmrf/codex/node_modules/.bin/codex}"

fail(){ echo "ERROR: $*" >&2; exit 1; }
[[ "$(hostname)" == "$EXPECTED_HOST" ]] || fail "must run on $EXPECTED_HOST"
[[ "$(id -u)" -eq 0 ]] || fail "run with sudo/root"
id "$REVIEW_USER" >/dev/null 2>&1 || fail "$REVIEW_USER must be created by install-spmrf-review-worker.sh first"
[[ "$(getent passwd "$REVIEW_USER" | cut -d: -f6)" == "$HOME_DIR" ]] || fail "$REVIEW_USER home must be $HOME_DIR"
for forbidden in sudo docker vati; do
  id -nG "$REVIEW_USER" | tr ' ' '\n' | grep -Fxq "$forbidden" && fail "$REVIEW_USER must not belong to privileged group $forbidden"
done

install -d -m 0700 -o "$REVIEW_USER" -g "$REVIEW_USER" "$SSH_DIR"
install -d -m 0755 -o "$REVIEW_USER" -g "$REVIEW_USER" "$BIN_DIR"

for harness in chatgpt claude; do
  key="$SSH_DIR/van-spmrf-$harness"
  if [[ ! -f "$key" ]]; then
    sudo -u "$REVIEW_USER" ssh-keygen -q -t ed25519 -N '' -C "van-spmrf-$harness" -f "$key"
  fi
  chmod 600 "$key"; chmod 644 "$key.pub"
  chown "$REVIEW_USER:$REVIEW_USER" "$key" "$key.pub"

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
  chmod 0755 "$wrapper"; chown "$REVIEW_USER:$REVIEW_USER" "$wrapper"
done

if [[ -x "$CODEX_BIN" ]]; then
  sudo -u "$REVIEW_USER" env HOME="$HOME_DIR" "$CODEX_BIN" mcp remove dial-shared-project-memory >/dev/null 2>&1 || true
  sudo -u "$REVIEW_USER" env HOME="$HOME_DIR" "$CODEX_BIN" mcp add dial-shared-project-memory     -- "$BIN_DIR/dial-shared-memory-chatgpt-stdio" >/dev/null
fi

if command -v claude >/dev/null 2>&1; then
  sudo -u "$REVIEW_USER" env HOME="$HOME_DIR" claude mcp remove --scope user dial-shared-project-memory >/dev/null 2>&1 || true
  sudo -u "$REVIEW_USER" env HOME="$HOME_DIR" claude mcp add --scope user dial-shared-project-memory     -- "$BIN_DIR/dial-shared-memory-claude-stdio" >/dev/null
fi

if sudo -u "$REVIEW_USER" ssh-keygen -F "$HERMES_HOST" -f "$SSH_DIR/known_hosts" >/dev/null 2>&1; then
  echo "SPMRF_HERMES_HOST_KEY=READY"
else
  echo "SPMRF_HERMES_HOST_KEY=PENDING"
  echo "Seed $HERMES_HOST into $SSH_DIR/known_hosts from trusted Oracle host-key evidence before first use."
fi

echo "SPMRF_TRADING_MEMORY_CLIENT=INSTALLED"
echo "chatgpt_public_key=$SSH_DIR/van-spmrf-chatgpt.pub"
echo "claude_public_key=$SSH_DIR/van-spmrf-claude.pub"
