#!/usr/bin/env bash
# Install source and pinned runtime. No listeners start during setup or --dry-run.
set -euo pipefail
DRY_RUN=0
PROFILE_FILE=""
LEGACY=0
while [ "$#" -gt 0 ]; do
  case "$1" in
    --dry-run) DRY_RUN=1; shift ;;
    --profile) [ "$#" -ge 2 ] || { echo 'refused: missing profile file' >&2; exit 2; }; PROFILE_FILE="$2"; shift 2 ;;
    --legacy-single-profile) LEGACY=1; shift ;;
    *) echo 'refused: unknown bootstrap option' >&2; exit 2 ;;
  esac
done
ROOT=/opt/van-browser-stream
ETC=/etc/van-browser-stream
SRC_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
PACKAGE="$SRC_DIR/deploy/van-browser-stream"
# Production consists of two independently isolated profile stacks. Retain the
# old dry-run fixture for source compatibility; real legacy installation is explicit.
if [ -n "$PROFILE_FILE" ]; then
  RUNTIME_PYTHON="${VAN_BROWSER_RUNTIME_PYTHON:-$ROOT/venv/bin/python}"
  if [ ! -x "$RUNTIME_PYTHON" ]; then
    if [ "$DRY_RUN" = 1 ]; then
      echo 'refused: RUNTIME_NOT_INSTALLED — bind an existing pinned runtime Python' >&2
      exit 2
    fi
    command -v python3.12 >/dev/null || { echo 'refused: CPython 3.12 is required' >&2; exit 2; }
    mkdir -p "$ROOT"
    python3.12 -m venv "$ROOT/venv"
    "$ROOT/venv/bin/python" -m pip install --require-hashes -r "$PACKAGE/requirements.lock"
    RUNTIME_PYTHON="$ROOT/venv/bin/python"
  fi
  if ! PYTHONPATH="$SRC_DIR:$SRC_DIR/backend${PYTHONPATH:+:$PYTHONPATH}" "$RUNTIME_PYTHON" \
    -m services.browser_control_agent.server --check-runtime; then
    echo 'refused: RUNTIME_NOT_INSTALLED — pinned dependencies failed verification' >&2
    exit 2
  fi
  if [ "$DRY_RUN" = 1 ]; then
    exec "$RUNTIME_PYTHON" "$PACKAGE/install_profiles.py" --profile "$PROFILE_FILE" --dry-run
  fi
  [ -x "$ROOT/venv/bin/python" ] || { echo 'refused: managed pinned runtime missing' >&2; exit 2; }
  exec "$RUNTIME_PYTHON" "$PACKAGE/install_profiles.py" --profile "$PROFILE_FILE"
fi
if [ "$DRY_RUN" = 0 ] && [ "$LEGACY" = 0 ]; then
  echo 'refused: production requires --profile with isolated public and owner stacks' >&2
  exit 2
fi
say() { printf '  %s\n' "$*"; }
run() {
  if [ "$DRY_RUN" = 1 ]; then
    printf '  would:'
    printf ' %q' "$@"
    printf '\n'
  else
    "$@"
  fi
}
require_env() {
  local name="$1" why="$2"
  if [ -z "${!name:-}" ]; then
    printf 'refused: %s is not set — %s\n' "$name" "$why" >&2
    exit 2
  fi
}
echo '== preflight =='
require_env VAN_BROWSER_CONTROL_BIND 'a specific private VCN listener address is required'
require_env VAN_BROWSER_PROFILE_DEVICE 'an existing encrypted block device is required'
require_env VAN_BROWSER_STREAM_TLS_CERT 'the phone needs the provisioned signalling certificate'
require_env VAN_BROWSER_STREAM_TLS_KEY 'the signalling server needs its protected key file'
require_env VAN_BROWSER_GRANT_PUBLIC_KEY 'the host verifies, never mints, stream grants'
require_env VAN_BROWSER_BROKER_ORIGIN 'typed current authority comes from Trading Core HTTPS'
require_env VAN_BROWSER_BROKER_CA 'private broker TLS verification must be provisioned'
require_env VAN_BROWSER_CONTROL_BROKER_TOKEN_FILE 'the private control proxy needs its producer-scoped credential'
require_env VAN_BROWSER_STREAM_BROKER_TOKEN_FILE 'public media needs a different producer-scoped credential'
case "$VAN_BROWSER_CONTROL_BIND" in
  0.0.0.0|::|"") echo 'refused: control bind must be a private address' >&2; exit 2 ;;
esac
PYTHONPATH="$SRC_DIR:$SRC_DIR/backend${PYTHONPATH:+:$PYTHONPATH}" python3 -c \
  'import os; from services.browser_control_agent.server import require_private_bind; require_private_bind(os.environ["VAN_BROWSER_CONTROL_BIND"])'
if ! command -v chromium >/dev/null 2>&1 && ! command -v chromium-browser >/dev/null 2>&1; then
  echo 'refused: no chromium on PATH; provision a qualified recorded build first' >&2
  exit 2
fi
RUNTIME_PYTHON="${VAN_BROWSER_RUNTIME_PYTHON:-$ROOT/venv/bin/python}"
if [ ! -x "$RUNTIME_PYTHON" ]; then
  if [ "$DRY_RUN" = 1 ]; then
    echo 'refused: RUNTIME_NOT_INSTALLED — provide a pinned runtime Python for this side-effect-free dry run' >&2
    exit 2
  fi
  command -v python3.12 >/dev/null || { echo 'refused: CPython 3.12 is required' >&2; exit 2; }
  mkdir -p "$ROOT"
  python3.12 -m venv "$ROOT/venv"
  "$ROOT/venv/bin/pip" install --require-hashes -r "$PACKAGE/requirements.lock"
fi
# This mode reads installed distribution metadata only. It never binds a socket,
# reads PKI, creates a browser profile or calls the broker (including in --dry-run).
if ! PYTHONPATH="$SRC_DIR:$SRC_DIR/backend${PYTHONPATH:+:$PYTHONPATH}" "$RUNTIME_PYTHON" \
  -m services.browser_control_agent.server --check-runtime; then
  echo 'refused: RUNTIME_NOT_INSTALLED — pinned dependencies failed verification' >&2
  exit 2
fi

echo '== users =='
for user in van-browser van-control van-stream van-egress; do
  if id "$user" >/dev/null 2>&1; then say "$user exists"; else
    run useradd --system --no-create-home --shell /usr/sbin/nologin "$user"
  fi
done
if ! getent group van-browser-transfer >/dev/null; then run groupadd --system van-browser-transfer; fi
run usermod -a -G van-browser-transfer van-browser
run usermod -a -G van-browser-transfer van-stream

echo '== profile volume =='
run mkdir -p /var/lib/van-browser-profiles
if [ "$DRY_RUN" = 0 ] && ! mountpoint -q /var/lib/van-browser-profiles; then
  cryptsetup open "$VAN_BROWSER_PROFILE_DEVICE" van-browser-profiles
  mount /dev/mapper/van-browser-profiles /var/lib/van-browser-profiles
fi
run chown van-browser:van-browser /var/lib/van-browser-profiles
run chmod 700 /var/lib/van-browser-profiles
# The staging directory is on the same encrypted filesystem, exposed by a bind
# mount that excludes every browser profile. Neither public media nor control can
# traverse the profile volume; Chromium and media share only this staging group.
run mkdir -p /var/lib/van-browser-profiles/.transfers /var/lib/van-browser-transfers
run chown van-stream:van-browser-transfer /var/lib/van-browser-profiles/.transfers
run chmod 1770 /var/lib/van-browser-profiles/.transfers

echo '== source and runtime =='
run mkdir -p "$ROOT/src" "$ROOT/pki" "$ETC" /var/log/van-browser-stream
run rsync -a --delete --exclude=__pycache__ "$SRC_DIR/services" "$ROOT/src/"
run rsync -a --delete --exclude=__pycache__ "$SRC_DIR/backend/van_gateway" "$ROOT/src/"
run install -m 644 "$PACKAGE/requirements.lock" "$ROOT/requirements.lock"
# RUNTIME_PYTHON may be an existing external environment for checking, but the
# service always uses this managed venv. Build/install it when actually absent.
if [ ! -x "$ROOT/venv/bin/python" ]; then
  run python3.12 -m venv "$ROOT/venv"
  run "$ROOT/venv/bin/pip" install --require-hashes -r "$PACKAGE/requirements.lock"
fi

echo '== configuration =='
if [ -f "$ETC/runtime.env" ]; then
  say "$ETC/runtime.env exists; left unchanged"
else
  run install -m 600 -o root -g root "$PACKAGE/runtime.env.example" "$ETC/runtime.env"
  say 'wrote runtime.env example; bind the actual operator provisioned paths before starting'
fi
run install -m 644 "$VAN_BROWSER_GRANT_PUBLIC_KEY" "$ROOT/pki/grant-verify.pem"

echo '== units =='
for unit in van-browser-egress-proxy.service van-browser-chromium.service van-browser-control-agent.service van-browser-stream.service van-browser-transfer-stage.service; do
  run install -m 644 "$PACKAGE/systemd/$unit" "/etc/systemd/system/$unit"
done
run install -m 644 "$PACKAGE/van-browser-stream-tmpfiles.conf" /etc/tmpfiles.d/van-browser-stream.conf
run systemctl daemon-reload

echo 'installed. Nothing is running yet. Provision distinct producer-only credentials,'
echo 'PKI permissions and runtime.env, then enable the stage, Chromium, control and stream units.'
echo 'Run deploy/van-browser-stream/qualify.sh on the actual host; qualify.sh is the gate.'
echo 'Source checks and successful installation never establish phone or live-host acceptance.'
