#!/usr/bin/env bash
set -euo pipefail

required=(
  supabase-db
  supabase-auth
  supabase-rest
  realtime-dev.supabase-realtime
  supabase-storage
  supabase-imgproxy
  supabase-meta
  supabase-edge-functions
  supabase-studio
  supabase-envoy
  supabase-pooler
)

for c in "${required[@]}"; do
  state="$(docker inspect -f '{{.State.Status}}' "$c" 2>/dev/null || true)"
  [[ "$state" == "running" ]] || { echo "SUPABASE_CONTAINER_NOT_RUNNING $c state=${state:-missing}" >&2; exit 1; }
  health="$(docker inspect -f '{{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}' "$c" 2>/dev/null || true)"
  [[ "$health" == "healthy" || "$health" == "none" ]] || { echo "SUPABASE_CONTAINER_UNHEALTHY $c health=$health" >&2; exit 1; }
done

probe="$(docker exec -i supabase-db psql -U postgres -d postgres -At -v ON_ERROR_STOP=1 <<'SQL'
select
  (select count(*) from pg_database where datname='_supabase')::text || '|' ||
  (select count(*) from pg_namespace where nspname='graphql_public')::text || '|' ||
  coalesce((select pg_get_userbyid(p.proowner) from pg_proc p join pg_namespace n on n.oid=p.pronamespace where n.nspname='auth' and p.proname='uid' and pg_get_function_identity_arguments(p.oid)=''), '');
SQL
)"
[[ "$probe" == "1|1|supabase_auth_admin" ]] || { echo "SUPABASE_DONOR_STATE_INVALID $probe" >&2; exit 1; }

curl -fsS --max-time 5 http://127.0.0.1:8000/auth/v1/health >/dev/null
curl -fsS --max-time 5 http://127.0.0.1:8000/rest/v1/ >/dev/null

echo SUPABASE_RUNTIME_GREEN
