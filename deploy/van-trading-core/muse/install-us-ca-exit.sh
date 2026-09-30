#!/usr/bin/env bash
set -euo pipefail
# Hardened WireGuard exit for a dedicated US/Canada VPS. Ubuntu 24.04 expected.
# Required env: MUSE_CLIENT_PUBLIC_KEY. Optional: WG_PORT, WG_NET, WG_SERVER_ADDR, WG_CLIENT_ADDR.
[[ $EUID -eq 0 ]] || { echo 'run as root' >&2; exit 2; }
: "${MUSE_CLIENT_PUBLIC_KEY:?set MUSE_CLIENT_PUBLIC_KEY to the trading-core client public key}"
: "${WG_PORT:=51820}"
: "${WG_NET:=10.66.77.0/24}"
: "${WG_SERVER_ADDR:=10.66.77.1/24}"
: "${WG_CLIENT_ADDR:=10.66.77.2/32}"
WAN_IF="${WAN_IF:-$(ip route show default | awk 'NR==1{print $5}')}"
[[ -n "$WAN_IF" ]] || { echo 'cannot resolve WAN interface' >&2; exit 3; }
apt-get update -qq
apt-get install -y -qq --no-install-recommends wireguard-tools nftables ca-certificates
install -d -m 0700 /etc/wireguard
[[ -s /etc/wireguard/muse-server.key ]] || (umask 077; wg genkey > /etc/wireguard/muse-server.key)
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
SYSCTL
sysctl --system >/dev/null
cat >/etc/nftables.d-van-muse-exit.nft <<NFT
 table inet van_muse_exit_filter {
   set blocked4 { type ipv4_addr; flags interval; elements = { 0.0.0.0/8, 10.0.0.0/8, 100.64.0.0/10, 127.0.0.0/8, 169.254.0.0/16, 172.16.0.0/12, 192.0.0.0/24, 192.168.0.0/16, 224.0.0.0/4, 240.0.0.0/4 } }
   chain forward {
     type filter hook forward priority -5; policy drop;
     ct state invalid drop
     iifname "wg-muse" ip daddr @blocked4 drop
     iifname "wg-muse" oifname "$WAN_IF" accept
     iifname "$WAN_IF" oifname "wg-muse" ct state established,related accept
   }
 }
 table ip van_muse_exit_nat {
   chain postrouting { type nat hook postrouting priority 100; ip saddr $WG_NET oifname "$WAN_IF" masquerade }
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
ExecStart=/usr/sbin/nft -f /etc/nftables.d-van-muse-exit.nft
ExecStop=/usr/sbin/nft delete table inet van_muse_exit_filter
ExecStop=/usr/sbin/nft delete table ip van_muse_exit_nat

[Install]
WantedBy=multi-user.target
UNIT
systemctl daemon-reload
systemctl enable --now van-muse-exit-nft.service wg-quick@wg-muse.service
PUBLIC_KEY="$(printf '%s' "$SERVER_KEY" | wg pubkey)"
printf 'MUSE_EXIT_SERVER_PUBLIC_KEY=%s\n' "$PUBLIC_KEY"
printf 'MUSE_EXIT_UDP_PORT=%s\n' "$WG_PORT"
printf 'Open only UDP/%s at the provider firewall in addition to your existing SSH policy.\n' "$WG_PORT"
