#!/usr/bin/env bash
set -euo pipefail
[[ -f /etc/van-muse-sandbox.env ]] || exit 2
# shellcheck disable=SC1091
set -a; . /etc/van-muse-sandbox.env; set +a
RUNTIME_DIR="/run/van-browser/muse_owner"
install -d -o van-browser -g van-browser -m 0700 "$RUNTIME_DIR"
tmp="$RUNTIME_DIR/.cdp-endpoint.json.tmp"
jq -n   --arg alias muse_owner   --arg url "http://127.0.0.1:$MUSE_SANDBOX_CDP_PORT"   --arg managed_by "van-muse-sandbox"   '{profile_alias:$alias,cdp_url:$url,external_managed:true,managed_by:$managed_by}' >"$tmp"
chown van-browser:van-browser "$tmp"
chmod 0600 "$tmp"
mv -f "$tmp" "$RUNTIME_DIR/cdp-endpoint.json"
