#!/usr/bin/env bash
set -euo pipefail

HOST="${VAN_TRADING_COMMANDER_HOST:-van-trading-core}"
USER_NAME="${VAN_TRADING_COMMANDER_USER:-ubuntu}"
KEY="${VAN_TRADING_COMMANDER_SSH_KEY:-$HOME/.ssh/van-trading-commander}"
REMOTE_WRAPPER="/home/$USER_NAME/.local/bin/van-local-commander-mcp"
PUB="$KEY.pub"

command -v ssh >/dev/null || { echo "ssh is required" >&2; exit 2; }
mkdir -p "$HOME/.ssh"; chmod 700 "$HOME/.ssh"
if [[ ! -f "$KEY" ]]; then
  ssh-keygen -q -t ed25519 -N '' -C 'hermes->van-trading-full-commander' -f "$KEY"
fi
chmod 600 "$KEY"; chmod 644 "$PUB"

# This one-time bootstrap uses an already-authorized administrative SSH path.
# The new key is forced to the Commander stdio binary and cannot obtain a shell.
PUBKEY="$(cat "$PUB")"
REMOTE_LINE="restrict,command=\"$REMOTE_WRAPPER\" $PUBKEY"
printf '%s\n' "$REMOTE_LINE" | ssh -T   -o BatchMode=yes -o StrictHostKeyChecking=yes   "$USER_NAME@$HOST"   'umask 077; mkdir -p ~/.ssh; touch ~/.ssh/authorized_keys; line=$(cat); grep -Fqx "$line" ~/.ssh/authorized_keys || printf "%s\n" "$line" >> ~/.ssh/authorized_keys'

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
chmod 0755 "$SCRIPT_DIR/van-trading-full-commander-stdio.sh"

# Prove the restricted key starts an MCP process: initialize must answer with JSON.
probe="$(printf '%s\n' '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-06-18","capabilities":{},"clientInfo":{"name":"van-transport-probe","version":"1.0.0"}}}'   | timeout 20 "$SCRIPT_DIR/van-trading-full-commander-stdio.sh" 2>/dev/null | head -n 1 || true)"
jq -e '.id==1 and .result' <<<"$probe" >/dev/null || { echo "Restricted Trading Commander transport probe failed" >&2; exit 3; }
echo "VAN_TRADING_COMMANDER_TRANSPORT=GREEN"
