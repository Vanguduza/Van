#!/usr/bin/env python3
"""Real logical restore/restart drill extending the disposable Auth/API rehearsal.

Never accepts a production endpoint. Source database is retained; only the newly
created fixture cluster receives effects. Archives and secrets are deleted after
success. The exported report contains hashes and check names, not private data.
"""
from __future__ import annotations
import hashlib
import json
import os
import pathlib
import secrets
import signal
import subprocess
import time
import uuid
import rehearse_native as native
from rehearse_native import BASE,Failure,b
import recovery


class RecoveryRehearsal(native.Rehearsal):
    def __init__(self,args):
        super().__init__(args)
        for path in (BASE/'tools/recovery.py',pathlib.Path(__file__)):
            self.source_hashes[str(path.relative_to(BASE))]=hashlib.sha256(path.read_bytes()).hexdigest()
        self.recovery_evidence={}

    def stop(self,label):
        process=self.process_by_label[label]
        if process.poll() is None:
            os.killpg(process.pid,signal.SIGTERM)
            try:process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid,signal.SIGKILL);process.wait(timeout=5)
        self.check(label+'_stopped_for_rehearsal',process.poll() is not None)

    def start_again(self,label,database=None):
        argv,env,cwd=self.process_specs[label]
        env=dict(env)
        if database is not None:
            project=next(p for p in self.projects if label.startswith(p['slug']+'-'))
            target={**project,'database':database};s=self.secret[project['slug']]
            kind='auth' if label.endswith('-auth') else 'rest'
            env['GOTRUE_DB_DATABASE_URL' if kind=='auth' else 'PGRST_DB_URI']=b.connection(target,s,kind,'127.0.0.1',self.pgport)
        proc=self.spawn(argv,env,label,cwd)
        project=next(p for p in self.projects if label.startswith(p['slug']+'-'))
        kind='auth' if label.endswith('-auth') else 'rest'
        headers=None if kind=='auth' else {'Authorization':'Bearer '+self.keys[project['slug']]['service_role']}
        self.wait_http(proc,self.endpoints[project['slug']][kind],'/health' if kind=='auth' else '/notes',headers)
        return proc

    def assert_refused(self,name,fn,code=None):
        try:fn()
        except (recovery.RecoveryError,ValueError,OSError) as exc:
            self.check(name,code is None or code in str(exc));return
        raise Failure(name)

    def fingerprint(self,database):
        # Full fixture-table fingerprints stay private; only the combined digest is reported.
        tables=json.loads(self.sql("SELECT coalesce(json_agg(json_build_array(n.nspname,c.relname) ORDER BY n.nspname,c.relname),'[]') FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace WHERE c.relkind='r' AND n.nspname IN ('auth','public','dial_private');",db=database).stdout)
        rows=[]
        for schema,table in tables:
            name='"'+schema.replace('"','""')+'"."'+table.replace('"','""')+'"'
            data=self.sql("SELECT count(*)::text || ':' || md5(coalesce(string_agg(rowtxt,E'\\n' ORDER BY rowtxt),'')) FROM (SELECT row_to_json(t)::text rowtxt FROM "+name+' t) x;',db=database).stdout.strip()
            rows.append([schema,table,data])
        policies=self.sql("SELECT coalesce(json_agg(row_to_json(t) ORDER BY schemaname,tablename,policyname),'[]') FROM pg_policies t WHERE schemaname='public';",db=database).stdout
        owner_acl=self.sql("SELECT coalesce(json_agg(row_to_json(t) ORDER BY schema_name,table_name),'[]') FROM (SELECT n.nspname schema_name,c.relname table_name,r.rolname owner,(SELECT jsonb_agg(jsonb_build_object('grantee',CASE WHEN a.grantee=0 THEN 'PUBLIC' ELSE pg_get_userbyid(a.grantee) END,'grantor',pg_get_userbyid(a.grantor),'privilege',a.privilege_type,'grantable',a.is_grantable) ORDER BY a.grantee,a.grantor,a.privilege_type,a.is_grantable) FROM aclexplode(coalesce(c.relacl,acldefault('r',c.relowner))) a) acl,c.relrowsecurity rls FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace JOIN pg_roles r ON r.oid=c.relowner WHERE c.relkind='r' AND n.nspname IN ('auth','public','dial_private')) t;",db=database).stdout
        parts=[rows,json.loads(policies),json.loads(owner_acl)]
        (self.work/('fingerprint-'+database+'.private.json')).write_text(json.dumps(parts,sort_keys=True))
        return hashlib.sha256(json.dumps(parts,sort_keys=True).encode()).hexdigest()

    def exercise(self):
        super().exercise()
        project=next(p for p in self.projects if p['slug']=='nissan-gtr')
        neighbor=next(p for p in self.projects if p!=project)
        slug=project['slug'];other=neighbor['slug'];ns=b.names(project)
        original=self.fingerprint(neighbor['database'])
        # API roles may execute the safe guard but cannot modify the recovery identity marker.
        for role in ('anon','authenticated','service_role'):
            r=self.sql('SET ROLE '+role+'; SELECT * FROM dial_private.project_identity;',db=project['database'],fail_ok=True)
            self.check('identity_marker_not_readable_by_'+role,r.returncode!=0)
        self.stop(slug+'-auth');self.stop(slug+'-rest')
        code,rows=self.api(neighbor,'/rest/v1/notes?select=body',bearer=self.sessions[other]['access_token'])
        self.check('neighbor_available_during_project_service_stop',code==200 and rows==[{'body':other}])
        self.start_again(slug+'-auth');self.start_again(slug+'-rest')
        code,login=self.api(project,'/auth/v1/token?grant_type=password','POST',{'email':'same-person@fixture.invalid','password':self.user_passwords[slug]})
        self.check('auth_identity_survives_own_service_restart',code==200 and login['user']['id']==self.users[slug])
        retained_refresh=login['refresh_token'];self.sessions[slug]=login
        self.check('neighbor_database_unchanged_by_service_restart',self.fingerprint(neighbor['database'])==original)
        # Quiesce only this project; its neighbor remains online during the dump and restore.
        self.stop(slug+'-auth');self.stop(slug+'-rest')
        before=self.fingerprint(project['database'])
        cluster=self.sql('SELECT system_identifier::text FROM pg_control_system();').stdout.strip()
        password_file=self.work/'backup.pgpass';password_file.write_text('# Fixture uses only its private local socket trust.\n');password_file.chmod(0o600)
        endpoint={'host':str(self.sock),'port':self.pgport,'user':'fixture_admin','passfile':str(password_file),'system_identifier':cluster,'sslmode':'disable'}
        backup=self.work/'project-backup'
        captured=recovery.capture(project,endpoint,self.args.pg_bin,backup,
            '58e7040342bfd7137fb9227d9709fd4287172574',str(self.args.pg_lib))
        self.check('real_snapshot_bound_project_dump_captured',captured['archive_bytes']>10000)
        self.check('backup_private_modes',backup.stat().st_mode&0o777==0o700 and all(f.stat().st_mode&0o777==0o600 for f in backup.iterdir()))
        self.assert_refused('backup_wrong_cluster_observation_denied',lambda:recovery.capture(project,{**endpoint,'system_identifier':'1'},self.args.pg_bin,self.work/'wrong-cluster','58e7040342bfd7137fb9227d9709fd4287172574',str(self.args.pg_lib)),'LIVE_BACKUP_SOURCE_MISMATCH')
        self.check('failed_capture_has_no_completed_manifest',not (self.work/'wrong-cluster/manifest.json').exists())
        digest=captured['manifest_sha256']
        def verify_as(p,d):
            with recovery.verified_archive(backup,d,p):pass
        self.assert_refused('wrong_project_backup_refused',lambda:verify_as(neighbor,digest),'BACKUP_PROJECT_MISMATCH')
        self.assert_refused('wrong_manifest_digest_refused',lambda:verify_as(project,'0'*64),'BACKUP_MANIFEST_DIGEST_MISMATCH')
        # Mutate one archived byte, prove refusal, restore only the synthetic file, then reverify.
        path=backup/'project.dump'
        with path.open('r+b') as handle:
            handle.seek(-1,2);last=handle.read(1);handle.seek(-1,2);handle.write(bytes([last[0]^1]));handle.flush();os.fsync(handle.fileno())
        self.assert_refused('corrupted_real_archive_refused',lambda:verify_as(project,digest),'BACKUP_ARCHIVE_DIGEST_MISMATCH')
        with path.open('r+b') as handle:
            handle.seek(-1,2);handle.write(last);handle.flush();os.fsync(handle.fileno())
        target='dial_restore_'+uuid.uuid4().hex[:16]
        with recovery.verified_archive(backup,digest,project) as (manifest,archive_fd):
            plan=recovery.restore_plan(project,manifest,target,self.projects,digest)
            for protected in (project['database'],neighbor['database'],'postgres','legacy_van'):
                self.assert_refused('restore_plan_denies_existing_'+protected,lambda p=protected:recovery.restore_plan(project,manifest,p,self.projects,digest))
            self.sql(plan['create_sql'])
            self.check('new_restore_target_rejects_existing_creation',self.sql(plan['create_sql'],fail_ok=True).returncode!=0)
            self.sql(plan['pre_restore_sql'],db=target)
            self.check('fresh_restore_target_identity_and_quarantine',True)
            # Deliberate fixture obstruction: preflight refuses a nonempty destination.
            self.sql('CREATE TABLE public.restore_obstruction(id integer);',db=target)
            refused=self.sql(plan['pre_restore_sql'],db=target,fail_ok=True)
            self.check('nonempty_restore_target_refused',refused.returncode!=0 and 'RESTORE_TARGET_NOT_EMPTY' in refused.stderr)
            self.sql('DROP TABLE public.restore_obstruction;',db=target)
            self.sql(plan['pre_restore_sql'],db=target)
            self.sql('CREATE FUNCTION public.restore_obstruction() RETURNS integer LANGUAGE sql AS $$ SELECT 1 $$;',db=target)
            refused=self.sql(plan['pre_restore_sql'],db=target,fail_ok=True)
            self.check('function_only_restore_target_refused',refused.returncode!=0 and 'RESTORE_TARGET_NOT_EMPTY' in refused.stderr)
            self.sql('DROP FUNCTION public.restore_obstruction();',db=target)
            self.sql(plan['pre_restore_sql'],db=target)
            self.sql('GRANT CONNECT ON DATABASE '+b.ident(target)+' TO PUBLIC;')
            refused=self.sql(plan['pre_restore_sql'],db=target,fail_ok=True)
            self.check('publicly_connectable_restore_target_refused',refused.returncode!=0 and 'RESTORE_TARGET_NOT_QUARANTINED' in refused.stderr)
            self.sql('REVOKE ALL ON DATABASE '+b.ident(target)+' FROM PUBLIC;')
            self.sql(plan['pre_restore_sql'],db=target)
            for p in self.projects:
                s=self.secret[p['slug']]
                for kind in ('auth','rest','migrate'):
                    denied=self.sql('SELECT 1',db=target,role=b.names(p)[kind],password=s[kind],tcp=True,fail_ok=True)
                    self.check('quarantine_denies_'+p['slug']+'_'+kind,denied.returncode!=0)
            # stdin is the exact verified open descriptor. No --clean or --create.
            env={**self.env,'PGHOST':str(self.sock),'PGPORT':str(self.pgport),'PGUSER':'fixture_admin'}
            restored=subprocess.run([str(self.args.pg_bin/'pg_restore'),*plan['restore_args']],stdin=archive_fd,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE,env=env,timeout=60)
            if restored.returncode:
                (self.work/'restore-error.private.txt').write_bytes(restored.stderr)
                raise Failure('REAL_RESTORE_FAILED')
        self.check('real_single_transaction_restore_succeeded',True)
        self.check('full_fixture_data_owners_acls_and_rls_restored',self.fingerprint(target)==before)
        self.check('original_project_database_preserved',self.fingerprint(project['database'])==before)
        marker=json.loads(self.sql('SELECT row_to_json(t) FROM dial_private.project_identity t;',db=target).stdout)
        self.check('restored_project_identity_matches',marker['project_uuid']==project['project_uuid'] and marker['issuer']=='https://'+project['hostname']+'/auth/v1')
        code,_=self.api(neighbor,'/rest/v1/notes','POST',{'id':42,'owner_id':self.users[other],'body':'neighbor-write-during-recovery'},bearer=self.sessions[other]['access_token'])
        self.check('neighbor_writes_while_project_restored',code==201)
        self.check('restored_database_not_in_current_source_hba',all(self.sql('SELECT 1',db=target,role=ns[k],password=self.secret[slug][k],tcp=True,fail_ok=True).returncode!=0 for k in ('auth','rest','migrate')))
        # Explicit fixture-only routing cutover. Source remains intact; no replay or restore over it.
        expected_sessions=int(self.sql('SELECT count(*) FROM pg_stat_activity WHERE datname='+b.lit(project['database'])+';',db='postgres').stdout)
        self.check('source_project_has_no_sessions_before_fixture_switch',expected_sessions==0)
        selected=[{**p,'database':target} if p==project else p for p in self.projects]
        prefix,_=b.hba(selected,['127.0.0.1/32'])
        # Preserve the actual original fixture suffix, not a guessed line count.
        suffix=self.original_hba_suffix
        (self.data/'pg_hba.conf').write_text(prefix+suffix)
        self.sql('GRANT CONNECT ON DATABASE '+b.ident(target)+' TO '+','.join(b.ident(ns[k]) for k in ('auth','rest','migrate'))+';')
        r=self.run([self.args.pg_bin/'pg_ctl','-D',self.data,'reload']);self.check('fixture_project_hba_switch_reloaded',r.returncode==0);time.sleep(.2)
        self.start_again(slug+'-auth',target);self.start_again(slug+'-rest',target)
        code,restored_session=self.api(project,'/auth/v1/token?grant_type=refresh_token','POST',{'refresh_token':retained_refresh})
        self.check('restored_auth_refresh_session_survives',code==200 and restored_session['user']['id']==self.users[slug])
        self.sessions[slug]=restored_session
        code,login=self.api(project,'/auth/v1/token?grant_type=password','POST',{'email':'same-person@fixture.invalid','password':self.user_passwords[slug]})
        self.check('restored_password_and_auth_uuid_work',code==200 and login['user']['id']==self.users[slug])
        code,rows=self.api(project,'/rest/v1/notes?select=body',bearer=restored_session['access_token'])
        self.check('restored_rest_rls_hides_second_user',code==200 and rows==[{'body':slug}])
        code,_=self.api(project,'/rest/v1/notes',bearer=self.sessions[other]['access_token'])
        self.check('foreign_jwt_still_denied_after_restore',code==401)
        for kind in ('auth','rest','migrate'):
            self.check('retired_source_new_login_denied_'+kind,self.sql('SELECT 1',db=project['database'],role=ns[kind],password=self.secret[slug][kind],tcp=True,fail_ok=True).returncode!=0)
        code,rows=self.api(neighbor,'/rest/v1/notes?select=body&order=id',bearer=self.sessions[other]['access_token'])
        self.check('neighbor_write_survives_project_switch',code==200 and rows==[{'body':other},{'body':'neighbor-write-during-recovery'}])
        self.check('source_copy_retained_after_switch',self.fingerprint(project['database'])==before)
        # Shared cluster restart is a shared outage, not per-project HA. Prove reconnect without data recreation.
        r=self.run([self.args.pg_bin/'pg_ctl','-D',self.data,'-l',self.work/'postgres-restart.log','-m','fast','-w','restart'],timeout=45)
        self.check('shared_fixture_postgres_restart_completed',r.returncode==0)
        for p in self.projects:
            expected=[{'body':slug}] if p==project else [{'body':other},{'body':'neighbor-write-during-recovery'}]
            deadline=time.monotonic()+20;ok=False
            while time.monotonic()<deadline:
                try:
                    code,rows=self.api(p,'/rest/v1/notes?select=body&order=id',bearer=self.sessions[p['slug']]['access_token'])
                    if code==200 and rows==expected:ok=True;break
                except (OSError,TimeoutError):pass
                time.sleep(.2)
            self.check(p['slug']+'_pool_reconnect_after_shared_restart',ok)
            code,login=self.api(p,'/auth/v1/token?grant_type=password','POST',{'email':'same-person@fixture.invalid','password':self.user_passwords[p['slug']]})
            self.check(p['slug']+'_auth_after_shared_restart',code==200 and login['user']['id']==self.users[p['slug']])
        self.check('hba_boundary_persists_across_postgres_restart',self.sql('SELECT 1',db=neighbor['database'],role=ns['rest'],password=self.secret[slug]['rest'],tcp=True,fail_ok=True).returncode!=0)
        self.check('legacy_fixture_still_unchanged_after_recovery',self.sql('SELECT value FROM public.sentinel',db='legacy_van').stdout.strip()=='unchanged-fixture' and self.sql("SELECT coalesce(datacl::text,'NULL') FROM pg_database WHERE datname='legacy_van'").stdout==self.legacy_acl)
        self.recovery_evidence={'logical_archive_bytes':captured['archive_bytes'],
            'logical_archive_sha256':captured['archive_sha256'],'manifest_sha256':digest,
            'full_fixture_snapshot_sha256':before,'archive_persisted_in_public_evidence':False,
            'source_database_retained':True,'quarantine_restore_then_fixture_only_rebind':True,
            'shared_database_restart_is_not_HA':True}

    def additional_evidence(self):
        return {'scope':'DISPOSABLE_PG17_AUTH_REST_LOGICAL_RECOVERY_AND_RESTART_NOT_PRODUCTION',
            'recovery':self.recovery_evidence,
            'native_recovery_binary_sha256':{name:hashlib.sha256((self.args.pg_bin/name).read_bytes()).hexdigest() for name in ('psql','pg_dump','pg_restore')},
            'not_tested':['Supabase donor image/ARM64','Storage','Realtime','Edge Functions','Studio','Supavisor','OAuth/MFA/SMTP','live VAN','GTR migration','off-host encrypted backup','physical WAL/PITR','large-scale restore performance','automatic production cutover']}

if __name__=='__main__':raise SystemExit(native.main(RecoveryRehearsal))
