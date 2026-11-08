#!/usr/bin/env python3
"""Exercise read-only ledger capture against one NEW synthetic non-root PG17.

No production endpoint, hosted credential, Docker service or existing DB input.
The real 311 SQL source files are hashed only, never executed by this harness.
"""
from __future__ import annotations
import argparse
from datetime import datetime,timezone
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
import gtr_history_reconcile as g

class Failure(RuntimeError):pass

class Fixture:
    def __init__(self,args):
        if os.geteuid()==0:raise Failure('NONROOT_FIXTURE_REQUIRED')
        self.args=args;self.checks=[];self.started=False;self.pid=None
        self.temp=tempfile.TemporaryDirectory(prefix='dial-gtr-ledger-')
        self.root=pathlib.Path(self.temp.name);self.root.chmod(0o700)
        self.data=self.root/'pgdata';self.sock=self.root/'sock';self.sock.mkdir(mode=0o700)
        self.env={'PATH':'/usr/bin:/bin','LANG':'C.UTF-8','HOME':str(self.root),
            'LD_LIBRARY_PATH':str(args.pg_lib),'PGCONNECT_TIMEOUT':'3'}
        self.hashes={str(p.relative_to(BASE)):hashlib.sha256(p.read_bytes()).hexdigest() for p in [
            BASE/'tools/gtr_history_reconcile.py',BASE/'tools/gtr_migration_plan.py',
            BASE/'tools/recovery.py',BASE/'tools/render.py',pathlib.Path(__file__)]}
    def check(self,name,passed):
        if not passed:raise Failure(name)
        self.checks.append(name);print('PASS '+name,flush=True)
    def command(self,argv,text=None,timeout=20):
        return subprocess.run([str(x) for x in argv],input=text,text=True,capture_output=True,env=self.env,timeout=timeout)
    def sql(self,text,role='fixture_admin',fail_ok=False):
        r=self.command([self.args.pg_bin/'psql','-X','-qAt','-v','ON_ERROR_STOP=1',
            '-h',self.sock,'-p','55487','-U',role,'-d','postgres'],text)
        if r.returncode and not fail_ok:
            (self.root/'private-sql-error.txt').write_text(r.stderr)
            raise Failure('FIXTURE_SQL_FAILED')
        return r
    def capture(self,nonce):
        p=self.sql(g.capture_sql(nonce),'history_observer')
        self.check('capture_'+nonce[:4]+'_one_json_result',len(p.stdout.strip().splitlines())==1)
        return json.loads(p.stdout)
    def start(self):
        pw=self.root/'password';pw.write_text(secrets.token_urlsafe(40));pw.chmod(0o600)
        r=self.command([self.args.pg_bin/'initdb','-D',self.data,'-U','fixture_admin','--encoding=UTF8','--locale=C.UTF-8',
            '--auth-local=trust','--auth-host=scram-sha-256','--pwfile='+str(pw)],timeout=40)
        if r.returncode:raise Failure('INITDB_FAILED')
        with (self.data/'postgresql.conf').open('a') as f:
            f.write("\nlisten_addresses=''\nshared_buffers='16MB'\nmax_connections=10\njit=off\nlog_statement=none\nlog_min_error_statement=panic\n")
        r=self.command([self.args.pg_bin/'pg_ctl','-D',self.data,'-l',self.root/'postgres.log','-o','-p 55487 -k '+str(self.sock),'-w','start'],timeout=30)
        self.started=(self.data/'postmaster.pid').exists()
        if r.returncode or not self.started:raise Failure('PG_START_FAILED')
        self.pid=int((self.data/'postmaster.pid').read_text().splitlines()[0])
        self.check('real_postgresql17',int(self.sql('SHOW server_version_num').stdout)//10000==17)
        self.check('no_tcp_listener',self.sql('SHOW listen_addresses').stdout.strip()=='')
        self.sql('CREATE ROLE history_observer LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS; '
            'CREATE ROLE no_ledger_access LOGIN NOSUPERUSER; '
            'CREATE TABLE public.sentinel(value text); INSERT INTO public.sentinel VALUES (\'preserved\'); '
            'CREATE SCHEMA supabase_migrations; '
            'CREATE TABLE supabase_migrations.schema_migrations(version text,name text,statements text[]); '
            'GRANT USAGE ON SCHEMA supabase_migrations TO history_observer; '
            'GRANT SELECT ON supabase_migrations.schema_migrations TO history_observer;')
    def exercise(self):
        catalog=g.source_catalog(self.args.source_root)
        self.check('all_311_pinned_sql_files_verified',sum(len(x) for x in catalog['histories'].values())==311)
        self.check('125_archived_hosted_versions_retained',len(catalog['histories']['hosted_archive'])==125)
        self.check('173_legacy_versions_retained',len(catalog['histories']['legacy'])==173)
        self.check('271_reconstruction_source_bindings_verified',catalog['curated_source_count']==271)
        self.check('ten_cross_family_version_collisions_not_lost',len(catalog['cross_family_version_overlap'])==10)
        self.check('all_ten_repeated_versions_have_distinct_archive_bytes',all(len(x)==2 for x in catalog['cross_family_content_variants'].values()))
        self.source_summary={'groups':{k:len(x) for k,x in catalog['histories'].items()},
            'curated':catalog['curated_source_count'],'cross_family_version_overlap':catalog['cross_family_version_overlap'],
            'catalog_sha256':g.digest(g.canonical(catalog).encode())}
        historical=catalog['histories']['hosted_archive'][0]
        self.sql("INSERT INTO supabase_migrations.schema_migrations VALUES ('"+historical['version']+"','"+historical['name']+"',ARRAY[$x$SELECT 'STATEMENT_SECRET_CANARY'$x$]),"
            "('20260725270000',NULL,NULL),('20261102080000','reconciled_erp_baseline',ARRAY[]::text[]);")
        a=self.capture('a'*32)
        self.check('capture_transaction_read_only',a['read_only'] is True and a['isolation']=='repeatable read')
        self.check('capture_all_ledger_rows',a['row_count']==3 and not a['truncated'])
        self.check('raw_statements_and_canary_not_returned','STATEMENT_SECRET_CANARY' not in json.dumps(a) and all('statements' not in x for x in a['rows']))
        validated=g.validate_snapshot(a,'a'*32)
        self.check('null_statement_array_distinguished',validated['20260725270000']['statement_count'] is None)
        self.check('empty_statement_array_hashed',validated['20261102080000']['statement_count']==0 and validated['20261102080000']['statements_sha256'] is not None)
        expected=hashlib.sha256(b'[]').hexdigest()
        self.check('native_builtin_statement_array_hash_matches',validated['20261102080000']['statements_sha256']==expected)
        result=g.compare(catalog,a,nonce='a'*32,now=datetime.now(timezone.utc))
        self.check('historical_known_version_classified',not any(x['version']==historical['version'] and not x['source_families'] for x in result['classified_versions']))
        self.check('baseline_marker_never_authorizes_replay',not result['may_apply_baseline'] and not result['may_repair_history'])
        self.check('capture_does_not_claim_hosted_connection',not result['current_hosted_state_independently_verified'])
        p=self.root/'capture.json';p.write_text(g.canonical(a));p.chmod(0o600)
        self.check('private_snapshot_reader_roundtrip',g.load_snapshot_file(p)==a)
        self.check('observer_cannot_mutate_ledger',self.sql("INSERT INTO supabase_migrations.schema_migrations VALUES ('20261109000000','forbidden',NULL)",'history_observer',True).returncode!=0)
        blocked=self.sql("BEGIN READ ONLY; UPDATE public.sentinel SET value='not-allowed';",fail_ok=True)
        self.check('postgres_enforces_read_only_write_refusal',blocked.returncode!=0 and 'read-only' in blocked.stderr)
        before=self.sql('SELECT count(*) FROM supabase_migrations.schema_migrations').stdout
        denied=self.sql(g.capture_sql('b'*32),'no_ledger_access',True)
        self.check('no_access_produces_error_not_empty_success',denied.returncode!=0 and not denied.stdout.strip())
        self.check('failed_capture_does_not_repair_ledger',self.sql('SELECT count(*) FROM supabase_migrations.schema_migrations').stdout==before)
        # Changes below affect only synthetic fixture history, not any source SQL.
        self.sql("UPDATE supabase_migrations.schema_migrations SET statements=ARRAY['SELECT 2'] WHERE version='"+historical['version']+"'; DELETE FROM supabase_migrations.schema_migrations WHERE version='20260725270000';")
        time.sleep(.02);z=self.capture('c'*32)
        diff=g.compare(catalog,z,nonce='c'*32,now=datetime.now(timezone.utc),previous=a)
        self.check('changed_original_statement_digest_detected',diff['previous_capture_diff']['changed']==[historical['version']])
        self.check('removed_history_version_detected',diff['previous_capture_diff']['removed']==['20260725270000'])
        self.check('same_baseline_statement_digest_still_not_schema_proof',diff['previous_capture_diff']['same']==['20261102080000'] and not diff['may_cutover'])
        self.sql("INSERT INTO supabase_migrations.schema_migrations SELECT * FROM supabase_migrations.schema_migrations LIMIT 1")
        dup=self.capture('d'*32)
        try:g.validate_snapshot(dup,'d'*32);bad=False
        except ValueError:bad=True
        self.check('duplicate_real_ledger_version_rejected',bad)
        self.sql('TRUNCATE supabase_migrations.schema_migrations; INSERT INTO supabase_migrations.schema_migrations SELECT lpad(i::text,14,\'0\'),\'synthetic\',NULL FROM generate_series(1,10002) i;')
        capped=self.capture('e'*32)
        self.check('native_capture_reports_truncation_at_10001',capped['row_count']==10001 and capped['truncated'])
        try:g.validate_snapshot(capped,'e'*32);bad=False
        except ValueError:bad=True
        self.check('truncated_native_ledger_never_accepted',bad)
        self.sql('ALTER TABLE supabase_migrations.schema_migrations ENABLE ROW LEVEL SECURITY;')
        rls=self.sql(g.capture_sql('f'*32),'history_observer',True)
        self.check('rls_filtered_ledger_refused_not_silently_empty',rls.returncode!=0 and not rls.stdout.strip())
        self.sql('ALTER TABLE supabase_migrations.schema_migrations DISABLE ROW LEVEL SECURITY;')
        self.sql('ALTER TABLE supabase_migrations.schema_migrations RENAME COLUMN statements TO missing_statements;')
        missing=self.sql(g.capture_sql('f'*32),'history_observer',True)
        self.check('unsupported_schema_fails_without_fabrication',missing.returncode!=0 and not missing.stdout.strip())
        self.sql('ALTER TABLE supabase_migrations.schema_migrations RENAME COLUMN missing_statements TO statements; '
            'ALTER TABLE supabase_migrations.schema_migrations RENAME TO original_ledger; '
            'CREATE VIEW supabase_migrations.schema_migrations AS SELECT * FROM supabase_migrations.original_ledger; '
            'GRANT SELECT ON supabase_migrations.schema_migrations TO history_observer;')
        view=self.sql(g.capture_sql('f'*32),'history_observer',True)
        self.check('view_instead_of_original_ledger_refused',view.returncode!=0 and not view.stdout.strip())
        self.check('existing_business_sentinel_preserved',self.sql('SELECT value FROM public.sentinel').stdout.strip()=='preserved')
        self.check('observer_privilege_not_expanded',self.sql("SELECT rolsuper OR rolcreatedb OR rolcreaterole OR rolreplication OR rolbypassrls FROM pg_roles WHERE rolname='history_observer'").stdout.strip()=='f')
    def stop(self):
        if self.started:
            r=self.command([self.args.pg_bin/'pg_ctl','-D',self.data,'-m','fast','-w','stop'],timeout=25)
            if r.returncode:raise Failure('PG_CLEANUP_FAILED')
            self.started=False
        if self.pid and pathlib.Path('/proc/'+str(self.pid)).exists():raise Failure('ORIGINAL_POSTGRES_PID_STILL_PRESENT')
        self.temp.cleanup()
    def execute(self):
        error=None
        try:self.start();self.exercise()
        except Exception as e:error=str(e) if isinstance(e,Failure) else type(e).__name__
        finally:
            try:self.stop()
            except Exception as e:error=(error or '')+';CLEANUP_'+type(e).__name__
        if any(hashlib.sha256((BASE/n).read_bytes()).hexdigest()!=h for n,h in self.hashes.items()):error='SOURCE_CHANGED_DURING_TEST'
        report={'schema_version':1,'state':'PASS' if error is None else 'FAIL','error':error,
            'scope':'DISPOSABLE_POSTGRES_READ_ONLY_LEDGER_CAPTURE_SYNTHETIC_HISTORY',
            'check_count':len(self.checks),'checks':self.checks,'source_sha256':self.hashes,
            'source_inventory':getattr(self,'source_summary',{}),
            'postgres_binary_sha256':hashlib.sha256((self.args.pg_bin/'postgres').read_bytes()).hexdigest(),
            'postgres_version':self.command([self.args.pg_bin/'postgres','--version']).stdout.strip(),
            'cleanup_completed':not self.started and not self.root.exists(),
            'hosted_connection_used':False,'production_changes':False,'release_authorized':False}
        fd=os.open(self.args.report,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
        with os.fdopen(fd,'w') as f:f.write(json.dumps(report,sort_keys=True,indent=2)+'\n')
        print(report['state']+'_ALL '+str(len(self.checks))+((' ERROR='+error) if error else ''),flush=True)
        return 0 if error is None else 1

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--pg-bin',type=pathlib.Path,required=True);p.add_argument('--pg-lib',type=pathlib.Path,required=True)
    p.add_argument('--source-root',type=pathlib.Path,required=True);p.add_argument('--report',type=pathlib.Path,required=True)
    a=p.parse_args();os.umask(0o077)
    if not a.report.is_absolute() or a.report.exists():raise Failure('NEW_ABSOLUTE_REPORT_REQUIRED')
    for f in (a.pg_bin/'initdb',a.pg_bin/'pg_ctl',a.pg_bin/'psql',a.pg_bin/'postgres'):
        if not f.is_absolute() or not f.is_file() or not os.access(f,os.X_OK):raise Failure('STAGED_EXECUTABLE_REQUIRED')
    return Fixture(a).execute()

if __name__=='__main__':raise SystemExit(main())
