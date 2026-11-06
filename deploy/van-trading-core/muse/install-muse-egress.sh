#!/usr/bin/env bash
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONFIG=/etc/van-muse-egress.env
DRY_RUN=0
[[ "${1:-}" == "--dry-run" ]] && DRY_RUN=1
log(){ printf '[muse-egress] %s\n' "$*"; }
die(){ printf '[muse-egress] ERROR: %s\n' "$*" >&2; exit 1; }
[[ $EUID -eq 0 ]] || die "run as root"

if (( DRY_RUN )); then
  cat <<'PLAN'
[muse-egress] PLAN install WireGuard/nftables/Dante/socat without modifying VATI
[muse-egress] PLAN create van-muse network namespace with WireGuard-only default route
[muse-egress] PLAN expose SOCKS only at trading-core loopback 127.0.0.1:17890
[muse-egress] PLAN verify fixed public IP + US/CA country and test fail-closed behavior
[muse-egress] PLAN prove the host/trading default route is unchanged
PLAN
  exit 0
fi

[[ "$(hostname)" == "van-trading-core" || "${VAN_MUSE_ALLOW_HOST_OVERRIDE:-0}" == "1" ]] ||   die "refusing to install on $(hostname); expected van-trading-core"
[[ -f "$CONFIG" ]] || die "$CONFIG missing; copy muse-egress.env.example there first"
chown root:root "$CONFIG"; chmod 0600 "$CONFIG"
# shellcheck disable=SC1091
set -a; . "$CONFIG"; set +a

: "${MUSE_WG_PRIVATE_KEY_FILE:=/opt/van-muse-egress/secrets/wg-private.key}"
: "${MUSE_WG_PEER_PUBLIC_KEY:=REPLACE_ME}"
: "${MUSE_WG_ENDPOINT:=203.0.113.10:51820}"
: "${MUSE_WG_ADDRESS:=10.66.77.2/32}"
: "${MUSE_WG_DNS:=1.1.1.1}"
: "${MUSE_EXPECTED_EGRESS_IP:=203.0.113.10}"
: "${MUSE_EXPECTED_COUNTRY:=US}"

[[ "$MUSE_WG_ENDPOINT" =~ ^([0-9]{1,3}\.){3}[0-9]{1,3}:[0-9]{1,5}$ ]] ||   die "MUSE_WG_ENDPOINT must be a fixed IPv4:port"
[[ "$MUSE_WG_ADDRESS" =~ ^([0-9]{1,3}\.){3}[0-9]{1,3}/[0-9]{1,2}$ ]] ||   die "MUSE_WG_ADDRESS must be IPv4 CIDR"
[[ "$MUSE_EXPECTED_EGRESS_IP" =~ ^([0-9]{1,3}\.){3}[0-9]{1,3}$ ]] ||   die "MUSE_EXPECTED_EGRESS_IP must be IPv4"
[[ "$MUSE_EXPECTED_COUNTRY" == "US" || "$MUSE_EXPECTED_COUNTRY" == "CA" ]] ||   die "MUSE_EXPECTED_COUNTRY must be US or CA"

export DEBIAN_FRONTEND=noninteractive NEEDRESTART_MODE=a
apt-get -o Acquire::Retries=3 update -qq
apt-get -o Acquire::Retries=3 install -y -qq --no-install-recommends   wireguard-tools nftables dante-server socat curl jq iproute2 ca-certificates >/dev/null

install -d -m 0755 /etc/van-muse-egress /var/lib/van-muse-egress
install -d -m 0700 /opt/van-muse-egress/secrets
id vanmuse >/dev/null 2>&1 || useradd --system --home-dir /var/lib/van-muse --create-home --shell /usr/sbin/nologin vanmuse
id vanmuseproxy >/dev/null 2>&1 || useradd --system --home-dir /var/lib/van-muse-proxy --create-home --shell /usr/sbin/nologin vanmuseproxy
chmod 0700 /var/lib/van-muse
if [[ ! -s "$MUSE_WG_PRIVATE_KEY_FILE" ]]; then
  install -d -m 0700 "$(dirname "$MUSE_WG_PRIVATE_KEY_FILE")"
  umask 077
  wg genkey >"$MUSE_WG_PRIVATE_KEY_FILE"
fi
chown root:root "$MUSE_WG_PRIVATE_KEY_FILE"; chmod 0600 "$MUSE_WG_PRIVATE_KEY_FILE"
CLIENT_PUBLIC_KEY="$(wg pubkey <"$MUSE_WG_PRIVATE_KEY_FILE")"

install -m 0644 "$HERE/danted.conf" /etc/van-muse-egress/danted.conf
install -m 0755 "$HERE/runtime/van-muse-netns-up.sh" /usr/local/sbin/van-muse-netns-up
install -m 0755 "$HERE/runtime/van-muse-netns-down.sh" /usr/local/sbin/van-muse-netns-down
install -m 0755 "$HERE/runtime/van-muse-egress-check.sh" /usr/local/bin/van-muse-egress-check
install -m 0755 "$HERE/qualify-muse-egress.sh" /usr/local/bin/qualify-muse-egress
for u in van-muse-netns.service van-muse-socks.service van-muse-bridge.service          van-muse-egress-health.service van-muse-egress-health.timer; do
  install -m 0644 "$HERE/systemd/$u" "/etc/systemd/system/$u"
done
systemctl daemon-reload

printf 'MUSE_CLIENT_PUBLIC_KEY=%s\n' "$CLIENT_PUBLIC_KEY"
if [[ "$MUSE_WG_PEER_PUBLIC_KEY" == "REPLACE_ME" || "$MUSE_WG_ENDPOINT" == 203.0.113.10:* ]]; then
  systemctl disable van-muse-netns.service van-muse-socks.service van-muse-bridge.service van-muse-egress-health.timer >/dev/null 2>&1 || true
  log "staged but not enabled: provision the US/Canada exit with the client public key, update $CONFIG, then rerun"
  exit 20
fi

systemctl enable van-muse-netns.service van-muse-socks.service van-muse-bridge.service van-muse-egress-health.timer >/dev/null

HOST_DEFAULT_BEFORE="$(ip -4 route show default)"
systemctl restart van-muse-netns.service
systemctl restart van-muse-socks.service
systemctl restart van-muse-bridge.service
HOST_DEFAULT_AFTER="$(ip -4 route show default)"
[[ "$HOST_DEFAULT_BEFORE" == "$HOST_DEFAULT_AFTER" ]] || {
  systemctl stop van-muse-bridge.service van-muse-socks.service van-muse-netns.service || true
  die "host default route changed; Muse enclave removed"
}

# Explicit kill-switch proof. With wg-muse down, the proxy must have no route to the Internet.
ip -n van-muse link set wg-muse down
if curl --proxy socks5h://127.0.0.1:17890 -fsS --max-time 4      https://www.cloudflare.com/cdn-cgi/trace >/dev/null 2>&1; then
  systemctl stop van-muse-bridge.service van-muse-socks.service van-muse-netns.service || true
  die "kill-switch failure: proxy reached Internet with wg-muse down"
fi
ip -n van-muse link set wg-muse up
sleep 3

/usr/local/bin/van-muse-egress-check
systemctl enable --now van-muse-egress-health.timer >/dev/null
/usr/local/bin/qualify-muse-egress | tee /var/lib/van-muse-egress/qualification-latest.json
jq -e '.status=="GREEN" and .required_failures==0'   /var/lib/van-muse-egress/qualification-latest.json >/dev/null

log "GREEN: fixed $MUSE_EXPECTED_COUNTRY egress at $MUSE_EXPECTED_EGRESS_IP; SOCKS5 is loopback-only on 127.0.0.1:17890"
