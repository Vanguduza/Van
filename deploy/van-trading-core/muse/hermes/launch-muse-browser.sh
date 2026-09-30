#!/usr/bin/env bash
set -euo pipefail
[[ -f "$HOME/.config/van/muse-egress.env" ]] && . "$HOME/.config/van/muse-egress.env"
PORT="${VAN_MUSE_LOCAL_PORT:-17891}"
PROFILE="${VAN_MUSE_PROFILE:-$HOME/.local/share/van/muse-browser-profile}"
CHECK="${VAN_MUSE_EGRESS_CHECK:-$HOME/.local/bin/van-muse-egress-check}"
"$CHECK" >/dev/null

BROWSER="${VAN_MUSE_BROWSER:-}"
if [[ -z "$BROWSER" ]]; then
  for c in chromium chromium-browser google-chrome google-chrome-stable; do
    if command -v "$c" >/dev/null 2>&1; then BROWSER="$(command -v "$c")"; break; fi
  done
fi
[[ -n "$BROWSER" && -x "$BROWSER" ]] || { echo 'Chromium/Chrome not found; set VAN_MUSE_BROWSER' >&2; exit 2; }
install -d -m 0700 "$PROFILE"

exec "$BROWSER"   --user-data-dir="$PROFILE"   --proxy-server="socks5://127.0.0.1:$PORT"   --host-resolver-rules="MAP * ~NOTFOUND, EXCLUDE 127.0.0.1"   --disable-quic   --force-webrtc-ip-handling-policy=disable_non_proxied_udp   --no-first-run   --no-default-browser-check   https://muse.ai/
