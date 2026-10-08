#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
STATE_ROOT="${VAN_STATE_ROOT:-$HOME/.local/share/van}"
CONFIG_ROOT="${VAN_CONFIG_ROOT:-$HOME/.config/van}"
STATE_ROOT="$(realpath -m -- "$STATE_ROOT")"
CONFIG_ROOT="$(realpath -m -- "$CONFIG_ROOT")"
RUNTIME_ROOT="$STATE_ROOT/runtime"
VENV="$STATE_ROOT/venv"
GOOGLE_ENV="$CONFIG_ROOT/google-workspace.env"
GATEWAY_ENV="$CONFIG_ROOT/gateway.env"
OWNER_CORE_ENV="${VAN_OWNER_CORE_PROFILE_ENV:-$CONFIG_ROOT/owner-core.env}"
UNIT_SRC="$ROOT/deploy/systemd/van-gateway.service"
UNIT_DST="$HOME/.config/systemd/user/van-gateway.service"

for required in "$GOOGLE_ENV" "$GATEWAY_ENV" "$UNIT_SRC"; do
  if [[ ! -f "$required" ]]; then
    echo "FAIL missing_required_file:$required" >&2
    exit 2
  fi
done

# Production installs attest the requested immutable source, never an uncommitted
# workspace mislabeled with HEAD. Stage-only remains available for local review.
PRODUCTION=$(VAN_ENV_READER_ROOT="$ROOT/tools/runtime" VAN_GATEWAY_ENV="$GATEWAY_ENV" VAN_OWNER_CORE_PROFILE_ENV="$OWNER_CORE_ENV" VAN_CONFIG_DIRECTORY="$CONFIG_ROOT" python3 - <<'MODE'
import os, sys
from pathlib import Path
sys.path.insert(0, os.environ["VAN_ENV_READER_ROOT"])
from preflight_owner_core import effective_environment
config = Path(os.environ["VAN_CONFIG_DIRECTORY"])
values = effective_environment(config / "google-workspace.env", Path(os.environ["VAN_GATEWAY_ENV"]),
                               config / "trading-commander.env", Path(os.environ["VAN_OWNER_CORE_PROFILE_ENV"]))
mode = values.get("VAN_ENV", os.environ.get("VAN_ENV", ""))
print("1" if mode.lower() == "production" else "0")
MODE
)
if [[ "${VAN_INSTALL_STAGE_ONLY:-}" != "1" && ( "$PRODUCTION" == "1" || -n "${VAN_EXPECTED_REPOSITORY_SHA:-}" ) ]]; then
  EXPECTED_SHA="${VAN_EXPECTED_REPOSITORY_SHA:-}"
  [[ "$EXPECTED_SHA" =~ ^[0-9a-f]{40}$ ]] || { echo "FAIL immutable_expected_repository_sha_required" >&2; exit 2; }
  [[ "$(git -C "$ROOT" rev-parse HEAD)" == "$EXPECTED_SHA" ]] || { echo "FAIL repository_sha_mismatch" >&2; exit 2; }
  [[ -z "$(git -C "$ROOT" status --porcelain --untracked-files=all)" ]] || { echo "FAIL deployment_repository_not_clean" >&2; exit 2; }
fi
OWNER_CORE_RESOURCE_DROPIN="${VAN_OWNER_CORE_RESOURCE_DROPIN:-${UNIT_DST}.d/owner-core-resources.conf}"
if [[ -f "$OWNER_CORE_ENV" && "${VAN_INSTALL_STAGE_ONLY:-}" != "1" ]]; then
  [[ -f "$OWNER_CORE_RESOURCE_DROPIN" ]] || { echo "FAIL owner_core_resource_dropin_required" >&2; exit 2; }
  python3 "$ROOT/tools/runtime/preflight_owner_core.py" --profile-env "$OWNER_CORE_ENV" \
    --gateway-env "$GATEWAY_ENV" --google-env "$GOOGLE_ENV" --trading-env "$CONFIG_ROOT/trading-commander.env" \
    --resource-dropin "$OWNER_CORE_RESOURCE_DROPIN" \
    --repository "$ROOT" --expected-sha "$VAN_EXPECTED_REPOSITORY_SHA"
fi

mkdir -p "$STATE_ROOT" "$CONFIG_ROOT" "$HOME/.config/systemd/user"
chmod 700 "$STATE_ROOT" "$CONFIG_ROOT"
chmod 600 "$GOOGLE_ENV" "$GATEWAY_ENV"
# Serialize this installer's local publication and dependency preparation. The
# admitted estate recipe still owns its wider deployment/ingress lock.
exec 9>"$STATE_ROOT/install.lock"
flock -n 9 || { echo "FAIL gateway_install_in_progress" >&2; exit 2; }

# Device HMAC credentials must survive gateway restarts without being stored in plaintext.
# Generate the dedicated Fernet key once, keep it owner-readable only, and never print it.
if ! grep -Eq '^VAN_DEVICE_SECRET_FERNET_KEY=.+$' "$GATEWAY_ENV"; then
  DEVICE_KEY="$(python3 - <<'KEYPY'
import base64, secrets
print(base64.urlsafe_b64encode(secrets.token_bytes(32)).decode('ascii'))
KEYPY
)"
  TMP_ENV="$(mktemp "$CONFIG_ROOT/gateway.env.XXXXXX")"
  grep -Ev '^VAN_DEVICE_SECRET_FERNET_KEY=' "$GATEWAY_ENV" > "$TMP_ENV" || true
  printf 'VAN_DEVICE_SECRET_FERNET_KEY=%s\n' "$DEVICE_KEY" >> "$TMP_ENV"
  install -m 0600 "$TMP_ENV" "$GATEWAY_ENV"
  rm -f "$TMP_ENV"
  unset DEVICE_KEY
fi

# Public tunnel access is gated again at the VAN application boundary.
# Generate the owner ingress bearer once and keep it out of logs/process args.
if ! grep -Eq '^VAN_INGRESS_TOKEN=.{32,}$' "$GATEWAY_ENV"; then
  INGRESS_TOKEN="$(python3 - <<'INGRESSPY'
import secrets
print(secrets.token_urlsafe(48))
INGRESSPY
)"
  TMP_ENV="$(mktemp "$CONFIG_ROOT/gateway.env.XXXXXX")"
  grep -Ev '^VAN_INGRESS_TOKEN=' "$GATEWAY_ENV" > "$TMP_ENV" || true
  printf 'VAN_INGRESS_TOKEN=%s\n' "$INGRESS_TOKEN" >> "$TMP_ENV"
  install -m 0600 "$TMP_ENV" "$GATEWAY_ENV"
  rm -f "$TMP_ENV"
  unset INGRESS_TOKEN
fi

STAGE="$(mktemp -d "$STATE_ROOT/runtime.stage.XXXXXX")"
trap 'rm -rf "$STAGE"' EXIT
mkdir -p "$STAGE/backend"
cp -a "$ROOT/backend/van_gateway" "$STAGE/backend/"
cp "$ROOT/backend/requirements.txt" "$STAGE/backend/requirements.txt"
cp "$ROOT/backend/requirements.lock" "$STAGE/backend/requirements.lock"
cp -a "$ROOT/registries" "$STAGE/registries"
cp -a "$ROOT/config" "$STAGE/config"
install -d "$STAGE/docs" "$STAGE/tools"
cp -a "$ROOT/docs/decisions" "$STAGE/docs/decisions"
cp -a "$ROOT/tools/certification" "$STAGE/tools/certification"
# `van_gateway.trading.accounts` puts <runtime>/trading on sys.path and imports `commander`
# from it. Without this copy the gateway crashes at startup; runtimes that worked had it
# placed by hand. The trading test suite is not runtime code.
tar -C "$ROOT" --exclude='trading/tests' --exclude='__pycache__' -cf - trading | tar -C "$STAGE" -xf -
# The private interactive browser caller is part of the core runtime, not a
# separately installed media dependency. Stage its shared narrow wire package.
tar -C "$ROOT" --exclude='*/tests' --exclude='__pycache__' -cf - services | tar -C "$STAGE" -xf -
# GAP-F-018/021 — `qualify_gateway_host.sh` reports the deployed commit on a GREEN
# qualification. The staged runtime is a plain `cp -a`, not a git checkout, so the SHA has
# to be captured here, at the one point that still has the source tree's git metadata.
git -C "$ROOT" rev-parse HEAD > "$STAGE/DEPLOYED_SHA" 2>/dev/null || echo "unknown" > "$STAGE/DEPLOYED_SHA"
VAN_SOURCE_ROOT="$ROOT" VAN_SOURCE_STAGE="$STAGE" python3 - <<'SOURCE'
import hashlib, json, os, subprocess
from pathlib import Path
root = os.environ["VAN_SOURCE_ROOT"]
sha = subprocess.check_output(["git", "-C", root, "rev-parse", "HEAD"], text=True).strip()
dirty = bool(subprocess.check_output(["git", "-C", root, "status", "--porcelain", "--untracked-files=all"], text=True))
stage = Path(os.environ["VAN_SOURCE_STAGE"])
runtime_hashes = {str(path.relative_to(stage)): hashlib.sha256(path.read_bytes()).hexdigest()
                  for directory in ("backend", "registries", "trading", "services") for path in (stage / directory).rglob("*")
                  if path.is_file() and "__pycache__" not in path.parts and path.suffix != ".pyc"}
config = Path(os.environ.get("VAN_CONFIG_ROOT", str(Path.home() / ".config/van")))
configuration = {name: hashlib.sha256((config / name).read_bytes()).hexdigest()
                 for name in ("google-workspace.env", "gateway.env", "trading-commander.env") if (config / name).is_file()}
profile = Path(os.environ.get("VAN_OWNER_CORE_PROFILE_ENV", str(config / "owner-core.env")))
if profile.is_file():
    configuration["owner-core.env"] = hashlib.sha256(profile.read_bytes()).hexdigest()
Path(os.environ["VAN_SOURCE_STAGE"], "DEPLOYED_SOURCE.json").write_text(json.dumps({
    "schema_version": 1, "repository_sha": sha, "source_clean": not dirty,
    "expected_repository_sha": os.environ.get("VAN_EXPECTED_REPOSITORY_SHA", ""),
    "live_qualified": False,
    "runtime_sha256": runtime_hashes, "configuration_sha256": configuration,
}) + "\n")
SOURCE
# GAP-F-017 — install from the exact-pinned lock, not the floating spec. Two installs of
# the same commit must resolve to the same bytes; requirements.txt alone cannot promise
# that once any dependency ships a new release between them.
if [[ "${VAN_INSTALL_STAGE_ONLY:-}" != "1" ]]; then
  # Never pip-install into the interpreter a serving runtime uses. Its unit retains
  # the exact previous interpreter until publication, including on a failed install.
  LOCK_SHA="$(python3 -c 'import hashlib, sys; print(hashlib.sha256(open(sys.argv[1], "rb").read()).hexdigest())' "$STAGE/backend/requirements.lock")"
  VENV="$STATE_ROOT/venvs/$LOCK_SHA"
  if [[ -f "$VENV/VAN_REQUIREMENTS.lock" ]]; then
    cmp -s "$STAGE/backend/requirements.lock" "$VENV/VAN_REQUIREMENTS.lock" \
      && [[ -x "$VENV/bin/python" ]] \
      || { echo "FAIL immutable_dependency_environment_changed" >&2; exit 2; }
  else
    [[ ! -e "$VENV" ]] || { echo "FAIL incomplete_dependency_environment_requires_reconciliation" >&2; exit 2; }
    if ! python3 -m venv "$VENV" \
        || ! "$VENV/bin/python" -m pip install --quiet -r "$STAGE/backend/requirements.lock"; then
      rm -rf "$VENV"
      echo "FAIL staged_dependency_install: serving interpreter unchanged" >&2
      exit 4
    fi
    install -m 0600 "$STAGE/backend/requirements.lock" "$VENV/VAN_REQUIREMENTS.lock"
  fi
else
  if [[ -f "$RUNTIME_ROOT/RUNTIME_PYTHON_PATH" ]]; then
    RUNTIME_PYTHON="$(cat "$RUNTIME_ROOT/RUNTIME_PYTHON_PATH")"
    [[ "$RUNTIME_PYTHON" == "$STATE_ROOT"/venvs/*/bin/python && "$RUNTIME_PYTHON" != *$'\n'* ]] \
      || { echo "FAIL runtime_interpreter_binding_invalid" >&2; exit 2; }
    VENV="${RUNTIME_PYTHON%/bin/python}"
  fi
  [[ -x "$VENV/bin/python" ]] || { echo "FAIL stage_only_requires_existing_dependency_interpreter" >&2; exit 2; }
fi
python3 "$ROOT/tools/runtime/render_systemd_unit.py" --service gateway --home "$HOME" \
  --state-root "$STATE_ROOT" --config-root "$CONFIG_ROOT" --python "$VENV/bin/python" \
  --output "$STAGE/van-gateway.service"
printf '%s\n' "$VENV/bin/python" > "$STAGE/RUNTIME_PYTHON_PATH"
VAN_SOURCE_STAGE="$STAGE" VAN_RUNTIME_INTERPRETER="$VENV/bin/python" python3 - <<'INTERPRETER'
import hashlib, json, os
from pathlib import Path
stage = Path(os.environ["VAN_SOURCE_STAGE"])
path = stage / "DEPLOYED_SOURCE.json"
metadata = json.loads(path.read_text())
metadata["runtime_python"] = os.environ["VAN_RUNTIME_INTERPRETER"]
metadata["requirements_sha256"] = hashlib.sha256((stage / "backend/requirements.lock").read_bytes()).hexdigest()
for name in ("RUNTIME_PYTHON_PATH", "van-gateway.service"):
    metadata["runtime_sha256"][name] = hashlib.sha256((stage / name).read_bytes()).hexdigest()
path.write_text(json.dumps(metadata) + "\n")
INTERPRETER

# Pre-flight: the staged runtime must build the app with this host's real environment
# *before* it replaces the running one. A runtime that cannot start never takes the
# gateway down; the old one keeps serving and this install fails instead.
if ! (cd "$STAGE/backend" && PYTHONPATH="$STAGE/backend:$STAGE" \
      VAN_GOOGLE_ENV="$GOOGLE_ENV" VAN_GATEWAY_ENV="$GATEWAY_ENV" \
      VAN_OWNER_CORE_PROFILE_ENV="$OWNER_CORE_ENV" \
      VAN_TRADING_ENV="$CONFIG_ROOT/trading-commander.env" \
      VAN_ENV_READER_ROOT="$ROOT/tools/runtime" \
      timeout 120 "$VENV/bin/python" - <<'PREFLIGHT'
import os, sys
from pathlib import Path
sys.path.insert(0, os.environ["VAN_ENV_READER_ROOT"])
from preflight_owner_core import effective_environment
paths = {key: Path(os.environ[key]) for key in ("VAN_GOOGLE_ENV", "VAN_GATEWAY_ENV", "VAN_TRADING_ENV", "VAN_OWNER_CORE_PROFILE_ENV")}
# A deployment shell is not the systemd manager. Check only explicitly bound unit
# files; ambient VAN_* settings cannot make an incomplete host configuration pass.
for key in tuple(os.environ):
    if key.startswith("VAN_"):
        del os.environ[key]
os.environ.update(effective_environment(paths["VAN_GOOGLE_ENV"], paths["VAN_GATEWAY_ENV"],
                                       paths["VAN_TRADING_ENV"], paths["VAN_OWNER_CORE_PROFILE_ENV"]))
import van_gateway.app  # noqa: F401  builds the app exactly as the unit's process does
import van_gateway.mtls.serve  # noqa: F401
PREFLIGHT
    ); then
  echo "FAIL van_gateway_preflight: the staged runtime cannot build the app; the running gateway was not touched" >&2
  exit 4
fi
echo "PASS van_gateway_preflight"
if [[ "${VAN_INSTALL_STAGE_ONLY:-}" == "1" ]]; then
  # Never the live runtime: stage-only must be safe to run on a serving host.
  rm -rf "$STATE_ROOT/runtime.staged"
  mv "$STAGE" "$STATE_ROOT/runtime.staged"
  trap - EXIT
  echo "staged=$STATE_ROOT/runtime.staged (the running runtime and unit were not touched)"
  exit 0
fi

rm -rf "$RUNTIME_ROOT.previous"
if [[ -d "$RUNTIME_ROOT" ]]; then
  mv "$RUNTIME_ROOT" "$RUNTIME_ROOT.previous"
fi
mv "$STAGE" "$RUNTIME_ROOT"
trap - EXIT

install -m 0644 "$RUNTIME_ROOT/van-gateway.service" "$UNIT_DST"
if [[ -f "$OWNER_CORE_ENV" && "$OWNER_CORE_ENV" != "$CONFIG_ROOT/owner-core.env" ]]; then
  install -m 0600 "$OWNER_CORE_ENV" "$CONFIG_ROOT/owner-core.env"
fi
if [[ -f "$OWNER_CORE_ENV" ]]; then
  mkdir -p "${UNIT_DST}.d"
  if [[ "$OWNER_CORE_RESOURCE_DROPIN" != "${UNIT_DST}.d/owner-core-resources.conf" ]]; then
    install -m 0644 "$OWNER_CORE_RESOURCE_DROPIN" "${UNIT_DST}.d/owner-core-resources.conf"
  fi
fi
systemctl --user daemon-reload
systemctl --user enable van-gateway.service >/dev/null
systemctl --user restart van-gateway.service

for _ in {1..20}; do
  if VAN_GATEWAY_ENV="$GATEWAY_ENV" VAN_ENV_READER_ROOT="$ROOT/tools/runtime" "$VENV/bin/python" - <<'HEALTH'
import os, sys
import urllib.request
from pathlib import Path
class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None

env_path = Path(os.environ["VAN_GATEWAY_ENV"])
sys.path.insert(0, os.environ["VAN_ENV_READER_ROOT"])
from preflight_owner_core import effective_environment
values = effective_environment(env_path.parent / "google-workspace.env", env_path,
                               env_path.parent / "trading-commander.env", env_path.parent / "owner-core.env")
token = values.get("VAN_INGRESS_TOKEN", "")
if not token:
    raise SystemExit(1)
request = urllib.request.Request(
    "http://127.0.0.1:" + values.get("VAN_LOOPBACK_PORT", "8787") + "/health",
    headers={"X-Van-Ingress-Token": token},
)
try:
    with urllib.request.build_opener(NoRedirect).open(request, timeout=2) as r:
        raise SystemExit(0 if r.status == 200 else 1)
except Exception:
    raise SystemExit(1)
HEALTH
  then
    echo "PASS van_gateway_http_ready"
    echo "runtime=$RUNTIME_ROOT"
    echo "service=van-gateway.service"
    exit 0
  fi
  sleep 1
done

systemctl --user --no-pager --full status van-gateway.service >&2 || true
echo "FAIL van_gateway_health_timeout" >&2
exit 3
