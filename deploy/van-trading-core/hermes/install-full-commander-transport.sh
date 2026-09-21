#!/usr/bin/env bash
set -euo pipefail

HOST="${VAN_TRADING_COMMANDER_HOST:-van-trading-core}"
ADMIN_USER="${VAN_TRADING_ADMIN_USER:-ubuntu}"
COMMANDER_USER="${VAN_TRADING_COMMANDER_USER:-vancommander}"
KEY="${VAN_TRADING_COMMANDER_SSH_KEY:-$HOME/.ssh/van-trading-commander}"
PUB="$KEY.pub"

command -v ssh >/dev/null || { echo "ssh is required" >&2; exit 2; }
mkdir -p "$HOME/.ssh"; chmod 700 "$HOME/.ssh"
if [[ ! -f "$KEY" ]]; then
  ssh-keygen -q -t ed25519 -N '' -C 'hermes->van-trading-full-commander' -f "$KEY"
fi
chmod 600 "$KEY"; chmod 644 "$PUB"

# One-time enrollment goes through the existing administrative path. The server-side,
# root-owned helper chooses the forced command and writes only the dedicated
# vancommander account's authorized_keys. Hermes never writes ubuntu's authorized_keys.
cat "$PUB" | ssh -T -o BatchMode=yes -o StrictHostKeyChecking=yes "$ADMIN_USER@$HOST" \
  'sudo -n /usr/local/sbin/van-install-commander-key'

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
chmod 0755 "$SCRIPT_DIR/van-trading-full-commander-stdio.sh"

probe="$(printf '%s\n' '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-06-18","capabilities":{},"clientInfo":{"name":"van-transport-probe","version":"1.0.0"}}}' \
  | VAN_TRADING_COMMANDER_USER="$COMMANDER_USER" timeout 20 "$SCRIPT_DIR/van-trading-full-commander-stdio.sh" 2>/dev/null | head -n 1 || true)"
jq -e '.id==1 and .result' <<<"$probe" >/dev/null || { echo "Restricted Trading Commander transport probe failed" >&2; exit 3; }
echo "VAN_TRADING_COMMANDER_TRANSPORT=GREEN"
echo "remote_user=$COMMANDER_USER"
