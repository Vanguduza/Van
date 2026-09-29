#!/usr/bin/env bash
#
# van-browser-core self-qualification (owner decision 2026-09-29 §1). JSON report; exits 0
# only when every required check is GREEN. A check it could not run is UNKNOWN, never GREEN.
#
# This is the host's view. The gateway's view is separate and stricter:
# van_gateway.automation.placement.stagehand_production_enabled(), which also requires the
# mTLS client identity, the owner-decided model and fresh worker health through the edge.
set -uo pipefail

ETC=/etc/van-browser-core
DATA=/var/lib/van-browser-core
PKI="$ETC/pki"
checks=()
fails=0
add() {
  local name="$1" status="$2" detail="$3" required="${4:-1}"
  checks+=("{\"check\":\"$name\",\"status\":\"$status\",\"required\":$required,\"detail\":$(printf '%s' "$detail" | jq -Rs .)}")
  if [[ "$status" != "GREEN" && "$required" == "1" ]]; then fails=$((fails+1)); fi
  return 0
}

# 1. The host is this zone and only this zone.
if grep -qx van-browser-core "$ETC/zone" 2>/dev/null; then add zone_marker GREEN "$ETC/zone"; else add zone_marker RED "zone marker missing or wrong"; fi
foreign=""
for marker in /opt/van-trading /var/lib/van-trading /etc/van-private-core /opt/van-private-core /etc/dial-control /opt/dial-control /etc/van-browser-stream; do
  [[ -e "$marker" ]] && foreign="$foreign $marker"
done
[[ -z "$foreign" ]] && add dedicated_host GREEN "no other zone installed" || add dedicated_host RED "foreign zone present:$foreign"
if systemctl list-unit-files 'vati-*' --no-legend 2>/dev/null | grep -q .; then add no_trading_units RED "vati-* units present on the browser zone"; else add no_trading_units GREEN "no vati-* units"; fi

# 2. Workers are loopback-only; the edge is the only non-loopback listener and is not wildcard.
listeners="$(ss -ltnH 2>/dev/null | awk '{print $4}')"
if [[ -z "$listeners" ]]; then add listeners UNKNOWN "ss unavailable"; else
  bad="$(printf '%s\n' "$listeners" | grep -E ':(9140|9141)$' | grep -Ev '^(127\.0\.0\.1|\[::1\]):' || true)"
  [[ -z "$bad" ]] && add workers_loopback_only GREEN "9140/9141 loopback" || add workers_loopback_only RED "$bad"
  wild="$(printf '%s\n' "$listeners" | grep -E '^(0\.0\.0\.0|\*|\[::\]):9443$' || true)"
  [[ -z "$wild" ]] && add edge_not_wildcard GREEN "9443 bound to a specific address" || add edge_not_wildcard RED "$wild"
fi

# 3. Worker identity.
if curl -fsS --max-time 3 http://127.0.0.1:9140/health >/tmp/vbcq-sh.json 2>/dev/null \
   && jq -e '.ok==true and .trust_zone=="van-browser-core" and .runtime_version=="4.1.0" and .runtime_version_source=="installed-package-metadata" and .act_endpoint_enabled==false and .stagehand_release_commit=="cd7b230778cf92269e4cb90e80d97f5113781c51" and .model_name=="anthropic/claude-sonnet-5" and .direct_agent_loop==false and .model_self_selection==false' /tmp/vbcq-sh.json >/dev/null; then
  add stagehand_identity GREEN "$(jq -c '{runtime_version,runtime_version_source,act_endpoint_enabled,trust_zone,model_name,model_key_present,provider_key_in_browser_memory}' /tmp/vbcq-sh.json)"
else add stagehand_identity RED "Stagehand health missing or not the van-browser-core 4.1.0 / anthropic/claude-sonnet-5 worker"; fi
if curl -fsS --max-time 3 http://127.0.0.1:9141/health >/tmp/vbcq-h.json 2>/dev/null \
   && jq -e '.ok==true and .trust_zone=="van-browser-core" and .runtime_version=="0.1.13" and .helper_authoring==false and .raw_cdp_http==false' /tmp/vbcq-h.json >/dev/null; then
  add harness_identity GREEN "$(jq -c '{runtime_version,trust_zone}' /tmp/vbcq-h.json)"
else add harness_identity RED "Harness health missing or not the van-browser-core worker"; fi

# 4. The edge refuses callers without a certificate from this zone's CA, and refuses /act.
EDGE_BIND="$(sed -n 's/^VAN_BROWSER_CORE_EDGE_BIND=//p' "$ETC/runtime.env" 2>/dev/null | tail -1)"
if [[ -n "$EDGE_BIND" ]]; then
  URL="https://$EDGE_BIND:9443/stagehand/health"
  if curl -fsS --max-time 5 --cacert "$PKI/ca.crt" "$URL" >/dev/null 2>&1; then add edge_refuses_no_cert RED "answered without a client certificate"; else add edge_refuses_no_cert GREEN "refused"; fi
  if [[ -f "$PKI/foreign-client.crt" ]]; then
    if curl -fsS --max-time 5 --cacert "$PKI/ca.crt" --cert "$PKI/foreign-client.crt" --key "$PKI/foreign-client.key" "$URL" >/dev/null 2>&1; then add edge_refuses_foreign_ca RED "accepted a foreign-CA certificate"; else add edge_refuses_foreign_ca GREEN "refused"; fi
  else add edge_refuses_foreign_ca UNKNOWN "run pki/make-browser-core-pki.sh --with-foreign-test-cert"; fi
  client="$(ls "$PKI"/client-*.crt 2>/dev/null | head -1)"
  if [[ -n "$client" ]]; then
    code="$(curl -s -o /dev/null -w '%{http_code}' --max-time 5 --cacert "$PKI/ca.crt" --cert "$client" --key "${client%.crt}.key" -X POST -H 'content-type: application/json' --data '{}' "https://$EDGE_BIND:9443/stagehand/act")"
    [[ "$code" == 404 ]] && add edge_refuses_stagehand_act GREEN "404" || add edge_refuses_stagehand_act RED "HTTP $code"
  else add edge_refuses_stagehand_act UNKNOWN "no client certificate on this host to probe with (expected: moved to van-gateway)"; fi
else add edge_configured RED "VAN_BROWSER_CORE_EDGE_BIND not set"; fi

# 5. No foreign-zone credential names in this zone's runtime environment.
if [[ -f "$ETC/runtime.env" ]] && grep -Eq '^(VAN_COMMANDER_|VAN_ACCOUNTS_REGISTRY|VAN_OWNER_AUTHORITY_KEYS|VAN_DATABASE_PATH|VAN_VATI_|DERIV_|CTRADER_|BRIDGE_|POSTGRES_PASSWORD|SERVICE_ROLE_KEY|VAN_INTERNAL_CONTROL|VAN_DEVICE_|HINDSIGHT|OPENVIKING|GITHUB_TOKEN|GH_TOKEN)' "$ETC/runtime.env"; then
  add runtime_env_clean RED "foreign-zone credential name in $ETC/runtime.env"
else add runtime_env_clean GREEN "no foreign-zone credential names"; fi

# 6. Model pin status (§4): informational, required=0. UNVERIFIED is not GREEN.
add model_immutable_snapshot UNKNOWN "immutable provider revision for claude-sonnet-5 not established" 0

printf '{"zone":"van-browser-core","fails":%d,"checks":[%s]}\n' "$fails" "$(IFS=,; echo "${checks[*]}")"
[[ "$fails" == 0 ]]
