#!/bin/sh
set -eu

[ "$(id -u)" = "10001" ] || {
  echo "refusing to run Muse browser as uid $(id -u); expected 10001" >&2
  exit 70
}

PROFILE=/home/muse/profile
[ -d "$PROFILE" ] || exit 71
[ -w "$PROFILE" ] || {
  echo "persistent Muse profile is not writable" >&2
  exit 72
}

exec /usr/bin/chromium \
  --headless=new \
  --user-data-dir="$PROFILE" \
  --remote-debugging-address=0.0.0.0 \
  --remote-debugging-port=9222 \
  --proxy-server=socks5://172.31.77.1:17892 \
  --host-resolver-rules="MAP * ~NOTFOUND, EXCLUDE 172.31.77.1" \
  --disable-quic \
  --force-webrtc-ip-handling-policy=disable_non_proxied_udp \
  --disable-background-networking \
  --disable-component-update \
  --disable-domain-reliability \
  --disable-sync \
  --disk-cache-size=536870912 \
  --media-cache-size=268435456 \
  --metrics-recording-only \
  --no-default-browser-check \
  --no-first-run \
  about:blank
