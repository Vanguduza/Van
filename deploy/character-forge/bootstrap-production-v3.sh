#!/usr/bin/env bash
set -Eeuo pipefail

INSTALL_ROOT="${CHARACTER_FORGE_INSTALL_ROOT:-/opt/dial-character-forge}"
STATE_ROOT="${CHARACTER_FORGE_STATE_ROOT:-/var/lib/dial-character-forge}"
WORKSPACE="${CHARACTER_FORGE_WORKSPACE:-$STATE_ROOT/work/Van}"
VENDOR_ROOT="${CHARACTER_FORGE_VENDOR_ROOT:-$INSTALL_ROOT/vendor}"
PY_VENV="${CHARACTER_FORGE_V3_VENV:-$INSTALL_ROOT/v3-venv}"
FORGE_USER="${CHARACTER_FORGE_USER:-vanforge}"

SEE_THROUGH_REPO="https://github.com/shitagaki-lab/see-through.git"
SEE_THROUGH_COMMIT="7f139bb25c46a0c8ac720d95ddab185fcda5451c"
STRETCHY_REPO="https://github.com/MangoLion/stretchystudio.git"
STRETCHY_COMMIT="24a83a27ba43e43e9d2e3de5e33994594e6199c2"

log(){ printf '[character-forge-v3] %s\n' "$*"; }
die(){ printf '[character-forge-v3] ERROR: %s\n' "$*" >&2; exit 1; }

[[ "$(id -u)" -eq 0 ]] || die "run as root"
command -v git >/dev/null || die "git missing; run the base Character Forge bootstrap first"
command -v python3 >/dev/null || die "python3 missing"
command -v rive >/dev/null || die "Rive CLI missing; run the base Character Forge bootstrap first"
[[ -d "$WORKSPACE/.git" ]] || die "VAN workspace missing at $WORKSPACE"

install -d -o "$FORGE_USER" -g "$FORGE_USER" -m 0755 \
  "$INSTALL_ROOT" "$STATE_ROOT" "$VENDOR_ROOT" "$STATE_ROOT/gpu-outbox" "$STATE_ROOT/gpu-inbox"

if [[ ! -x "$PY_VENV/bin/python" ]]; then
  python3 -m venv "$PY_VENV"
fi
"$PY_VENV/bin/pip" install --disable-pip-version-check --no-input "PyYAML==6.0.2"

pin_repo(){
  local repo="$1" commit="$2" target="$3"
  if [[ ! -d "$target/.git" ]]; then
    runuser -u "$FORGE_USER" -- git clone --filter=blob:none "$repo" "$target"
  fi
  runuser -u "$FORGE_USER" -- git -C "$target" fetch --depth=1 origin "$commit"
  runuser -u "$FORGE_USER" -- git -C "$target" checkout --detach "$commit"
  [[ "$(runuser -u "$FORGE_USER" -- git -C "$target" rev-parse HEAD)" == "$commit" ]] || die "failed to pin $target"
  [[ -z "$(runuser -u "$FORGE_USER" -- git -C "$target" status --porcelain)" ]] || die "vendor checkout dirty: $target"
}

log "pinning proposal-engine source trees"
pin_repo "$SEE_THROUGH_REPO" "$SEE_THROUGH_COMMIT" "$VENDOR_ROOT/see-through"
pin_repo "$STRETCHY_REPO" "$STRETCHY_COMMIT" "$VENDOR_ROOT/stretchystudio"

install -o root -g root -m 0755 /dev/stdin /usr/local/bin/van-character-forge-v3 <<EOF
#!/usr/bin/env bash
set -Eeuo pipefail
cd "$WORKSPACE"
exec "$PY_VENV/bin/python" -m tools.character_forge.production_cli "\$@"
EOF

cat > "$STATE_ROOT/production-v3.lock.json" <<EOF
{
  "workspace": "$WORKSPACE",
  "see_through": {
    "repository": "$SEE_THROUGH_REPO",
    "commit": "$SEE_THROUGH_COMMIT",
    "weights": "BLOCKED_PENDING_LICENSE_AND_HASH_LOCK"
  },
  "stretchy_studio": {
    "repository": "$STRETCHY_REPO",
    "commit": "$STRETCHY_COMMIT"
  },
  "rive_cli": "$(rive --version 2>&1 | head -n1)"
}
EOF
chown "$FORGE_USER:$FORGE_USER" "$STATE_ROOT/production-v3.lock.json"
chmod 0644 "$STATE_ROOT/production-v3.lock.json"

log "validating repository production contract"
runuser -u "$FORGE_USER" -- env PYTHONPATH="$WORKSPACE" \
  "$PY_VENV/bin/python" -m tools.character_forge.production_cli --help >/dev/null

if command -v node >/dev/null 2>&1 && command -v corepack >/dev/null 2>&1; then
  log "Node/corepack available; Stretchy Studio can be installed from the pinned source."
else
  log "Node/corepack absent; Stretchy source is pinned but editor dependencies are not installed."
fi

if command -v nvidia-smi >/dev/null 2>&1; then
  log "GPU detected. See-through code is pinned, but production weights remain intentionally blocked."
else
  log "No NVIDIA GPU on this controller. Use the external GPU lane for See-through inference."
fi

log "Character Forge Production V3 controller bootstrap complete"
