#!/usr/bin/env bash
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
COMMANDER_USER="${VAN_DESKTOP_COMMANDER_USER:-vancommander}"
SUDOERS="/etc/sudoers.d/vancommander-recovery"

[[ "$(hostname)" == "${VAN_TRADING_HOST_ID:-van-trading-core}" ]] || { echo "REFUSE: wrong host" >&2; exit 3; }
[[ "$(id -u)" -eq 0 ]] || { echo "REFUSE: run with sudo/root" >&2; exit 4; }
id "$COMMANDER_USER" >/dev/null 2>&1 || { echo "REFUSE: isolated Commander user missing" >&2; exit 5; }
command -v visudo >/dev/null 2>&1 || { echo "REFUSE: visudo missing" >&2; exit 6; }

install -m 0755 -o root -g root "$HERE/van-github-recovery.sh" /usr/local/bin/van-github-recovery

# The isolated full Commander gets exactly one elevation surface. It can invoke the
# enumerated recovery actions, but it cannot run arbitrary sudo, read VATI secrets,
# or become root. Exact command+argument sudoers entries keep the privilege boundary
# independent of model/tool wording.
tmp="$(mktemp)"
cat > "$tmp" <<EOF
$COMMANDER_USER ALL=(root) NOPASSWD: /usr/local/bin/van-github-recovery probe
$COMMANDER_USER ALL=(root) NOPASSWD: /usr/local/bin/van-github-recovery collect_diagnostics
$COMMANDER_USER ALL=(root) NOPASSWD: /usr/local/bin/van-github-recovery restart_trading_services
$COMMANDER_USER ALL=(root) NOPASSWD: /usr/local/bin/van-github-recovery recover_trading_chatgpt_sessions
EOF
chmod 0440 "$tmp"
visudo -cf "$tmp" >/dev/null
install -m 0440 -o root -g root "$tmp" "$SUDOERS"
rm -f "$tmp"
visudo -cf "$SUDOERS" >/dev/null

sudo -n -u "$COMMANDER_USER" sudo -n /usr/local/bin/van-github-recovery probe >/dev/null
if sudo -n -u "$COMMANDER_USER" sudo -n true >/dev/null 2>&1; then
  echo "REFUSE: $COMMANDER_USER has generic sudo authority" >&2
  exit 7
fi

echo "VAN_GITHUB_RECOVERY_INSTALL=GREEN"
echo "commander_user=$COMMANDER_USER"
echo "sudo_surface=BOUNDED_RECOVERY_ONLY"
