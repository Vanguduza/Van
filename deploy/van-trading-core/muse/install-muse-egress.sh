#!/usr/bin/env bash
set -euo pipefail

BASE=/opt/van-muse-egress
CONFIG=/etc/van-muse-egress.env
NS=van-muse
WG=wg-muse
VETH_HOST=muse-host
VETH_NS=muse-ns
HOST_IP=169.254.77.1/30
NS_IP=169.254.77.2/30
PROXY_PORT=1080
BRIDGE_PORT=17890
DRY_RUN=0
[[ "${1:-}" == "--dry-run" ]] && DRY_RUN=1

log(){ printf '[muse-egress] %s\n' "$*"; }
die(){ printf '[muse-egress] ERROR: %s\n' "$*" >&2; exit 1; }
run(){ if ((DRY_RUN)); then printf '+ '; printf '%q ' "$@"; printf '\n'; else "$@"; fi; }
[[ $EUID -eq 0 ]] || die "run as root"

if (( ! DRY_RUN )); then
  [[ -f "$CONFIG" ]] || die "$CONFIG missing; copy muse-egress.env.example there first"
  [[ "$(stat -c '%U:%G:%a' "$CONFIG")" == "root:root:600" ]] || die "$CONFIG must be root:root mode 0600"
  # shellcheck disable=SC1090
  set -a; . "$CONFIG"; set +a
fi
: "${MUSE_WG_PRIVATE_KEY_FILE:=/opt/van-muse-egress/secrets/wg-private.key}"
: "${MUSE_WG_PEER_PUBLIC_KEY:=REPLACE_ME}"
: "${MUSE_WG_ENDPOINT:=203.0.113.10:51820}"
: "${MUSE_WG_ADDRESS:=10.66.77.2/32}"
: "${MUSE_WG_DNS:=1.1.1.1}"
: "${MUSE_EXPECTED_EGRESS_IP:=203.0.113.10}"

if (( DRY_RUN )); then
  cat <<PLAN
[muse-egress] PLAN install wireguard-tools nftables dante-server socat curl
[muse-egress] PLAN create isolated namespace $NS with WireGuard-only default route
[muse-egress] PLAN bind SOCKS5 inside namespace and bridge only to host 127.0.0.1:$BRIDGE_PORT
[muse-egress] PLAN block RFC1918/link-local/metadata/IPv6 escape paths
[muse-egress] PLAN verify fixed egress $MUSE_EXPECTED_EGRESS_IP and fail closed on mismatch
PLAN
  exit 0
fi

if (( ! DRY_RUN )); then
  [[ "$MUSE_WG_PEER_PUBLIC_KEY" != REPLACE_ME ]] || die "peer key not configured"
  [[ -s "$MUSE_WG_PRIVATE_KEY_FILE" ]] || die "WireGuard private key missing"
  keymode="$(stat -c '%a' "$MUSE_WG_PRIVATE_KEY_FILE")"
  [[ "$keymode" == 600 || "$keymode" == 400 ]] || die "WireGuard private key must be 0600 or 0400"
  [[ "$MUSE_WG_ENDPOINT" =~ ^([0-9]{1,3}\.){3}[0-9]{1,3}:[0-9]{1,5}$ ]] || die "MUSE_WG_ENDPOINT must be a fixed IPv4:port"
  [[ "$MUSE_WG_ADDRESS" =~ ^([0-9]{1,3}\.){3}[0-9]{1,3}/[0-9]{1,2}$ ]] || die "MUSE_WG_ADDRESS must be IPv4 CIDR"
  [[ "$MUSE_EXPECTED_EGRESS_IP" =~ ^([0-9]{1,3}\.){3}[0-9]{1,3}$ ]] || die "MUSE_EXPECTED_EGRESS_IP must be IPv4"
fi

run apt-get update -qq
run apt-get install -y -qq --no-install-recommends wireguard-tools nftables dante-server socat curl ca-certificates
run install -d -m 0750 -o root -g root "$BASE" "$BASE/secrets"
run install -d -m 0755 /run/van-muse
if (( ! DRY_RUN )); then
  id vanmuse >/dev/null 2>&1 || useradd --system --home-dir /var/lib/van-muse --create-home --shell /usr/sbin/nologin vanmuse
  chmod 0700 /var/lib/van-muse
fi

cat >/usr/local/sbin/van-muse-netns-up <<'UP'
#!/usr/bin/env bash
set -euo pipefail
NS=van-muse; WG=wg-muse; VETH_HOST=muse-host; VETH_NS=muse-ns
HOST_IP=169.254.77.1/30; NS_IP=169.254.77.2/30
# shellcheck disable=SC1091
set -a; . /etc/van-muse-egress.env; set +a
: "${MUSE_WG_PRIVATE_KEY_FILE:?}" "${MUSE_WG_PEER_PUBLIC_KEY:?}" "${MUSE_WG_ENDPOINT:?}" "${MUSE_WG_ADDRESS:?}" "${MUSE_WG_DNS:?}"

ip netns del "$NS" 2>/dev/null || true
ip link del "$VETH_HOST" 2>/dev/null || true
ip link del "$WG" 2>/dev/null || true
ip netns add "$NS"
ip link add "$VETH_HOST" type veth peer name "$VETH_NS"
ip link set "$VETH_NS" netns "$NS"
ip addr add "$HOST_IP" dev "$VETH_HOST"
ip link set "$VETH_HOST" up
ip -n "$NS" addr add "$NS_IP" dev "$VETH_NS"
ip -n "$NS" link set "$VETH_NS" up
ip -n "$NS" link set lo up

# WireGuard's UDP socket is born in the host namespace and stays there after the
# interface is moved. The Muse namespace therefore never gains a host/LAN NIC.
ip link add "$WG" type wireguard
wg set "$WG" private-key "$MUSE_WG_PRIVATE_KEY_FILE" peer "$MUSE_WG_PEER_PUBLIC_KEY" endpoint "$MUSE_WG_ENDPOINT" allowed-ips 0.0.0.0/0 persistent-keepalive 25
ip link set "$WG" netns "$NS"
ip -n "$NS" addr add "$MUSE_WG_ADDRESS" dev "$WG"
ip -n "$NS" link set "$WG" up
ip -n "$NS" route replace default dev "$WG"

mkdir -p "/etc/netns/$NS"
printf 'nameserver %s\noptions timeout:2 attempts:2\n' "$MUSE_WG_DNS" > "/etc/netns/$NS/resolv.conf"

ip netns exec "$NS" nft -f - <<'NFT'
flush ruleset
table inet muse_filter {
  set blocked4 {
    type ipv4_addr
    flags interval
    elements = { 0.0.0.0/8, 10.0.0.0/8, 100.64.0.0/10, 127.0.0.0/8, 169.254.0.0/16, 172.16.0.0/12, 192.0.0.0/24, 192.168.0.0/16, 224.0.0.0/4, 240.0.0.0/4 }
  }
  chain input {
    type filter hook input priority 0; policy drop;
    iifname "lo" accept
    ct state established,related accept
    iifname "muse-ns" ip saddr 169.254.77.1 tcp dport 1080 accept
  }
  chain output {
    type filter hook output priority 0; policy drop;
    oifname "lo" accept
    ct state established,related accept
    oifname "wg-muse" ip daddr @blocked4 drop
    oifname "wg-muse" accept
    oifname "muse-ns" ip daddr 169.254.77.1 ct state established,related accept
  }
}
NFT
ip netns exec "$NS" sysctl -q -w net.ipv6.conf.all.disable_ipv6=1 net.ipv6.conf.default.disable_ipv6=1 || true
UP
chmod 0755 /usr/local/sbin/van-muse-netns-up

cat >/usr/local/sbin/van-muse-netns-down <<'DOWN'
#!/usr/bin/env bash
set -euo pipefail
ip netns del van-muse 2>/dev/null || true
ip link del muse-host 2>/dev/null || true
rm -rf /etc/netns/van-muse
DOWN
chmod 0755 /usr/local/sbin/van-muse-netns-down

cat >"$BASE/danted.conf" <<'DANTE'
logoutput: syslog
internal: 169.254.77.2 port = 1080
external: wg-muse
socksmethod: none
user.privileged: vanmuse
user.unprivileged: vanmuse
client pass { from: 169.254.77.1/32 to: 0.0.0.0/0 }
socks pass { from: 169.254.77.1/32 to: 0.0.0.0/0 protocol: tcp }
DANTE
chmod 0644 "$BASE/danted.conf"

cat >/etc/systemd/system/van-muse-netns.service <<'UNIT'
[Unit]
Description=VAN Muse isolated network namespace and WireGuard egress
After=network-online.target
Wants=network-online.target
Before=van-muse-socks.service

[Service]
Type=oneshot
RemainAfterExit=yes
EnvironmentFile=/etc/van-muse-egress.env
ExecStart=/usr/local/sbin/van-muse-netns-up
ExecStop=/usr/local/sbin/van-muse-netns-down

[Install]
WantedBy=multi-user.target
UNIT

cat >/etc/systemd/system/van-muse-socks.service <<'UNIT'
[Unit]
Description=VAN Muse SOCKS5 proxy inside isolated egress namespace
Requires=van-muse-netns.service
After=van-muse-netns.service

[Service]
Type=simple
User=vanmuse
Group=vanmuse
NetworkNamespacePath=/run/netns/van-muse
# Force libc/Dante DNS through the namespace resolver; never inherit host systemd-resolved.
BindReadOnlyPaths=/etc/netns/van-muse/resolv.conf:/etc/resolv.conf
ExecStart=/usr/sbin/danted -f /opt/van-muse-egress/danted.conf
Restart=on-failure
RestartSec=3
NoNewPrivileges=yes
PrivateTmp=yes
PrivateDevices=yes
ProtectSystem=strict
ProtectHome=yes
ProtectKernelTunables=yes
ProtectKernelModules=yes
ProtectControlGroups=yes
RestrictSUIDSGID=yes
LockPersonality=yes
CapabilityBoundingSet=
RestrictAddressFamilies=AF_UNIX AF_INET

[Install]
WantedBy=multi-user.target
UNIT

cat >/etc/systemd/system/van-muse-bridge.service <<'UNIT'
[Unit]
Description=Loopback-only bridge to VAN Muse SOCKS5 proxy
Requires=van-muse-socks.service
After=van-muse-socks.service

[Service]
Type=simple
ExecStart=/usr/bin/socat TCP-LISTEN:17890,bind=127.0.0.1,reuseaddr,fork TCP:169.254.77.2:1080
Restart=on-failure
RestartSec=3
NoNewPrivileges=yes
PrivateTmp=yes
PrivateDevices=yes
ProtectSystem=strict
ProtectHome=yes
ProtectKernelTunables=yes
ProtectKernelModules=yes
ProtectControlGroups=yes
RestrictSUIDSGID=yes
LockPersonality=yes
CapabilityBoundingSet=
RestrictAddressFamilies=AF_UNIX AF_INET

[Install]
WantedBy=multi-user.target
UNIT

cat >/usr/local/bin/van-muse-egress-check <<'CHECK'
#!/usr/bin/env bash
set -euo pipefail
# shellcheck disable=SC1091
set -a; . /etc/van-muse-egress.env; set +a
observed="$(curl -fsS --connect-timeout 5 --max-time 15 --proxy socks5h://127.0.0.1:17890 https://api.ipify.org)"
[[ "$observed" == "$MUSE_EXPECTED_EGRESS_IP" ]] || {
  logger -t van-muse-egress "FAIL_CLOSED expected=$MUSE_EXPECTED_EGRESS_IP observed=${observed:-none}"
  systemctl stop van-muse-bridge.service
  exit 42
}
printf '%s\n' "$observed"
CHECK
chmod 0755 /usr/local/bin/van-muse-egress-check

cat >/etc/systemd/system/van-muse-egress-health.service <<'UNIT'
[Unit]
Description=Verify VAN Muse fixed egress and fail closed on mismatch
After=van-muse-bridge.service
Requires=van-muse-bridge.service

[Service]
Type=oneshot
ExecStart=/usr/local/bin/van-muse-egress-check
UNIT

cat >/etc/systemd/system/van-muse-egress-health.timer <<'UNIT'
[Unit]
Description=Periodic VAN Muse egress verification

[Timer]
OnBootSec=45s
OnUnitActiveSec=5min
Unit=van-muse-egress-health.service

[Install]
WantedBy=timers.target
UNIT

if (( ! DRY_RUN )); then
  systemctl daemon-reload
  systemctl enable --now van-muse-netns.service van-muse-socks.service van-muse-bridge.service van-muse-egress-health.timer
  /usr/local/bin/van-muse-egress-check >/dev/null
  log "GREEN: loopback SOCKS5 at 127.0.0.1:$BRIDGE_PORT exits only through $MUSE_EXPECTED_EGRESS_IP"
  log "Consume it from dial-control through SSH local forwarding; never expose $BRIDGE_PORT publicly."
else
  log "dry-run complete"
fi
