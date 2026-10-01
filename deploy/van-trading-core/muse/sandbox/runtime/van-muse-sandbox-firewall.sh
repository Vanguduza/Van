#!/usr/bin/env bash
set -euo pipefail
[[ $EUID -eq 0 ]] || { echo "run as root" >&2; exit 2; }
ENVF=/etc/van-muse-sandbox.env
[[ -f "$ENVF" ]] || { echo "missing $ENVF" >&2; exit 2; }
# shellcheck disable=SC1090
set -a; . "$ENVF"; set +a

: "${MUSE_SANDBOX_BRIDGE:?}"
: "${MUSE_SANDBOX_IP:?}"
: "${MUSE_SANDBOX_PROXY_PORT:?}"
: "${MUSE_SANDBOX_CDP_PORT:?}"
: "${MUSE_SANDBOX_CONTROL_PORT:?}"

CTL_UID="$(id -u vanmusectl)"
BROWSER_UID="$(id -u van-browser)"
ip link show "$MUSE_SANDBOX_BRIDGE" >/dev/null

nft delete table inet van_muse_sandbox 2>/dev/null || true
nft -f - <<NFT
table inet van_muse_sandbox {
  chain input {
    type filter hook input priority -150; policy accept;
    # The sandbox may talk to the host only through its egress proxy.
    iifname "$MUSE_SANDBOX_BRIDGE" ct state established,related accept
    iifname "$MUSE_SANDBOX_BRIDGE" ip saddr $MUSE_SANDBOX_IP tcp dport $MUSE_SANDBOX_PROXY_PORT accept
    iifname "$MUSE_SANDBOX_BRIDGE" drop
  }

  chain forward {
    type filter hook forward priority -150; policy accept;
    # Docker's internal network is defense-in-depth; this prevents forwarding even
    # if a later Docker rule accidentally introduces NAT or another connected network.
    iifname "$MUSE_SANDBOX_BRIDGE" drop
  }

  chain output {
    type filter hook output priority -150; policy accept;

    # 17892 is an ingress capability for packets arriving from the sandbox bridge,
    # never a general-purpose proxy for processes already on Trading Core.
    ip daddr $MUSE_SANDBOX_GATEWAY tcp dport $MUSE_SANDBOX_PROXY_PORT reject with tcp reset

    # Existing Browser Harness/Stagehand attach through the loopback CDP bridge.
    ip daddr 127.0.0.1 tcp dport $MUSE_SANDBOX_CDP_PORT meta skuid { 0, $CTL_UID, $BROWSER_UID } accept
    ip daddr 127.0.0.1 tcp dport $MUSE_SANDBOX_CDP_PORT reject with tcp reset

    # Only the dedicated principals may originate host->sandbox control traffic.
    oifname "$MUSE_SANDBOX_BRIDGE" ip daddr $MUSE_SANDBOX_IP tcp dport 9222 meta skuid { 0, $CTL_UID } accept
    oifname "$MUSE_SANDBOX_BRIDGE" ip daddr $MUSE_SANDBOX_IP tcp dport 9230 meta skuid { 0, $CTL_UID } accept
    oifname "$MUSE_SANDBOX_BRIDGE" ip daddr $MUSE_SANDBOX_IP ct state established,related accept
    oifname "$MUSE_SANDBOX_BRIDGE" ip daddr $MUSE_SANDBOX_IP drop
  }
}
NFT
