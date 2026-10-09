#!/usr/bin/env bash
# Owner decision 2026-09-29 §3 — qualify an installed van-private-core host.
#
# Never run: no van-private-core host exists yet (external provisioning gate). Prints one
# JSON report and exits 0 only when every required check is GREEN. A check that cannot be
# evaluated is PENDING, and PENDING is not GREEN.
set -uo pipefail

ENV_FILE="${VAN_PRIVATE_CORE_ENV:-/etc/van-private-core/runtime.env}"
[[ -r "$ENV_FILE" ]] && set -a && . "$ENV_FILE" && set +a

declare -a NAMES=() STATES=() DETAILS=()
record() { NAMES+=("$1"); STATES+=("$2"); DETAILS+=("$3"); }

# 1. The API is up, and bound to the private address only.
if systemctl is-active --quiet van-private-core.service 2>/dev/null; then
  record service_active GREEN "van-private-core.service active"
else
  record service_active RED "van-private-core.service not active"
fi
listeners="$(ss -Hltn 2>/dev/null | awk '{print $4}' | grep -E ":${VAN_PRIVATE_CORE_PORT:-9140}\$" || true)"
if [[ -n "$listeners" ]] && ! grep -qE '^(0\.0\.0\.0|\*|\[::\]|::):' <<<"$listeners" \
   && grep -qF "${VAN_PRIVATE_CORE_BIND:-unset}:" <<<"$listeners"; then
  record private_bind GREEN "$listeners"
else
  record private_bind RED "listeners=[${listeners//$'\n'/,}] expected ${VAN_PRIVATE_CORE_BIND:-unset} only"
fi

# 2. The plane hosts none of what it must not host.
# An inventory that cannot be read proves nothing: PENDING, never GREEN by absence.
if unit_files="$(systemctl list-unit-files --no-legend 2>/dev/null)"; then
  forbidden_units="$(awk '{print $1}' <<<"$unit_files" | grep -E '^(vati-|van-browser-)' || true)"
else
  forbidden_units=""; inventory_unreadable=1
fi
forbidden_procs="$(ps -eo comm= 2>/dev/null | grep -Ei '^(chrom|chromium|headless_shell|stagehand|playwright)' || true)"
forbidden_pkgs="$(dpkg-query -W -f='${Package}\n' 2>/dev/null | grep -Ei '^(chromium|google-chrome)' || true)"
if [[ -n "${inventory_unreadable:-}" ]]; then
  record no_forbidden_workloads PENDING "systemd unit inventory unreadable"
elif [[ -z "$forbidden_units$forbidden_procs$forbidden_pkgs" && ! -e /opt/van-trading ]]; then
  record no_forbidden_workloads GREEN "no browser, trading-execution or broker workloads"
else
  record no_forbidden_workloads RED "units=[${forbidden_units//$'\n'/,}] procs=[${forbidden_procs//$'\n'/,}] pkgs=[${forbidden_pkgs//$'\n'/,}]"
fi

# The service's own deployed tree and venv are pruned (A-MIN-VAN, reviewer D2). A host with
# no browser unit can still ship the code and packages that drive one inside the service's
# import path; this plane must not carry them at all.
core_root="${VAN_PRIVATE_CORE_ROOT:-/opt/van-private-core}"
core_src="$core_root/src"; core_venv="$core_root/venv"
if [[ ! -d "$core_src" || ! -d "$core_venv" ]]; then
  record deployed_tree_pruned PENDING "deployed tree or venv not found under $core_root"
elif ! tree_hits="$(find "$core_src" \( -type d -name trading \
        -o -path '*/van_gateway/browser' -o -path '*/van_gateway/automation' \
        -o -path '*/van_gateway/computer_use' -o -path '*/services/browser_*' \) -prune -print)" \
     || ! venv_hits="$(find "$core_venv" -path '*/site-packages/*' -prune \( -iname 'playwright*' \
        -o -iname 'patchright*' -o -iname 'browser_use*' -o -iname 'browser-use*' \) -print)"; then
  record deployed_tree_pruned PENDING "deployed tree or venv unreadable under $core_root"
elif [[ -z "$tree_hits$venv_hits" ]]; then
  record deployed_tree_pruned GREEN "$core_src and $core_venv carry no browser or trading code"
else
  record deployed_tree_pruned RED "src=[${tree_hits//$'\n'/,}] venv=[${venv_hits//$'\n'/,}]"
fi

# 3. The Owner Model store is private to the service account.
db="${VAN_DATABASE_PATH:-}"
if [[ "$db" == /var/lib/van-private-core/* && -f "$db" ]] \
   && [[ "$(stat -c '%U:%a' "$db")" == "van-private:600" ]]; then
  record owner_model_store GREEN "$db van-private:600"
else
  record owner_model_store RED "store=${db:-unset} must exist under /var/lib/van-private-core as van-private:600"
fi

# 4. Crossing requires both the client certificate and the scoped credential.
base="https://${VAN_PRIVATE_CORE_BIND:-127.0.0.1}:${VAN_PRIVATE_CORE_PORT:-9140}"
pki="${VAN_PRIVATE_CORE_PKI_DIR:-/opt/van-private-core/pki}"
no_cert="$(curl -s -o /dev/null -w '%{http_code}' --cacert "$pki/ca.crt" "$base/v1/private-core/owner-model/revision" 2>/dev/null || true)"
no_token="$(curl -s -o /dev/null -w '%{http_code}' --cacert "$pki/ca.crt" --cert "$pki/qualify-client.crt" --key "$pki/qualify-client.key" "$base/v1/private-core/owner-model/revision" 2>/dev/null || true)"
if [[ "$no_cert" == "000" && "$no_token" == "403" ]]; then
  record bounded_authenticated_api GREEN "no client cert: handshake refused; cert without token: 403"
else
  record bounded_authenticated_api RED "no_cert=$no_cert (want 000) no_token=$no_token (want 403)"
fi

# 5. Owner-private Hindsight and OpenViking projection: loopback on this host, or PENDING.
for svc in HINDSIGHT OPENVIKING; do
  dir_var="VAN_PRIVATE_${svc}_DIR"; dir="${!dir_var:-}"
  if [[ -n "$dir" && -d "$dir" ]]; then
    record "owner_private_${svc,,}" GREEN "$dir present"
  else
    record "owner_private_${svc,,}" PENDING "not provisioned (external gate)"
  fi
done

status=GREEN
printf '{"zone":"van-private-core","checks":['
for i in "${!NAMES[@]}"; do
  [[ $i -gt 0 ]] && printf ','
  printf '{"name":"%s","status":"%s","detail":"%s"}' "${NAMES[$i]}" "${STATES[$i]}" "${DETAILS[$i]//\"/\'}"
  [[ "${STATES[$i]}" != GREEN ]] && status=NOT_GREEN
done
printf '],"status":"%s"}\n' "$status"
[[ "$status" == GREEN ]]
