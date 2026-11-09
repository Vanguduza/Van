#!/usr/bin/env python3
"""Real shared Supavisor + pg-meta + unmodified Studio HTTP project gateway.

Synthetic issuer keys and databases only; not existing Owner credential issuance.
A successful HTML check is not full browser-interaction/UI acceptance.
"""
import base64
import concurrent.futures
import hashlib
import http.client
import json
import os
import pathlib
import secrets
import signal
import time
from rehearse_native import BASE,Failure,main,port,request
from rehearse_pooler import PoolerRehearsal
import shared_pooler as pool
import shared_admin as admin
import bootstrap as b

class AdminRehearsal(PoolerRehearsal):
    def __init__(self,args):
        super().__init__(args)
        self.node=pathlib.Path(os.environ['DIAL_REHEARSAL_ADMIN_NODE'])
        self.meta_source=pathlib.Path(os.environ['DIAL_REHEARSAL_META_SOURCE'])
        self.studio_root=pathlib.Path(os.environ['DIAL_REHEARSAL_STUDIO_ROOT'])
        if not self.node.is_file() or not (self.meta_source/'dist/server/server.js').is_file() or not (self.studio_root/'apps/studio/server.js').is_file():raise Failure('EXACT_NATIVE_ADMIN_COMPONENTS_REQUIRED')
        self.admin_port=port();self.meta_port=port();self.studio_port=port();self.tls_port=port()
        self.crypto_key=secrets.token_urlsafe(48);self.admin_health=secrets.token_urlsafe(48)
        self.admin_origin='https://localhost:'+str(self.tls_port)
        self.tokens={};self.admin_record={}
        for f in (BASE/'tools/shared_admin.py',BASE/'admin/server.mjs',BASE/'admin/admission.mjs',BASE/'admin/health.mjs',BASE/'admin/package-lock.json',BASE/'tests/studio_browser.mjs',pathlib.Path(__file__)):
            self.source_hashes[str(f.relative_to(BASE))]=hashlib.sha256(f.read_bytes()).hexdigest()
    def admin_http(self,path,method='GET',body=None,token=None,headers=None):
        conn=http.client.HTTPConnection('127.0.0.1',self.admin_port,timeout=15)
        head={'Host':'localhost','Content-Type':'application/json'}
        if token is not False:head['Authorization']='Bearer '+(self.tokens['owner'] if token is None else token)
        head.update(headers or {})
        try:
            conn.request(method,path,json.dumps(body) if body is not None else None,head)
            response=conn.getresponse();raw=response.read(10*1024*1024)
            try:value=json.loads(raw)
            except (ValueError,UnicodeError):value=None
            return response.status,value,raw
        finally:conn.close()
    def setup_admin(self):
        issuer='https://owner.fixture.invalid';audience='dial-supabase-project-admin'
        uuids=[p['project_uuid'] for p in self.projects]
        # Private fixture signing key exists only in this ephemeral subprocess.
        # The real gateway receives the public JWK and never signs a token.
        script="""const c=require('node:crypto');const {publicKey,privateKey}=c.generateKeyPairSync('ed25519');const now=Math.floor(Date.now()/1000);const enc=o=>Buffer.from(JSON.stringify(o)).toString('base64url');const sign=p=>{const v=enc({alg:'EdDSA',typ:'JWT'})+'.'+enc(p);return v+'.'+c.sign(null,Buffer.from(v),privateKey).toString('base64url')};const claim={iss:'https://owner.fixture.invalid',aud:'dial-supabase-project-admin',iat:now,exp:now+600};console.log(JSON.stringify({public_jwk:publicKey.export({format:'jwk'}),tokens:Object.fromEntries(['owner','one-project','readonly','unknown'].map(sub=>[sub,sign({...claim,sub})]).concat([['expired',sign({...claim,sub:'owner',exp:now-1})],['wrong-audience',sign({...claim,sub:'owner',aud:'unrelated'})],['too-long',sign({...claim,sub:'owner',exp:now+3600})]]))}));"""
        r=self.run([self.node,'-e',script]);self.check('ephemeral_fixture_issuer_created',r.returncode==0)
        identity=json.loads(r.stdout);self.tokens=identity['tokens']
        operators=[{'subject':'owner','projects':uuids,'can_query':True},{'subject':'one-project','projects':[uuids[0]],'can_query':True},{'subject':'readonly','projects':uuids,'can_query':False}]
        config=admin.registry(self.projects,{p['project_uuid']:self.shared_pool['projects'][p['project_uuid']]['admin'] for p in self.projects},
            origin=self.admin_origin,meta_url='http://127.0.0.1:'+str(self.meta_port),studio_url='http://127.0.0.1:'+str(self.studio_port),crypto_key=self.crypto_key,health_key=self.admin_health,issuer=issuer,audience=audience,public_jwk=identity['public_jwk'],operators=operators,db_host='127.0.0.1',db_port=self.pgport)
        private=self.work/'project-admin.private.json';private.write_text(json.dumps(config,separators=(',',':'),sort_keys=True)+'\n');private.chmod(0o600)
        self.admin_config=config
        meta_env={'PG_META_HOST':'127.0.0.1','PG_META_PORT':str(self.meta_port),
            'PG_META_DB_URL':f'postgresql://nonexistent:never-a-real-password@127.0.0.1:{self.pgport}/postgres',
            'CRYPTO_KEY':self.crypto_key,'PG_QUERY_TIMEOUT_SECS':'5','PG_CONN_TIMEOUT_SECS':'3',
            'NODE_OPTIONS':'--max-old-space-size=192','PG_META_MAX_RESULT_SIZE_MB':'4','SENTRY_DSN':''}
        child=self.spawn([self.node,self.meta_source/'dist/server/server.js'],meta_env,'shared-meta',self.meta_source)
        self.wait_http(child,self.meta_port,'/health');self.check('real_pinned_postgres_meta_ready',True)
        # Studio is the actual retained compiled upstream server, not a fake UI.
        studio_env={'NODE_OPTIONS':'--max-old-space-size=256','NODE_ENV':'production','PORT':str(self.studio_port),'HOSTNAME':'127.0.0.1',
            'STUDIO_PG_META_URL':'http://127.0.0.1:'+str(self.meta_port),'PG_META_CRYPTO_KEY':self.crypto_key,
            'POSTGRES_HOST':'127.0.0.1','POSTGRES_PORT':str(self.pgport),'POSTGRES_DB':'nonexistent','POSTGRES_PASSWORD':'fixture-no-default-database-authority',
            'SUPABASE_URL':'http://127.0.0.1:1','SUPABASE_PUBLIC_URL':'https://unused.fixture.invalid',
            'SUPABASE_ANON_KEY':'fixture-no-key','SUPABASE_SERVICE_KEY':'fixture-no-key','AUTH_JWT_SECRET':'fixture-no-real-signing-key-abcdefghijklmnopqrstuvwxyz','NEXT_TELEMETRY_DISABLED':'1'}
        child=self.spawn([self.node,self.studio_root/'apps/studio/server.js'],studio_env,'shared-studio',self.studio_root)
        self.wait_http(child,self.studio_port,'/api/platform/profile');self.check('real_upstream_studio_server_ready',True)
        gateway_env={'DIAL_PROJECT_ADMIN_REGISTRY':str(private),'DIAL_PROJECT_ADMIN_REGISTRY_SHA256':hashlib.sha256(private.read_bytes()).hexdigest(),
            'DIAL_PROJECT_ADMIN_HOST':'127.0.0.1','DIAL_PROJECT_ADMIN_PORT':str(self.admin_port),'NODE_OPTIONS':'--max-old-space-size=96'}
        child=self.spawn([self.node,BASE/'admin/server.mjs'],gateway_env,'shared-project-admin',BASE/'admin')
        self.wait_http(child,self.admin_port,'/_internal/health',{'X-Dial-Admin-Health':self.admin_health});self.check('operator_verified_admin_gateway_ready',True)
        health=self.run([self.node,BASE/'admin/health.mjs'],env=gateway_env,timeout=8)
        self.check('private_health_probe_binds_exact_registry_and_process',health.returncode==0)
        health=self.run([self.node,BASE/'admin/health.mjs'],env={**gateway_env,'DIAL_PROJECT_ADMIN_REGISTRY_SHA256':'0'*64},timeout=8)
        self.check('health_probe_cannot_accept_changed_registry',health.returncode!=0)

    def exercise_admin(self):
        p,other=self.projects;pid=p['project_uuid'];foreign=other['project_uuid']
        code,rows,raw=self.admin_http('/api/platform/projects');self.check('studio_catalogue_contains_both_authorized_projects',code==200 and {x['ref'] for x in rows}=={pid,foreign})
        self.check('catalogue_contains_no_database_credentials',all(s['admin'].encode() not in raw for s in self.shared_pool['projects'].values()))
        code,rows,_=self.admin_http('/api/platform/projects',token=self.tokens['one-project']);self.check('scoped_operator_sees_only_allowed_project',code==200 and [x['ref'] for x in rows]==[pid])
        code,_,_=self.admin_http('/api/platform/projects/'+foreign,token=self.tokens['one-project']);self.check('scoped_operator_foreign_project_hidden',code==404)
        for token in (False,self.tokens['expired'],self.tokens['wrong-audience'],self.tokens['too-long'],self.tokens['unknown'],self.keys[p['slug']]['service_role']):
            code,_,_=self.admin_http('/api/platform/projects',token=token)
            self.check('operator_authority_invalid_case_'+str(len(self.checks)),code==401)
        for project in self.projects:
            ref=project['project_uuid'];slug=project['slug'];route='/api/platform/pg-meta/'+ref+'/query'
            code,result,raw=self.admin_http(route,'POST',{'query':'SELECT current_database() AS db,current_user AS role;'})
            self.check(slug+'_real_meta_query_selected_database',code==200 and isinstance(result,list) and result[0]['db']==project['database'] and result[0]['role']==pool.role(project,'admin'))
            malicious={'pg':'postgresql://fixture_admin@127.0.0.1/postgres','X-Connection-Encrypted':'forged','X-Tenant-ID':foreign,'X-Forwarded-Host':'untrusted'}
            code,result,_=self.admin_http(route,'POST',{'query':'SELECT current_database() AS db;'},headers=malicious)
            self.check(slug+'_caller_connection_headers_cannot_change_database',code==200 and result[0]['db']==project['database'])
            code,_,_=self.admin_http(route,'POST',{'query':'CREATE TABLE public.admin_fixture(id integer PRIMARY KEY); INSERT INTO public.admin_fixture VALUES('+str(17 if project==self.projects[0] else 29)+');'})
            self.check(slug+'_operator_can_manage_own_public_schema',code==200)
            code,result,_=self.admin_http('/api/platform/pg-meta/'+ref+'/tables?included_schemas=public')
            self.check(slug+'_real_meta_lists_own_tables',code==200 and isinstance(result,list) and any(x.get('name')=='admin_fixture' for x in result))
            for query,name in [('CREATE ROLE admin_escape','cannot_create_cluster_role'),('SET ROLE fixture_admin','cannot_become_cluster_admin'),('SELECT rolpassword FROM pg_authid','cannot_read_cluster_passwords')]:
                code,_,_=self.admin_http(route,'POST',{'query':query});self.check(slug+'_'+name,code>=400)
            for db in ('postgres','legacy_van',pool.CONTROL_DB,next(q for q in self.projects if q!=project)['database']):
                denied=self.sql('SELECT 1',db=db,role=pool.role(project,'admin'),password=self.shared_pool['projects'][ref]['admin'],tcp=True,fail_ok=True)
                self.check(slug+'_operator_sql_login_denied_'+db,denied.returncode!=0)
            code,_,_=self.admin_http(route,'POST',{'query':'SELECT 1'},token=self.tokens['readonly']);self.check(slug+'_read_only_operator_cannot_run_sql',code==403)
            code,_,_=self.admin_http('/api/platform/pg-meta/'+ref+'/roles');self.check(slug+'_cluster_admin_api_not_exposed',code==501)
            code,_,raw=self.admin_http('/project/'+ref+'/editor')
            self.check(slug+'_native_studio_project_page_served',code==200 and b'__next' in raw.lower())
        code,_,_=self.admin_http('/api/platform/pg-meta/'+foreign+'/query','POST',{'query':'SELECT 1'},token=self.tokens['one-project'])
        self.check('other_project_sql_ref_denied_before_meta',code==404)
        cookie='__Host-dial-admin='+self.tokens['owner']
        code,_,_=self.admin_http('/api/platform/pg-meta/'+pid+'/query','POST',{'query':'SELECT 1'},token=False,headers={'Cookie':cookie})
        self.check('cookie_admin_requires_same_origin_for_writes',code==401)
        code,_,_=self.admin_http('/api/platform/pg-meta/'+pid+'/query','POST',{'query':'SELECT 1'},token=False,headers={'Cookie':cookie,'Origin':self.admin_origin})
        self.check('verified_cookie_same_origin_query_allowed',code==200)
        code,_,_=self.admin_http('/api/platform/projects',headers={'Host':'foreign.fixture.invalid'})
        self.check('admin_gateway_rejects_foreign_host',code==421)
        code,_,_=self.admin_http('/api/platform/projects',headers={'Origin':'https://evil.fixture.invalid'})
        self.check('admin_gateway_rejects_foreign_origin',code==401)
        code,_,_=self.admin_http('/api/platform/projects/'+pid+'/api-keys')
        self.check('unqualified_platform_api_does_not_fall_back_to_default_project',code==501)
        # Raw meta has no working default DB. It is not publicly exposed.
        code,_=request(self.meta_port,'/query','POST',{'query':'SELECT current_database()'})
        self.check('meta_without_server_selected_context_has_no_db_authority',code>=400)
        self.check('admin_work_did_not_change_legacy_data',self.sql('SELECT value FROM public.sentinel',db='legacy_van').stdout.strip()=='unchanged-fixture')
        # Concurrent operator SQL remains bounded while an unrelated operator
        # can read its catalogue. Only synthetic temporary queries are used.
        route='/api/platform/pg-meta/'+pid+'/query'
        with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
            first=executor.submit(self.admin_http,route,'POST',{'query':'SELECT pg_sleep(1.5)'})
            second=executor.submit(self.admin_http,route,'POST',{'query':'SELECT pg_sleep(1.5)'})
            time.sleep(.3)
            queued=executor.submit(self.admin_http,route,'POST',{'query':'SELECT 1'})
            time.sleep(.2)
            self.check('operator_query_is_queued_before_execution_not_replayed',not queued.done())
            executing=int(self.sql("SELECT count(*) FROM pg_stat_activity WHERE usename="+b.lit(pool.role(p,'admin'))+" AND state='active' AND query LIKE '%pg_sleep(1.5)%'").stdout)
            self.check('at_most_two_native_queries_execute_for_one_operator',executing==2)
            code,_,_=self.admin_http('/api/platform/projects',token=self.tokens['one-project'])
            self.check('another_operator_remains_available_with_bounded_capacity',code==200)
            self.check('original_bounded_queries_and_queued_request_finish',first.result()[0]==200 and second.result()[0]==200 and queued.result()[0]==200)
        code,_,_=self.admin_http(route,'POST',{'query':'SELECT 1'})
        self.check('capacity_released_after_original_query_completion',code==200)
        self.admin_record={'real_postgres_meta':True,'real_upstream_studio_http':True,'full_browser_interaction_qualified':False,'new_identity_issuer':False,'native_ui_http_only':True}
    def exercise_browser(self):
        # Free the unrelated earlier fixture processes before starting Chrome;
        # their native tests already finished. This browser test does NOT prove
        # simultaneous full-stack production capacity or availability.
        for label in ['shared-pooler']+[p['slug']+'-'+kind for p in self.projects for kind in ('auth','rest','nginx')]:
            child=self.process_by_label[label]
            if child.poll() is None:
                os.killpg(child.pid,signal.SIGTERM)
                try:child.wait(timeout=8)
                except Exception:os.killpg(child.pid,signal.SIGKILL);child.wait(timeout=5)
        cert=self.work/'tls-cert.pem';key=self.work/'tls-key.pem'
        made=self.run(['/usr/bin/openssl','req','-x509','-newkey','rsa:2048','-nodes','-keyout',key,'-out',cert,'-days','1','-subj','/CN=localhost','-addext','subjectAltName=DNS:localhost'],timeout=15)
        self.check('ephemeral_browser_tls_certificate',made.returncode==0)
        cfg=self.work/'admin-tls.conf';buffers=self.work/'tls-buffers';buffers.mkdir()
        temp='\n'.join(k+'_temp_path '+str(buffers/k)+';' for k in ('client_body','proxy','fastcgi','uwsgi','scgi'))
        cfg.write_text('\n'.join(['daemon off;','master_process off;','pid '+str(self.work/'admin-tls.pid')+';',
            'error_log '+str(self.work/'admin-tls-error.log')+';','events { worker_connections 64; }',
            'http { access_log off;',temp,
            'server { listen 127.0.0.1:'+str(self.tls_port)+' ssl; server_name localhost;',
            'ssl_certificate '+str(cert)+'; ssl_certificate_key '+str(key)+';',
            'location / { proxy_set_header Host $http_host; proxy_pass http://127.0.0.1:'+str(self.admin_port)+'; }','} }']))
        checked=self.run([self.args.nginx,'-t','-p',str(self.work)+'/', '-c',cfg])
        self.check('private_browser_tls_proxy_config',checked.returncode==0)
        self.spawn([self.args.nginx,'-p',str(self.work)+'/', '-c',cfg],{},'admin-fixture-tls');time.sleep(.2)
        private=self.work/'browser.private.json'
        private.write_text(json.dumps({'driver':os.environ['DIAL_REHEARSAL_BROWSER_DRIVER'],'engine':os.environ.get('DIAL_REHEARSAL_BROWSER_ENGINE','firefox'),'chrome':'/usr/bin/google-chrome',
            'origin':self.admin_origin,'token':self.tokens['owner'],'projects':[{'ref':p['project_uuid'],'name':p['slug'],'database':p['database'],'row_value':17 if p==self.projects[0] else 29} for p in self.projects]}));private.chmod(0o600)
        child=self.spawn([self.node,BASE/'tests/studio_browser.mjs',private],{'NODE_OPTIONS':'--max-old-space-size=128','PLAYWRIGHT_BROWSERS_PATH':os.environ['DIAL_REHEARSAL_BROWSER_CACHE']},'browser')
        try:child.wait(timeout=110)
        except Exception:
            os.killpg(child.pid,signal.SIGTERM)
            try:child.wait(timeout=10)
            except Exception:os.killpg(child.pid,signal.SIGKILL);child.wait(timeout=5)
            raise Failure('NATIVE_BROWSER_BOUNDED_TIME_EXPIRED')
        self.check('native_browser_process_completed',child.returncode==0)
        lines=(self.work/'browser.log').read_text().strip().splitlines()
        report=json.loads(next(line for line in reversed(lines) if line.startswith('{')))
        self.admin_record['browser']=report
        for item in report['checks']:self.check(item['check'],item['pass'])
        self.admin_record['full_browser_interaction_qualified']=False
        self.admin_record['basic_browser_selection_and_query_qualified']=report['state']=='PASS'
        self.admin_record['native_ui_http_only']=False
        self.admin_record['same_session_live_project_switch_qualified']=False
        self.admin_record['browser_scope']='separate_fresh_sessions_select_real_Studio_tables_and_read_distinct_project_rows'
        self.admin_record['earlier_services_stopped_before_browser_for_memory']=['pooler','auth','rest','project-api-routers']
    def exercise(self):
        super().exercise();self.setup_admin();self.exercise_admin()
        if os.environ.get('DIAL_REHEARSAL_BROWSER_DRIVER'):
            self.exercise_browser()
        else:
            self.admin_record['browser']={'state':'NOT_RUN','reason':'HOST_CHROME_SANDBOX_NOT_QUALIFIED','sandbox_disabled':False}
    def additional_evidence(self):
        value=super().additional_evidence()
        value.update(scope='ONE_SERVER_SHARED_POOLER_META_STUDIO_ADMIN_NATIVE_REHEARSAL',
            admin=self.admin_record,meta_source=admin.META_SOURCE,studio_image=admin.STUDIO_IMAGE,
            not_tested=['live VAN','real operator identity issuer integration','full browser-interaction Studio coverage','production TLS/ARM64','all shared Storage/Realtime/Edge together','Nissan GTR migration'])
        return value

if __name__=='__main__':raise SystemExit(main(AdminRehearsal))
