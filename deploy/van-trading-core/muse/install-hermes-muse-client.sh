#!/usr/bin/env bash
set -euo pipefail
# Install on dial-control as the Hermes user. No Meta credentials are stored here by this script.
PORT="${MUSE_LOCAL_PROXY_PORT:-17890}"
SSH_HOST="${MUSE_TRADING_CORE_SSH_HOST:-van-trading-core}"
PROFILE="${MUSE_BROWSER_PROFILE:-$HOME/.local/share/van/muse-browser-profile}"
UNIT_DIR="$HOME/.config/systemd/user"
BIN_DIR="$HOME/.local/bin"

mkdir -p "$UNIT_DIR" "$BIN_DIR" "$PROFILE"
chmod 0700 "$PROFILE"
command -v ssh >/dev/null || { echo "ssh missing" >&2; exit 2; }
ssh -o BatchMode=yes -o ConnectTimeout=8 "$SSH_HOST" true >/dev/null   || { echo "existing SSH path to $SSH_HOST is not ready" >&2; exit 3; }

cat >"$UNIT_DIR/van-muse-egress-tunnel.service" <<UNIT
[Unit]
Description=Hermes tunnel to VAN Muse hardened egress
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
ExecStart=/usr/bin/ssh -NT -o BatchMode=yes -o ExitOnForwardFailure=yes -o ServerAliveInterval=30 -o ServerAliveCountMax=3 -o TCPKeepAlive=yes -L 127.0.0.1:$PORT:127.0.0.1:17890 $SSH_HOST
Restart=always
RestartSec=5

[Install]
WantedBy=default.target
UNIT

cat >"$BIN_DIR/van-muse-egress-check" <<CHECK
#!/usr/bin/env bash
set -euo pipefail
curl -fsS --connect-timeout 5 --max-time 15 --proxy socks5h://127.0.0.1:$PORT https://api.ipify.org
printf '\n'
CHECK
chmod 0755 "$BIN_DIR/van-muse-egress-check"

cat >"$BIN_DIR/van-muse-browser" <<'BROWSER'
#!/usr/bin/env bash
set -euo pipefail
PORT="${MUSE_LOCAL_PROXY_PORT:-17890}"
PROFILE="${MUSE_BROWSER_PROFILE:-$HOME/.local/share/van/muse-browser-profile}"
for b in chromium chromium-browser google-chrome google-chrome-stable; do
  if command -v "$b" >/dev/null 2>&1; then BROWSER_BIN="$(command -v "$b")"; break; fi
done
: "${BROWSER_BIN:?Chromium/Chrome not installed}"
"$HOME/.local/bin/van-muse-egress-check" >/dev/null
exec "$BROWSER_BIN" \
  --user-data-dir="$PROFILE" \
  --proxy-server="socks5://127.0.0.1:$PORT" \
  --proxy-bypass-list="<-loopback>" \
  --host-resolver-rules="MAP * ~NOTFOUND, EXCLUDE 127.0.0.1" \
  --disable-quic \
  --force-webrtc-ip-handling-policy=disable_non_proxied_udp \
  "https://muse.ai/"
BROWSER
chmod 0755 "$BIN_DIR/van-muse-browser"

systemctl --user daemon-reload
systemctl --user enable --now van-muse-egress-tunnel.service
sleep 2
"$BIN_DIR/van-muse-egress-check" >/dev/null
echo "GREEN: Hermes Muse tunnel active on 127.0.0.1:$PORT"
echo "Launch the isolated persistent client with: $BIN_DIR/van-muse-browser"
