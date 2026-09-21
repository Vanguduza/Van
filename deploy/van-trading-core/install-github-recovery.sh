#!/usr/bin/env bash
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
[[ "$(hostname)" == "${VAN_TRADING_HOST_ID:-van-trading-core}" ]] || { echo "REFUSE: wrong host" >&2; exit 3; }
sudo install -m 0755 -o root -g root "$HERE/van-github-recovery.sh" /usr/local/bin/van-github-recovery
sudo /usr/local/bin/van-github-recovery probe
echo "VAN_GITHUB_RECOVERY_INSTALL=GREEN"
