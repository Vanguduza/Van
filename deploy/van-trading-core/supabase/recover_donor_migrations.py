#!/usr/bin/env python3
"""Resume the exact Supabase donor migration phase after an interrupted first init.

This is deliberately fail-closed. It only repairs the known state where the donor
init-scripts completed but the donor migrations phase never started. It never
replays a partially-applied migration set.
"""
import argparse
import subprocess
import time

def run(cmd, *, input_text=None, check=True):
    p = subprocess.run(cmd, input=input_text, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if check and p.returncode:
        raise RuntimeError((p.stderr or p.stdout)[-2000:])
    return p

def psql(container, sql, user="postgres", database="postgres"):
    return run(
        ["docker", "exec", "-i", container, "psql", "-U", user, "-d", database,
         "-At", "-v", "ON_ERROR_STOP=1"],
        input_text=sql,
    ).stdout.strip()

def wait_for_db(container, attempts=60):
    for _ in range(attempts):
        if subprocess.run(
            ["docker", "exec", container, "pg_isready", "-U", "postgres", "-d", "postgres"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        ).returncode == 0:
            return
        time.sleep(2)
    raise RuntimeError("Supabase PostgreSQL did not become ready")

def state(container):
    sql = r"""
select
  (select count(*) from pg_database where datname='_supabase')::text || '|' ||
  (select count(*) from pg_namespace where nspname='graphql_public')::text || '|' ||
  coalesce((select pg_get_userbyid(p.proowner) from pg_proc p join pg_namespace n on n.oid=p.pronamespace where n.nspname='auth' and p.proname='uid' and pg_get_function_identity_arguments(p.oid)=''), '') || '|' ||
  coalesce((select pg_get_userbyid(p.proowner) from pg_proc p join pg_namespace n on n.oid=p.pronamespace where n.nspname='auth' and p.proname='role' and pg_get_function_identity_arguments(p.oid)=''), '') || '|' ||
  coalesce((select rolsuper::text from pg_roles where rolname='supabase_admin'), 'false');
"""
    parts = psql(container, sql).split("|")
    if len(parts) != 5:
        raise RuntimeError("unexpected Supabase migration-state probe")
    return {
        "supabase_db": parts[0] == "1",
        "graphql_public": parts[1] == "1",
        "auth_uid_owner": parts[2],
        "auth_role_owner": parts[3],
        "supabase_admin_super": parts[4] == "true",
    }

def classify(st):
    complete = (
        st["supabase_db"]
        and st["graphql_public"]
        and st["auth_uid_owner"] == "supabase_auth_admin"
        and st["auth_role_owner"] == "supabase_auth_admin"
    )
    untouched = (
        not st["supabase_db"]
        and not st["graphql_public"]
        and st["auth_uid_owner"] == "postgres"
        and st["auth_role_owner"] == "postgres"
        and st["supabase_admin_super"]
    )
    if complete:
        return "complete"
    if untouched:
        return "interrupted_before_donor_migrations"
    return "ambiguous_partial"

def replay_migration_phase(container):
    script = r"""set -eu
db=/docker-entrypoint-initdb.d
for sql in "$db"/migrations/*.sql; do
  echo "SUPABASE_DONOR_MIGRATION $(basename "$sql")"
  psql -v ON_ERROR_STOP=1 --no-password --no-psqlrc -U supabase_admin -f "$sql"
done
postinit=/etc/postgresql.schema.sql
if [ -e "$postinit" ]; then
  echo "SUPABASE_DONOR_POSTINIT"
  psql -v ON_ERROR_STOP=1 --no-password --no-psqlrc -U supabase_admin -f "$postinit"
fi
psql -v ON_ERROR_STOP=1 --no-password --no-psqlrc -U supabase_admin -c   'SELECT extensions.pg_stat_statements_reset(); SELECT pg_stat_reset();' >/dev/null 2>&1 || true
"""
    out = run(["docker", "exec", "-i", container, "sh", "-s"], input_text=script)
    return out.stdout

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--container", default="supabase-db")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    wait_for_db(args.container)
    before = state(args.container)
    mode = classify(before)
    if mode == "complete":
        print("SUPABASE_DONOR_MIGRATIONS_PRESENT")
        return
    if mode != "interrupted_before_donor_migrations":
        raise SystemExit("refusing donor migration replay from ambiguous partial state: " + repr(before))
    if args.dry_run:
        print("SUPABASE_DONOR_RECOVERY_ELIGIBLE")
        return

    replay_migration_phase(args.container)
    after = state(args.container)
    if classify(after) != "complete":
        raise SystemExit("donor migration replay did not reach canonical state: " + repr(after))
    print("SUPABASE_DONOR_MIGRATIONS_RECOVERED_GREEN")

if __name__ == "__main__":
    main()
