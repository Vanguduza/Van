#!/usr/bin/env bash
set -Eeuo pipefail
[[ "$(id -u)" == 0 ]] || { echo 'run as root' >&2; exit 40; }

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BASE=/opt/van-browser-runtime
CONFIG=/opt/van-trading/config/browser-runtime.env
VEKL_WORKER_HOST="${VAN_VEKL_WORKER_HOST:-}"
[[ -n "$VEKL_WORKER_HOST" ]] || { echo 'VAN_VEKL_WORKER_HOST is required' >&2; exit 41; }

node - <<'NODE'
const [major, minor] = process.versions.node.split('.').map(Number);
if (major !== 22 || minor < 18) {
  console.error(`Node >=22.18 <23 required, got ${process.versions.node}`);
  process.exit(42);
}
NODE

if ! id van-browser >/dev/null 2>&1; then
  useradd --system --home-dir "$BASE" --shell /usr/sbin/nologin van-browser
fi
install -d -o van-browser -g van-browser -m 0750 "$BASE" "$BASE/browsers"
install -d -o van-browser -g van-browser -m 0700 /var/lib/van-trading/browser/profiles
install -d -o van-browser -g van-browser -m 0700 /var/lib/van-trading/browser/secrets
install -d -o van-browser -g van-browser -m 0750 /var/lib/van-trading/browser/downloads
install -d -o van-browser -g van-browser -m 0750 /var/lib/van-trading/evidence/browser/sha256
install -d -o van-browser -g van-browser -m 0700 /run/van-browser
install -d -o vati -g vati -m 0750 /var/lib/van-trading/evidence/automation/sha256
install -d -o van-browser -g van-browser -m 0750 /var/log/van-trading/browser

install -o van-browser -g van-browser -m 0644 "$HERE/package.json" "$BASE/package.json"
install -o van-browser -g van-browser -m 0644 "$HERE/package-lock.json" "$BASE/package-lock.json"
install -o root -g root -m 0644 "$HERE/runtime.env.example" "$CONFIG"
python3 - "$CONFIG" "$VEKL_WORKER_HOST" <<'PY'
import re, sys
p, host = sys.argv[1:]
s = open(p, encoding='utf-8').read()
s = re.sub(r'^VAN_VEKL_WORKER_HOST=.*$', 'VAN_VEKL_WORKER_HOST='+host, s, flags=re.M)
open(p, 'w', encoding='utf-8').write(s)
PY
chmod 0644 "$CONFIG"

sudo -u van-browser npm --prefix "$BASE" ci --omit=dev --no-audit --no-fund
export PLAYWRIGHT_BROWSERS_PATH="$BASE/browsers"
"$BASE/node_modules/.bin/playwright" install-deps chromium
sudo -u van-browser env PLAYWRIGHT_BROWSERS_PATH="$PLAYWRIGHT_BROWSERS_PATH" \
  "$BASE/node_modules/.bin/playwright" install chromium
chown -R van-browser:van-browser "$BASE/browsers"
stagehand_ver="$(node -p "require('$BASE/node_modules/@browserbasehq/stagehand/package.json').version")"
playwright_ver="$(node -p "require('$BASE/node_modules/@playwright/test/package.json').version")"
[[ "$stagehand_ver" == 4.1.0 ]] || { echo "Stagehand pin mismatch: $stagehand_ver" >&2; exit 43; }
[[ "$playwright_ver" == 1.63.0 ]] || { echo "Playwright pin mismatch: $playwright_ver" >&2; exit 44; }
chromium_path="$(cd "$BASE" && PLAYWRIGHT_BROWSERS_PATH="$PLAYWRIGHT_BROWSERS_PATH" node -e \
  "const { chromium } = require('playwright'); process.stdout.write(chromium.executablePath())")"
[[ -x "$chromium_path" ]] || { echo "Chromium executable missing: $chromium_path" >&2; exit 45; }

# Browser Harness is the adopted deterministic actuator. Pin the released package and its
# direct runtime dependencies. The installed environment is also frozen into deployment
# evidence so a later qualification can detect transitive drift rather than assuming it.
python3.12 -m venv "$BASE/harness-venv"
"$BASE/harness-venv/bin/python" -m pip install --disable-pip-version-check --no-cache-dir \
  "browser-harness==0.1.13" "cdp-use==1.4.5" "fetch-use==0.4.0" \
  "pillow==12.2.0" "websockets==15.0.1"
"$BASE/harness-venv/bin/python" - <<'PY'
import importlib.metadata as m
expected = {
    "browser-harness": "0.1.13",
    "cdp-use": "1.4.5",
    "fetch-use": "0.4.0",
    "pillow": "12.2.0",
    "websockets": "15.0.1",
}
for package, version in expected.items():
    observed = m.version(package)
    if observed != version:
        raise SystemExit(f"{package} pin mismatch: {observed} != {version}")
PY
"$BASE/harness-venv/bin/python" -m pip freeze --all | LC_ALL=C sort > "$BASE/harness-freeze.txt"
harness_freeze_sha="$(sha256sum "$BASE/harness-freeze.txt" | awk '{print $1}')"
harness_ver="$("$BASE/harness-venv/bin/python" -c 'import importlib.metadata as m; print(m.version("browser-harness"))')"

install -o root -g root -m 0755 "$HERE/harness_service.py" "$BASE/harness_service.py"
install -o root -g root -m 0644 "$HERE/../systemd/vati-browser-harness.service" /etc/systemd/system/vati-browser-harness.service

python3 - "$CONFIG" "$chromium_path" "$BASE/harness-venv/bin/browser-harness" <<'PY'
import re, sys
p, chromium, harness = sys.argv[1:]
s = open(p, encoding="utf-8").read()
values = {
    "VAN_CHROMIUM_EXECUTABLE": chromium,
    "VAN_BROWSER_HARNESS_BIN": harness,
}
for key, value in values.items():
    line = f"{key}={value}"
    if re.search(rf"^{re.escape(key)}=", s, re.M):
        s = re.sub(rf"^{re.escape(key)}=.*$", line, s, flags=re.M)
    else:
        s += "\n" + line
open(p, "w", encoding="utf-8").write(s)
PY
chmod 0644 "$CONFIG"

systemctl daemon-reload
systemctl enable vati-browser-harness.service
systemctl restart vati-browser-harness.service
for attempt in 1 2 3 4 5; do
  if curl -fsS --max-time 3 "http://127.0.0.1:${VAN_HARNESS_PORT:-9141}/health" >/tmp/van-harness-health.json 2>/dev/null \
     && python3 - /tmp/van-harness-health.json <<'PY'
import json, sys
d = json.load(open(sys.argv[1], encoding="utf-8"))
assert d["ok"] is True
assert d["runtime_version"] == "0.1.13"
assert d["helper_authoring"] is False
assert d["raw_cdp_http"] is False
PY
  then
    echo BROWSER_HARNESS_RUNTIME_GREEN
    break
  fi
  if [[ "$attempt" == 5 ]]; then
    journalctl -u vati-browser-harness.service -n 100 --no-pager >&2 || true
    exit 46
  fi
  sleep 2
done

/opt/van-trading/venv/bin/python - <<'PY'
import temporalio
assert temporalio.__version__ == '1.33.0', temporalio.__version__
PY

cat > /var/lib/van-trading/evidence/browser/runtime-manifest.json <<JSON
{
  "schema_version": 1,
  "stagehand": "$stagehand_ver",
  "browser_harness": "$harness_ver",
  "browser_harness_freeze_sha256": "$harness_freeze_sha",
  "playwright": "$playwright_ver",
  "chromium_executable": "$chromium_path",
  "node": "$(node -v)",
  "python": "$(python3.12 --version | awk '{print $2}')",
  "temporalio": "1.33.0",
  "stagehand_bind": "127.0.0.1:9140",
  "harness_bind": "127.0.0.1:9141",
  "vekl_worker": "$VEKL_WORKER_HOST",
  "service_state": "HARNESS_IMPLEMENTED_STAGEHAND_PENDING",
  "generated_at": "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
}
JSON
chmod 0644 /var/lib/van-trading/evidence/browser/runtime-manifest.json
echo BROWSER_DEVELOPMENT_RUNTIME_GREEN
