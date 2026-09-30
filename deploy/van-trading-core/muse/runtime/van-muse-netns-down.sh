#!/usr/bin/env bash
set -euo pipefail
[[ $EUID -eq 0 ]] || exit 2
ip netns del van-muse 2>/dev/null || true
ip link del muse-host 2>/dev/null || true
ip link del wg-muse 2>/dev/null || true
rm -f /etc/netns/van-muse/resolv.conf
rmdir /etc/netns/van-muse 2>/dev/null || true
