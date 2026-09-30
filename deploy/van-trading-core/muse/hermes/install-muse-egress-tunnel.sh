#!/usr/bin/env bash
set -euo pipefail
TRADING_HOST="${VAN_TRADING_HOST:-van-trading-core}"
LOCAL_PORT="${VAN_MUSE_LOCAL_PORT:-17891}"
REMOTE_PORT="${VAN_MUSE_REMOTE_PORT:-17890}"
BASE="$HOME/.config/van"
UNIT_DIR="$HOME/.config/systemd/user"
mkdir -p "$BASE" "$UNIT_DIR"
chmod 0700 "$BASE"

ssh -o BatchMode=yes -o ConnectTimeout=10 "$TRADING_HOST" 'sudo -n true' >/dev/null
identity="$(ssh -o BatchMode=yes "$TRADING_HOST"   "sudo -n awk -F= '/^MUSE_EXPECTED_EGRESS_IP=|^MUSE_EXPECTED_COUNTRY=/ {print}' /etc/van-muse-egress.env")"
grep -q '^MUSE_EXPECTED_EGRESS_IP=' <<<"$identity"
grep -Eq '^MUSE_EXPECTED_COUNTRY=(US|CA)$' <<<"$identity"
printf '%s\n' "$identity" >"$BASE/muse-egress.env"
chmod 0600 "$BASE/muse-egress.env"

cat >"$UNIT_DIR/van-muse-egress-tunnel.service" <<UNIT
[Unit]
Description=Hermes persistent tunnel to VAN Muse hardened egress
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
ExecStart=/usr/bin/ssh -NT -o BatchMode=yes -o ExitOnForwardFailure=yes -o ServerAliveInterval=30 -o ServerAliveCountMax=3 -L 127.0.0.1:$LOCAL_PORT:127.0.0.1:$REMOTE_PORT $TRADING_HOST
Restart=always
RestartSec=3
NoNewPrivileges=yes
PrivateTmp=yes
ProtectSystem=strict
ProtectHome=read-only

[Install]
WantedBy=default.target
UNIT

install -d -m 0755 "$HOME/.local/bin"
cat >"$HOME/.local/bin/van-muse-egress-check" <<'CHECK'
#!/usr/bin/env bash
set -euo pipefail
# shellcheck disable=SC1090
. "$HOME/.config/van/muse-egress.env"
port="${VAN_MUSE_LOCAL_PORT:-17891}"
trace="$(curl --proxy "socks5h://127.0.0.1:$port" -fsS --max-time 12 https://www.cloudflare.com/cdn-cgi/trace)"
ip="$(sed -n 's/^ip=//p' <<<"$trace" | tail -1)"
country="$(sed -n 's/^loc=//p' <<<"$trace" | tail -1)"
[[ "$ip" == "$MUSE_EXPECTED_EGRESS_IP" && "$country" == "$MUSE_EXPECTED_COUNTRY" ]]
printf '%s %s\n' "$ip" "$country"
CHECK
chmod 0755 "$HOME/.local/bin/van-muse-egress-check"

systemctl --user daemon-reload
systemctl --user enable --now van-muse-egress-tunnel.service
sleep 2
"$HOME/.local/bin/van-muse-egress-check"
printf 'HERMES_MUSE_EGRESS_GREEN socks5h://127.0.0.1:%s\n' "$LOCAL_PORT"
