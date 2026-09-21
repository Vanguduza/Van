#!/usr/bin/env bash
#
# Rev 1.5 §13 — install a Browser Stream Host.
#
# Idempotent: running it twice changes nothing the second time. It installs files, users and
# units; it does not decide whether the result is correct. That is `qualify.sh`, and the two
# are separate on purpose — a bootstrap that also judged itself would report success for
# having written the files it just wrote.
#
# It refuses rather than guesses. No public TLS certificate, no VCN address, no profile
# volume means it stops and says which, because every one of those has a wrong default that
# would look like it worked: 0.0.0.0, a self-signed certificate, a local directory standing
# in for an encrypted volume.
set -euo pipefail

DRY_RUN=0
[ "${1:-}" = "--dry-run" ] && DRY_RUN=1

ROOT="/opt/van-browser-stream"
ETC="/etc/van-browser-stream"
SRC_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

say() { printf '  %s\n' "$*"; }
run() { if [ "$DRY_RUN" = 1 ]; then printf '  would: %s\n' "$*"; else eval "$@"; fi; }

require_env() {
  local name="$1" why="$2"
  if [ -z "${!name:-}" ]; then
    echo "refused: $name is not set — $why" >&2
    exit 2
  fi
}

echo "== preflight =="
# These are the four things this package will not invent.
require_env VAN_BROWSER_CONTROL_BIND \
  "the control agent must bind to a private VCN address. 0.0.0.0 would put the only bridge to Chromium on the internet."
require_env VAN_BROWSER_PROFILE_DEVICE \
  "§13.5 option A needs an encrypted block device for the owner's browser profile. A plain directory is not that, and the difference is the owner's logged-in cookies."
require_env VAN_BROWSER_STREAM_TLS_CERT \
  "the public signalling endpoint needs a real certificate. A self-signed one means the phone cannot distinguish this host from anything else claiming to be it."
require_env VAN_BROWSER_GRANT_PUBLIC_KEY \
  "the host verifies BrowserStreamGrant tokens and never mints one; without the Gateway's public key it cannot tell a real grant from any other JWT."

case "$VAN_BROWSER_CONTROL_BIND" in
  0.0.0.0|::|"") echo "refused: VAN_BROWSER_CONTROL_BIND must be a specific private address" >&2; exit 2 ;;
esac

if ! command -v chromium >/dev/null 2>&1 && ! command -v chromium-browser >/dev/null 2>&1; then
  echo "refused: no chromium on PATH. This package does not install a browser: the version " \
       "that runs here is recorded in registries/remote_browser_dependencies.json and is a " \
       "provisioning decision, not something a script should pick." >&2
  exit 2
fi

echo "== users =="
# Two users, not one. The browser holds the owner's sessions; the agent holds the private
# key that lets Trading Core talk to it. A single user means a page escaping Chromium reads
# the control agent's client certificates.
for user in van-browser van-control; do
  if id "$user" >/dev/null 2>&1; then say "$user exists"; else
    run "useradd --system --no-create-home --shell /usr/sbin/nologin $user"
  fi
done

echo "== profile volume (§13.5 option A) =="
run "mkdir -p /var/lib/van-browser-profiles"
if [ "$DRY_RUN" = 0 ] && ! mountpoint -q /var/lib/van-browser-profiles; then
  say "opening $VAN_BROWSER_PROFILE_DEVICE as van-browser-profiles"
  cryptsetup open "$VAN_BROWSER_PROFILE_DEVICE" van-browser-profiles
  mount /dev/mapper/van-browser-profiles /var/lib/van-browser-profiles
fi
run "chown -R van-browser:van-browser /var/lib/van-browser-profiles"
run "chmod 700 /var/lib/van-browser-profiles"

echo "== source and venv =="
run "mkdir -p $ROOT/src $ROOT/pki $ETC /var/log/van-browser-stream"
run "rsync -a --delete $SRC_DIR/services $ROOT/src/"
run "python3 -m venv $ROOT/venv"
run "$ROOT/venv/bin/pip install --quiet --upgrade pip"

echo "== configuration =="
if [ -f "$ETC/runtime.env" ]; then
  say "$ETC/runtime.env exists; left alone"
else
  run "install -m 600 -o root -g root $(dirname "${BASH_SOURCE[0]}")/runtime.env.example $ETC/runtime.env"
  say "wrote $ETC/runtime.env from the example — edit it before starting the units"
fi
run "install -m 644 $VAN_BROWSER_GRANT_PUBLIC_KEY $ROOT/pki/grant-verify.pem"

echo "== units =="
for unit in van-browser-chromium.service van-browser-control-agent.service; do
  run "install -m 644 $(dirname "${BASH_SOURCE[0]}")/systemd/$unit /etc/systemd/system/$unit"
done
run "systemctl daemon-reload"

echo
echo "installed. Nothing is running yet, and nothing here has checked that this host is"
echo "safe to run it on. Next:"
echo
echo "    sudo bash deploy/van-browser-stream/pki/make-stream-pki.sh"
echo "    sudo systemctl enable --now van-browser-chromium van-browser-control-agent"
echo "    sudo bash deploy/van-browser-stream/qualify.sh"
echo
echo "qualify.sh is the gate. Until it exits 0, RB-002 and RB-010 stay BLOCKED."
