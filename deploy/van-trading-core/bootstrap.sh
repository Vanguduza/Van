#!/usr/bin/env bash
# =============================================================================
# van-trading-core bootstrap — Ubuntu 24.04 ARM64 (OCI VM.Standard.A1.Flex, 2 OCPU / 12 GB)
#
# Installs, idempotently and fail-closed, everything the trading estate needs on this host:
#   python3.12 + venv (Ubuntu 24.04 ships 3.12)   node 22 (NodeSource)   docker + compose plugin
#   vati service user, /opt/van-trading layout, secrets (0700), commander + VEKL tokens, bridge PKI
#   repo checkout, venv with requirements-vm.txt [+ nautilus_trader at --with-nautilus]
#   local Supabase (PostgreSQL authority store) + post-bootstrap VATI ledger reconciliation
#   systemd: vati-supabase, vati-vekl, vati-commander, vati-session@<alias> (enabled per account)
#   ufw: deny incoming; 22 and 9133 only from oracle-admin + dial-hermes-control /32s
#
# MetaTrader 5 CANNOT run on this host: MT5 is a Windows x86-64 program and this VM is ARM64
# Linux. The MT5 bridge worker runs on a Windows host (windows/mt5_worker) and this VM holds only
# the bridge CLIENT (mTLS). The script records that fact instead of pretending.
#
# Usage:  sudo bash bootstrap.sh [--dry-run] [--with-nautilus] [--repo-url URL] [--branch NAME] [--skip-supabase] [--skip-docker]
# Re-running is safe; each step checks its own state.
# =============================================================================
set -euo pipefail

DRY_RUN=0; WITH_NAUTILUS=0; SKIP_SUPABASE=0; SKIP_DOCKER=0; PUBLIC_HOST="${VAN_PUBLIC_HOST:-}"
REPO_URL="${VAN_REPO_URL:-https://github.com/Vanguduza/Van.git}"
BRANCH="${VAN_BRANCH:-main}"
for a in "$@"; do case "$a" in
  --dry-run) DRY_RUN=1;; --with-nautilus) WITH_NAUTILUS=1;; --skip-supabase) SKIP_SUPABASE=1;; --skip-docker) SKIP_DOCKER=1;;
  --repo-url=*) REPO_URL="${a#*=}";; --branch=*) BRANCH="${a#*=}";; --public-host=*) PUBLIC_HOST="${a#*=}";;
  *) echo "unknown arg $a" >&2; exit 2;; esac; done

BASE=/opt/van-trading; APP=$BASE/app; VENV=$BASE/venv; SECRETS=$BASE/secrets; CONFIG=$BASE/config; DATA=/var/lib/van-trading; LOGS=/var/log/van-trading
ADMIN_CIDRS="${VAN_ADMIN_CIDRS:-10.0.0.123/32,10.0.0.184/32}"; CORE_IP="${VAN_CORE_IP:-10.0.1.233}"
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
STEPS=(); ok() { STEPS+=("OK   $1"); echo "[bootstrap] OK   $1"; }; skip() { STEPS+=("SKIP $1"); echo "[bootstrap] SKIP $1"; }; plan() { STEPS+=("PLAN $1"); echo "[bootstrap] PLAN $1"; }
run() { if (( DRY_RUN )); then plan "$*"; else "$@"; fi; }
die() { echo "[bootstrap] ERROR: $*" >&2; exit 1; }

# ---------------------------------------------------------------- preflight
ARCH="$(uname -m)"; . /etc/os-release 2>/dev/null || true
echo "[bootstrap] host=$(hostname) arch=$ARCH os=${PRETTY_NAME:-unknown} dry_run=$DRY_RUN"
if (( ! DRY_RUN )); then
  [[ "$(id -u)" == "0" ]] || die "run as root (sudo)"
  [[ "${ID:-}" == "ubuntu" && "${VERSION_ID:-}" == "24.04" ]] || die "expects Ubuntu 24.04 (got ${PRETTY_NAME:-?})"
fi
MT5_NATIVE=0; [[ "$ARCH" == "x86_64" ]] && MT5_NATIVE=1
if (( ! MT5_NATIVE )); then echo "[bootstrap] NOTE: $ARCH host — MetaTrader 5 cannot run here; only the MT5 bridge client is installed. Use windows/mt5_worker on a Windows host."; fi

# ---------------------------------------------------------------- packages
export DEBIAN_FRONTEND=noninteractive
export NEEDRESTART_MODE="${NEEDRESTART_MODE:-a}"
apt_update() {
  local n
  for n in $(seq 1 60); do
    apt-get -o Acquire::Retries=3 update -qq && return 0
    echo "[bootstrap] apt update retry $n/60" >&2; sleep 5
  done
  die "apt update did not succeed within retry window"
}
apt_install() {
  local n
  for n in $(seq 1 60); do
    apt-get -o Acquire::Retries=3 install -y -qq --no-install-recommends "$@" >/dev/null && return 0
    echo "[bootstrap] apt install retry $n/60: $*" >&2; sleep 5
  done
  die "apt install did not succeed within retry window: $*"
}
write_keyring() {
  local url="$1" out="$2" tmp
  tmp="$(mktemp)"; rm -f "$tmp"
  curl -fsSL "$url" | gpg --batch --yes --dearmor -o "$tmp"
  install -m 0644 "$tmp" "$out"; rm -f "$tmp"
}
if (( ! DRY_RUN )); then
  apt_update
  apt_install ca-certificates curl gnupg git jq ufw openssl build-essential python3.12 python3.12-venv python3-pip python3-yaml rsync
fi
python3.12 --version >/dev/null 2>&1 || (( DRY_RUN )) || die "python3.12 missing after install"
for b in curl gpg git jq ufw openssl rsync; do command -v "$b" >/dev/null 2>&1 || (( DRY_RUN )) || die "$b missing after base package install"; done
ok "apt base packages (python3.12, venv, yaml, ufw, openssl, jq, git)"

if ! command -v node >/dev/null 2>&1 || [[ "$(node -v | cut -c2- | cut -d. -f1)" -ne 22 ]]; then
  if (( DRY_RUN )); then plan "install Node 22 from NodeSource (deb.nodesource.com/node_22.x, key verified via signing key)"; else
    install -m 0755 -d /etc/apt/keyrings
    write_keyring https://deb.nodesource.com/gpgkey/nodesource-repo.gpg.key /etc/apt/keyrings/nodesource.gpg
    echo "deb [signed-by=/etc/apt/keyrings/nodesource.gpg] https://deb.nodesource.com/node_22.x nodistro main" > /etc/apt/sources.list.d/nodesource.list
    apt_update; apt_install nodejs
  fi
  command -v node >/dev/null 2>&1 || (( DRY_RUN )) || die "node missing after install"
  (( DRY_RUN )) || [[ "$(node -v | cut -c2- | cut -d. -f1)" -ge 20 ]] || die "node version too old after install: $(node -v)"
  ok "node 22"
else skip "node $(node -v) present"; fi

if (( ! SKIP_DOCKER )); then
  if ! command -v docker >/dev/null 2>&1 || ! docker compose version >/dev/null 2>&1; then
    if (( DRY_RUN )); then plan "install docker-ce + compose plugin from download.docker.com (arm64)"; else
      install -m 0755 -d /etc/apt/keyrings
      write_keyring https://download.docker.com/linux/ubuntu/gpg /etc/apt/keyrings/docker.gpg
      echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu ${VERSION_CODENAME} stable" > /etc/apt/sources.list.d/docker.list
      apt_update; apt_install docker-ce docker-ce-cli containerd.io docker-compose-plugin
      command -v docker >/dev/null 2>&1 || die "docker missing after install"
      docker compose version >/dev/null 2>&1 || die "docker compose plugin missing after install"
      systemctl enable --now docker
      systemctl is-active --quiet docker || die "docker service not active after enable"
    fi
    ok "docker engine + compose plugin"
  else skip "docker present"; fi
fi

# ---------------------------------------------------------------- user + layout
if ! id vati >/dev/null 2>&1; then run useradd --system --home-dir "$BASE" --shell /usr/sbin/nologin vati; ok "user vati"; else skip "user vati exists"; fi
for d in "$BASE" "$APP" "$CONFIG" "$CONFIG/sessions" "$DATA" "$DATA/heartbeats" "$DATA/lake" "$DATA/vekl" "$DATA/backtests" "$LOGS"; do run install -d -o vati -g vati -m 0750 "$d"; done
run install -d -o vati -g vati -m 0700 "$SECRETS" "$SECRETS/pki"
ok "layout under $BASE, $DATA, $LOGS"

# ---------------------------------------------------------------- repo
if [[ -d "$APP/.git" ]]; then
  run sudo -u vati git -C "$APP" fetch -q origin "$BRANCH"; run sudo -u vati git -C "$APP" checkout -q "$BRANCH"; run sudo -u vati git -C "$APP" reset -q --hard "origin/$BRANCH"; ok "repo updated to origin/$BRANCH"
else
  run sudo -u vati git clone -q --branch "$BRANCH" "$REPO_URL" "$APP"; ok "repo cloned ($BRANCH)"
fi

# ---------------------------------------------------------------- python venv
if [[ ! -x "$VENV/bin/python" ]]; then run sudo -u vati python3.12 -m venv "$VENV"; ok "venv (python3.12)"; else skip "venv present"; fi
run sudo -u vati "$VENV/bin/pip" install -q --upgrade pip
run sudo -u vati "$VENV/bin/pip" install -q -r "$APP/deploy/van-trading-core/requirements-vm.txt"
ok "python requirements"
if (( WITH_NAUTILUS )); then run sudo -u vati "$VENV/bin/pip" install -q "nautilus_trader==1.231.0"; ok "nautilus_trader 1.231.0 (Phase 3 donor gate acknowledged by --with-nautilus)"; else skip "nautilus_trader (pass --with-nautilus at the Phase 3 gate)"; fi

# ---------------------------------------------------------------- secrets + pki
gen_token() { local f="$1"; if [[ ! -f "$f" ]]; then run bash -c "umask 077; openssl rand -hex 32 > '$f'"; run chown vati:vati "$f"; ok "token $f"; else skip "token $f exists"; fi; }
gen_token "$SECRETS/commander.token"; gen_token "$SECRETS/vekl.token"
if [[ ! -f "$SECRETS/pki/ca.crt" ]]; then run bash -c "OUT='$SECRETS/pki' CORE_IP='$CORE_IP' bash '$HERE/pki/make-bridge-pki.sh' >/dev/null"; run chown -R vati:vati "$SECRETS/pki"; ok "bridge PKI (ca, commander, mt5-worker, client)"; else skip "PKI present"; fi

# ---------------------------------------------------------------- config
if [[ ! -f "$CONFIG/van-trading-core.env" ]]; then run install -o root -g vati -m 0640 "$HERE/env/van-trading-core.env.example" "$CONFIG/van-trading-core.env"; ok "config env"; else skip "config env exists"; fi
if [[ ! -f "$CONFIG/accounts.json" ]]; then run bash -c "echo '{\"schema_version\": 1, \"accounts\": []}' > '$CONFIG/accounts.json'"; run chown vati:vati "$CONFIG/accounts.json"; run chmod 0640 "$CONFIG/accounts.json"; ok "empty account registry (add accounts with: sudo -u vati $VENV/bin/python -m vati accounts add ...)"; fi

# ---------------------------------------------------------------- supabase
if (( ! SKIP_SUPABASE )); then
  run install -d -o root -g root -m 0750 "$BASE/supabase" "$BASE/supabase/init"
  run rsync -a --chown=root:root "$HERE/supabase/docker-compose.yml" "$HERE/supabase/docker-compose.override.yml" "$HERE/supabase/env.example" "$HERE/supabase/DONOR_PROVENANCE.json" "$BASE/supabase/"
  [[ -d "$HERE/supabase/volumes" ]] || die "vendored Supabase volumes tree missing"
  for rel in api/envoy/cds.yaml api/envoy/docker-entrypoint.sh api/envoy/envoy.yaml api/envoy/lds.template.yaml db/_supabase.sql db/jwt.sql db/logs.sql db/pooler.sql db/realtime.sql db/roles.sql db/webhooks.sql pooler/pooler.exs; do
    [[ -f "$HERE/supabase/volumes/$rel" ]] || die "required Supabase bind source missing: volumes/$rel"
  done
  run rsync -a --chown=root:root "$HERE/supabase/volumes/" "$BASE/supabase/volumes/"
  run rsync -a "$HERE/supabase/init/01_vati_ledger.sql.tpl" "$BASE/supabase/init/"
  if [[ ! -f "$BASE/supabase/.env" ]]; then run bash "$HERE/supabase/generate-env.sh" "$BASE/supabase/.env"; ok "supabase secrets generated (0600)"; else skip "supabase .env exists"; fi
  if (( ! DRY_RUN )); then
    PW="$(grep '^VATI_LEDGER_PASSWORD=' "$BASE/supabase/.env" | cut -d= -f2-)"
    [[ -n "$PW" ]] || die "VATI_LEDGER_PASSWORD missing from Supabase env"
    chmod 0640 "$CONFIG/van-trading-core.env"
    chown root:vati "$CONFIG/van-trading-core.env"
    (cd "$BASE/supabase" && docker compose --env-file .env pull -q) || die "supabase image pull failed (arm64 images must resolve)"
  else plan "docker compose pull (supabase arm64 images)"; fi
  run install -m 0644 "$HERE/systemd/vati-supabase.service" /etc/systemd/system/vati-supabase.service
  ok "supabase staged under $BASE/supabase (loopback only)"
fi

# ---------------------------------------------------------------- systemd
for u in vati-commander.service vati-vekl.service vati-session@.service vati-mt5-pull.service; do run install -m 0644 "$HERE/systemd/$u" "/etc/systemd/system/$u"; done
run install -d -m 0755 /etc/polkit-1/rules.d
run install -m 0644 "$HERE/systemd/vati-polkit-restart.rules" /etc/polkit-1/rules.d/49-vati-restart.rules
run systemctl daemon-reload
if (( ! SKIP_SUPABASE )); then
  run systemctl enable --now vati-supabase.service
  if (( DRY_RUN )); then
    plan "reconcile VATI ledger role/schema against persisted Supabase secret"
  else
    "$VENV/bin/python" "$HERE/supabase/recover_donor_migrations.py" --container supabase-db
    systemctl restart vati-supabase.service
    "$VENV/bin/python" "$HERE/supabase/reconcile_vati_ledger.py" \
      --env "$BASE/supabase/.env" \
      --template "$HERE/supabase/init/01_vati_ledger.sql.tpl" \
      --core-env "$CONFIG/van-trading-core.env"
  fi
  ok "VATI ledger role/schema reconciled"
fi
run systemctl enable --now vati-vekl.service
run systemctl enable --now vati-commander.service
run systemctl enable --now vati-mt5-pull.service
ok "systemd units installed and enabled (sessions: systemctl enable --now vati-session@<alias> after adding an account)"

# ---------------------------------------------------------------- automation + browser fabric
if [[ -n "$PUBLIC_HOST" ]]; then
  if (( DRY_RUN )); then plan "bootstrap self-hosted n8n automation fabric"; else VAN_PUBLIC_HOST="$PUBLIC_HOST" bash "$HERE/automation/bootstrap-automation-fabric.sh"; fi
  ok "self-hosted n8n automation fabric"
else
  (( DRY_RUN )) || die "--public-host is required for the complete production bootstrap"
fi
VEKL_WORKER_HOST="${VAN_VEKL_WORKER_HOST:-}"
if [[ -n "$VEKL_WORKER_HOST" ]]; then
  if (( DRY_RUN )); then plan "bootstrap Stagehand/Playwright/Temporal runtime for VEKL worker $VEKL_WORKER_HOST"; else VAN_VEKL_WORKER_HOST="$VEKL_WORKER_HOST" bash "$HERE/browser/bootstrap-browser-runtime.sh"; fi
  ok "browser development runtime foundation"
else
  (( DRY_RUN )) || die "VAN_VEKL_WORKER_HOST is required for complete production bootstrap"
fi

# ---------------------------------------------------------------- public TLS front for the MT5 pull bridge (optional)
if [[ -n "$PUBLIC_HOST" ]]; then
  if ! command -v caddy >/dev/null 2>&1; then
    if (( DRY_RUN )); then plan "install caddy (apt repo dl.cloudsmith.io/public/caddy/stable)"; else
      apt_install debian-keyring debian-archive-keyring apt-transport-https
      write_keyring 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' /usr/share/keyrings/caddy-stable-archive-keyring.gpg
      curl -fsSL 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' > /etc/apt/sources.list.d/caddy-stable.list
      apt_update; apt_install caddy
      command -v caddy >/dev/null 2>&1 || die "caddy missing after install"
    fi
  fi
  run install -m 0644 "$HERE/caddy/Caddyfile" /etc/caddy/Caddyfile
  run bash -c "grep -q '^VAN_PUBLIC_HOST=' '$CONFIG/van-trading-core.env' && sed -i 's#^VAN_PUBLIC_HOST=.*#VAN_PUBLIC_HOST=$PUBLIC_HOST#' '$CONFIG/van-trading-core.env' || echo 'VAN_PUBLIC_HOST=$PUBLIC_HOST' >> '$CONFIG/van-trading-core.env'"
  run bash -c "mkdir -p /etc/systemd/system/caddy.service.d && printf '[Service]\nEnvironment=VAN_PUBLIC_HOST=%s\n' '$PUBLIC_HOST' > /etc/systemd/system/caddy.service.d/van.conf"
  if (( DRY_RUN )); then
    plan "validate /etc/caddy/Caddyfile with VAN_PUBLIC_HOST=$PUBLIC_HOST"
  else
    VAN_PUBLIC_HOST="$PUBLIC_HOST" caddy validate --config /etc/caddy/Caddyfile --adapter caddyfile >/dev/null || die "invalid caddy configuration"
  fi
  run systemctl daemon-reload; run systemctl enable --now caddy
  (( DRY_RUN )) || systemctl is-active --quiet caddy || die "caddy service not active after enable"
  ok "caddy public TLS front for $PUBLIC_HOST → 127.0.0.1:9443 (Let's Encrypt; ports 80/443 must be open to the internet for ACME + the EA)"
else skip "public host for the MT5 pull bridge (pass --public-host=<dns> when using VanBridgeEA)"; fi

# ---------------------------------------------------------------- firewall
if (( ! DRY_RUN )); then
  ufw --force reset >/dev/null; ufw default deny incoming >/dev/null; ufw default allow outgoing >/dev/null
  IFS=',' read -r -a admin_cidrs <<< "$ADMIN_CIDRS"
  for cidr in "${admin_cidrs[@]}"; do
    [[ "$cidr" =~ ^10\.0\.[0-9]+\.[0-9]+/32$ ]] || die "invalid admin CIDR: $cidr"
    ufw allow from "$cidr" to any port 22 proto tcp >/dev/null
    ufw allow from "$cidr" to any port 9133 proto tcp >/dev/null
  done
  if [[ -n "$PUBLIC_HOST" ]]; then ufw allow 80/tcp >/dev/null; ufw allow 443/tcp >/dev/null; fi
  ufw --force enable >/dev/null
  VAN_ADMIN_CIDRS="$ADMIN_CIDRS" VAN_PUBLIC_HOST="$PUBLIC_HOST" bash "$HERE/oci/harden-oracle-image-firewall.sh"
else plan "ufw + OCI image firewall: allow 22/tcp and 9133/tcp from $ADMIN_CIDRS; public 80/443 only when configured"; fi
ok "firewall"

# ---------------------------------------------------------------- record
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
REPORT="{\"host\":\"$(hostname)\",\"arch\":\"$ARCH\",\"dry_run\":$DRY_RUN,\"mt5_native\":$MT5_NATIVE,\"branch\":\"$BRANCH\",\"with_nautilus\":$WITH_NAUTILUS,\"steps\":$(printf '%s\n' "${STEPS[@]}" | jq -R . | jq -s .),\"at\":\"$STAMP\"}"
if (( ! DRY_RUN )); then echo "$REPORT" > "$DATA/bootstrap-$STAMP.json"; chown vati:vati "$DATA/bootstrap-$STAMP.json"; fi
echo "$REPORT" | jq .
echo "[bootstrap] next: 1) copy $SECRETS/pki/mt5-worker.{crt,key} + ca.crt to the Windows worker and run windows/mt5_worker/install.ps1"
echo "[bootstrap]       2) sudo -u vati $VENV/bin/python -m vati accounts add --registry $CONFIG/accounts.json --alias <alias> --broker MT5|DERIV|PAPER ..."
echo "[bootstrap]       3) write $CONFIG/sessions/<alias>.json and: systemctl enable --now vati-session@<alias>"
echo "[bootstrap]       4) on dial-hermes-control: bash deploy/van-trading-core/hermes/register-commander-mcp.sh"
echo "[bootstrap]       5) bash deploy/van-trading-core/qualify.sh"
