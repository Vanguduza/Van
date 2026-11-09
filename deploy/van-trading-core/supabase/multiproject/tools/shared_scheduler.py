#!/usr/bin/env python3
"""Source-locked GTR cron split and inactive central scheduling. NEVER deploys.

pg_cron is installed once per PostgreSQL cluster. Keep that existing control
plane; no project-local pg_cron, replacement scheduler or automatic activation.
All SQL below is a reviewed candidate requiring the original owner authority.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import pathlib
import re
import bootstrap as b
import render

GTR_COMMIT='8131858c7c7479d178cbe9e246f83cb49ed80f5e'
BASELINE_SHA256='2502826ee08e67d7bcee3f7bdacdc31d944ccbb1bf9c3d86090b79b938ea016c'
BASELINE_PATH='supabase/migrations/20261102080000_reconciled_erp_baseline.sql'
BASELINE_SIZE=4027262
CRON_INSTALL=b'CREATE EXTENSION IF NOT EXISTS pg_cron WITH SCHEMA pg_catalog;'
# Original names, expressions, statements and true SQL signatures. In particular
# the morning-summary function takes a DEFAULT date; its signature is NOT ().
JOBS=(
 ('approval-alerts-sweep-v1','*/5 * * * *','SELECT private.sweep_approval_alerts()','private.sweep_approval_alerts()'),
 ('commerce-expire-checkouts-v1','*/2 * * * *','SELECT private.expire_commerce_checkouts_internal();','private.expire_commerce_checkouts_internal()'),
 ('customer-suspension-sweep-v1','10 2 * * *','SELECT private.sweep_customer_suspensions();','private.sweep_customer_suspensions()'),
 ('morning-summary-v1','0 5 * * *','SELECT private.send_morning_summaries()','private.send_morning_summaries(date)'),
)

def project(p:dict)->dict:
    return render.validate({'schema_version':1,'target_installation':render.ROOT,
        'allowed_postgres_service':'db','projects':[p]})[0]

def role(p:dict)->str:
    return 'dial_'+project(p)['project_uuid'].replace('-','')+'_cron'

def job_name(p:dict,name:str)->str:
    if name not in {x[0] for x in JOBS}:raise ValueError('UNKNOWN_GTR_JOB')
    return 'dial:'+project(p)['project_uuid'].replace('-','')+':'+name

def original_schedule(job:tuple)->bytes:
    name,schedule,command,_=job
    return ('SELECT cron.schedule('+', '.join(b.lit(x) for x in (name,schedule,command))+');').encode()

def adapt_baseline(raw:bytes)->tuple[bytes,dict]:
    """Only five exact statements may change. Everything else is retained."""
    if type(raw) is not bytes or len(raw)!=BASELINE_SIZE or hashlib.sha256(raw).hexdigest()!=BASELINE_SHA256:
        raise ValueError('GTR_BASELINE_SOURCE_MISMATCH')
    replacements=[(CRON_INSTALL,b'-- DIAL: original pg_cron installation is retained in the existing central cron database.')]
    replacements += [(original_schedule(j),('-- DIAL: central inactive schedule for '+j[0]+' is staged separately.').encode()) for j in JOBS]
    result=raw;edits=[]
    for old,new in replacements:
        if raw.count(old)!=1:raise ValueError('EXACT_SCHEDULER_STATEMENT_REQUIRED')
        if new in raw:raise ValueError('ADAPTATION_MARKER_COLLISION')
        edits.append({'source_offset':raw.index(old),'original_utf8':old.decode(),
            'replacement_utf8':new.decode()})
        result=result.replace(old,new,1)
    restored=result
    for old,new in reversed(replacements):restored=restored.replace(new,old,1)
    if restored!=raw:raise ValueError('BYTE_EXACT_REVERSAL_FAILED')
    return result,{'kind':'GTR_FRESH_BASELINE_CENTRAL_CRON_ADAPTATION',
        'upstream_commit':GTR_COMMIT,'upstream_path':BASELINE_PATH,
        'upstream_sha256':BASELINE_SHA256,'candidate_sha256':hashlib.sha256(result).hexdigest(),
        'edit_count':5,'edits':edits,'byte_exact_reverse_verified':True,
        'application_functions_tables_policies_unchanged':True,
        'production_authorized':False,'full_baseline_replayed':False}

def role_sql(p:dict)->str:
    p=project(p);r=role(p)
    return '\n'.join(['\\set ON_ERROR_STOP on','BEGIN;',
        f'DO $g$ BEGIN IF EXISTS(SELECT FROM pg_roles WHERE rolname={b.lit(r)}) THEN RAISE EXCEPTION \'CRON_ROLE_EXISTS_RECONCILE\'; END IF; END $g$;',
        f'CREATE ROLE {b.ident(r)} NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS NOINHERIT CONNECTION LIMIT 2;',
        f'GRANT CONNECT ON DATABASE {b.ident(p["database"])} TO {b.ident(r)};',
        f'ALTER ROLE {b.ident(r)} SET statement_timeout=60000;',
        f'ALTER ROLE {b.ident(r)} SET lock_timeout=5000;',
        'COMMIT;',''])

def grants_sql(p:dict)->str:
    p=project(p);r=role(p);signatures=[x[3] for x in JOBS]
    allowed=','.join(b.lit(x) for x in signatures)
    sql=['\\set ON_ERROR_STOP on','BEGIN;',
        f"DO $g$ BEGIN IF current_database()<>{b.lit(p['database'])} OR NOT EXISTS(SELECT FROM dial_private.project_identity WHERE singleton AND project_uuid={b.lit(p['project_uuid'])}::uuid) THEN RAISE EXCEPTION 'CRON_PROJECT_IDENTITY_MISMATCH'; END IF; END $g$;",
        f'GRANT USAGE ON SCHEMA private TO {b.ident(r)};']
    for sig in signatures:
        sql += [f"DO $g$ BEGIN IF NOT EXISTS(SELECT FROM pg_proc WHERE oid=to_regprocedure({b.lit(sig)}) AND prosecdef AND prokind='f' AND prorettype='integer'::regtype AND ('search_path='||chr(34)||chr(34))=ANY(proconfig)) THEN RAISE EXCEPTION 'CRON_GTR_FUNCTION_CONTRACT_MISMATCH'; END IF; END $g$;",
                f'GRANT EXECUTE ON FUNCTION {sig} TO {b.ident(r)};']
    sql += [f"DO $g$ BEGIN IF EXISTS(SELECT FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace WHERE n.nspname='private' AND p.oid NOT IN ({','.join('to_regprocedure('+b.lit(s)+')' for s in signatures)}) AND has_function_privilege({b.lit(r)},p.oid,'EXECUTE')) THEN RAISE EXCEPTION 'CRON_UNREVIEWED_PRIVATE_FUNCTION_ACCESS'; END IF; END $g$;",
        'COMMIT;','']
    return '\n'.join(sql)

def deny_hba(projects:list[dict])->tuple[str,list[dict]]:
    projects=render.validate({'schema_version':1,'target_installation':render.ROOT,'allowed_postgres_service':'db','projects':projects})
    rows=[];text=['# Scheduler roles may use native background workers only. FIRST rules.']
    for p in projects:
        r=role(p)
        for typ,addr,mask,cidr in [('local',None,None,None),('host','0.0.0.0','0.0.0.0','0.0.0.0/0'),('host','::','::','::/0')]:
            rows.append({'type':typ,'database':['all'],'user_name':[r],'address':addr,'netmask':mask,'auth_method':'reject'})
            text.append(' '.join([typ,'all',r]+([cidr] if cidr else [])+['reject']))
    return '\n'.join(text)+'\n',rows

def activation_sql(projects:list[dict])->str:
    _,rows=deny_hba(projects)
    sql=['\\set ON_ERROR_STOP on','BEGIN;',
        'DO $g$ DECLARE observed jsonb; BEGIN',
        "IF current_setting('cron.use_background_workers',true) IS DISTINCT FROM 'on' THEN RAISE EXCEPTION 'CRON_NATIVE_BACKGROUND_WORKERS_REQUIRED'; END IF;",
        "IF EXISTS(SELECT FROM pg_hba_file_rules WHERE error IS NOT NULL) OR pg_conf_load_time()<(pg_stat_file(current_setting('hba_file'))).modification THEN RAISE EXCEPTION 'CRON_HBA_RELOAD_REQUIRED'; END IF;",
        f"SELECT jsonb_agg(jsonb_build_object('type',type,'database',database,'user_name',user_name,'address',address,'netmask',netmask,'auth_method',auth_method) ORDER BY rule_number) INTO observed FROM (SELECT * FROM pg_hba_file_rules ORDER BY rule_number LIMIT {len(rows)}) t;",
        f"IF observed IS DISTINCT FROM {b.lit(json.dumps(rows))}::jsonb THEN RAISE EXCEPTION 'CRON_EXACT_DENY_PREFIX_REQUIRED'; END IF; END $g$;"]
    for p in projects:
        r=role(p)
        sql += [f"DO $g$ BEGIN IF NOT EXISTS(SELECT FROM pg_authid WHERE rolname={b.lit(r)} AND NOT rolcanlogin AND NOT rolsuper AND NOT rolcreatedb AND NOT rolcreaterole AND NOT rolreplication AND NOT rolbypassrls AND NOT rolinherit AND rolpassword IS NULL) OR EXISTS(SELECT FROM pg_auth_members WHERE member=(SELECT oid FROM pg_roles WHERE rolname={b.lit(r)})) THEN RAISE EXCEPTION 'CRON_ROLE_NOT_QUARANTINED'; END IF; END $g$;",
                f'ALTER ROLE {b.ident(r)} LOGIN;']
    return '\n'.join(sql+['COMMIT;',''])

def registration_sql(p:dict,cron_database:str,timezone:str)->str:
    p=project(p);b.ident(cron_database)
    if cron_database==p['database']:raise ValueError('SEPARATE_EXISTING_CRON_DATABASE_REQUIRED')
    if not isinstance(timezone,str) or not re.fullmatch(r'[A-Za-z0-9_+/-]{1,64}',timezone):raise ValueError('EXACT_CRON_TIMEZONE_REQUIRED')
    r=role(p);names=[job_name(p,j[0]) for j in JOBS]
    sql=['\\set ON_ERROR_STOP on','BEGIN;','SET LOCAL lock_timeout=5000;',
        "SELECT pg_advisory_xact_lock(hashtextextended('dial:shared-cron-registration-v1',0));",
        'LOCK TABLE cron.job IN SHARE ROW EXCLUSIVE MODE;',
        'DO $g$ BEGIN',
        f"IF current_database()<>{b.lit(cron_database)} OR current_setting('cron.database_name',true) IS DISTINCT FROM {b.lit(cron_database)} THEN RAISE EXCEPTION 'CRON_EXISTING_DATABASE_MISMATCH'; END IF;",
        f"IF current_setting('cron.timezone',true) IS DISTINCT FROM {b.lit(timezone)} THEN RAISE EXCEPTION 'CRON_TIMEZONE_MISMATCH'; END IF;",
        "IF current_setting('cron.use_background_workers',true) IS DISTINCT FROM 'on' THEN RAISE EXCEPTION 'CRON_NATIVE_BACKGROUND_WORKERS_REQUIRED'; END IF;",
        f"IF NOT EXISTS(SELECT FROM pg_roles WHERE rolname={b.lit(r)} AND rolcanlogin AND NOT rolsuper AND NOT rolcreatedb AND NOT rolcreaterole AND NOT rolreplication AND NOT rolbypassrls AND NOT rolinherit) THEN RAISE EXCEPTION 'CRON_RUNTIME_ROLE_NOT_SCOPED'; END IF;",
        f"IF EXISTS(SELECT FROM pg_auth_members WHERE member=(SELECT oid FROM pg_roles WHERE rolname={b.lit(r)})) OR has_schema_privilege({b.lit(r)},'cron','USAGE') THEN RAISE EXCEPTION 'CRON_RUNTIME_HAS_SCHEDULING_AUTHORITY'; END IF;",
        f"IF EXISTS(SELECT FROM cron.job WHERE jobname IN ({','.join(b.lit(x) for x in names)})) THEN RAISE EXCEPTION 'CRON_JOB_ALREADY_EXISTS_NO_UPSERT'; END IF; END $g$;"]
    for name,expr,command,_ in JOBS:
        full=job_name(p,name)
        sql += [f'SELECT cron.schedule_in_database({b.lit(full)},{b.lit(expr)},{b.lit(command)},{b.lit(p["database"])},{b.lit(r)},false);',
                f"DO $g$ BEGIN IF (SELECT count(*) FROM cron.job WHERE jobname={b.lit(full)} AND database={b.lit(p['database'])} AND username={b.lit(r)} AND command={b.lit(command)} AND schedule={b.lit(expr)} AND NOT active)<>1 THEN RAISE EXCEPTION 'CRON_REGISTRATION_READBACK_MISMATCH'; END IF; END $g$;"]
    return '\n'.join(sql+['COMMIT;',''])

def compile_bundle(raw:bytes,p:dict,cron_database:str,timezone:str)->dict[str,str]:
    p=project(p);adapted,proof=adapt_baseline(raw)
    hba,_=deny_hba([p])
    files={'gtr-baseline.central-cron.sql':adapted.decode(),
        'cron-role.quarantined.sql':role_sql(p),'cron-grants.project.sql':grants_sql(p),
        'cron-deny.hba-prefix.conf':hba,'cron-role.enable-after-hba.sql':activation_sql([p]),
        'cron-register.inactive.sql':registration_sql(p,cron_database,timezone)}
    proof.update({'database':p['database'],'project_uuid':p['project_uuid'],'scheduler_role':role(p),
        'existing_cron_database':cron_database,'observed_cron_timezone':timezone,
        'jobs':[{'name':job_name(p,n),'schedule':s,'command':c,'function_signature':f,'active':False} for n,s,c,f in JOBS],
        'files':{n:hashlib.sha256(v.encode()).hexdigest() for n,v in files.items()},
        'native_scheduler_changes_executed':False,'canary_activation_authorized':False,
        'limitations':['Only pinned FRESH-INSTALL baseline may be adapted; original GTR source stays unchanged.',
            'Application/source-history comparison, Auth/Storage/Vault/pg_net versions and entire migration replay remain unqualified.',
            'Actual central cron database, timezone, background workers, HBA and role/function grants must be independently admitted.',
            'No job activation SQL is supplied. Registration is inactive; original owner must approve enabling effects.',
            'Shared background workers do not use HBA. SQL role isolation and protected central scheduling authority remain essential.']})
    files['scheduler-candidate.json']=json.dumps(proof,sort_keys=True,indent=2)+'\n'
    return files

def main(argv=None)->int:
    pa=argparse.ArgumentParser(description=__doc__)
    pa.add_argument('--manifest',type=pathlib.Path,required=True)
    pa.add_argument('--baseline',type=pathlib.Path,required=True)
    pa.add_argument('--cron-database',required=True);pa.add_argument('--cron-timezone',required=True)
    pa.add_argument('--out',type=pathlib.Path,required=True)
    a=pa.parse_args(argv)
    try:
        projects,_=render.load_manifest(a.manifest)
        if len(projects)!=1:raise ValueError('EXACT_SINGLE_GTR_TARGET_REQUIRED')
        if a.baseline.is_symlink() or not a.baseline.is_file():raise ValueError('BASELINE_REGULAR_FILE_REQUIRED')
        with a.baseline.open('rb') as f:raw=f.read(BASELINE_SIZE+1)
        render.write_bundle(a.out,compile_bundle(raw,projects[0],a.cron_database,a.cron_timezone))
        print('SHARED_CRON_CANDIDATE_CREATED_NO_DEPLOYMENT');return 0
    except (ValueError,TypeError,KeyError,OSError):
        print('REFUSED_SHARED_CRON_CANDIDATE');return 2

if __name__=='__main__':raise SystemExit(main())
