#!/usr/bin/env bash
set -Eeuo pipefail
[[ "$(id -u)" == 0 ]] || { echo 'run as root' >&2; exit 40; }

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BASE=/opt/van-trading
DEST="$BASE/automation"
SECRETS="$BASE/secrets/automation"
ENVF="$BASE/config/automation.env"
PUBLIC_HOST="${VAN_PUBLIC_HOST:-}"
[[ -n "$PUBLIC_HOST" ]] || { echo 'VAN_PUBLIC_HOST is required' >&2; exit 41; }

install -d -o root -g root -m 0750 "$DEST" "$DEST/postgres/init"
install -d -o root -g root -m 0700 "$SECRETS"
install -d -o vati -g vati -m 0750 /var/lib/van-trading/evidence/automation
install -d -o vati -g vati -m 0750 /var/lib/van-trading/automation/transient

for f in postgres_admin_password n8n_db_password n8n_encryption_key n8n_runner_auth_token; do
  if [[ ! -s "$SECRETS/$f" ]]; then
    umask 077
    openssl rand -hex 32 > "$SECRETS/$f"
  fi
  chown root:root "$SECRETS/$f"; chmod 0600 "$SECRETS/$f"
done
if [[ ! -s "$SECRETS/n8n-owner-password" ]]; then
  umask 077
  openssl rand -base64 36 | tr -d '\n=/+' | head -c 32 > "$SECRETS/n8n-owner-password"
fi
chown root:root "$SECRETS/n8n-owner-password"; chmod 0600 "$SECRETS/n8n-owner-password"

install -m 0644 "$HERE/docker-compose.yml" "$DEST/docker-compose.yml"
install -m 0755 "$HERE/postgres/init/01-create-n8n-db.sh" "$DEST/postgres/init/01-create-n8n-db.sh"
install -m 0755 "$HERE/qualify-automation-runtime.sh" "$DEST/qualify-automation-runtime.sh"
install -m 0755 "$HERE/provision-api.py" "$DEST/provision-api.py"
install -d -o root -g root -m 0750 "$DEST/policy"
cp -a "$BASE/app/config/automation/." "$DEST/policy/"

if [[ ! -f "$ENVF" ]]; then
  install -o root -g root -m 0644 "$HERE/runtime.env.example" "$ENVF"
fi
python3 - "$ENVF" "$PUBLIC_HOST" <<'PY'
import re, sys
p, host = sys.argv[1:]
s = open(p, encoding='utf-8').read()
line = 'VAN_PUBLIC_HOST=' + host
s = re.sub(r'^VAN_PUBLIC_HOST=.*$', line, s, flags=re.M) if re.search(r'^VAN_PUBLIC_HOST=', s, re.M) else s + '\n' + line + '\n'
open(p, 'w', encoding='utf-8').write(s)
PY
chown root:root "$ENVF"; chmod 0644 "$ENVF"

set -a; . "$ENVF"; set +a
cd "$DEST"
docker compose --env-file "$ENVF" config >/dev/null
docker compose --env-file "$ENVF" pull --quiet
install -m 0644 "$HERE/../systemd/vati-automation.service" /etc/systemd/system/vati-automation.service
systemctl daemon-reload
systemctl enable --now vati-automation.service
systemctl is-active --quiet vati-automation.service
"$DEST/qualify-automation-runtime.sh"
python3 "$DEST/provision-api.py" --base http://127.0.0.1:5678 --secrets-dir "$SECRETS"
[[ -s "$SECRETS/n8n-hermes-api.key" ]] || { echo 'n8n Hermes API key missing' >&2; exit 52; }

n8n_digest="$(docker image inspect "docker.n8n.io/n8nio/n8n:$N8N_VERSION" --format '{{index .RepoDigests 0}}' 2>/dev/null || true)"
runner_digest="$(docker image inspect "n8nio/runners:$N8N_VERSION" --format '{{index .RepoDigests 0}}' 2>/dev/null || true)"
postgres_digest="$(docker image inspect "postgres:$POSTGRES_VERSION" --format '{{index .RepoDigests 0}}' 2>/dev/null || true)"
cat > /var/lib/van-trading/evidence/automation/runtime-manifest.json <<JSON
{
  "schema_version": 1,
  "n8n": {"version": "$N8N_VERSION", "image_digest": "$n8n_digest"},
  "n8n_runner": {"version": "$N8N_VERSION", "image_digest": "$runner_digest"},
  "postgres": {"version": "$POSTGRES_VERSION", "image_digest": "$postgres_digest"},
  "execution_mode": "regular-single-instance",
  "redis": false,
  "queue_mode": false,
  "public_webhook_base": "https://$PUBLIC_HOST/automation-webhook/",
  "management_url": "http://127.0.0.1:5678/",
  "generated_at": "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
}
JSON
chmod 0644 /var/lib/van-trading/evidence/automation/runtime-manifest.json
echo AUTOMATION_FABRIC_BOOTSTRAP_GREEN
