#!/usr/bin/env bash
set -Eeuo pipefail
BASE=/opt/van-trading
ENVF="$BASE/config/automation.env"
[[ -r "$ENVF" ]] || { echo 'automation env missing' >&2; exit 40; }
set -a; . "$ENVF"; set +a
cd "$BASE/automation"
compose=(docker compose --env-file "$ENVF")

end=$((SECONDS+300))
while (( SECONDS < end )); do
  pg="$(${compose[@]} ps --format json postgres 2>/dev/null | jq -r 'if type=="array" then .[0].Health else .Health end' 2>/dev/null || true)"
  n8n="$(${compose[@]} ps --format json n8n 2>/dev/null | jq -r 'if type=="array" then .[0].Health else .Health end' 2>/dev/null || true)"
  runner="$(${compose[@]} ps --format json n8n-runner 2>/dev/null | jq -r 'if type=="array" then .[0].Health else .Health end' 2>/dev/null || true)"
  [[ "$pg" == healthy && "$n8n" == healthy && "$runner" == healthy ]] && break
  sleep 5
done
[[ "$pg" == healthy ]] || { echo "postgres not healthy: $pg" >&2; exit 41; }
[[ "$n8n" == healthy ]] || { echo "n8n not healthy: $n8n" >&2; exit 42; }
[[ "$runner" == healthy ]] || { echo "runner not healthy: $runner" >&2; exit 43; }
n8n_version="$(${compose[@]} exec -T n8n n8n --version | tr -d '\r')"
[[ "$n8n_version" == "$N8N_VERSION" ]] || { echo "n8n version mismatch: $n8n_version" >&2; exit 44; }

role_flags="$(${compose[@]} exec -T postgres psql -U postgres -d postgres -Atc \
  "SELECT rolsuper::text||':'||rolcreatedb::text||':'||rolcreaterole::text FROM pg_roles WHERE rolname='van_n8n'")"
[[ "$role_flags" == "false:false:false" ]] || { echo "van_n8n privilege boundary invalid: $role_flags" >&2; exit 45; }

db_owner="$(${compose[@]} exec -T postgres psql -U postgres -d postgres -Atc \
  "SELECT pg_catalog.pg_get_userbyid(datdba) FROM pg_database WHERE datname='van_n8n'")"
[[ "$db_owner" == van_n8n ]] || { echo "van_n8n database owner invalid: $db_owner" >&2; exit 46; }

${compose[@]} config --services | grep -qx redis && { echo 'Redis/queue mode forbidden in initial topology' >&2; exit 47; } || true
listeners="$(ss -ltnH | awk '{print $4}' | grep ':5678$' || true)"
[[ "$listeners" == *"127.0.0.1:5678"* ]] || { echo "n8n loopback listener missing: $listeners" >&2; exit 48; }
printf '%s\n' "$listeners" | grep -Eq '(^|\[::\]|0\.0\.0\.0):5678$' && { echo "n8n exposed beyond loopback: $listeners" >&2; exit 49; } || true
cfg="$(${compose[@]} config)"
for forbidden in '/var/run/docker.sock' '/etc/ssh' '/var/lib/vati' '/root'; do
  grep -Fq "$forbidden" <<<"$cfg" && { echo "forbidden n8n mount/reference: $forbidden" >&2; exit 50; } || true
done

host_broker="$(ss -ltnH | awk '{print $4}' | grep ':5679$' || true)"
[[ -z "$host_broker" ]] || { echo "task broker leaked to host: $host_broker" >&2; exit 51; }

mkdir -p /var/lib/van-trading/evidence/automation
cat > /var/lib/van-trading/evidence/automation/runtime-qualification.json <<JSON
{
  "status": "GREEN",
  "n8n_version": "$n8n_version",
  "postgres_version": "$POSTGRES_VERSION",
  "execution_mode": "regular-single-instance",
  "external_task_runner": true,
  "redis": false,
  "queue_mode": false,
  "management_bind": "127.0.0.1:5678",
  "resource_budget_state": "${VAN_AUTOMATION_RESOURCE_BUDGET_STATE:-PROVISIONAL}",
  "qualified_at": "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
}
JSON
chmod 0644 /var/lib/van-trading/evidence/automation/runtime-qualification.json
echo AUTOMATION_FABRIC_RUNTIME_GREEN
