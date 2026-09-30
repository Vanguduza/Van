#!/usr/bin/env bash
set -uo pipefail
fails=0; checks=()
add(){ local n="$1" s="$2" d="$3"; checks+=("{\"check\":\"$n\",\"status\":\"$s\",\"detail\":$(printf '%s' "$d"|jq -Rs .)}"); [[ "$s" == GREEN ]] || fails=$((fails+1)); }
[[ $EUID -eq 0 ]] || { echo 'run as root' >&2; exit 2; }
[[ -f /etc/van-muse-egress.env ]] || { echo 'missing /etc/van-muse-egress.env' >&2; exit 2; }
# shellcheck disable=SC1091
set -a; . /etc/van-muse-egress.env; set +a

perm="$(stat -c '%U:%G:%a' /etc/van-muse-egress.env 2>/dev/null || true)"
[[ "$perm" == "root:root:600" ]] && add config_secret GREEN "$perm" || add config_secret RED "$perm"
keyperm="$(stat -c '%U:%G:%a' "$MUSE_WG_PRIVATE_KEY_FILE" 2>/dev/null || true)"
[[ "$keyperm" == "root:root:600" || "$keyperm" == "root:root:400" ]] && add wireguard_secret GREEN "$keyperm" || add wireguard_secret RED "$keyperm"

for u in van-muse-netns.service van-muse-socks.service van-muse-bridge.service van-muse-egress-health.timer; do
  systemctl is-active --quiet "$u" && add "$u" GREEN active || add "$u" RED "$(systemctl is-active "$u" 2>&1)"
done

ip netns list | grep -q '^van-muse\b' && add namespace GREEN present || add namespace RED missing
links="$(ip -n van-muse -o link show 2>/dev/null | awk -F': ' '{print $2}' | cut -d@ -f1 | sort -u | tr '\n' ' ')"
missing=""; extra=""
for x in lo muse-ns wg-muse; do grep -qw "$x" <<<"$links" || missing="$missing $x"; done
for x in $links; do [[ "$x" == lo || "$x" == muse-ns || "$x" == wg-muse ]] || extra="$extra $x"; done
[[ -z "$missing$extra" ]] && add namespace_links GREEN "$links" || add namespace_links RED "links=$links missing=$missing extra=$extra"

host_default="$(ip -4 route show default)"
if grep -Eq 'dev (wg-muse|muse-host)' <<<"$host_default"; then add host_default_route RED "$host_default"; else add host_default_route GREEN "$host_default"; fi

defroute="$(ip -n van-muse route show default 2>/dev/null)"
grep -q 'dev wg-muse' <<<"$defroute" && add namespace_default_route GREEN "$defroute" || add namespace_default_route RED "$defroute"
v6default="$(ip -n van-muse -6 route show default 2>/dev/null)"
[[ -z "$v6default" ]] && add ipv6_escape GREEN none || add ipv6_escape RED "$v6default"

nslisten="$(ip netns exec van-muse ss -ltnH 2>/dev/null | awk '{print $4}' | grep ':1080$' || true)"
[[ "$nslisten" == "169.254.77.2:1080" ]] && add socks_bind GREEN "$nslisten" || add socks_bind RED "${nslisten:-missing}"
hostlisten="$(ss -ltnH 2>/dev/null | awk '{print $4}' | grep ':17890$' || true)"
[[ "$hostlisten" == "127.0.0.1:17890" ]] && add bridge_bind GREEN "$hostlisten" || add bridge_bind RED "${hostlisten:-missing-or-not-loopback}"

if observed="$(/usr/local/bin/van-muse-egress-check 2>/dev/null)"; then
  add egress_identity GREEN "$observed"
else
  add egress_identity RED "expected $MUSE_EXPECTED_EGRESS_IP $MUSE_EXPECTED_COUNTRY"
fi

latest="$(ip netns exec van-muse wg show wg-muse latest-handshakes 2>/dev/null | awk '{print $2}' | head -1)"
now="$(date +%s)"
if [[ "$latest" =~ ^[0-9]+$ ]] && (( latest > 0 && now-latest < 180 )); then
  add wireguard_handshake GREEN "age=$((now-latest))s"
else
  add wireguard_handshake RED "latest=${latest:-none}"
fi

rules="$(ip netns exec van-muse nft list table inet van_muse_ns 2>/dev/null || true)"
grep -q '169.254.0.0/16' <<<"$rules" && grep -q '10.0.0.0/8' <<<"$rules" &&   add private_destination_policy GREEN present || add private_destination_policy RED missing

if ip netns exec van-muse curl -fsS --max-time 3 http://169.254.169.254/ >/dev/null 2>&1; then add metadata_block RED reachable; else add metadata_block GREEN blocked; fi
if ip netns exec van-muse curl -fsS --max-time 3 http://10.0.1.233/ >/dev/null 2>&1; then add trading_lan_block RED reachable; else add trading_lan_block GREEN blocked; fi

status=GREEN; ((fails)) && status=RED
jq -n --arg status "$status" --arg at "$(date -u +%Y-%m-%dT%H:%M:%SZ)"   --argjson failures "$fails" --argjson checks "[$(IFS=,; echo "${checks[*]}")]"   '{status:$status,required_failures:$failures,at:$at,checks:$checks}'
((fails==0))
