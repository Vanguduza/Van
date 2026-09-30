#!/usr/bin/env bash
#
# Owner decision 2026-09-29 §1 — install the van-browser-core trust zone on its own host.
#
# Installs the Harness-owned Chromium, the deterministic Browser Harness worker, the
# Stagehand 4.1.0 semantic worker and the mTLS edge. Idempotent. It installs; it does not
# judge — qualify.sh is the gate.
#
# It refuses rather than guesses:
#   * a host that carries another zone's install (trading core, private core, dial-control,
#     browser stream host) is refused. There is no "temporary" co-location: if this zone is
#     not available, STAGEHAND = PRODUCTION_DISABLED, not "run it on van-trading-core";
#   * no private overlay address for the edge, or a wildcard/loopback one, is refused.
#
# Nothing here reads, writes or references trading, broker, owner-model, owner-private
# memory or Project Truth credentials. tests/contracts/test_van_browser_core_zone.py
# enforces that for every unit/env/config file in this package.
set -Eeuo pipefail

DRY_RUN=0
[[ "${1:-}" == "--dry-run" ]] && DRY_RUN=1
[[ "$(id -u)" == 0 || "$DRY_RUN" == 1 ]] || { echo 'run as root' >&2; exit 40; }

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ZONE=van-browser-core
BASE=/opt/van-browser-core
RUNTIME="$BASE/runtime"
ETC=/etc/van-browser-core
DATA=/var/lib/van-browser-core
CONFIG="$ETC/runtime.env"

say() { printf '  %s\n' "$*"; }
run() { if [[ "$DRY_RUN" == 1 ]]; then printf '  would: %s\n' "$*"; else eval "$@"; fi; }
refuse() { echo "refused: $*" >&2; exit 2; }

echo "== preflight: dedicated zone host =="
# BEGIN foreign-zone markers — presence of any of these means this host already belongs to
# another trust zone. They are checked for, never created, read or used.
FOREIGN_ZONE_MARKERS=(
  /opt/van-trading            # van-trading-core
  /var/lib/van-trading        # van-trading-core
  /etc/van-private-core       # van-private-core
  /opt/van-private-core       # van-private-core
  /etc/dial-control           # dial-control
  /opt/dial-control           # dial-control
  /etc/van-browser-stream     # Browser Stream Host (public media zone)
)
# END foreign-zone markers
for marker in "${FOREIGN_ZONE_MARKERS[@]}"; do
  [[ -e "$marker" ]] && refuse "$marker exists: this host belongs to another trust zone. van-browser-core must be a dedicated host (no temporary co-location)."
done
if [[ -e "$ETC/zone" ]] && ! grep -qx "$ZONE" "$ETC/zone"; then
  refuse "$ETC/zone names a different zone"
fi

EDGE_BIND="${VAN_BROWSER_CORE_EDGE_BIND:-}"
case "$EDGE_BIND" in
  ""|0.0.0.0|::|127.*|localhost) refuse "VAN_BROWSER_CORE_EDGE_BIND must be this host's private overlay address" ;;
esac

node - <<'NODE'
const [major, minor] = process.versions.node.split('.').map(Number);
if (major !== 22 || minor < 18) {
  console.error(`Node >=22.18 <23 required, got ${process.versions.node}`);
  process.exit(42);
}
NODE
if ! command -v caddy >/dev/null 2>&1; then
  [[ "$DRY_RUN" == 1 ]] && say "would refuse: caddy is not installed" || refuse "caddy is not installed; the mTLS edge is the only cross-zone listener and is not optional"
fi

echo "== users =="
# Two users: the browser/worker identity and the edge identity. The edge holds the server
# key; a page escaping Chromium must not read it.
for user in van-browser van-browser-edge; do
  if id "$user" >/dev/null 2>&1; then say "$user exists"; else
    run "useradd --system --home-dir $BASE --shell /usr/sbin/nologin $user"
  fi
done

echo "== zone marker and directories =="
run "install -d -o root -g root -m 0755 $ETC $BASE"
run "printf '%s\n' $ZONE > $ETC/zone && chmod 0644 $ETC/zone"
run "install -d -o van-browser -g van-browser -m 0750 $RUNTIME $RUNTIME/browsers"
run "install -d -o van-browser -g van-browser -m 0700 $DATA $DATA/profiles $DATA/secrets $DATA/harness-state"
run "install -d -o van-browser -g van-browser -m 0750 $DATA/downloads $DATA/evidence $DATA/evidence/sha256"
run "install -d -o van-browser -g van-browser -m 0700 /run/van-browser-core"
run "install -d -o van-browser -g van-browser -m 0750 /var/log/van-browser-core"
run "install -d -o van-browser-edge -g van-browser-edge -m 0700 /var/lib/van-browser-edge"
# Review I5 F2 — the lease fence install marker and an empty fence manifest, together and
# only once. Re-running bootstrap never recreates a manifest that was lost: with the marker
# present the Harness then refuses fenced calls until the state is restored.
FENCE_MARKER="$ETC/harness-fence-installed"
if [[ -e "$FENCE_MARKER" ]]; then say "$FENCE_MARKER exists; fence state left alone"; else
  run "printf '{\"schema_version\":1,\"aliases\":[]}\n' > $DATA/harness-state/lease-fence-manifest.json"
  run "chown van-browser:van-browser $DATA/harness-state/lease-fence-manifest.json && chmod 0600 $DATA/harness-state/lease-fence-manifest.json"
  run "date -u +%Y-%m-%dT%H:%M:%SZ > $FENCE_MARKER && chmod 0644 $FENCE_MARKER"
fi
# Review I5 F3 — the lease fence MAC key, generated here and never in the repository. Copy
# it to the gateway host (VAN_BROWSER_HARNESS_FENCE_KEY_FILE) with the mTLS client files.
FENCE_KEY="$DATA/secrets/harness-fence.key"
if [[ -e "$FENCE_KEY" ]]; then say "$FENCE_KEY exists; left alone"; else
  run "(umask 0277 && head -c 32 /dev/urandom | od -An -tx1 | tr -d ' \\n' > $FENCE_KEY)"
  run "chown van-browser:van-browser $FENCE_KEY && chmod 0400 $FENCE_KEY"
fi
run "install -d -o root -g van-browser-edge -m 0750 $ETC/pki"

echo "== configuration =="
if [[ -f "$CONFIG" ]]; then say "$CONFIG exists; left alone"; else
  run "install -o root -g van-browser -m 0640 $HERE/runtime.env.example $CONFIG"
fi
run "python3 - $CONFIG $EDGE_BIND <<'PY'
import re, sys
p, bind = sys.argv[1:]
s = open(p, encoding='utf-8').read()
s = re.sub(r'^VAN_BROWSER_CORE_EDGE_BIND=.*$', 'VAN_BROWSER_CORE_EDGE_BIND=' + bind, s, flags=re.M)
s = re.sub(r'^VAN_TRUST_ZONE=.*$', 'VAN_TRUST_ZONE=van-browser-core', s, flags=re.M)
open(p, 'w', encoding='utf-8').write(s)
PY"
run "install -o root -g van-browser-edge -m 0640 $HERE/edge/Caddyfile $ETC/Caddyfile"

echo "== pinned runtime (Stagehand 4.1.0 @ cd7b2307, Playwright 1.63.0) =="
run "install -o van-browser -g van-browser -m 0644 $HERE/browser/package.json $RUNTIME/package.json"
run "install -o van-browser -g van-browser -m 0644 $HERE/browser/package-lock.json $RUNTIME/package-lock.json"
run "sudo -u van-browser npm --prefix $RUNTIME ci --omit=dev --no-audit --no-fund"
run "PLAYWRIGHT_BROWSERS_PATH=$RUNTIME/browsers $RUNTIME/node_modules/.bin/playwright install-deps chromium"
run "sudo -u van-browser env PLAYWRIGHT_BROWSERS_PATH=$RUNTIME/browsers $RUNTIME/node_modules/.bin/playwright install chromium"
if [[ "$DRY_RUN" == 0 ]]; then
  stagehand_ver="$(node -p "require('$RUNTIME/node_modules/@browserbasehq/stagehand/package.json').version")"
  [[ "$stagehand_ver" == 4.1.0 ]] || { echo "Stagehand pin mismatch: $stagehand_ver" >&2; exit 43; }
  stagehand_integrity="$(node -p "require('$RUNTIME/package-lock.json').packages['node_modules/@browserbasehq/stagehand'].integrity")"
  [[ "$stagehand_integrity" == "sha512-PJikMBVoaCRh6TFD7GcmeISmsMq4IwUu1BD5FOsGUVDUxrVqZomWa6W6dF+a/zu4xRZu2Z2xX1nXVMDaCuZWsw==" ]] \
    || { echo "Stagehand integrity mismatch: $stagehand_integrity" >&2; exit 43; }
  playwright_ver="$(node -p "require('$RUNTIME/node_modules/@playwright/test/package.json').version")"
  [[ "$playwright_ver" == 1.63.0 ]] || { echo "Playwright pin mismatch: $playwright_ver" >&2; exit 44; }
  chromium_path="$(cd "$RUNTIME" && PLAYWRIGHT_BROWSERS_PATH="$RUNTIME/browsers" node -e \
    "const { chromium } = require('playwright'); process.stdout.write(chromium.executablePath())")"
  [[ -x "$chromium_path" ]] || { echo "Chromium executable missing: $chromium_path" >&2; exit 45; }
fi

echo "== Browser Harness 0.1.13 =="
run "python3.12 -m venv $RUNTIME/harness-venv"
run "$RUNTIME/harness-venv/bin/python -m pip install --disable-pip-version-check --no-cache-dir browser-harness==0.1.13 cdp-use==1.4.5 fetch-use==0.4.0 pillow==12.2.0 websockets==15.0.1"
run "$RUNTIME/harness-venv/bin/python -m pip freeze --all | LC_ALL=C sort > $RUNTIME/harness-freeze.txt"

echo "== workers and units =="
run "install -o root -g root -m 0755 $HERE/browser/harness_service.py $RUNTIME/harness_service.py"
run "install -o root -g root -m 0755 $HERE/browser/stagehand_service.mjs $RUNTIME/stagehand_service.mjs"
for unit in van-browser-harness.service van-stagehand.service van-browser-core-edge.service; do
  run "install -o root -g root -m 0644 $HERE/systemd/$unit /etc/systemd/system/$unit"
done
if [[ "$DRY_RUN" == 0 ]]; then
  python3 - "$CONFIG" "$chromium_path" "$RUNTIME/harness-venv/bin/browser-harness" <<'PY'
import re, sys
p, chromium, harness = sys.argv[1:]
s = open(p, encoding="utf-8").read()
for key, value in {"VAN_CHROMIUM_EXECUTABLE": chromium, "VAN_BROWSER_HARNESS_BIN": harness}.items():
    s = re.sub(rf"^{re.escape(key)}=.*$", f"{key}={value}", s, flags=re.M)
open(p, "w", encoding="utf-8").write(s)
PY
fi
run "systemctl daemon-reload"

if [[ ! -f "$ETC/pki/edge.crt" ]]; then
  echo
  echo "Edge PKI not issued yet. Run, then re-run this script:"
  echo "    sudo VAN_BROWSER_CORE_EDGE_BIND=$EDGE_BIND bash $HERE/pki/make-browser-core-pki.sh"
  exit 0
fi

run "systemctl enable van-browser-harness.service van-stagehand.service van-browser-core-edge.service"
run "systemctl restart van-browser-harness.service van-stagehand.service van-browser-core-edge.service"
if [[ "$DRY_RUN" == 1 ]]; then echo "dry run complete"; exit 0; fi

for attempt in 1 2 3 4 5; do
  if curl -fsS --max-time 3 http://127.0.0.1:9141/health >/tmp/vbc-harness.json 2>/dev/null \
     && curl -fsS --max-time 3 http://127.0.0.1:9140/health >/tmp/vbc-stagehand.json 2>/dev/null \
     && python3 - /tmp/vbc-harness.json /tmp/vbc-stagehand.json <<'PY'
import json, sys
h = json.load(open(sys.argv[1], encoding="utf-8"))
s = json.load(open(sys.argv[2], encoding="utf-8"))
assert h["ok"] is True and h["runtime_version"] == "0.1.13" and h["trust_zone"] == "van-browser-core"
assert h["helper_authoring"] is False and h["raw_cdp_http"] is False
assert s["ok"] is True and s["runtime_version"] == "4.1.0" and s["trust_zone"] == "van-browser-core"
assert s["stagehand_release_commit"] == "cd7b230778cf92269e4cb90e80d97f5113781c51"
assert s["model_name"] == "anthropic/claude-sonnet-5"
assert s["direct_agent_loop"] is False and s["model_self_selection"] is False
PY
  then echo VAN_BROWSER_CORE_WORKERS_GREEN; break; fi
  if [[ "$attempt" == 5 ]]; then
    journalctl -u van-browser-harness.service -u van-stagehand.service -n 100 --no-pager >&2 || true
    exit 46
  fi
  sleep 2
done

cat > "$DATA/evidence/runtime-manifest.json" <<JSON
{
  "schema_version": 1,
  "trust_zone": "van-browser-core",
  "stagehand": "$stagehand_ver",
  "stagehand_release_commit": "cd7b230778cf92269e4cb90e80d97f5113781c51",
  "stagehand_integrity": "$stagehand_integrity",
  "stagehand_model": "anthropic/claude-sonnet-5",
  "stagehand_model_revision": "UNVERIFIED",
  "browser_harness": "0.1.13",
  "browser_harness_freeze_sha256": "$(sha256sum "$RUNTIME/harness-freeze.txt" | awk '{print $1}')",
  "playwright": "$playwright_ver",
  "chromium_executable": "$chromium_path",
  "node": "$(node -v)",
  "edge_bind": "$EDGE_BIND:9443",
  "service_state": "VAN_BROWSER_CORE_INSTALLED_PENDING_QUALIFY_AND_GATES",
  "stagehand_production": "PRODUCTION_DISABLED_UNTIL_GATEWAY_PLACEMENT_GATE_PASSES",
  "generated_at": "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
}
JSON
chmod 0644 "$DATA/evidence/runtime-manifest.json"
echo "installed. Next: sudo bash $HERE/qualify.sh"
