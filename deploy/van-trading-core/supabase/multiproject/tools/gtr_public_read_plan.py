#!/usr/bin/env python3
"""Pure source-only plan for one Nissan GTR public catalogue read grant.

This module does not execute SQL, connect to Supabase, or authorize deployment.
The output is intentionally scoped to an explicit separate project database
and must pass the DIAL owner admission and canary gates before any application.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import pathlib
import re
import render as artifact_render

SOURCE_COMMIT="8131858c7c7479d178cbe9e246f83cb49ed80f5e"
KIND="GTR_SOURCE_ONLY_STOCK_ITEM_IMAGE_READ_PLAN_V1"
PROJECT_RE=re.compile(r"^[a-z][a-z0-9_]{0,62}$")
FORBIDDEN={"postgres","_supabase","template0","template1","supabase","gtr_replay_backup"}

class GrantPlanError(ValueError):
    pass

def render(project_database:str)->str:
    """Return one review-only SQL transaction; never execute it."""
    if not isinstance(project_database,str) or not PROJECT_RE.fullmatch(project_database):
        raise GrantPlanError("EXACT_SAFE_PROJECT_DATABASE_NAME_REQUIRED")
    if project_database in FORBIDDEN:
        raise GrantPlanError("EXISTING_DONOR_OR_PLATFORM_DATABASE_REFUSED")
    return f"""-- REVIEW ONLY: source-locked Nissan GTR compatibility candidate.
-- This is NOT a deployment/release authorization. Do not apply automatically.
-- SQL affects only the selected project DB, never an original VAN/VATI DB.
-- Intended after the thirteen pinned Nissan GTR source migrations.
BEGIN;
SET LOCAL statement_timeout='8s';
SET LOCAL lock_timeout='2s';
SET LOCAL search_path=pg_catalog;
DO $gtr_public_read_gate$
BEGIN
  IF current_database() <> '{project_database}'
     OR current_user <> 'postgres'
     OR NOT EXISTS (SELECT 1 FROM pg_catalog.pg_roles WHERE rolname='anon')
     OR NOT EXISTS (
       SELECT 1 FROM pg_catalog.pg_class c
       JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace
       WHERE n.nspname='public' AND c.relname='stock_item_images'
         AND c.relkind='r' AND c.relrowsecurity
         AND pg_catalog.pg_get_userbyid(c.relowner)='postgres')
     OR NOT EXISTS (
       SELECT 1 FROM pg_catalog.pg_policies p
       WHERE p.schemaname='public'
         AND p.tablename='stock_item_images'
         AND p.policyname='stock_item_images_public_read'
         AND p.cmd='SELECT'
         AND 'anon'=ANY(p.roles)
         AND p.qual='true'
         AND p.with_check IS NULL)
  THEN
    RAISE EXCEPTION 'GTR_PUBLIC_READ_COMPATIBILITY_PRECONDITION_REFUSED';
  END IF;
END $gtr_public_read_gate$;
GRANT SELECT ON TABLE public.stock_item_images TO anon;
COMMIT;
"""

def manifest(project_database:str)->dict:
    sql=render(project_database)
    return {
        "schema_version":1,
        "kind":KIND,
        "project_database_binding":project_database,
        "declared_source_commit":SOURCE_COMMIT,
        "source_bytes_verified_by_compiler":False,
        "candidate_sql_sha256":hashlib.sha256(sql.encode()).hexdigest(),
        "tables_affected":["public.stock_item_images"],
        "role":"anon","privileges":["SELECT"],
        "expected_policy":"stock_item_images_public_read",
        "requires_rls_enabled":True,
        "requires_existing_public_read_policy":True,
        "production_sql_executed":False,
        "release_admitted":False,
        "canary_authorized":False,
        "migration_history_repair_authorized":False,
        "nissan_gtr_cutover_authorized":False,
        "deletes_or_revokes_permissions":False,
        "limits":[
          "Only one narrow project-local SELECT grant is proposed.",
          "It restores a hosted table-level permission with a pre-existing TRUE RLS SELECT policy.",
          "It is neither a blanket copy of 1735 hosted grants nor proof of PostgREST behavior.",
          "Never apply this review candidate to the original postgres or _supabase database.",
          "Original canary execution refusal and signed-release gates remain binding."
        ]
    }

def main(argv=None)->int:
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-database",required=True)
    parser.add_argument("--out",type=pathlib.Path,required=True)
    args=parser.parse_args(argv)
    try:
        values=manifest(args.project_database)
        sql=render(args.project_database)
        out=args.out
        if not out.is_absolute() or ".." in out.parts or out.exists():
            raise GrantPlanError("NEW_ABSOLUTE_PRIVATE_OUTPUT_REQUIRED")
        if any(p in out.parents or out==p for p in map(pathlib.Path,("/opt/van-trading","/etc/dial-supabase","/srv/dial-supabase"))):
            raise GrantPlanError("ACTIVE_INSTALLATION_OUTPUT_REFUSED")
        artifact_render.write_bundle(out,{
            "candidate-not-admitted.sql":sql,
            "candidate-manifest.json":json.dumps(values,indent=2,sort_keys=True)+"\n"
        })
        print("GTR_STOCK_IMAGE_SOURCE_CANDIDATE_ONLY")
        return 0
    except (OSError,GrantPlanError,artifact_render.CandidateError):
        print("GTR_STOCK_IMAGE_COMPATIBILITY_PRECONDITION_REFUSED")
        return 2
if __name__=="__main__":raise SystemExit(main())
