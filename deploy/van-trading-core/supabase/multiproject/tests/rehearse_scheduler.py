#!/usr/bin/env python3
"""Real pg_cron on a NEW unprivileged disposable PG17 cluster only.

Synthetic private functions exercise scheduler routing/permissions; they are NOT
GTR ERP logic. No production endpoint, credential or database is accepted.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
import pathlib
import secrets
import subprocess
import sys
import tempfile
import time
BASE=pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0,str(BASE/'tools'))
import shared_scheduler as s

class Failure(RuntimeError):pass

class Fixture:
    def __init__(self,a):
        if os.geteuid()==0:raise Failure('NONROOT_ONLY')
        self.a=a;self.tmp=tempfile.TemporaryDirectory(prefix='dial-cron-')
        self.root=pathlib.Path(self.tmp.name);self.root.chmod(0o700)
        self.data=self.root/'pgdata';self.socket=self.root/'socket';self.socket.mkdir(mode=0o700)
        self.env={'PATH':'/usr/bin:/bin','HOME':str(self.root),'LANG':'C.UTF-8',
            'LD_LIBRARY_PATH':str(a.pg_lib),'PGCONNECT_TIMEOUT':'3'}
        self.checks=[];self.started=False
        self.projects=s.render.validate(json.loads((BASE/'projects.rehearsal.json').read_text()))
        self.hashes={str(p.relative_to(BASE)):hashlib.sha256(p.read_bytes()).hexdigest() for p in (BASE/'tools/shared_scheduler.py',pathlib.Path(__file__),BASE/'tools/render.py')}
    def check(self,name,ok):
        if not ok:raise Failure(name)
        self.checks.append(name);print('PASS '+name,flush=True)
    def run(self,argv,text=None,timeout=15):
        return subprocess.run([str(x) for x in argv],input=text,text=True,capture_output=True,env=self.env,timeout=timeout)
    def sql(self,sql,db='postgres',user='fixture_admin',fail=False):
        p=self.run([self.a.pg_bin/'psql','-X','-qAt','-v','ON_ERROR_STOP=1','-h',self.socket,'-p','55479','-U',user,'-d',db],text=sql)
        if p.returncode and not fail:
            (self.root/'last-sql-error.txt').write_text(p.stderr)
            raise Failure('SQL_FAILED_'+db)
        return p
    def start(self):
        pw=self.root/'admin-password';pw.write_text(secrets.token_urlsafe(48));pw.chmod(0o600)
        r=self.run([self.a.pg_bin/'initdb','-D',self.data,'-U','fixture_admin','--encoding=UTF8','--locale=C.UTF-8','--auth-local=trust','--auth-host=scram-sha-256','--pwfile='+str(pw)],timeout=40)
        if r.returncode:raise Failure('INITDB_FAILED')
        with (self.data/'postgresql.conf').open('a') as f:
            f.write("\nlisten_addresses=''\nshared_buffers='16MB'\nmax_connections=24\nmax_worker_processes=10\njit=off\nlog_min_error_statement=panic\nshared_preload_libraries='pg_cron'\ncron.database_name='postgres'\ncron.timezone='GMT'\ncron.use_background_workers=on\ncron.enable_superuser_jobs=off\ncron.max_running_jobs=4\ncron.log_statement=off\n")
        r=self.run([self.a.pg_bin/'pg_ctl','-D',self.data,'-l',self.root/'postgres.log','-o','-p 55479 -k '+str(self.socket),'-w','start'],timeout=25)
        if r.returncode:
            (self.root/'pgctl-error.txt').write_text(r.stderr);raise Failure('PG_START_FAILED')
        self.started=True
        self.check('real_postgresql17_server',self.sql('SHOW server_version_num').stdout.startswith('17'))
        self.sql('CREATE EXTENSION pg_cron; CREATE DATABASE fixture_legacy;')
        self.version=self.sql("SELECT extversion FROM pg_extension WHERE extname='pg_cron'").stdout.strip()
        self.check('real_pg_cron_extension_present',bool(self.version))
        self.sql("CREATE TABLE public.sentinel(value text); INSERT INTO public.sentinel VALUES('preserve-legacy');",db='fixture_legacy')
        self.legacy_acl=self.sql("SELECT coalesce(datacl::text,'NULL') FROM pg_database WHERE datname='fixture_legacy'").stdout
        self.sql('CREATE ROLE fixture_owner NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS; CREATE ROLE anon NOLOGIN;')
        for p in self.projects:
            db=p['database'];self.sql(f'CREATE DATABASE {s.b.ident(db)} OWNER fixture_owner; REVOKE ALL ON DATABASE {s.b.ident(db)} FROM PUBLIC;')
            self.sql(s.role_sql(p))
            identity=f"CREATE SCHEMA dial_private; CREATE TABLE dial_private.project_identity(singleton boolean,project_uuid uuid); INSERT INTO dial_private.project_identity VALUES(true,{s.b.lit(p['project_uuid'])});"
            fixture=identity+"SET ROLE fixture_owner; CREATE SCHEMA private; REVOKE ALL ON SCHEMA public FROM PUBLIC; CREATE TABLE public.scheduler_events(job text,db text,login text);"
            for name,expr,command,sig in s.JOBS:
                signature=sig.replace('(date)','(p_day date DEFAULT NULL::date)')
                fixture+=f"CREATE FUNCTION {signature} RETURNS integer LANGUAGE plpgsql SECURITY DEFINER SET search_path='' AS $fn$ BEGIN INSERT INTO public.scheduler_events VALUES({s.b.lit(name)},current_database(),session_user); RETURN 1; END $fn$; REVOKE ALL ON FUNCTION {sig} FROM PUBLIC;"
            self.sql(fixture,db=db)
            d=self.sql('CREATE EXTENSION pg_cron;',db=db,fail=True)
            self.check(p['slug']+'_second_cron_installation_refused',d.returncode!=0)
            self.check(p['slug']+'_job_role_initially_nologin',self.sql(f"SELECT rolcanlogin FROM pg_roles WHERE rolname={s.b.lit(s.role(p))}").stdout.strip()=='f')
            # A leaked PUBLIC EXECUTE grant must not become authority merely
            # because cron gains USAGE on the application's private schema.
            self.sql("SET ROLE fixture_owner; CREATE FUNCTION private.unreviewed_fixture() RETURNS integer LANGUAGE sql AS 'SELECT 1';",db=db)
            denied=self.sql(s.grants_sql(p),db=db,fail=True)
            self.check(p['slug']+'_unreviewed_private_function_refused',denied.returncode!=0 and 'CRON_UNREVIEWED_PRIVATE_FUNCTION_ACCESS' in denied.stderr)
            self.check(p['slug']+'_refused_grant_transaction_rolled_back',self.sql(f"SELECT has_schema_privilege({s.b.lit(s.role(p))},'private','USAGE')",db=db).stdout.strip()=='f')
            self.sql('DROP FUNCTION private.unreviewed_fixture();',db=db)
            self.sql(s.grants_sql(p),db=db)
            self.check(p['slug']+'_correct_default_date_function_grant',self.sql(f"SELECT has_function_privilege({s.b.lit(s.role(p))},'private.send_morning_summaries(date)','EXECUTE')",db=db).stdout.strip()=='t')
            wrong={**p,'project_uuid':'17171717-1717-4717-8717-171717171717'}
            self.check(p['slug']+'_wrong_project_identity_refused',self.sql(s.grants_sql(wrong),db=db,fail=True).returncode!=0)
            self.check(p['slug']+'_role_recreation_refused',self.sql(s.role_sql(p),fail=True).returncode!=0)
        prefix,_=s.deny_hba(self.projects);activation=s.activation_sql(self.projects)
        failed=self.sql(activation,fail=True)
        self.check('activation_without_exact_hba_refused',failed.returncode!=0 and 'CRON_EXACT_DENY_PREFIX_REQUIRED' in failed.stderr)
        hba=self.data/'pg_hba.conf';hba.write_text(prefix+hba.read_text())
        self.run([self.a.pg_bin/'pg_ctl','-D',self.data,'reload']);time.sleep(.25)
        self.sql(activation)
        self.check('scheduler_login_enabled_only_after_deny_prefix',True)
        self.check('activation_replay_refused',self.sql(activation,fail=True).returncode!=0)
    def exercise(self):
        for p in self.projects:
            db=p['database'];r=s.role(p);slug=p['slug']
            self.check(slug+'_own_direct_socket_login_rejected',self.sql('SELECT 1',db=db,user=r,fail=True).returncode!=0)
            self.check(slug+'_central_direct_socket_login_rejected',self.sql('SELECT 1',user=r,fail=True).returncode!=0)
            self.check(slug+'_cron_registry_unreadable_to_job_role',self.sql(f'SET ROLE {s.b.ident(r)}; SELECT * FROM cron.job;',fail=True).returncode!=0)
            self.check(slug+'_job_role_cannot_schedule',self.sql(f"SET ROLE {s.b.ident(r)}; SELECT cron.schedule('bad','1 seconds','SELECT 1');",fail=True).returncode!=0)
            self.check(slug+'_timezone_change_refused',self.sql(s.registration_sql(p,'postgres','Africa/Harare'),fail=True).returncode!=0)
            self.sql(s.registration_sql(p,'postgres','GMT'))
            original=self.sql(f"SELECT jobname,schedule,command,database,username,active FROM cron.job WHERE username={s.b.lit(r)} ORDER BY jobname").stdout
            self.check(slug+'_four_inactive_scoped_jobs',len(original.splitlines())==4 and all(line.endswith('|f') for line in original.splitlines()))
            fail=self.sql(s.registration_sql(p,'postgres','GMT'),fail=True)
            self.check(slug+'_native_upsert_blocked_before_overwrite',fail.returncode!=0 and 'CRON_JOB_ALREADY_EXISTS_NO_UPSERT' in fail.stderr)
            again=self.sql(f"SELECT jobname,schedule,command,database,username,active FROM cron.job WHERE username={s.b.lit(r)} ORDER BY jobname").stdout
            self.check(slug+'_rejected_replay_preserves_original_jobs',again==original)
            other=next(q for q in self.projects if q!=p)
            deny=self.sql(f"SELECT cron.schedule_in_database('fixture-forbidden-target','1 seconds','SELECT 1',{s.b.lit(other['database'])},{s.b.lit(r)},false);",fail=True)
            self.check(slug+'_native_scheduler_denies_foreign_database',deny.returncode!=0 and 'CONNECT privilege' in deny.stderr)
            denied=self.sql(f'SET ROLE {s.b.ident(r)}; SELECT * FROM public.scheduler_events;',db=db,fail=True)
            self.check(slug+'_job_role_cannot_read_ungranted_application_table',denied.returncode!=0)
        time.sleep(1.5)
        for p in self.projects:
            self.check(p['slug']+'_inactive_jobs_have_no_effects',self.sql('SELECT count(*) FROM public.scheduler_events',db=p['database']).stdout.strip()=='0')
        self.check('one_central_scheduler_contains_eight_distinct_jobs',self.sql('SELECT count(DISTINCT jobname) FROM cron.job').stdout.strip()=='8')
        # TEST-ONLY activation on this newly created cluster. Original GTR
        # schedules were proved above; accelerate synthetic function probes.
        self.sql("SELECT cron.alter_job(jobid,schedule:='1 seconds',username:=username,active:=true) FROM cron.job;")
        deadline=time.monotonic()+15;complete=False
        while time.monotonic()<deadline:
            if all(self.sql('SELECT count(DISTINCT job) FROM public.scheduler_events',db=p['database']).stdout.strip()=='4' for p in self.projects):complete=True;break
            time.sleep(.3)
        self.check('real_background_workers_execute_four_functions_in_each_database',complete)
        self.sql('SELECT cron.alter_job(jobid,username:=username,active:=false) FROM cron.job;')
        time.sleep(.5)
        for p in self.projects:
            db=p['database'];r=s.role(p)
            result=self.sql(f"SELECT bool_and(db={s.b.lit(db)} AND login={s.b.lit(r)}),count(DISTINCT job) FROM public.scheduler_events",db=db).stdout.strip()
            self.check(p['slug']+'_real_execution_uses_exact_database_and_login',result=='t|4')
            self.check(p['slug']+'_no_project_cron_extension',self.sql("SELECT count(*) FROM pg_extension WHERE extname='pg_cron'",db=db).stdout.strip()=='0')
        self.check('native_jobs_succeeded_under_nonprivileged_runtime_roles',int(self.sql("SELECT count(*) FROM cron.job_run_details WHERE status='succeeded'").stdout)>=8)
        self.check('no_job_runs_as_cluster_superuser',self.sql("SELECT count(*) FROM cron.job j JOIN pg_roles r ON r.rolname=j.username WHERE r.rolsuper OR r.rolcreaterole OR r.rolbypassrls").stdout.strip()=='0')
        self.check('application_role_has_no_central_scheduler_authority',self.sql('SET ROLE anon; SELECT * FROM cron.job;',fail=True).returncode!=0)
        self.check('original_fixture_data_preserved',self.sql('SELECT value FROM public.sentinel',db='fixture_legacy').stdout.strip()=='preserve-legacy')
        self.check('original_fixture_acl_preserved',self.sql("SELECT coalesce(datacl::text,'NULL') FROM pg_database WHERE datname='fixture_legacy'").stdout==self.legacy_acl)
        self.check('jobs_disabled_after_test_activation',self.sql('SELECT count(*) FROM cron.job WHERE active').stdout.strip()=='0')
        raw=self.a.gtr_baseline.read_bytes();adapted,proof=s.adapt_baseline(raw)
        self.check('actual_pinned_gtr_baseline_sha_matches',hashlib.sha256(raw).hexdigest()==s.BASELINE_SHA256)
        self.check('actual_baseline_has_only_five_scheduler_edits',proof['edit_count']==5 and proof['byte_exact_reverse_verified'])
        self.check('actual_gtr_business_sql_preserved_by_reversible_split',proof['application_functions_tables_policies_unchanged'])
        self.adaptation=proof
    def cleanup(self):
        if self.started:
            r=self.run([self.a.pg_bin/'pg_ctl','-D',self.data,'-m','fast','-w','stop'],timeout=20)
            if r.returncode:raise Failure('PG_CLEANUP_FAILED')
            self.started=False
    def execute(self):
        error=None
        try:self.start();self.exercise()
        except Exception as e:error=str(e) if isinstance(e,Failure) else type(e).__name__
        finally:
            try:self.cleanup()
            except Exception as e:error=(error or '')+';cleanup:'+type(e).__name__
        for name,digest in self.hashes.items():
            if hashlib.sha256((BASE/name).read_bytes()).hexdigest()!=digest:error='SOURCE_CHANGED_DURING_RUN'
        report={'state':'PASS' if error is None else 'FAIL','error':error,'checks':self.checks,'check_count':len(self.checks),
            'scope':'ONE_NEW_PG17_REAL_PG_CRON_TWO_DATABASE_SYNTHETIC_SCHEDULER','cron_sql_version':getattr(self,'version',None),
            'source_sha256':self.hashes,'native_sha256':hashlib.sha256((self.a.pg_bin/'postgres').read_bytes()).hexdigest(),
            'pg_cron_library_sha256':hashlib.sha256((self.a.pg_bin.parent/'lib/pg_cron.so').read_bytes()).hexdigest(),
            'gtr_adaptation':getattr(self,'adaptation',None),'production_changes':False,'full_gtr_sql_replayed':False,
            'gtr_business_job_logic_tested':False,'cleanup_completed':not self.started,
            'not_tested':['live VAN','ARM64 donor','full GTR baseline/Auth/Storage/Vault/pg_net','real job cadence/timezone','active writer migration','production cron authority and release']}
        fd=os.open(self.a.report,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
        with os.fdopen(fd,'w') as f:f.write(json.dumps(report,indent=2,sort_keys=True)+'\n')
        if error:
            self.tmp._finalizer.detach();print('FAIL '+error+' PRIVATE_DIAGNOSTICS='+str(self.root),flush=True);return 1
        self.tmp.cleanup();print('PASS_ALL '+str(len(self.checks)),flush=True);return 0

def main():
    pa=argparse.ArgumentParser(description=__doc__)
    pa.add_argument('--pg-bin',type=pathlib.Path,required=True);pa.add_argument('--pg-lib',type=pathlib.Path,required=True)
    pa.add_argument('--gtr-baseline',type=pathlib.Path,required=True);pa.add_argument('--report',type=pathlib.Path,required=True)
    a=pa.parse_args();os.umask(0o077)
    if not a.report.is_absolute() or a.report.exists():raise Failure('NEW_ABSOLUTE_REPORT_REQUIRED')
    for f in (a.pg_bin/'postgres',a.pg_bin/'initdb',a.pg_bin/'psql',a.gtr_baseline):
        if not f.is_absolute() or not f.is_file():raise Failure('EXACT_STAGED_INPUT_REQUIRED')
    return Fixture(a).execute()
if __name__=='__main__':raise SystemExit(main())
