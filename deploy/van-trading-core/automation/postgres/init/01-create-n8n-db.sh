#!/bin/bash
set -Eeuo pipefail

pw="$(cat /run/secrets/n8n_db_password)"
[[ ${#pw} -ge 32 ]] || { echo "n8n DB password too short" >&2; exit 40; }

psql -v ON_ERROR_STOP=1 \
  --username "$POSTGRES_USER" \
  --dbname postgres \
  --set=n8n_password="$pw" <<'SQL'
SELECT format(
  'CREATE ROLE van_n8n LOGIN PASSWORD %L NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT',
  :'n8n_password'
)
WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'van_n8n') \gexec

SELECT 'CREATE DATABASE van_n8n OWNER van_n8n'
WHERE NOT EXISTS (SELECT 1 FROM pg_database WHERE datname = 'van_n8n') \gexec

REVOKE CONNECT ON DATABASE postgres FROM van_n8n;
REVOKE CONNECT ON DATABASE template1 FROM van_n8n;
SQL

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname van_n8n <<'SQL'
REVOKE CREATE ON SCHEMA public FROM PUBLIC;
GRANT USAGE, CREATE ON SCHEMA public TO van_n8n;
SQL
