#!/usr/bin/env bash
set -Eeuo pipefail

[[ "$(id -u)" == "0" ]] || { echo "run as root" >&2; exit 40; }

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BASE=/opt/van-web-acquisition
CONFIG_DIR=/opt/van-trading/config
CONFIG="$CONFIG_DIR/web-acquisition.env"
BROWSER_CONFIG="$CONFIG_DIR/browser-runtime.env"
UNIT=/etc/systemd/system/vati-web-acquisition.service

if ! id van-acquisition >/dev/null 2>&1; then
  useradd --system --home-dir "$BASE" --shell /usr/sbin/nologin van-acquisition
fi

[[ -d "$CONFIG_DIR" ]] || { echo "missing existing VAN config directory: $CONFIG_DIR" >&2; exit 41; }
install -d -o root -g van-acquisition -m 0750 "$BASE"
install -d -o van-acquisition -g van-acquisition -m 0700 /run/van-acquisition
install -d -o van-acquisition -g van-acquisition -m 0750 /var/log/van-trading/acquisition
install -d -o van-acquisition -g van-acquisition -m 0700 /var/lib/van-acquisition/storage

install -o root -g root -m 0755 "$HERE/acquisition_service.py" "$BASE/acquisition_service.py"
install -o root -g root -m 0644 "$HERE/requirements.txt" "$BASE/requirements.txt"

if [[ ! -f "$CONFIG" ]]; then
  install -o root -g van-acquisition -m 0640 "$HERE/runtime.env.example" "$CONFIG"
fi

python3.12 -m venv "$BASE/venv"
"$BASE/venv/bin/python" -m pip install --disable-pip-version-check --upgrade pip
"$BASE/venv/bin/python" -m pip install --disable-pip-version-check --no-cache-dir   -r "$BASE/requirements.txt"

"$BASE/venv/bin/python" - <<'PY'
import importlib.metadata as m
expected={"scrapling":"0.4.15","crawlee":"1.10.2"}
for package, version in expected.items():
    observed=m.version(package)
    if observed != version:
        raise SystemExit(f"{package} version mismatch: {observed} != {version}")
print("DEPENDENCY_PINS_OK")
PY

chromium=""
if [[ -f "$BROWSER_CONFIG" ]]; then
  chromium="$(sed -n 's/^VAN_CHROMIUM_EXECUTABLE=//p' "$BROWSER_CONFIG" | tail -n1)"
fi
if [[ -n "$chromium" && -x "$chromium" ]]; then
  python3 - "$CONFIG" "$chromium" <<'PY'
import re, sys
path, chromium=sys.argv[1:]
text=open(path, encoding="utf-8").read()
text=re.sub(r"^VAN_CHROMIUM_EXECUTABLE=.*$", "VAN_CHROMIUM_EXECUTABLE="+chromium, text, flags=re.M)
open(path, "w", encoding="utf-8").write(text)
PY
else
  echo "NOTE: no qualified Chromium path found; HTTP/Crawlee remain usable, Scrapling browser route remains unavailable." >&2
fi

install -o root -g root -m 0644   "$HERE/../systemd/vati-web-acquisition.service" "$UNIT"

systemctl daemon-reload
systemctl enable vati-web-acquisition.service
systemctl restart vati-web-acquisition.service

for attempt in 1 2 3 4 5; do
  if curl -fsS --max-time 5 http://127.0.0.1:9143/health > /tmp/van-web-acquisition-health.json; then
    "$BASE/venv/bin/python" - /tmp/van-web-acquisition-health.json <<'PY'
import json, sys
d=json.load(open(sys.argv[1], encoding="utf-8"))
assert d["ok"] is True
assert d["service"] == "van-web-acquisition-worker/1.1.0"
assert d["scrapling"] == "0.4.15"
assert d["crawlee"] == "1.10.2"
assert d["crawlee_ready"] is True
assert d["auth_surface"] is False
assert d["challenge_solver_enabled"] is False
assert d["bind"] == "127.0.0.1"
PY
    echo "WEB_ACQUISITION_RUNTIME_CONFIGURED"
    exit 0
  fi
  sleep 2
done

journalctl -u vati-web-acquisition.service -n 100 --no-pager >&2 || true
exit 44
