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
    "commit": "$STRETCHY_COMMIT",
    "url": "http://127.0.0.1:5173"
  },
  "rive_cli": "$(rive --version 2>&1 | head -n1)"
}
EOF
chown "$FORGE_USER:$FORGE_USER" "$STATE_ROOT/production-v3.lock.json"
chmod 0644 "$STATE_ROOT/production-v3.lock.json"

log "validating repository production contract"
runuser -u "$FORGE_USER" -- env PYTHONPATH="$WORKSPACE" \
  "$PY_VENV/bin/python" -m tools.character_forge.production_cli --help >/dev/null

# The base bootstrap installs a forge-owned, checksum-pinned Node under INSTALL_ROOT. Use it
# explicitly: root's PATH may not carry a Node at all, and the one it does find may live in
# another user's home, which the forge user cannot (and should not) read.
NODE_BIN="$INSTALL_ROOT/node/current/bin"
if [[ -x "$NODE_BIN/node" && -x "$NODE_BIN/npm" ]]; then
  NODE_MAJOR="$("$NODE_BIN/node" -p 'process.versions.node.split(".")[0]')"
  [[ "$NODE_MAJOR" -ge 18 ]] || die "Stretchy Studio requires Node 18+"
  log "building pinned Stretchy Studio from package-lock.json"
  runuser -u "$FORGE_USER" -- env PATH="$NODE_BIN:/usr/local/bin:/usr/bin:/bin" HOME="$STATE_ROOT" \
    bash -c "cd '$VENDOR_ROOT/stretchystudio' && npm ci --no-audit --no-fund && npm run build"
  [[ -f "$VENDOR_ROOT/stretchystudio/dist/index.html" ]] || die "Stretchy Studio build produced no dist/index.html"
  cat > /etc/systemd/system/van-stretchy-studio.service <<EOF
[Unit]
Description=VAN Character Forge Stretchy Studio
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=$FORGE_USER
Group=$FORGE_USER
WorkingDirectory=$VENDOR_ROOT/stretchystudio
ExecStart=/usr/bin/python3 -m http.server 5173 --bind 127.0.0.1 --directory dist
Restart=on-failure
RestartSec=3
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ProtectHome=true

[Install]
WantedBy=multi-user.target
EOF
  systemctl daemon-reload
  systemctl enable --now van-stretchy-studio.service
  curl --fail --silent --show-error http://127.0.0.1:5173/ >/dev/null || die "Stretchy Studio health check failed"
  log "Stretchy Studio available to Commander/browser automation at http://127.0.0.1:5173"
else
  log "Forge Node.js missing at $NODE_BIN (run the base bootstrap); Stretchy source is pinned but editor build is skipped."
fi

if command -v nvidia-smi >/dev/null 2>&1; then
  log "GPU detected. See-through code is pinned, but production weights remain intentionally blocked."
else
  log "No NVIDIA GPU on this controller. Use the external GPU lane for See-through inference."
fi

log "Character Forge Production V3 controller bootstrap complete"
