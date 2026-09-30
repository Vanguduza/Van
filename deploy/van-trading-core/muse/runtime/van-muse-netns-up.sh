#!/usr/bin/env bash
set -euo pipefail
[[ $EUID -eq 0 ]] || { echo "run as root" >&2; exit 2; }
ENVF=/etc/van-muse-egress.env
[[ -f "$ENVF" ]] || { echo "missing $ENVF" >&2; exit 2; }
# shellcheck disable=SC1090
set -a; . "$ENVF"; set +a

: "${MUSE_WG_PRIVATE_KEY_FILE:?}"
: "${MUSE_WG_PEER_PUBLIC_KEY:?}"
: "${MUSE_WG_ENDPOINT:?}"
: "${MUSE_WG_ADDRESS:?}"
: "${MUSE_WG_DNS:?}"
: "${MUSE_EXPECTED_EGRESS_IP:?}"
: "${MUSE_EXPECTED_COUNTRY:?}"

[[ "$MUSE_WG_ENDPOINT" =~ ^([0-9]{1,3}\.){3}[0-9]{1,3}:[0-9]{1,5}$ ]] || {
  echo "MUSE_WG_ENDPOINT must be a fixed IPv4:port; DNS endpoints are deliberately rejected" >&2; exit 3;
}
[[ "$MUSE_EXPECTED_COUNTRY" == "US" || "$MUSE_EXPECTED_COUNTRY" == "CA" ]] || {
  echo "MUSE_EXPECTED_COUNTRY must be US or CA" >&2; exit 3;
}
[[ -s "$MUSE_WG_PRIVATE_KEY_FILE" ]] || { echo "private key missing" >&2; exit 3; }

# Always rebuild from a known-empty namespace. No host default route is touched.
ip netns del van-muse 2>/dev/null || true
ip link del muse-host 2>/dev/null || true
ip link del wg-muse 2>/dev/null || true

install -d -m 0755 /etc/netns/van-muse
printf 'nameserver %s\noptions edns0 trust-ad\n' "$MUSE_WG_DNS" >/etc/netns/van-muse/resolv.conf
chmod 0644 /etc/netns/van-muse/resolv.conf

ip netns add van-muse
ip link add muse-host type veth peer name muse-ns
ip addr add 169.254.77.1/30 dev muse-host
ip link set muse-host up
ip link set muse-ns netns van-muse
ip -n van-muse addr add 169.254.77.2/30 dev muse-ns
ip -n van-muse link set lo up
ip -n van-muse link set muse-ns up

# Create WireGuard in the root namespace and move only the interface. WireGuard's
# encrypted UDP socket remains in the root namespace, so endpoint reachability uses
# the host's existing route while decrypted traffic exists only inside van-muse.
ip link add wg-muse type wireguard
wg set wg-muse   private-key "$MUSE_WG_PRIVATE_KEY_FILE"   peer "$MUSE_WG_PEER_PUBLIC_KEY"   endpoint "$MUSE_WG_ENDPOINT"   allowed-ips 0.0.0.0/0   persistent-keepalive 25
ip link set wg-muse netns van-muse
ip -n van-muse addr add "$MUSE_WG_ADDRESS" dev wg-muse
ip -n van-muse link set wg-muse mtu 1380
ip -n van-muse link set wg-muse up
ip -n van-muse route replace default dev wg-muse

# IPv6 is disabled in this namespace until the Muse egress has an explicitly
# provisioned IPv6 peer. This prevents an accidental host/ISP IPv6 fallback.
ip netns exec van-muse sysctl -q -w net.ipv6.conf.all.disable_ipv6=1
ip netns exec van-muse sysctl -q -w net.ipv6.conf.default.disable_ipv6=1

# Namespace policy: the only clear-text path is host -> danted:1080 across the
# veth. New outbound connections may leave only through wg-muse.
ip netns exec van-muse nft -f - <<'NFT'
flush table inet van_muse_ns
table inet van_muse_ns {
  chain input {
    type filter hook input priority 0; policy drop;
    ct state established,related accept
    iifname "lo" accept
    iifname "muse-ns" ip saddr 169.254.77.1 tcp dport 1080 accept
  }
  chain output {
    type filter hook output priority 0; policy drop;
    oifname "lo" accept
    oifname "wg-muse" accept
    oifname "muse-ns" ip daddr 169.254.77.1 ct state established,related accept
  }
}
NFT

# The host must never forward namespace packets into the trading VCN.
sysctl -q -w net.ipv4.conf.muse-host.forwarding=0 || true
