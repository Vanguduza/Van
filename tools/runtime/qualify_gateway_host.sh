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
HEALTH_URL_INPUT="${VAN_GATEWAY_HEALTH_URL:-}"
EXPECTED_SOURCE_SHA="${VAN_EXPECTED_REPOSITORY_SHA:-}"
ENV_READER_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

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
  # EnvironmentFile is data, not shell source. Never execute command substitution
  # or credentials copied into a config value during a qualification probe.
  for variable in "${!VAN_@}"; do unset "$variable"; done
  while IFS= read -r assignment; do
    export "$assignment"
  done < <(VAN_CONFIG_ROOT="$CONFIG_ROOT" VAN_ENV_READER_ROOT="$ENV_READER_ROOT" python3 - <<'ENV_DATA'
import os, sys
from pathlib import Path
root = Path(os.environ["VAN_CONFIG_ROOT"])
sys.path.insert(0, os.environ["VAN_ENV_READER_ROOT"])
from preflight_owner_core import read_environment, effective_environment
# Google file is mandatory for installation; legacy host checks may inspect an
# incomplete host, so absence supplies no secret and fails the relevant checks.
values = read_environment(root / "gateway.env")
if (root / "google-workspace.env").is_file():
    values = effective_environment(root / "google-workspace.env", root / "gateway.env",
                                   root / "trading-commander.env", root / "owner-core.env")
else:
    for path in (root / "trading-commander.env", root / "owner-core.env"):
        if path.is_file():
            values.update(read_environment(path))
for key, value in values.items():
    print(f"{key}={value}")
ENV_DATA
)
fi
HEALTH_URL="${HEALTH_URL_INPUT:-http://127.0.0.1:${VAN_LOOPBACK_PORT:-8787}/health}"

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

health_code="000"
if [[ -n "${VAN_INGRESS_TOKEN:-}" ]]; then
  health_code="$(VAN_GATEWAY_HEALTH_URL="$HEALTH_URL" python3 - <<'HEALTH'
import os, urllib.request
from urllib.parse import urlsplit
class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None
url = os.environ["VAN_GATEWAY_HEALTH_URL"]
parsed = urlsplit(url)
# This is a host-local probe. Never forward an ingress credential to an arbitrary URL.
if parsed.scheme != "http" or parsed.hostname not in {"127.0.0.1", "localhost", "::1"} or parsed.path != "/health" or parsed.username or parsed.password or parsed.query or parsed.fragment:
    print("000")
else:
    request = urllib.request.Request(url, headers={"X-Van-Ingress-Token": os.environ["VAN_INGRESS_TOKEN"]})
    try:
        with urllib.request.build_opener(NoRedirect).open(request, timeout=5) as reply:
            print(reply.status)
    except Exception:
        print("000")
HEALTH
)"
fi
check "health_authenticated_200" \
  '[[ "$health_code" == "200" ]]' \
  "GET $HEALTH_URL with the configured ingress token returned '$health_code', not 200 — either the unit is not running or the credential the file carries is not the one the process accepted"

source_matches="0"
if [[ -n "$EXPECTED_SOURCE_SHA" ]]; then
  source_matches="$(VAN_RUNTIME_ROOT="$RUNTIME_ROOT" VAN_SOURCE_EXPECTED_SHA="$EXPECTED_SOURCE_SHA" python3 - <<'SOURCE'
import hashlib, json, os, re
from pathlib import Path
try:
    root = Path(os.environ["VAN_RUNTIME_ROOT"])
    metadata = json.loads((root / "DEPLOYED_SOURCE.json").read_text())
    expected = os.environ["VAN_SOURCE_EXPECTED_SHA"]
    valid = bool(re.fullmatch(r"[0-9a-f]{40}", expected)) and metadata.get("source_clean") is True and metadata.get("repository_sha") == expected and (root / "DEPLOYED_SHA").read_text().strip() == expected
    hashes = metadata.get("runtime_sha256")
    valid = valid and isinstance(hashes, dict) and bool(hashes)
    if valid:
        for name, digest in hashes.items():
            path = Path(name)
            if path.is_absolute() or ".." in path.parts or hashlib.sha256((root / path).read_bytes()).hexdigest() != digest:
                valid = False
                break
    print("1" if valid else "0")
except (OSError, ValueError, KeyError):
    print("0")
SOURCE
)"
fi
check "immutable_clean_source_matches" '[[ "$source_matches" == "1" ]]' \
  "external VAN_EXPECTED_REPOSITORY_SHA and a matching clean deployment receipt are required"

echo
if (( checks_ok == checks_total )); then
  sha="unknown"
  [[ -f "$RUNTIME_ROOT/DEPLOYED_SHA" ]] && sha="$(cat "$RUNTIME_ROOT/DEPLOYED_SHA")"
  echo "GREEN — $checks_ok/$checks_total local host checks passed — deployed commit $sha (owner/Hermes/device E2E unverified)"
  exit 0
else
  echo "RED — $checks_ok/$checks_total checks passed — failing: ${fail_names[*]}"
  exit 1
fi
