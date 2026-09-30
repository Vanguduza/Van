#!/usr/bin/env bash
set -euo pipefail
[[ -f /etc/van-muse-egress.env ]] || exit 2
# shellcheck disable=SC1091
set -a; . /etc/van-muse-egress.env; set +a
trace="$(curl --proxy socks5h://127.0.0.1:17890 -fsS --max-time 12 https://www.cloudflare.com/cdn-cgi/trace)"
observed_ip="$(sed -n 's/^ip=//p' <<<"$trace" | tail -1)"
observed_country="$(sed -n 's/^loc=//p' <<<"$trace" | tail -1)"
[[ -n "$observed_ip" && "$observed_ip" == "$MUSE_EXPECTED_EGRESS_IP" ]] || {
  echo "egress IP mismatch: expected=$MUSE_EXPECTED_EGRESS_IP observed=${observed_ip:-none}" >&2; exit 10;
}
[[ "$observed_country" == "$MUSE_EXPECTED_COUNTRY" ]] || {
  echo "egress country mismatch: expected=$MUSE_EXPECTED_COUNTRY observed=${observed_country:-none}" >&2; exit 11;
}
printf '%s %s\n' "$observed_ip" "$observed_country"
