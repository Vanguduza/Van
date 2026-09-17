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
install -d -o van-browser -g van-browser -m 0750 /var/lib/van-trading/browser/downloads
install -d -o van-browser -g van-browser -m 0750 /var/lib/van-trading/evidence/browser/sha256
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

/opt/van-trading/venv/bin/python - <<'PY'
import temporalio
assert temporalio.__version__ == '1.33.0', temporalio.__version__
PY

cat > /var/lib/van-trading/evidence/browser/runtime-manifest.json <<JSON
{
  "schema_version": 1,
  "stagehand": "$stagehand_ver",
  "playwright": "$playwright_ver",
  "chromium_executable": "$chromium_path",
  "node": "$(node -v)",
  "python": "$(python3.12 --version | awk '{print $2}')",
  "temporalio": "1.33.0",
  "stagehand_bind": "127.0.0.1:9140",
  "harness_bind": "127.0.0.1:9141",
  "vekl_worker": "$VEKL_WORKER_HOST",
  "service_state": "ENVIRONMENT_PREPARED_NOT_IMPLEMENTED",
  "generated_at": "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
}
JSON
chmod 0644 /var/lib/van-trading/evidence/browser/runtime-manifest.json
echo BROWSER_DEVELOPMENT_RUNTIME_GREEN
