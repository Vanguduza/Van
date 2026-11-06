#!/usr/bin/env bash
set -euo pipefail
# Dedicated US/Canada WireGuard exit. Ubuntu 24.04 expected; do not colocate other forwarding workloads.
[[ $EUID -eq 0 ]] || { echo 'run as root' >&2; exit 2; }
: "${MUSE_CLIENT_PUBLIC_KEY:?set MUSE_CLIENT_PUBLIC_KEY to the trading-core client public key}"
: "${MUSE_EXIT_EXPECTED_COUNTRY:?set MUSE_EXIT_EXPECTED_COUNTRY=US or CA}"
: "${WG_PORT:=51820}"
: "${WG_NET:=10.66.77.0/24}"
: "${WG_SERVER_ADDR:=10.66.77.1/24}"
: "${WG_CLIENT_ADDR:=10.66.77.2/32}"
[[ "$MUSE_EXIT_EXPECTED_COUNTRY" == "US" || "$MUSE_EXIT_EXPECTED_COUNTRY" == "CA" ]] || {
  echo 'MUSE_EXIT_EXPECTED_COUNTRY must be US or CA' >&2; exit 3;
}
WAN_IF="${WAN_IF:-$(ip route show default | awk 'NR==1{print $5}')}"
[[ -n "$WAN_IF" ]] || { echo 'cannot resolve WAN interface' >&2; exit 3; }

export DEBIAN_FRONTEND=noninteractive NEEDRESTART_MODE=a
apt-get -o Acquire::Retries=3 update -qq
apt-get -o Acquire::Retries=3 install -y -qq --no-install-recommends wireguard-tools nftables curl ca-certificates >/dev/null

trace="$(curl -fsS --max-time 12 https://www.cloudflare.com/cdn-cgi/trace)"
PUBLIC_IP="$(sed -n 's/^ip=//p' <<<"$trace" | tail -1)"
COUNTRY="$(sed -n 's/^loc=//p' <<<"$trace" | tail -1)"
[[ -n "$PUBLIC_IP" ]] || { echo 'cannot determine public IP' >&2; exit 4; }
[[ "$COUNTRY" == "$MUSE_EXIT_EXPECTED_COUNTRY" ]] || {
  echo "exit region mismatch: expected=$MUSE_EXIT_EXPECTED_COUNTRY observed=${COUNTRY:-none}" >&2; exit 4;
}

install -d -m 0700 /etc/wireguard
[[ -s /etc/wireguard/muse-server.key ]] || (umask 077; wg genkey > /etc/wireguard/muse-server.key)
chmod 0600 /etc/wireguard/muse-server.key
SERVER_KEY="$(cat /etc/wireguard/muse-server.key)"
cat >/etc/wireguard/wg-muse.conf <<CFG
[Interface]
Address = $WG_SERVER_ADDR
ListenPort = $WG_PORT
PrivateKey = $SERVER_KEY

[Peer]
PublicKey = $MUSE_CLIENT_PUBLIC_KEY
AllowedIPs = $WG_CLIENT_ADDR
CFG
chmod 0600 /etc/wireguard/wg-muse.conf

cat >/etc/sysctl.d/90-van-muse-exit.conf <<'SYSCTL'
net.ipv4.ip_forward=1
net.ipv6.conf.all.forwarding=0
SYSCTL
sysctl --system >/dev/null

cat >/etc/nftables.d-van-muse-exit.nft <<NFT
table inet van_muse_exit_filter {
  set blocked4 {
    type ipv4_addr
    flags interval
    elements = {
      0.0.0.0/8, 10.0.0.0/8, 100.64.0.0/10, 127.0.0.0/8,
      169.254.0.0/16, 172.16.0.0/12, 192.0.0.0/24, 192.168.0.0/16,
      224.0.0.0/4, 240.0.0.0/4
    }
  }
  chain input {
    type filter hook input priority -5; policy accept;
    iifname "wg-muse" drop
  }
  chain forward {
    type filter hook forward priority -5; policy drop;
    ct state invalid drop
    iifname "wg-muse" ip daddr @blocked4 drop
    iifname "wg-muse" oifname "$WAN_IF" accept
    iifname "$WAN_IF" oifname "wg-muse" ct state established,related accept
  }
}
table ip van_muse_exit_nat {
  chain postrouting {
    type nat hook postrouting priority 100;
    ip saddr $WG_NET oifname "$WAN_IF" masquerade
  }
}
NFT

cat >/etc/systemd/system/van-muse-exit-nft.service <<'UNIT'
[Unit]
Description=VAN Muse exit forwarding/NAT policy
Before=wg-quick@wg-muse.service
After=network-online.target
Wants=network-online.target

[Service]
Type=oneshot
RemainAfterExit=yes
ExecStartPre=-/usr/sbin/nft delete table inet van_muse_exit_filter
ExecStartPre=-/usr/sbin/nft delete table ip van_muse_exit_nat
ExecStart=/usr/sbin/nft -f /etc/nftables.d-van-muse-exit.nft
ExecStop=-/usr/sbin/nft delete table inet van_muse_exit_filter
ExecStop=-/usr/sbin/nft delete table ip van_muse_exit_nat

[Install]
WantedBy=multi-user.target
UNIT

systemctl daemon-reload
systemctl enable --now van-muse-exit-nft.service wg-quick@wg-muse.service >/dev/null
systemctl is-active --quiet wg-quick@wg-muse.service
systemctl is-active --quiet van-muse-exit-nft.service

PUBLIC_KEY="$(printf '%s' "$SERVER_KEY" | wg pubkey)"
printf 'MUSE_WG_PEER_PUBLIC_KEY=%s\n' "$PUBLIC_KEY"
printf 'MUSE_WG_ENDPOINT=%s:%s\n' "$PUBLIC_IP" "$WG_PORT"
printf 'MUSE_EXPECTED_EGRESS_IP=%s\n' "$PUBLIC_IP"
printf 'MUSE_EXPECTED_COUNTRY=%s\n' "$COUNTRY"
printf 'Provider firewall: expose UDP/%s only to the trading-core source IP if the provider supports source filtering; retain a separately restricted SSH admin rule.\n' "$WG_PORT"
