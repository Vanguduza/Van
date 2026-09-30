#!/usr/bin/env bash
set -uo pipefail
fails=0; checks=()
add(){ local n="$1" s="$2" d="$3"; checks+=("{\"check\":\"$n\",\"status\":\"$s\",\"detail\":$(printf '%s' "$d"|jq -Rs .)}"); [[ "$s" == GREEN ]] || fails=$((fails+1)); }
[[ $EUID -eq 0 ]] || { echo 'run as root' >&2; exit 2; }
[[ -f /etc/van-muse-egress.env ]] || { echo 'missing /etc/van-muse-egress.env' >&2; exit 2; }
# shellcheck disable=SC1091
set -a; . /etc/van-muse-egress.env; set +a
for u in van-muse-netns.service van-muse-socks.service van-muse-bridge.service; do
  systemctl is-active --quiet "$u" && add "$u" GREEN active || add "$u" RED "$(systemctl is-active "$u" 2>&1)"
done
ip netns list | grep -q '^van-muse\b' && add namespace GREEN present || add namespace RED missing
links="$(ip -n van-muse -o link show 2>/dev/null | awk -F': ' '{print $2}' | cut -d@ -f1 | sort -u | tr '\n' ' ')"
missing=""; extra=""
for x in lo muse-ns wg-muse; do grep -qw "$x" <<<"$links" || missing="$missing $x"; done
for x in $links; do [[ "$x" == lo || "$x" == muse-ns || "$x" == wg-muse ]] || extra="$extra $x"; done
[[ -z "$missing$extra" ]] && add namespace_links GREEN "$links" || add namespace_links RED "links=$links missing=$missing extra=$extra"
defroute="$(ip -n van-muse route show default 2>/dev/null)"
grep -q 'dev wg-muse' <<<"$defroute" && add default_route GREEN "$defroute" || add default_route RED "$defroute"
ss -ltnH | awk '{print $4}' | grep -q '^127\.0\.0\.1:17890$' && add bridge_bind GREEN 'loopback-only' || add bridge_bind RED '127.0.0.1:17890 missing'
if observed="$(/usr/local/bin/van-muse-egress-check 2>/dev/null)"; then add egress_ip GREEN "$observed"; else add egress_ip RED "expected ${MUSE_EXPECTED_EGRESS_IP:-unset}"; fi
if ip netns exec van-muse curl -fsS --max-time 3 http://169.254.169.254/ >/dev/null 2>&1; then add metadata_block RED reachable; else add metadata_block GREEN blocked; fi
if ip netns exec van-muse curl -fsS --max-time 3 http://10.0.1.233/ >/dev/null 2>&1; then add trading_lan_block RED reachable; else add trading_lan_block GREEN blocked; fi
status=GREEN; ((fails)) && status=RED
jq -n --arg status "$status" --arg at "$(date -u +%Y-%m-%dT%H:%M:%SZ)" --argjson failures "$fails" --argjson checks "[$(IFS=,; echo "${checks[*]}")]" '{status:$status,required_failures:$failures,at:$at,checks:$checks}'
((fails==0))
