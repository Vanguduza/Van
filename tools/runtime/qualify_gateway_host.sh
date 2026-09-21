#!/usr/bin/env bash
#
# GAP-F-018 / GAP-F-021 — decide whether an installed VAN Gateway host is actually a
# production host, rather than a development default that was never turned off.
#
# `install_van_gateway_service.sh` completing proves the files were copied and the unit
# was started. It proves nothing about whether device binding is enforced, whether the
# owner ingress is real credentials rather than an empty default, or whether the process
# that answered "active" also answers a real HTTP request correctly. Those are the facts
# this script exists to check, on the host, after install.
#
# Every check is GREEN or RED. There is no AMBER here: `config.py`'s own
# `assert_production_safe` already refuses to construct a `Settings` with the load-bearing
# defects (unbound devices, a loopback Hermes/public URL) when `VAN_ENV=production`, so if
# the process is running at all with that env file, those two are structurally satisfied —
# this script's job is to prove the env file the process actually reads carries the
# settings a release host needs, and that the running process answers for them.
#
# Usage: tools/runtime/qualify_gateway_host.sh
# Exit 0 and "GREEN" on stdout with the deployed commit SHA when every check passes;
# exit 1 and "RED" with the failing checks otherwise.
set -uo pipefail

STATE_ROOT="${VAN_STATE_ROOT:-$HOME/.local/share/van}"
RUNTIME_ROOT="$STATE_ROOT/runtime"
CONFIG_ROOT="${VAN_CONFIG_ROOT:-$HOME/.config/van}"
GATEWAY_ENV="$CONFIG_ROOT/gateway.env"
#: Where the installed unit actually listens (deploy/systemd/van-gateway.service pins
#: this exact host:port). Overridable for a host that fronts it differently.
HEALTH_URL="${VAN_GATEWAY_HEALTH_URL:-http://127.0.0.1:8787/health}"

checks_ok=0
checks_total=0
fail_names=()

# check NAME CONDITION_COMMAND DETAIL_ON_FAIL
check() {
  local name="$1" detail="$3"
  checks_total=$((checks_total + 1))
  if eval "$2"; then
    checks_ok=$((checks_ok + 1))
    echo "GREEN  $name"
  else
    fail_names+=("$name")
    echo "RED    $name — $detail"
  fi
}

echo "VAN Gateway host qualification — $(hostname) — $(date -u +%Y-%m-%dT%H:%M:%SZ)"
echo

check "env_file_present" \
  '[[ -f "$GATEWAY_ENV" ]]' \
  "no gateway env file at $GATEWAY_ENV"

# Every remaining env-file check needs the file's contents. Reading it into the shell's
# own environment (rather than grepping line by line) means a value that spans a
# continuation or is quoted differently is still read the way the process itself reads it.
if [[ -f "$GATEWAY_ENV" ]]; then
  set -a
  # shellcheck disable=SC1090
  . "$GATEWAY_ENV"
  set +a
fi

check "van_env_is_production" \
  '[[ "${VAN_ENV:-}" == "production" ]]' \
  "VAN_ENV=${VAN_ENV:-<unset>} (must be 'production'; config.py's assert_production_safe only runs its release-host checks when this is set)"

check "device_binding_required" \
  '[[ "${VAN_REQUIRE_DEVICE_BINDING:-}" =~ ^([Tt]rue|1)$ ]]' \
  "VAN_REQUIRE_DEVICE_BINDING=${VAN_REQUIRE_DEVICE_BINDING:-<unset>} (GAP-F-018 — a production gateway must not accept token-only mutations from an unbound device)"

check "ingress_token_set" \
  '[[ -n "${VAN_INGRESS_TOKEN:-}" && "${#VAN_INGRESS_TOKEN}" -ge 32 ]]' \
  "VAN_INGRESS_TOKEN is unset or shorter than 32 characters"

check "scoped_control_tokens_configured" \
  '[[ -n "${VAN_INTERNAL_CONTROL_SCOPED_TOKENS:-}" ]]' \
  "VAN_INTERNAL_CONTROL_SCOPED_TOKENS is unset (P0-SEC-001 — Hermes has no per-purpose credential, only the legacy all-scopes token if that is set)"

check "device_secret_fernet_key_set" \
  '[[ -n "${VAN_DEVICE_SECRET_FERNET_KEY:-}" ]]' \
  "VAN_DEVICE_SECRET_FERNET_KEY is unset (Android HMAC secrets would have nothing to encrypt at rest under)"

check "google_token_fernet_key_set" \
  '[[ -n "${VAN_GOOGLE_TOKEN_FERNET_KEY:-}" ]]' \
  "VAN_GOOGLE_TOKEN_FERNET_KEY is unset (Google refresh tokens would have nothing to encrypt at rest under)"

health_body="$(mktemp)"
trap 'rm -f "$health_body"' EXIT
health_code="000"
if [[ -n "${VAN_INGRESS_TOKEN:-}" ]]; then
  health_code="$(curl -fsS -o "$health_body" -w '%{http_code}' --max-time 5 \
    -H "X-Van-Ingress-Token: ${VAN_INGRESS_TOKEN}" \
    "$HEALTH_URL" 2>/dev/null || echo "000")"
fi
check "health_authenticated_200" \
  '[[ "$health_code" == "200" ]]' \
  "GET $HEALTH_URL with the configured ingress token returned '$health_code', not 200 — either the unit is not running or the credential the file carries is not the one the process accepted"

echo
if (( checks_ok == checks_total )); then
  sha="unknown"
  [[ -f "$RUNTIME_ROOT/DEPLOYED_SHA" ]] && sha="$(cat "$RUNTIME_ROOT/DEPLOYED_SHA")"
  echo "GREEN — $checks_ok/$checks_total checks passed — deployed commit $sha"
  exit 0
else
  echo "RED — $checks_ok/$checks_total checks passed — failing: ${fail_names[*]}"
  exit 1
fi
