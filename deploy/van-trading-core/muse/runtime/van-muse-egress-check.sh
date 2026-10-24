#!/usr/bin/env bash
set -euo pipefail
[[ -f /etc/van-muse-egress.env ]] || exit 2
# shellcheck disable=SC1091
set -a; . /etc/van-muse-egress.env; set +a

fail_closed(){
  local code="$1"; shift
  logger -t van-muse-egress "FAIL_CLOSED $*"
  systemctl --no-block stop van-muse-bridge.service >/dev/null 2>&1 || true
  echo "$*" >&2
  exit "$code"
}

trace="$(curl --proxy socks5h://127.0.0.1:17890 -fsS --max-time 12 https://www.cloudflare.com/cdn-cgi/trace)" ||   fail_closed 9 "unable to verify Muse egress"
observed_ip="$(sed -n 's/^ip=//p' <<<"$trace" | tail -1)"
observed_country="$(sed -n 's/^loc=//p' <<<"$trace" | tail -1)"

[[ -n "$observed_ip" && "$observed_ip" == "$MUSE_EXPECTED_EGRESS_IP" ]] ||   fail_closed 10 "egress IP mismatch expected=$MUSE_EXPECTED_EGRESS_IP observed=${observed_ip:-none}"
[[ "$observed_country" == "$MUSE_EXPECTED_COUNTRY" ]] ||   fail_closed 11 "egress country mismatch expected=$MUSE_EXPECTED_COUNTRY observed=${observed_country:-none}"

printf '%s %s\n' "$observed_ip" "$observed_country"
