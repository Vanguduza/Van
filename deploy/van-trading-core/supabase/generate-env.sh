#!/usr/bin/env bash
# Generates a real Supabase .env for van-trading-core from the donor env.example.
# Every secret in the donor example is a public demo value; this script replaces all of them
# with fresh random material and mints ANON/SERVICE_ROLE JWTs from the new JWT_SECRET.
# Idempotent: an existing .env is left untouched unless --force is passed.
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
OUT="${1:-$HERE/.env}"
FORCE="${FORCE:-0}"
if [[ -f "$OUT" && "$FORCE" != "1" ]]; then echo "exists: $OUT (FORCE=1 to regenerate)"; exit 0; fi
python3 - "$HERE/env.example" "$OUT" <<'PY'
import base64, hashlib, hmac, json, os, re, secrets, sys, time
src, out = sys.argv[1], sys.argv[2]
def b64(b): return base64.urlsafe_b64encode(b).rstrip(b"=").decode()
def jwt(secret, role, years=10):
    now = int(time.time())
    h = b64(json.dumps({"alg": "HS256", "typ": "JWT"}, separators=(",", ":")).encode())
    p = b64(json.dumps({"role": role, "iss": "supabase", "iat": now, "exp": now + years * 365 * 86400}, separators=(",", ":")).encode())
    sig = b64(hmac.new(secret.encode(), f"{h}.{p}".encode(), hashlib.sha256).digest())
    return f"{h}.{p}.{sig}"
jwt_secret = secrets.token_urlsafe(48)
values = {
    "POSTGRES_PASSWORD": secrets.token_urlsafe(32), "JWT_SECRET": jwt_secret, "ANON_KEY": jwt(jwt_secret, "anon"), "SERVICE_ROLE_KEY": jwt(jwt_secret, "service_role"),
    "DASHBOARD_USERNAME": "van-owner", "DASHBOARD_PASSWORD": secrets.token_urlsafe(24), "SECRET_KEY_BASE": secrets.token_urlsafe(64), "VAULT_ENC_KEY": secrets.token_hex(16),
    "LOGFLARE_PUBLIC_ACCESS_TOKEN": secrets.token_urlsafe(24), "LOGFLARE_PRIVATE_ACCESS_TOKEN": secrets.token_urlsafe(24), "POOLER_TENANT_ID": "van-trading",
    "SITE_URL": "http://127.0.0.1:3000", "API_EXTERNAL_URL": "http://127.0.0.1:8000", "SUPABASE_PUBLIC_URL": "http://127.0.0.1:8000", "STUDIO_DEFAULT_ORGANIZATION": "VAN", "STUDIO_DEFAULT_PROJECT": "van-trading",
    "VATI_LEDGER_PASSWORD": secrets.token_urlsafe(32),
}
lines = []
seen = set()
for line in open(src, encoding="utf-8"):
    m = re.match(r"^([A-Z0-9_]+)=(.*)$", line.rstrip("\n"))
    if m and m.group(1) in values:
        lines.append(f"{m.group(1)}={values[m.group(1)]}\n"); seen.add(m.group(1))
    else:
        lines.append(line)
for k, v in values.items():
    if k not in seen:
        lines.append(f"{k}={v}\n")
fd = os.open(out, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
with os.fdopen(fd, "w", encoding="utf-8") as f:
    f.writelines(lines)
tpl = os.path.join(os.path.dirname(src), "init", "01_vati_ledger.sql.tpl")
gen = os.path.join(os.path.dirname(src), "init", "01_vati_ledger.sql")
fd = os.open(gen, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
with os.fdopen(fd, "w", encoding="utf-8") as f:
    f.write(open(tpl, encoding="utf-8").read().replace("__VATI_LEDGER_PASSWORD__", values["VATI_LEDGER_PASSWORD"].replace("'", "''")))
print(json.dumps({"written": out, "mode": "0600", "replaced": sorted(seen), "added": sorted(set(values) - seen), "ledger_init": gen}))
PY
