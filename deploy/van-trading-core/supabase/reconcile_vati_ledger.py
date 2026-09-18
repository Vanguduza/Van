#!/usr/bin/env python3
import argparse
import os
import pathlib
import re
import subprocess
import time
from urllib.parse import quote

ROLE_STMT = "CREATE ROLE vati LOGIN PASSWORD '__VATI_LEDGER_PASSWORD__' NOSUPERUSER NOCREATEDB NOCREATEROLE;"

def load_env(path):
    out = {}
    for line in pathlib.Path(path).read_text(encoding="utf-8").splitlines():
        if "=" in line and not line.lstrip().startswith("#"):
            key, value = line.split("=", 1)
            out[key] = value
    return out

def build_sql(template, password):
    if ROLE_STMT not in template:
        raise RuntimeError("canonical VATI role statement missing from ledger template")
    escaped = password.replace("'", "''")
    reconcile = f"""DO $vati_role$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'vati') THEN
    CREATE ROLE vati LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE;
  END IF;
END
$vati_role$;
ALTER ROLE vati WITH LOGIN PASSWORD '{escaped}' NOSUPERUSER NOCREATEDB NOCREATEROLE;
"""
    return template.replace(ROLE_STMT, reconcile, 1)

def update_core_env(path, password):
    p = pathlib.Path(path)
    current = p.read_text(encoding="utf-8")
    uri = f"postgres://vati:{quote(password, safe='')}@127.0.0.1:5432/postgres"
    if re.search(r"^VAN_COMMANDER_LEDGER=.*$", current, re.M):
        updated = re.sub(r"^VAN_COMMANDER_LEDGER=.*$", "VAN_COMMANDER_LEDGER=" + uri, current, flags=re.M)
    else:
        updated = current.rstrip() + "\nVAN_COMMANDER_LEDGER=" + uri + "\n"
    st = p.stat()
    tmp = p.with_name(p.name + ".tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, st.st_mode & 0o777)
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        handle.write(updated)
        handle.flush()
        os.fsync(handle.fileno())
    try:
        os.chown(tmp, st.st_uid, st.st_gid)
    except PermissionError:
        pass
    os.replace(tmp, p)

def wait_for_db(container, attempts=60):
    for _ in range(attempts):
        probe = subprocess.run(
            ["docker", "exec", container, "pg_isready", "-U", "postgres", "-d", "postgres"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        if probe.returncode == 0:
            return
        time.sleep(2)
    raise RuntimeError("Supabase PostgreSQL did not become ready")

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--env", required=True)
    parser.add_argument("--template", required=True)
    parser.add_argument("--core-env")
    parser.add_argument("--container", default="supabase-db")
    args = parser.parse_args()

    values = load_env(args.env)
    password = values.get("VATI_LEDGER_PASSWORD", "")
    if len(password) < 32:
        raise SystemExit("VATI_LEDGER_PASSWORD missing or too short")

    template = pathlib.Path(args.template).read_text(encoding="utf-8")
    sql = build_sql(template, password)
    wait_for_db(args.container)
    applied = subprocess.run(
        ["docker", "exec", "-i", args.container, "psql", "-U", "postgres", "-d", "postgres",
         "-v", "ON_ERROR_STOP=1"],
        input=sql, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    )
    if applied.returncode:
        raise SystemExit("VATI ledger reconciliation failed: " + applied.stderr[-1000:])

    import psycopg
    with psycopg.connect(
        host="127.0.0.1", port=5432, dbname="postgres",
        user="vati", password=password, connect_timeout=5,
    ) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT count(*) FROM vati.events")
            cur.fetchone()
            cur.execute("SELECT count(*) FROM vati.chain_head")
            cur.fetchone()

    if args.core_env:
        update_core_env(args.core_env, password)
    print("VATI_LEDGER_RECONCILED_GREEN")

if __name__ == "__main__":
    main()
