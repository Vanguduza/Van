#!/usr/bin/env bash
# Additive, exact-source BRC agent install on van-trading-core. Does not enable or pair the agent.
set -Eeuo pipefail
umask 027

readonly EXPECTED_HOST='van-trading-core'
readonly UPSTREAM='https://github.com/shahidx0x/better-remote-commander.git'
readonly PIN='cbe511702dd0147650353c29ac6ab1decd8afda1'
readonly EXPECTED_VERSION='2.0.2'
readonly SERVICE_USER='vanbrc'
readonly SERVICE_HOME='/var/lib/van-brc'
readonly SRC="$SERVICE_HOME/releases/$PIN"
readonly WORKSPACE="$SERVICE_HOME/work/Van"
readonly STATE="$SERVICE_HOME/state"
readonly UNIT='/etc/systemd/system/van-brc-agent.service'
readonly ENV_PATH='/etc/van-brc/agent.env'
MODE="${1:---dry-run}"

fail() { echo "BRC_INSTALL_REFUSED: $*" >&2; exit 2; }
[[ "$MODE" == '--dry-run' || "$MODE" == '--apply' ]] || fail 'usage: install-agent.sh --dry-run|--apply'
[[ "$(hostname)" == "$EXPECTED_HOST" ]] || fail "wrong host: $(hostname)"
[[ "$(uname -m)" == 'aarch64' ]] || fail 'expected OCI A1 aarch64'
for bin in node git corepack systemctl runuser; do command -v "$bin" >/dev/null 2>&1 || fail "missing $bin"; done
[[ -x /usr/bin/node ]] || fail 'Node.js must be at /usr/bin/node for hardened systemd unit'
/usr/bin/node -e 'const [a,b]=process.versions.node.split(".").map(Number);if(a<22||(a===22&&b<13))process.exit(1)' \
  || fail 'BRC requires Node.js >=22.13; refused to modify system Node'
[[ "$(df -Pk / | awk 'NR==2 {print $4}')" -ge 2097152 ]] || fail 'less than 2 GiB of root-disk headroom'
[[ "$(free -m | awk '/^Mem:/ {print $7}')" -ge 1024 ]] || fail 'less than 1 GiB of available RAM'

if id "$SERVICE_USER" >/dev/null 2>&1; then
  [[ "$(getent passwd "$SERVICE_USER" | cut -d: -f6)" == "$SERVICE_HOME" ]] || fail 'preexisting vanbrc user has unexpected home'
  for forbidden in root sudo docker vati; do
    id -nG "$SERVICE_USER" | tr ' ' '\n' | grep -Fxq "$forbidden" && fail "vanbrc member of forbidden group: $forbidden"
  done
fi
if [[ -e "$UNIT" ]] && ! grep -Fq 'X-VAN-BRC-AGENT-MANAGED=1' "$UNIT"; then
  fail 'existing unit name is not managed by this installer'
fi
cat <<INFO
BRC_INSTALL_PLAN=READY
host=$EXPECTED_HOST
arch=aarch64
upstream_commit=$PIN
version=$EXPECTED_VERSION
service_identity=$SERVICE_USER
source_directory=$SRC
workspace=$WORKSPACE
service_unit=$UNIT
relay_config=$ENV_PATH
run_state=NOT_MODIFIED
INFO
[[ "$MODE" == '--apply' ]] || exit 0
[[ "$(id -u)" -eq 0 ]] || fail '--apply requires root under an owner-authorized host execution route'

if ! id "$SERVICE_USER" >/dev/null 2>&1; then
  useradd --system --create-home --home-dir "$SERVICE_HOME" --shell /usr/sbin/nologin "$SERVICE_USER"
fi
passwd -l "$SERVICE_USER" >/dev/null 2>&1 || :
for forbidden in root sudo docker vati; do
  id -nG "$SERVICE_USER" | tr ' ' '\n' | grep -Fxq "$forbidden" && fail "vanbrc member of forbidden group: $forbidden"
done
install -d -o "$SERVICE_USER" -g "$SERVICE_USER" -m 0750 "$SERVICE_HOME" "$SERVICE_HOME/releases" "$SERVICE_HOME/work"
install -d -o "$SERVICE_USER" -g "$SERVICE_USER" -m 0700 "$STATE"
install -d -o root -g root -m 0750 /etc/van-brc

# Fetch exactly one upstream immutable commit; use its frozen dependency graph.
if [[ ! -d "$SRC/.git" ]]; then
  install -d -o "$SERVICE_USER" -g "$SERVICE_USER" -m 0750 "$SRC"
  runuser -u "$SERVICE_USER" -- git -C "$SRC" init -q
  runuser -u "$SERVICE_USER" -- git -C "$SRC" remote add origin "$UPSTREAM"
  runuser -u "$SERVICE_USER" -- git -C "$SRC" fetch --depth 1 -q origin "$PIN"
  runuser -u "$SERVICE_USER" -- git -C "$SRC" checkout --detach -q FETCH_HEAD
fi
[[ "$(runuser -u "$SERVICE_USER" -- git -C "$SRC" rev-parse HEAD)" == "$PIN" ]] || fail 'source pin mismatch'
[[ "$(node -p "require('$SRC/packages/agent/package.json').version")" == "$EXPECTED_VERSION" ]] || fail 'source package version mismatch'
[[ "$(node -p "require('$SRC/packages/shared/package.json').version")" == "$EXPECTED_VERSION" ]] || fail 'shared protocol version mismatch'

(
  cd "$SRC"
  runuser -u "$SERVICE_USER" -- env HOME="$SERVICE_HOME" COREPACK_ENABLE_DOWNLOAD_PROMPT=0 corepack pnpm install --frozen-lockfile --filter 'brc-agent...' --config.confirmModulesPurge=false
  runuser -u "$SERVICE_USER" -- env HOME="$SERVICE_HOME" COREPACK_ENABLE_DOWNLOAD_PROMPT=0 corepack pnpm --filter brc-shared build
  runuser -u "$SERVICE_USER" -- env HOME="$SERVICE_HOME" COREPACK_ENABLE_DOWNLOAD_PROMPT=0 corepack pnpm --filter brc-agent build
)
[[ -f "$SRC/packages/agent/dist/cli.js" ]] || fail 'agent CLI build absent'

# BRC may edit its copy, not the live /opt/van-trading production tree.
if [[ ! -e "$WORKSPACE" ]]; then
  runuser -u "$SERVICE_USER" -- git clone -q --depth 1 https://github.com/Vanguduza/Van.git "$WORKSPACE"
fi
[[ -d "$WORKSPACE/.git" ]] || fail 'sandbox repository not a Git checkout'

unit_tmp="$(mktemp /etc/systemd/system/.van-brc-agent.XXXXXXXX)"
trap 'rm -f "$unit_tmp"' EXIT
cat >"$unit_tmp" <<UNIT
[Unit]
Description=Better Remote Commander restricted outbound agent for VAN
Documentation=https://github.com/shahidx0x/better-remote-commander
After=network-online.target
Wants=network-online.target
ConditionPathExists=$ENV_PATH

[Service]
Type=simple
User=$SERVICE_USER
Group=$SERVICE_USER
WorkingDirectory=$WORKSPACE
Environment=HOME=$SERVICE_HOME
Environment=BRC_HOME=$STATE
EnvironmentFile=$ENV_PATH
ExecStart=/usr/bin/node $SRC/packages/agent/dist/cli.js --relay \${BRC_RELAY} --name van-trading-core --allow-dir $WORKSPACE --no-browser
Restart=on-failure
RestartSec=15
NoNewPrivileges=true
CapabilityBoundingSet=
AmbientCapabilities=
PrivateDevices=true
PrivateTmp=true
ProtectSystem=strict
ProtectHome=true
ReadWritePaths=$SERVICE_HOME
ProtectKernelModules=true
ProtectKernelTunables=true
ProtectControlGroups=true
RestrictSUIDSGID=true
LockPersonality=true
MemoryMax=768M
CPUQuota=50%
UMask=0077
# X-VAN-BRC-AGENT-MANAGED=1

[Install]
WantedBy=multi-user.target
UNIT
chmod 0644 "$unit_tmp"
install -o root -g root -m 0644 "$unit_tmp" "$UNIT"
systemctl daemon-reload
# Never enable automatically: owner must pair with an authenticated HTTPS relay.
[[ ! -e "$ENV_PATH" ]] || echo 'BRC_ENV_PRESERVED=EXISTING'
echo BRC_AGENT_INSTALL=INSTALLED_NOT_PAIRED
printf 'service_enabled='; systemctl is-enabled van-brc-agent.service 2>/dev/null || :
echo BRC_TRADING_SERVICES=UNTOUCHED
