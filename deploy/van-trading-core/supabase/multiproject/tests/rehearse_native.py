#!/usr/bin/env python3
"""Real two-project Auth/REST rehearsal in a NEW non-root temporary PG17 cluster.

No Docker daemon, existing DB endpoint, production secrets, service restart or
VM configuration is accepted. Native binaries are supplied explicitly. This is
not a production installer and does not qualify Storage/Realtime/Edge/OAuth.
"""
from __future__ import annotations
import argparse
import base64
import concurrent.futures
import hashlib
import hmac
import http.client
import json
import os
import pathlib
import platform
import secrets
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import time
import uuid
from datetime import datetime,timezone

BASE=pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0,str(BASE/'tools'))
import bootstrap as b
import render

class Failure(RuntimeError): pass

def port():
    with socket.socket() as s:
        s.bind(('127.0.0.1',0)); return s.getsockname()[1]

def request(port_number,path,method='GET',body=None,headers=None):
    conn=http.client.HTTPConnection('127.0.0.1',port_number,timeout=8)
    try:
        data=json.dumps(body) if body is not None else None
        conn.request(method,path,data,{'Content-Type':'application/json',**(headers or {})})
        r=conn.getresponse();raw=r.read(1048576)
        try: value=json.loads(raw)
        except (ValueError,UnicodeError): value=None
        return r.status,value
    finally:conn.close()

class Rehearsal:
    def __init__(self,args):
        if os.geteuid()==0: raise Failure('NON_ROOT_REHEARSAL_REQUIRED')
        self.args=args; self.checks=[];self.children=[];self.handles=[];self.pg_started=False
        self.process_specs={}; self.process_by_label={}
        self.source_hashes={str(path.relative_to(BASE)):hashlib.sha256(path.read_bytes()).hexdigest() for path in [BASE/'tools/bootstrap.py',BASE/'tools/render.py',pathlib.Path(__file__)]}
        self.temp=tempfile.TemporaryDirectory(prefix='dial-supa-auth-')
        self.work=pathlib.Path(self.temp.name);self.work.chmod(0o700)
        self.data=self.work/'data';self.sock=self.work/'socket';self.sock.mkdir()
        self.pgport=port()
        self.env={'PATH':'/usr/bin:/bin','HOME':str(self.work),'LANG':'C.UTF-8',
                  'LD_LIBRARY_PATH':str(args.pg_lib),'PGCONNECT_TIMEOUT':'5',
                  'GOMAXPROCS':'2'}
        self.projects=render.validate(json.loads((BASE/'projects.rehearsal.json').read_text()))
        self.secret={p['slug']:b.new_secrets() for p in self.projects}
        self.keys={p['slug']:{r:b.token(p,self.secret[p['slug']]['jwt'],r) for r in ('anon','service_role')} for p in self.projects}
        self.endpoints={p['slug']:{'auth':port(),'rest':port(),'api':port()} for p in self.projects}
    def check(self,name,ok):
        if not ok: raise Failure(name)
        self.checks.append(name); print('PASS '+name,flush=True)
    def run(self,argv,stdin=None,env=None,timeout=30):
        return subprocess.run([str(x) for x in argv],input=stdin,text=True,
            capture_output=True,env={**self.env,**(env or {})},timeout=timeout)
    def sql(self,text,db='postgres',role='fixture_admin',password=None,tcp=False,fail_ok=False):
        env={'PGPASSWORD':password} if password else {}
        args=[self.args.pg_bin/'psql','-X','-qAt','-v','ON_ERROR_STOP=1',
              '-h','127.0.0.1' if tcp else str(self.sock),'-p',str(self.pgport),'-U',role,'-d',db]
        r=self.run(args,stdin=text,env=env)
        if r.returncode and not fail_ok:
            (self.work/'last-sql-error.txt').write_text(r.stderr)
            raise Failure('SQL_FAILED_'+db)
        return r
    def spawn(self,argv,env,label,cwd=None):
        f=open(self.work/(label+'.log'),'w'); self.handles.append(f)
        p=subprocess.Popen([str(x) for x in argv],env={**self.env,**env},
            cwd=cwd or self.work,stdout=f,stderr=subprocess.STDOUT,start_new_session=True)
        self.children.append(p)
        self.process_specs[label]=([str(x) for x in argv],dict(env),cwd)
        self.process_by_label[label]=p
        return p
    def wait_http(self,proc,pn,path,headers=None):
        deadline=time.monotonic()+30
        while time.monotonic()<deadline:
            if proc.poll() is not None: raise Failure('SERVICE_EXITED_'+str(proc.returncode))
            try:
                code,_=request(pn,path,headers=headers)
                if code==200:return
            except (OSError,http.client.HTTPException):pass
            time.sleep(.15)
        raise Failure('SERVICE_NOT_READY')
    def start_pg(self):
        pw=self.work/'admin.pw';pw.write_text(secrets.token_urlsafe(48)+'\n');pw.chmod(0o600)
        r=self.run([self.args.pg_bin/'initdb','-D',self.data,'-U','fixture_admin',
            '--encoding=UTF8','--locale=C.UTF-8','--auth-local=trust',
            '--auth-host=scram-sha-256','--pwfile='+str(pw),'--no-sync'],timeout=45)
        if r.returncode:
            (self.work/'initdb-error.txt').write_text(r.stderr);raise Failure('INITDB_FAILED')
        with (self.data/'postgresql.conf').open('a') as f:
            f.write("\nshared_buffers='16MB'\nmax_connections=32\njit=off\nlog_statement='none'\nlog_min_error_statement='panic'\nlog_parameter_max_length=0\n")
        r=self.run([self.args.pg_bin/'pg_ctl','-D',self.data,'-l',self.work/'postgres.log',
                    '-o',f'-h 127.0.0.1 -p {self.pgport} -k {self.sock}','-w','start'],timeout=30)
        if r.returncode: raise Failure('PG_START_FAILED')
        self.pg_started=True
        self.check('postgres17_real_server',int(self.sql('SHOW server_version_num').stdout.strip())//10000==17)
        # Shared roles belong only to this synthetic cluster, never installed into VAN.
        self.sql('CREATE ROLE postgres NOLOGIN; CREATE ROLE anon NOLOGIN NOINHERIT; CREATE ROLE authenticated NOLOGIN NOINHERIT; CREATE ROLE service_role NOLOGIN NOINHERIT BYPASSRLS; CREATE DATABASE legacy_van;')
        self.sql("CREATE TABLE public.sentinel (value text); INSERT INTO public.sentinel VALUES ('unchanged-fixture');",db='legacy_van')
        self.legacy_acl=self.sql("SELECT coalesce(datacl::text,'NULL') FROM pg_database WHERE datname='legacy_van'").stdout
    def setup(self):
        self.start_pg()
        for p in self.projects:
            s=self.secret[p['slug']]
            self.sql(b.roles_sql(p,s));self.sql(b.database_sql(p));self.sql(b.schema_sql(p),db=p['database'])
        fragment,expected=b.hba(self.projects,['127.0.0.1/32'])
        activate=b.activate_sql(self.projects,expected)
        refused=self.sql(activate,fail_ok=True)
        self.check('activation_refuses_missing_hba_prefix',refused.returncode!=0 and 'EXACT_HBA_PREFIX_REQUIRED' in refused.stderr)
        hba=self.data/'pg_hba.conf';original=hba.read_text();self.original_hba_suffix=original;hba.write_text(fragment+original)
        r=self.run([self.args.pg_bin/'pg_ctl','-D',self.data,'reload']);self.check('fixture_hba_reload',r.returncode==0)
        time.sleep(.3)
        self.sql(activate)
        self.check('activation_after_exact_hba_prefix',True)
        self.check('activation_replay_refused',self.sql(activate,fail_ok=True).returncode!=0)
        for p in self.projects:
            ns=b.names(p);s=self.secret[p['slug']]
            for kind in ('auth','rest','migrate'):
                own=self.sql('SELECT current_database()',db=p['database'],role=ns[kind],password=s[kind],tcp=True)
                self.check(p['slug']+'_'+kind+'_own_db_login',own.stdout.strip()==p['database'])
                targets=['postgres','legacy_van']+[q['database'] for q in self.projects if q!=p]
                for target in targets:
                    denied=self.sql('SELECT 1',db=target,role=ns[kind],password=s[kind],tcp=True,fail_ok=True)
                    self.check(p['slug']+'_'+kind+'_deny_db_'+target,denied.returncode!=0 and 'pg_hba.conf rejects' in denied.stderr)
            denied=self.sql('SET ROLE fixture_admin',db=p['database'],role=ns['rest'],password=s['rest'],tcp=True,fail_ok=True)
            self.check(p['slug']+'_rest_cannot_become_admin',denied.returncode!=0)
            self.check(p['slug']+'_bootstrap_replay_refused',self.sql(b.roles_sql(p,s),fail_ok=True).returncode!=0)
            ae=b.auth_env(p,s,'127.0.0.1',self.pgport)
            ae.update(GOTRUE_API_HOST='127.0.0.1',GOTRUE_API_PORT=str(self.endpoints[p['slug']]['auth']),
                      PORT=str(self.endpoints[p['slug']]['auth']),GOTRUE_DB_MIGRATIONS_PATH=str(self.args.auth_bin.parent/'migrations'))
            proc=self.spawn([self.args.auth_bin],ae,p['slug']+'-auth',self.args.auth_bin.parent)
            self.wait_http(proc,self.endpoints[p['slug']]['auth'],'/health')
            self.check(p['slug']+'_real_auth_migrations',int(self.sql('SELECT count(*) FROM auth.schema_migrations',db=p['database']).stdout)>50)
            self.sql(b.helper_sql(p),db=p['database'])
            self.sql('CREATE TABLE public.notes (id integer PRIMARY KEY,owner_id uuid NOT NULL REFERENCES auth.users(id),body text NOT NULL); ALTER TABLE public.notes ENABLE ROW LEVEL SECURITY; CREATE POLICY own_notes ON public.notes TO authenticated USING (owner_id=auth.uid()) WITH CHECK (owner_id=auth.uid()); GRANT SELECT,INSERT,UPDATE,DELETE ON public.notes TO authenticated,service_role;',db=p['database'])
            re=b.rest_env(p,s,'127.0.0.1',self.pgport)
            re.update(PGRST_SERVER_HOST='127.0.0.1',PGRST_SERVER_PORT=str(self.endpoints[p['slug']]['rest']))
            proc=self.spawn([self.args.rest_bin],re,p['slug']+'-rest')
            key=b.token(p,s['jwt'],'service_role')
            self.wait_http(proc,self.endpoints[p['slug']]['rest'],'/notes',{'Authorization':'Bearer '+key})
            self.check(p['slug']+'_real_postgrest_ready',True)
        configs=[]
        for p in self.projects:
            s=self.secret[p['slug']];ep=self.endpoints[p['slug']]
            txt=b.gateway(p,self.keys[p['slug']]['anon'],self.keys[p['slug']]['service_role'])
            txt=txt.replace('listen 8080','listen 127.0.0.1:'+str(ep['api']))
            for kind,pn in [('auth',9999),('rest',3000)]:
                txt=txt.replace('tenant-'+p['slug']+'-'+kind+':'+str(pn),'127.0.0.1:'+str(ep[kind]))
            cfg=self.work/(p['slug']+'-nginx.conf')
            buffers=self.work/(p['slug']+'-buffers');buffers.mkdir()
            temp_settings='\n'.join(k+'_temp_path '+str(buffers/k)+';' for k in ('client_body','proxy','fastcgi','uwsgi','scgi'))
            cfg.write_text('\n'.join(['daemon off;','master_process off;','pid '+str(self.work/(p['slug']+'.pid'))+';','error_log '+str(self.work/(p['slug']+'-nginx-error.log'))+';','events { worker_connections 64; }','http { access_log off;',temp_settings,txt,'}']))
            checked=self.run([self.args.nginx,'-t','-p',str(self.work)+'/', '-c',cfg]);self.check(p['slug']+'_real_nginx_configuration',checked.returncode==0)
            self.spawn([self.args.nginx,'-p',str(self.work)+'/', '-c',cfg],{},p['slug']+'-nginx')
        time.sleep(.25)
    def api(self,p,path,method='GET',body=None,bearer=None,key=None,extra=None):
        s=self.secret[p['slug']]
        headers={'Host':p['hostname'],'apikey':key if key is not None else self.keys[p['slug']]['anon']}
        if bearer:headers['Authorization']='Bearer '+bearer
        headers.update(extra or {})
        return request(self.endpoints[p['slug']]['api'],path,method,body,headers)
    def exercise(self):
        self.users={};self.sessions={};self.user_passwords={}
        for p in self.projects:
            slug=p['slug'];pw=secrets.token_urlsafe(32);self.user_passwords[slug]=pw
            service=b.token(p,self.secret[slug]['jwt'],'service_role')
            code,user=self.api(p,'/auth/v1/admin/users','POST',{'email':'same-person@fixture.invalid','password':pw,'email_confirm':True},bearer=service)
            self.check(slug+'_admin_create_real_user',code in (200,201) and 'id' in (user or {}))
            self.users[slug]=user['id']
            code,session=self.api(p,'/auth/v1/token?grant_type=password','POST',{'email':'same-person@fixture.invalid','password':pw})
            self.check(slug+'_password_login',code==200 and 'access_token' in (session or {}))
            self.sessions[slug]=session
            code,_=self.api(p,'/rest/v1/notes','POST',{'id':1,'owner_id':user['id'],'body':slug},bearer=session['access_token'])
            self.check(slug+'_rls_owner_insert',code==201)
            code,second=self.api(p,'/auth/v1/admin/users','POST',{'email':'second-user@fixture.invalid','password':secrets.token_urlsafe(32),'email_confirm':True},bearer=service)
            self.check(slug+'_second_real_user',code in (200,201) and 'id' in (second or {}))
            code,_=self.api(p,'/rest/v1/notes','POST',{'id':2,'owner_id':second['id'],'body':slug+'-private-second'},bearer=service)
            self.check(slug+'_service_role_writes_second_owner',code==201)
            code,allrows=self.api(p,'/rest/v1/notes?select=id&order=id',bearer=service)
            self.check(slug+'_service_role_reads_project_rows',code==200 and allrows==[{'id':1},{'id':2}])
            code,rows=self.api(p,'/rest/v1/notes?select=body',bearer=session['access_token'])
            self.check(slug+'_rls_read_hides_second_owner',code==200 and rows==[{'body':slug}])
            code,_=self.api(p,'/auth/v1/admin/users',bearer=session['access_token'])
            self.check(slug+'_ordinary_user_cannot_admin_auth',code in (401,403))
            code,_=self.api(p,'/rest/v1/users',bearer=session['access_token'],extra={'Accept-Profile':'auth'})
            self.check(slug+'_auth_schema_not_exposed_by_rest',code==406)
            code,_=self.api(p,'/rest/v1/notes','POST',{'id':3,'owner_id':second['id'],'body':'forbidden'},bearer=session['access_token'])
            self.check(slug+'_rls_foreign_owner_insert_denied',code in (401,403))
            code,_=self.api(p,'/rest/v1/notes');self.check(slug+'_anonymous_table_denied',code in (401,403))
            code,_=self.api(p,'/rest/v1/notes',key='invalid');self.check(slug+'_invalid_api_key_denied',code==401)
            code,_=self.api(p,'/rest/v1/notes',key='');self.check(slug+'_missing_api_key_denied',code==401)
        a,c=self.projects
        self.check('same_email_separate_auth_identities',self.users[a['slug']]!=self.users[c['slug']])
        for p,other in ((a,c),(c,a)):
            slug=p['slug'];foreign=other['slug'];own=self.sessions[slug]['access_token'];alien=self.sessions[foreign]['access_token']
            code,_=self.api(p,'/rest/v1/notes',bearer=alien);self.check(slug+'_foreign_user_jwt_denied',code==401)
            head,payload,_=own.split('.')
            claims=json.loads(base64.urlsafe_b64decode(payload+'='*(-len(payload)%4)))
            for claim,value,want in [('iss','https://'+other['hostname']+'/auth/v1',403),('aud','foreign-audience',401)]:
                changed={**claims,claim:value}
                encoded=base64.urlsafe_b64encode(json.dumps(changed,separators=(',',':')).encode()).decode().rstrip('=')
                message=head+'.'+encoded
                signed=message+'.'+base64.urlsafe_b64encode(hmac.digest(self.secret[slug]['jwt'].encode(),message.encode(),'sha256')).decode().rstrip('=')
                code,_=self.api(p,'/rest/v1/notes',bearer=signed)
                self.check(slug+'_correct_signature_wrong_'+claim+'_denied',code==want)

            alien_key=self.keys[foreign]['anon']
            code,_=self.api(p,'/rest/v1/notes',key=alien_key,bearer=own);self.check(slug+'_foreign_apikey_denied',code==401)
            alien_service=b.token(other,self.secret[foreign]['jwt'],'service_role')
            for path in ('/rest/v1/notes','/auth/v1/admin/users'):
                code,_=self.api(p,path,bearer=alien_service);self.check(slug+'_foreign_service_key_denied_'+path,code in (401,403))
            code,_=self.api(p,'/auth/v1/token?grant_type=password','POST',{'email':'same-person@fixture.invalid','password':self.user_passwords[foreign]})
            self.check(slug+'_other_realm_password_denied',code==400)
            code,_=self.api(p,'/auth/v1/token?grant_type=refresh_token','POST',{'refresh_token':self.sessions[foreign]['refresh_token']})
            self.check(slug+'_other_realm_refresh_denied',code==400)
            code,rows=self.api(p,'/rest/v1/notes?select=body',bearer=own,extra={'X-Tenant-ID':other['project_uuid'],'X-Forwarded-Host':other['hostname'],'X-Dial-Project-ID':other['project_uuid']})
            self.check(slug+'_header_spoof_cannot_change_database',code==200 and rows==[{'body':slug}])
            code,_=self.api(p,'/rest/v1/notes',bearer=own,extra={'Host':other['hostname']});self.check(slug+'_foreign_host_denied',code==421)
            for path in ('/storage/v1/test','/realtime/v1/websocket','/functions/v1/test','/_health','/auth/v1/callback'):
                code,_=self.api(p,path);self.check(slug+'_unqualified_route_closed_'+path,code==503)
        def pooled(n):
            p=self.projects[n%2];code,rows=self.api(p,'/rest/v1/notes?select=body',bearer=self.sessions[p['slug']]['access_token'])
            return code==200 and rows==[{'body':p['slug']}]
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
            self.check('concurrent_project_pools_isolated_40_requests',all(executor.map(pooled,range(40))))
        for p in self.projects:
            code,session=self.api(p,'/auth/v1/token?grant_type=refresh_token','POST',{'refresh_token':self.sessions[p['slug']]['refresh_token']})
            self.check(p['slug']+'_own_refresh_still_works',code==200 and session.get('user',{}).get('id')==self.users[p['slug']])
        self.check('legacy_database_data_untouched',self.sql('SELECT value FROM public.sentinel',db='legacy_van').stdout.strip()=='unchanged-fixture')
        self.check('legacy_database_acl_untouched',self.sql("SELECT coalesce(datacl::text,'NULL') FROM pg_database WHERE datname='legacy_van'").stdout==self.legacy_acl)
    def additional_evidence(self):
        return {}

    def cleanup(self):
        for child in reversed(self.children):
            if child.poll() is None:
                os.killpg(child.pid,signal.SIGTERM)
                try:child.wait(timeout=8)
                except subprocess.TimeoutExpired:os.killpg(child.pid,signal.SIGKILL);child.wait(timeout=5)
        for f in self.handles:f.close()
        if self.pg_started:
            r=self.run([self.args.pg_bin/'pg_ctl','-D',self.data,'-m','fast','-w','stop'],timeout=30)
            if r.returncode:raise Failure('FIXTURE_POSTGRES_CLEANUP_FAILED')
            self.pg_started=False
    def execute(self):
        error=None
        try:self.setup();self.exercise()
        except Exception as exc:
            error=type(exc).__name__+':'+str(exc) if isinstance(exc,Failure) else type(exc).__name__
        finally:
            try:self.cleanup()
            except Exception as exc:error=(error or '')+';CLEANUP:'+type(exc).__name__
        for name,digest in self.source_hashes.items():
            if hashlib.sha256((BASE/name).read_bytes()).hexdigest()!=digest:error='SOURCE_CHANGED_DURING_REHEARSAL'
        result={'schema_version':1,'state':'PASS' if error is None else 'FAIL',
            'scope':'DISPOSABLE_PG17_AUTH_REST_NATIVE_REHEARSAL_NOT_PRODUCTION',
            'checks':self.checks,'check_count':len(self.checks),'error':error,
            'production_changes':False,'rea_used':False,'runtime_architecture':platform.machine(),
            'postgres_version':self.run([self.args.pg_bin/'postgres','--version']).stdout.strip(),
            'native_binary_sha256':{name:hashlib.sha256(path.read_bytes()).hexdigest() for name,path in [('auth',self.args.auth_bin),('rest',self.args.rest_bin),('postgres',self.args.pg_bin/'postgres')]},
            'source_sha256':self.source_hashes,'observed_at':datetime.now(timezone.utc).isoformat(),
            'not_tested':['live Supabase donor state/production deployment','Storage','Realtime','Edge Functions','Studio','Supavisor','OAuth/MFA/SMTP','live VAN','GTR migration','backup restore'],
            'cleanup_completed':not self.pg_started and all(p.poll() is not None for p in self.children)}
        result.update(self.additional_evidence())
        fd=os.open(self.args.report,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
        with os.fdopen(fd,'w') as handle:handle.write(json.dumps(result,indent=2,sort_keys=True)+'\n')
        if error:print('FAIL '+error+' PRIVATE_DIAGNOSTICS='+str(self.work),flush=True)
        else:self.temp.cleanup();print('PASS_ALL '+str(len(self.checks)),flush=True)
        # Retain failed private evidence while the current process exists; no secrets in report.
        if error:self.temp._finalizer.detach()
        return 0 if error is None else 1

def main(rehearsal_class=Rehearsal):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--pg-bin',type=pathlib.Path,required=True)
    parser.add_argument('--pg-lib',type=pathlib.Path,required=True)
    parser.add_argument('--auth-bin',type=pathlib.Path,required=True)
    parser.add_argument('--rest-bin',type=pathlib.Path,required=True)
    parser.add_argument('--nginx',type=pathlib.Path,default=pathlib.Path('/usr/sbin/nginx'))
    parser.add_argument('--report',type=pathlib.Path,required=True)
    args=parser.parse_args()
    os.umask(0o077)
    for path in (args.pg_bin/'postgres',args.pg_bin/'initdb',args.auth_bin,args.rest_bin,args.nginx):
        if not path.is_absolute() or not path.is_file() or not os.access(path,os.X_OK):raise Failure('EXACT_EXECUTABLE_REQUIRED')
    if args.report.exists() or not args.report.is_absolute():raise Failure('NEW_ABSOLUTE_REPORT_REQUIRED')
    return rehearsal_class(args).execute()

if __name__=='__main__':raise SystemExit(main())
