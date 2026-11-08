#!/usr/bin/env python3
"""Prepare exact GTR migration SQL with explicit platform-owner sections.

Pure source transformation only: no SQL/SSH/Docker, credentials or release grant.
Only the pinned 13-file source is supported. Five cron statements are separated
by the existing scheduler adapter; all other application SQL bytes are retained.
"""
from __future__ import annotations
import hashlib
import json
import pathlib
import re
import shared_scheduler

BASE=pathlib.Path(__file__).resolve().parents[1]
LOCK=BASE/'evidence/2026-11-08-scheduler/gtr-source-lock.json'
LOCK_SHA256='5305d1db166f1496fe2a56a2e7ac20de9b46c3d86c578d308c2712a12ef604a0'
BASELINE='20261102080000_reconciled_erp_baseline.sql'
STAFF='20261102100000_staff_self_service_reconciliation.sql'
BASELINE_START='-- Application hooks and policies on platform-owned relations are outside the\n-- public/private pg_dump selection and must travel with the application baseline.'
BASELINE_END='-- Retain canonical maintenance schedules; credentials remain in native Vault.'
STAFF_START='INSERT INTO storage.buckets (id, name, public, file_size_limit, allowed_mime_types)'
STAFF_END='CREATE OR REPLACE FUNCTION public.update_my_staff_profile('
RESET='\n-- DIAL_OWNER_SECTION_BEGIN\nRESET ROLE;\n'
RESUME='\n-- DIAL_OWNER_SECTION_END\nSET LOCAL ROLE postgres;\n'
GUARD="""DO $guard$ BEGIN
 IF current_database() <> '__DIAL_GTR_TARGET_DB__' OR current_database() IN ('postgres','_supabase','template0','template1')
    OR current_user <> 'supabase_admin'
    OR NOT EXISTS (SELECT FROM pg_roles WHERE rolname=current_user AND rolsuper)
 THEN RAISE EXCEPTION 'GTR_EXACT_PRIVATE_DATABASE_AND_PLATFORM_OWNER_REQUIRED'; END IF;
END $guard$;
SET LOCAL ROLE postgres;
"""

def digest(data:bytes)->str:return hashlib.sha256(data).hexdigest()

def load_lock(path:pathlib.Path=LOCK)->dict:
    raw=path.read_bytes()
    if LOCK_SHA256 is not None and digest(raw)!=LOCK_SHA256:raise ValueError('GTR_LOCK_DIGEST_MISMATCH')
    value=json.loads(raw)
    if value.get('commit')!=shared_scheduler.GTR_COMMIT or value.get('repo')!='Vanguduza/Nissan-Gtr-Auto':
        raise ValueError('GTR_SOURCE_IDENTITY_MISMATCH')
    rows=value.get('files')
    if not isinstance(rows,list) or len(rows)!=13:raise ValueError('GTR_EXACT_MIGRATION_SET_REQUIRED')
    names=[pathlib.PurePosixPath(x['path']).name for x in rows]
    if names!=sorted(names) or len(set(names))!=13 or names[0]!=BASELINE:
        raise ValueError('GTR_MIGRATION_ORDER_MISMATCH')
    for row in rows:
        if row['path']!='supabase/migrations/'+pathlib.PurePosixPath(row['path']).name or not re.fullmatch(r'[0-9]{14}_[a-z0-9_]+\.sql',pathlib.PurePosixPath(row['path']).name):
            raise ValueError('GTR_SOURCE_PATH_UNSAFE')
        if type(row['bytes']) is not int or row['bytes']<=0 or not re.fullmatch('[a-f0-9]{64}',row['sha256']):
            raise ValueError('GTR_SOURCE_BINDING_INVALID')
    return value

def scoped_section(text:str,start:str,end:str)->tuple[str,dict]:
    if RESET in text or RESUME in text:raise ValueError('GTR_ALREADY_SCOPED')
    if text.count(start)!=1 or text.count(end)!=1 or text.index(start)>=text.index(end):
        raise ValueError('GTR_OWNER_SECTION_BOUNDARY_MISMATCH')
    before=text.index(start);after=text.index(end)
    segment=text[before:after]
    # The two approved regions contain native Auth/Storage DDL/configuration,
    # never new SECURITY DEFINER application functions under a superuser owner.
    if re.search(r'(?m)^CREATE(?: OR REPLACE)? FUNCTION ',segment):
        raise ValueError('GTR_APPLICATION_FUNCTION_IN_PLATFORM_SECTION')
    result=text[:before]+RESET+segment+RESUME+text[after:]
    if result.replace(RESET,'',1).replace(RESUME,'',1)!=text:
        raise ValueError('GTR_OWNER_SCOPE_REVERSAL_FAILED')
    return result,{'source_start':before,'source_end':after,
        'protected_section_sha256':digest(segment.encode()),'byte_exact_reverse_verified':True}

def prepare(name:str,raw:bytes,lock:dict,*,target_database:str)->tuple[str,dict]:
    if not isinstance(target_database,str) or not re.fullmatch(r"[a-z][a-z0-9_]{2,47}",target_database) or target_database in ("postgres","_supabase","template0","template1"):
        raise ValueError("GTR_EXACT_FRESH_PROJECT_DATABASE_REQUIRED")
    if lock!=load_lock():raise ValueError('GTR_UNTRUSTED_MIGRATION_MANIFEST')
    rows={pathlib.PurePosixPath(x['path']).name:x for x in lock['files']}
    if name not in rows:raise ValueError('GTR_UNKNOWN_MIGRATION')
    row=rows[name]
    if type(raw) is not bytes or len(raw)!=row['bytes'] or digest(raw)!=row['sha256']:
        raise ValueError('GTR_MIGRATION_BYTES_CHANGED')
    text=raw.decode('utf-8');cron=None;scope=None
    if name==BASELINE:
        adapted,cron=shared_scheduler.adapt_baseline(raw)
        text,scope=scoped_section(adapted.decode(),BASELINE_START,BASELINE_END)
    elif name==STAFF:text,scope=scoped_section(text,STAFF_START,STAFF_END)
    sql='BEGIN;\n'+GUARD.replace('__DIAL_GTR_TARGET_DB__',target_database)+text+'\nRESET ROLE;\nCOMMIT;\n'
    return sql,{'kind':'GTR_SOURCE_LOCKED_OWNER_CONTEXT_PLAN_NOT_AUTHORIZATION',
        'source_commit':lock['commit'],'target_database':target_database,'source_path':row['path'],
        'source_sha256':row['sha256'],'source_bytes':len(raw),
        'sql_sha256':digest(sql.encode()),'platform_section':scope,
        'cron_statement_edits':cron['edit_count'] if cron else 0,
        'application_sql_owner':'postgres','native_owner_context':'supabase_admin',
        'application_roles_granted_platform_membership':False,
        'native_table_owners_changed':False,'production_authorized':False,
        'live_canary_refusal_resolved':False}

def prepare_all(sources:dict[str,bytes],lock:dict,*,target_database:str)->dict[str,tuple[str,dict]]:
    names=[pathlib.PurePosixPath(x['path']).name for x in lock['files']]
    if set(sources)!=set(names):raise ValueError('GTR_EXACT_MIGRATION_SET_REQUIRED')
    return {name:prepare(name,sources[name],lock,target_database=target_database) for name in names}
