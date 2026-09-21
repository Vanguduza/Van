#!/usr/bin/env bash
set -euo pipefail

HOST="${VAN_TRADING_COMMANDER_HOST:-van-trading-core}"
USER_NAME="${VAN_TRADING_COMMANDER_USER:-ubuntu}"
KEY="${VAN_TRADING_COMMANDER_SSH_KEY:-$HOME/.ssh/van-trading-commander}"
KNOWN_HOSTS="${VAN_TRADING_COMMANDER_KNOWN_HOSTS:-$HOME/.ssh/known_hosts}"

[[ -r "$KEY" ]] || { echo "Trading Commander SSH key missing: $KEY" >&2; exit 2; }
[[ -r "$KNOWN_HOSTS" ]] || { echo "known_hosts missing: $KNOWN_HOSTS" >&2; exit 2; }

exec ssh -T   -o BatchMode=yes   -o IdentitiesOnly=yes   -o StrictHostKeyChecking=yes   -o UserKnownHostsFile="$KNOWN_HOSTS"   -o ConnectTimeout=10   -i "$KEY"   "$USER_NAME@$HOST"
