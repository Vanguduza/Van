#!/usr/bin/env python3
"""Real one-Supavisor/two-database fixture; no existing database accepted."""
from __future__ import annotations
import concurrent.futures
import hashlib
import json
import os
import pathlib
import signal
import subprocess
import time
from rehearse_native import Rehearsal,Failure,BASE,main,port,request
import shared_pooler as pool
import bootstrap as b

class PoolerRehearsal(Rehearsal):
    def __init__(self,args):
        super().__init__(args)
        self.pool_release=pathlib.Path(os.environ['DIAL_REHEARSAL_POOLER_RELEASE'])
        self.pool_lib=pathlib.Path(os.environ['DIAL_REHEARSAL_POOLER_LIB'])
        if not self.pool_release.is_absolute() or not (self.pool_release/'bin/supavisor').is_file() or not self.pool_lib.is_dir():raise Failure('EXACT_POOLER_RELEASE_REQUIRED')
        self.shared_pool=pool.new_secrets(self.projects)
        self.pool_ports={k:port() for k in ('management','session','transaction','proxy','session_shard','tx_shard','distribution')}
        self.source_hashes['tools/shared_pooler.py']=hashlib.sha256((BASE/'tools/shared_pooler.py').read_bytes()).hexdigest()
        self.source_hashes[str(pathlib.Path(__file__).relative_to(BASE))]=hashlib.sha256(pathlib.Path(__file__).read_bytes()).hexdigest()
        self.pool_receipts={}
        self.source_hashes['tests/pooler_loopback_fixture.exs']=hashlib.sha256((BASE/'tests/pooler_loopback_fixture.exs').read_bytes()).hexdigest()
    def pool_env(self):
        s=self.shared_pool;pn=self.pool_ports
        env=pool.environment(s,registry_host='127.0.0.1',registry_port=self.pgport,registry_database=pool.CONTROL_DB,registry_user=pool.CONTROL_ROLE)
        # Erlang default listen policy is applied before any Ranch/Phoenix
        # socket opens. Native listener addresses are independently observed.
        env.update(PORT=str(pn['management']),PROXY_PORT_SESSION=str(pn['session']),PROXY_PORT_TRANSACTION=str(pn['transaction']),PROXY_PORT=str(pn['proxy']),
            SESSION_PROXY_PORTS=str(pn['session_shard']),TRANSACTION_PROXY_PORTS=str(pn['tx_shard']),
            LD_LIBRARY_PATH=str(self.pool_lib),LANG='C.UTF-8',LC_ALL='C.UTF-8',
            NODE_NAME='dial_pooler_fixture_'+str(os.getpid()),NODE_IP='127.0.0.1',
            ERL_AFLAGS='-proto_dist inet_tcp',
            ERL_FLAGS='+S 2:2 +SDcpu 1 +SDio 1',
            ERL_EPMD_ADDRESS='127.0.0.1',ERL_EPMD_PORT=str(port()),ERL_CRASH_DUMP=str(self.work/'pooler-crash.dump'))
        return env
    def pooler_admin(self,path,method='GET',body=None,token=None):
        return request(self.pool_ports['management'],path,method,body,{'Authorization':'Bearer '+(pool.management_token(self.shared_pool['admin_secret']) if token is None else token)})
    def pooled(self,p,sql,mode='transaction',*,password=None,username=None,database=None,fail_ok=False):
        pn=self.pool_ports[mode];s=self.shared_pool['projects'][p['project_uuid']]
        cmd=[self.args.pg_bin/'psql','-X','-qAt','-v','ON_ERROR_STOP=1','-h','127.0.0.1','-p',str(pn),'-U',username or pool.role(p)+'.'+pool.tenant_id(p),'-d',database or p['database']]
        result=self.run(cmd,stdin=sql,env={'PGPASSWORD':s['pool'] if password is None else password,'PGSSLMODE':'disable','PGCONNECT_TIMEOUT':'3'},timeout=12)
        if result.returncode and not fail_ok:
            (self.work/'pooler-last-error.txt').write_text(result.stderr)
            raise Failure('POOLER_QUERY_FAILED_'+p['slug']+'_'+mode)
        return result
    def start_pooler(self):
        env=self.pool_env();env['DIAL_POOLER_FIXTURE_APPLICATION_SOURCE']=str(self.pool_release.parent.parent/'supavisor-source/lib/supavisor/application.ex')
        child=self.spawn([self.pool_release/'bin/supavisor','eval','Code.eval_file('+json.dumps(str(BASE/'tests/pooler_loopback_fixture.exs'))+')'],env,'shared-pooler')
        end=time.monotonic()+25
        while time.monotonic()<end:
            if child.poll() is not None:raise Failure('POOLER_NATIVE_EXIT')
            try:
                status,_=self.pooler_admin('/api/health')
                if status==204:break
            except (OSError,TimeoutError):pass
            time.sleep(.2)
        else:raise Failure('POOLER_NATIVE_HEALTH_TIMEOUT')
        self.check('one_real_supavisor_ready',True)
        # Inspect only our known listener ports, not other service details.
        observed=[]
        for name in ('management','session','transaction','proxy','session_shard','tx_shard'):
            number=self.pool_ports[name]
            entries=[]
            for fname in ('/proc/net/tcp','/proc/net/tcp6'):
                for line in pathlib.Path(fname).read_text().splitlines()[1:]:
                    fields=line.split();address,encoded=fields[1].split(':')
                    if int(encoded,16)==number and fields[3]=='0A':entries.append(address)
            self.check(name+'_listener_loopback_only',entries==['0100007F'])
            observed.append({'purpose':name,'loopback':True})
        self.pool_receipts['private_listeners']=observed
    def setup_pooler(self):
        # Do not shrink/restart an already sufficient shared fixture. Its other
        # native consumers may have a larger independently bounded connection budget.
        if int(self.sql('SHOW max_connections').stdout)<64:
            self.sql('ALTER SYSTEM SET max_connections=64')
            r=self.run([self.args.pg_bin/'pg_ctl','-D',self.data,'-l',self.work/'postgres.log','-w','restart'],timeout=30)
            if r.returncode:raise Failure('TEMPORARY_POOL_CAPACITY_RESTART_FAILED')
        self.check('temporary_pg_pool_capacity',int(self.sql('SHOW max_connections').stdout)>=64)
        for p in self.projects:
            self.sql(pool.project_roles_sql(p,self.shared_pool['projects'][p['project_uuid']]),db=p['database'])
            self.sql(f'CREATE TABLE public.pool_fixture(id integer PRIMARY KEY,value text NOT NULL); INSERT INTO public.pool_fixture VALUES(1,{b.lit(p["slug"])}); GRANT SELECT,INSERT,UPDATE,DELETE ON public.pool_fixture TO {b.ident(pool.role(p))}; ALTER TABLE public.pool_fixture OWNER TO {b.ident(b.names(p)["owner"])};',db=p['database'])
        roles,db=pool.fresh_registry_sql(self.shared_pool['registry_password']);self.sql(roles);self.sql(db)
        prefix,expected=pool.hba(self.projects,['127.0.0.1/32']);activate=pool.activate_sql(self.projects,expected)
        refused=self.sql(activate,fail_ok=True)
        self.check('pooler_activation_without_scoped_hba_denied',refused.returncode!=0)
        hba=self.data/'pg_hba.conf';hba.write_text(prefix+hba.read_text())
        self.run([self.args.pg_bin/'pg_ctl','-D',self.data,'reload']);time.sleep(.25);self.sql(activate)
        self.check('pooler_repeated_activation_denied',self.sql(activate,fail_ok=True).returncode!=0)
        result=self.run([self.pool_release/'bin/migrate'],env=self.pool_env(),timeout=35)
        (self.work/'pooler-migration.log').write_text(result.stdout+result.stderr)
        self.check('real_supavisor_registry_migrations',result.returncode==0)
        self.start_pooler()
        self.check('shared_pooler_admin_rejects_project_service_key',self.pooler_admin('/api/tenants/unknown',token=self.keys[self.projects[0]['slug']]['service_role'])[0]==403)
        self.check('shared_pooler_admin_requires_token',self.pooler_admin('/api/tenants/unknown',token='')[0]==403)
        for p in self.projects:
            tid=pool.tenant_id(p);self.check(p['slug']+'_pool_tenant_not_existing',self.pooler_admin('/api/tenants/'+tid)[0]==404)
            body=pool.registration(p,self.shared_pool['projects'][p['project_uuid']]['pool'],db_host='127.0.0.1',db_port=self.pgport,client_cidrs=['127.0.0.1/32'],upstream_ssl=False,enforce_ssl=False)
            code,value=self.pooler_admin('/api/tenants/'+tid,'PUT',body)
            self.check(p['slug']+'_native_pool_tenant_registered',code==201)
            self.check(p['slug']+'_pool_config_uses_own_database',value.get('data',{}).get('db_database')==p['database'])
            self.check(p['slug']+'_native_management_readback_requires_secret_redaction',self.shared_pool['projects'][p['project_uuid']]['pool'] in json.dumps(value))
            safe=pool.safe_readback(p,value)
            self.check(p['slug']+'_safe_readback_has_no_password',self.shared_pool['projects'][p['project_uuid']]['pool'] not in json.dumps(safe))
    def exercise_pooler(self):
        for p in self.projects:
            slug=p['slug'];other=next(q for q in self.projects if q!=p)
            for mode in ('session','transaction'):
                result=self.pooled(p,'SELECT current_database(),current_user; SELECT value FROM public.pool_fixture;',mode)
                self.check(slug+'_'+mode+'_real_database_and_user',p['database']+'|'+pool.role(p) in result.stdout and slug in result.stdout)
                result=self.pooled(p,"BEGIN; SET LOCAL application_name='scoped-fixture'; SELECT current_setting('application_name'); ROLLBACK; SELECT value FROM public.pool_fixture;",mode)
                self.check(slug+'_'+mode+'_transactions_work',result.stdout.strip().endswith(slug))
                result=self.pooled(p,'SELECT 1',mode,password=self.shared_pool['projects'][other['project_uuid']]['pool'],fail_ok=True)
                self.check(slug+'_'+mode+'_foreign_password_denied',result.returncode!=0)
                # Startup database selector must not bypass the PostgreSQL HBA
                # boundary, even if the native pooler accepts the selector.
                result=self.pooled(p,'SELECT current_database()',mode,database=other['database'],fail_ok=True)
                self.check(slug+'_'+mode+'_foreign_database_denied',result.returncode!=0 or result.stdout.strip()==p['database'])
                for query,label in [('SET ROLE fixture_admin','no_cluster_superuser'),('SELECT rolpassword FROM pg_authid','no_global_passwords'),('CREATE ROLE pooler_escape','no_cluster_role_creation')]:
                    result=self.pooled(p,query,mode,fail_ok=True)
                    self.check(slug+'_'+mode+'_'+label,result.returncode!=0)
            denied=self.pooled(p,'SELECT 1',username=pool.role(other)+'.'+pool.tenant_id(p),password=self.shared_pool['projects'][other['project_uuid']]['pool'],fail_ok=True)
            self.check(slug+'_foreign_role_on_own_tenant_denied',denied.returncode!=0)
            denied=self.sql('SELECT 1',db=other['database'],role=pool.role(p),password=self.shared_pool['projects'][p['project_uuid']]['pool'],tcp=True,fail_ok=True)
            self.check(slug+'_raw_pool_login_cross_database_denied',denied.returncode!=0)
        def read(index):
            p=self.projects[index%2]
            return self.pooled(p,'SELECT value FROM public.pool_fixture;').stdout.strip()==p['slug']
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
            self.check('concurrent_tenant_pools_keep_24_requests_separate',all(executor.map(read,range(24))))
        count=int(self.sql("SELECT count(*) FROM pg_stat_activity WHERE usename LIKE '%_pool' AND backend_type='client backend'").stdout)
        self.check('bounded_backend_connections_for_both_tenants',count<=8)
        self.pool_receipts['observed_project_backend_connections']=count
        child=self.process_by_label['shared-pooler'];os.killpg(child.pid,signal.SIGTERM);child.wait(timeout=10)
        self.start_pooler()
        for p in self.projects:
            self.check(p['slug']+'_pool_recovers_after_shared_restart',self.pooled(p,'SELECT value FROM public.pool_fixture;').stdout.strip()==p['slug'])
            code,rows=self.api(p,'/rest/v1/notes?select=body',bearer=self.sessions[p['slug']]['access_token'])
            self.check(p['slug']+'_direct_rest_preserved',code==200 and rows==[{'body':p['slug']}])
        self.check('pooler_preserves_legacy_database',self.sql('SELECT value FROM public.sentinel',db='legacy_van').stdout.strip()=='unchanged-fixture')
    def exercise(self):
        super().exercise();self.setup_pooler();self.exercise_pooler()
    def additional_evidence(self):
        return {'scope':'ONE_POSTGRES_ONE_SUPAVISOR_TWO_PROJECT_NATIVE_REHEARSAL',
            'pooler_version':pool.VERSION,'upstream_source':pool.SOURCE_COMMIT,
            'runtime_module_sha256':hashlib.sha256((self.pool_release/'lib/supavisor-2.9.12/ebin/Elixir.Supavisor.Application.beam').read_bytes()).hexdigest(),
            'pooler_processes':1,'postgres_servers':1,'pooler_observations':self.pool_receipts,
            'not_tested':['live VAN','production TLS/target architecture','original registry migration','Studio','all shared components together','Nissan GTR migration']}

if __name__=='__main__':raise SystemExit(main(PoolerRehearsal))
