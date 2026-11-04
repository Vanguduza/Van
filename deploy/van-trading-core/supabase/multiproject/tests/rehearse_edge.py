#!/usr/bin/env python3
"""Actual upstream Edge Runtime worker isolation on ONE new private PG fixture.

Never accepts a production DB, deployment authority, current runtime path or
credential. Native untrusted-function tests only use synthetic temporary data.
"""
from __future__ import annotations
import base64
import concurrent.futures
import hashlib
import hmac
import http.client
import json
import os
import pathlib
import signal
import subprocess
import time
import tempfile
from rehearse_native import BASE,Rehearsal,Failure,main,port,request
import shared_edge as edge

IDENTITY = r'''Deno.serve(async req=>{
 const digest=async s=>[...new Uint8Array(await crypto.subtle.digest('SHA-256',new TextEncoder().encode(s)))].map(x=>x.toString(16).padStart(2,'0')).join('');
 const get=k=>{try{return Deno.env.get(k)??null}catch{return null}};
 return Response.json({project:get('DIAL_PROJECT_ID'),secret_sha256:await digest(get('CUSTOM_CANARY')??''),
  service_key_present:get('SUPABASE_SERVICE_ROLE_KEY')!==null,manager_registry_visible:get('DIAL_EDGE_REGISTRY')!==null,
  identity_header:req.headers.get('x-dial-project-id'),gateway_secret_forwarded:req.headers.has('x-dial-edge-gateway'),
  forwarded_host:req.headers.get('x-forwarded-host'),marker:'identity-v1'});
});'''
NOTES = r'''Deno.serve(async req=>{
 const privileged=new URL(req.url).pathname.includes('service-notes');
 const key=Deno.env.get(privileged?'SUPABASE_SERVICE_ROLE_KEY':'SUPABASE_ANON_KEY');
 const result=await fetch(Deno.env.get('SUPABASE_URL')+'/rest/v1/notes?select=body&order=id',{
 headers:{apikey:key,Authorization:privileged?'Bearer '+key:req.headers.get('authorization')}});
 return new Response(await result.text(),{status:result.status,headers:{'Content-Type':'application/json'}});
});'''
SANDBOX = r'''Deno.serve(async req=>{
 const tryCall=async fn=>{try{await fn();return 'ALLOWED'}catch(e){return 'DENIED:'+e.name}};
 return Response.json({
  main_registry:await tryCall(()=>Deno.readTextFile(Deno.env.get('TEST_REGISTRY_PATH'))),
  foreign_source:await tryCall(()=>Deno.readTextFile(Deno.env.get('TEST_FOREIGN_SOURCE'))),
  foreign_import:await tryCall(()=>import('file://'+Deno.env.get('TEST_FOREIGN_SOURCE'))),
  write:await tryCall(()=>Deno.writeTextFile('/tmp/edge-should-not-write','bad')),
  process:await tryCall(()=>new Deno.Command('/usr/bin/true').output()),
  manager_env:await tryCall(()=>Deno.env.get('DIAL_EDGE_REGISTRY')),
  foreign_network:await tryCall(()=>fetch(Deno.env.get('TEST_FOREIGN_API')+'/rest/v1/notes')),
  runtime_network:await tryCall(()=>fetch(Deno.env.get('TEST_RUNTIME_API')+'/_internal/health')),
  dynamic_remote_import:await tryCall(()=>import('https://example.invalid/forbidden.ts')),
  worker_factory:typeof EdgeRuntime.userWorkers==='undefined'?'DENIED:NotExposed':'ALLOWED'
 });
});'''
MUTATE_THROW=r'''Deno.serve(async req=>{
 const token=req.headers.get('authorization').slice(7).split('.')[1];
 const sub=JSON.parse(atob(token.replaceAll('-','+').replaceAll('_','/'))).sub;
 const result=await fetch(Deno.env.get('SUPABASE_URL')+'/rest/v1/notes',{
  method:'POST',headers:{apikey:Deno.env.get('SUPABASE_ANON_KEY'),Authorization:req.headers.get('authorization'),'Content-Type':'application/json'},
  body:JSON.stringify({id:Math.floor(Math.random()*1000000000)+1000,owner_id:sub,body:'edge-write-once'})});
 if(result.status!==201)return Response.json({fixture:'write-failed'},{status:500});
 throw new Error('PRIVATE_ERROR_MUST_NOT_LEAK_'+Deno.env.get('CUSTOM_CANARY'));
});'''

class EdgeRehearsal(Rehearsal):
    def __init__(self,args):
        super().__init__(args)
        self.edge_bin=pathlib.Path(os.environ['DIAL_REHEARSAL_EDGE_BIN'])
        self.edge_main=pathlib.Path(os.environ['DIAL_REHEARSAL_EDGE_MAIN'])
        if not self.edge_bin.is_absolute() or not self.edge_bin.is_file() or not self.edge_main.is_absolute() or not self.edge_main.is_dir():
            raise Failure('EXACT_STAGED_EDGE_RUNTIME_REQUIRED')
        self.edgeport=port();self.edge_shared=edge.runtime_secrets(self.projects)
        self.edge_credentials={p['project_uuid']:{'project_uuid':p['project_uuid'],
            'jwt_secret':self.secret[p['slug']]['jwt'],'anon_key':self.keys[p['slug']]['anon'],
            'service_role_key':self.keys[p['slug']]['service_role']} for p in self.projects}
        self.edge_api={p['project_uuid']:'http://127.0.0.1:'+str(self.endpoints[p['slug']]['api']) for p in self.projects}
        # The upstream runtime virtualizes /tmp even for the main worker. Its
        # private registry is mounted outside that virtual namespace, as in prod.
        self.edge_temp=tempfile.TemporaryDirectory(prefix='edge-native-',dir=self.edge_bin.parent)
        self.edge_state=pathlib.Path(self.edge_temp.name)
        self.edge_registry=self.edge_state/'edge-registry.private.json'
        self.foreign_module=self.edge_state/'other-project-private.ts'
        self.foreign_module.write_text('export const canary="SHOULD_NOT_REACH_A_DIFFERENT_WORKER";')
        self.edge_canaries={p['slug']:p['slug']+'-synthetic-function-secret' for p in self.projects}
        for path in [BASE/'tools/shared_edge.py',BASE/'edge/main/index.ts',BASE/'edge/main/package-lock.json',pathlib.Path(__file__)]:
            self.source_hashes[str(path.relative_to(BASE))]=hashlib.sha256(path.read_bytes()).hexdigest()
        self.edge_hashes={'native_binary':hashlib.sha256(self.edge_bin.read_bytes()).hexdigest(),
            'bundled_main':hashlib.sha256((self.edge_main/'index.ts').read_bytes()).hexdigest()}
    def stop_edge_label(self,label):
        child=self.process_by_label[label]
        if child.poll() is None:
            os.killpg(child.pid,signal.SIGTERM)
            try:child.wait(timeout=8)
            except subprocess.TimeoutExpired:os.killpg(child.pid,signal.SIGKILL);child.wait(timeout=5)
    def descriptor(self,name,source,*,auth='user',privileged=False,env=None,timeout=5000,cpu=500):
        return {'name':name,'source':source,'auth':auth,'allow_service_role':privileged,
            'env':env or {},'net_allow':[],'memory_mb':64,'timeout_ms':timeout,'cpu_ms':cpu}
    def setup_edge(self):
        functions={}
        for p in self.projects:
            pid=p['project_uuid'];slug=p['slug'];other=next(q for q in self.projects if q!=p)
            custom={'CUSTOM_CANARY':self.edge_canaries[slug]}
            functions[pid]=[
                self.descriptor('identity',IDENTITY,env=custom),
                self.descriptor('notes',NOTES),
                self.descriptor('service-notes',NOTES,auth='service_role',privileged=True),
                self.descriptor('api-ping',"Deno.serve(()=>Response.json({project:Deno.env.get('DIAL_PROJECT_ID')}));",auth='apikey'),
                self.descriptor('sandbox',SANDBOX,env={'TEST_REGISTRY_PATH':str(self.edge_registry),
                    'TEST_FOREIGN_SOURCE':str(self.foreign_module),'TEST_FOREIGN_API':self.edge_api[other['project_uuid']],
                    'TEST_RUNTIME_API':'http://127.0.0.1:'+str(self.edgeport)}),
                self.descriptor('slow',"Deno.serve(async()=>{await new Promise(r=>setTimeout(r,800));return Response.json({project:Deno.env.get('DIAL_PROJECT_ID')})});"),
                self.descriptor('deadline',"Deno.serve(async()=>{await new Promise(r=>setTimeout(r,6000));return new Response('too late')});",timeout=300),
                self.descriptor('cpu-bounded',"Deno.serve(()=>{while(true){};return new Response('unreachable')});",timeout=2000,cpu=100),
                self.descriptor('mutate-then-throw',MUTATE_THROW,env=custom),
                self.descriptor('foreign-import','import {canary} from '+json.dumps(self.foreign_module.as_uri())+'; Deno.serve(()=>new Response(canary));'),
                self.descriptor('oversize-response',"Deno.serve(()=>new Response(new Uint8Array(4194305)));"),
                self.descriptor('echo-body',"Deno.serve(async req=>Response.json({size:(await req.arrayBuffer()).byteLength}));"),
            ]
        self.edge_private={'credentials':self.edge_credentials,'shared':self.edge_shared,
            'functions':functions,'api_endpoints':self.edge_api,
            'allowed_origins':{p['project_uuid']:['https://app-'+p['slug']+'.example.invalid'] for p in self.projects},
            'worker_root':str(self.edge_state/'immutable-edge-workers')}
        self.edge_config=edge.registry(self.projects,**self.edge_private)
        self.edge_registry.write_text(edge.canonical(self.edge_config)+'\n');self.edge_registry.chmod(0o600)
        self.edge_config_hash=hashlib.sha256(self.edge_registry.read_bytes()).hexdigest()
        self.start_edge()
        for p in self.projects:self.install_edge_gateway(p)
    def start_edge(self):
        env={'DIAL_EDGE_REGISTRY':str(self.edge_registry),'DIAL_EDGE_REGISTRY_SHA256':self.edge_config_hash,
            'DENO_DIR':str(self.work/'edge-cache'),'DIAL_EDGE_MANAGER_ONLY_CANARY':'manager-only-synthetic-canary',
            'RUST_LOG':'error','TOKIO_WORKER_THREADS':'2','NO_COLOR':'1'}
        args=[self.edge_bin,'start','-i','127.0.0.1','-p',str(self.edgeport),'--main-service',self.edge_main,
            '--policy','per_worker','--max-parallelism','4','--request-wait-timeout','2000',
            '--user-worker-request-idle-timeout','11000','--request-read-timeout','5000','--graceful-exit-timeout','1']
        child=self.spawn(args,env,'shared-edge-runtime')
        self.wait_http(child,self.edgeport,'/_internal/health',{'x-dial-edge-health':self.edge_shared['health_key']})
        self.check('shared_edge_native_main_ready',True)
    def install_edge_gateway(self,p):
        self.stop_edge_label(p['slug']+'-nginx')
        config=edge.gateway(p,self.edge_credentials[p['project_uuid']],self.edge_shared['gateway_keys'][p['project_uuid']],
            self.edge_api[p['project_uuid']],upstream='127.0.0.1:'+str(self.edgeport))
        self.launch_edge_gateway(p,config)
    def launch_edge_gateway(self,p,text):
        ep=self.endpoints[p['slug']];text=text.replace('listen 8080','listen 127.0.0.1:'+str(ep['api']))
        for kind,pn in [('auth',9999),('rest',3000)]:text=text.replace('tenant-'+p['slug']+'-'+kind+':'+str(pn),'127.0.0.1:'+str(ep[kind]))
        cfg=self.work/(p['slug']+'-nginx.conf');buffers=self.work/(p['slug']+'-buffers')
        temp='\n'.join(k+'_temp_path '+str(buffers/k)+';' for k in ('client_body','proxy','fastcgi','uwsgi','scgi'))
        cfg.write_text('\n'.join(['daemon off;','master_process off;','pid '+str(self.work/(p['slug']+'.pid'))+';',
            'error_log '+str(self.work/(p['slug']+'-edge-nginx.log'))+';','events {worker_connections 128;}','http {access_log off;',temp,text,'}']))
        r=self.run([self.args.nginx,'-t','-p',str(self.work)+'/','-c',cfg]);self.check(p['slug']+'_edge_gateway_native_valid',r.returncode==0)
        child=self.spawn([self.args.nginx,'-p',str(self.work)+'/','-c',cfg],{},p['slug']+'-nginx')
        self.wait_http(child,ep['api'],'/rest/v1/notes',{'Host':p['hostname'],'apikey':self.keys[p['slug']]['service_role']})
    def invoke(self,p,name,*,token=None,key=None,method='GET',body=None,extra=None):
        headers={'Host':p['hostname'],'apikey':self.keys[p['slug']]['anon'] if key is None else key}
        if token is not False:headers['Authorization']='Bearer '+(token or self.sessions[p['slug']]['access_token'])
        headers.update(extra or {})
        return request(self.endpoints[p['slug']]['api'],'/functions/v1/'+name,method,body,headers)
    def exercise_edge(self):
        for p in self.projects:
            slug=p['slug'];other=next(q for q in self.projects if q!=p);foreign=other['slug']
            code,result=self.invoke(p,'identity')
            self.check(slug+'_edge_real_user_function',code==200 and result.get('project')==p['project_uuid'])
            self.check(slug+'_edge_scoped_function_secret',result['secret_sha256']==hashlib.sha256(self.edge_canaries[slug].encode()).hexdigest())
            self.check(slug+'_edge_no_unrequested_service_key',result['service_key_present'] is False)
            self.check(slug+'_edge_no_main_registry_env',result['manager_registry_visible'] is False)
            self.check(slug+'_edge_trusted_identity_only',result['identity_header']==p['project_uuid'] and not result['gateway_secret_forwarded'] and result['forwarded_host'] is None)
            code,rows=self.invoke(p,'notes')
            self.check(slug+'_edge_reads_own_real_rest_rls',code==200 and rows==[{'body':slug}])
            code,rows=self.invoke(p,'service-notes',token=self.keys[slug]['service_role'])
            self.check(slug+'_edge_explicit_service_capability',code==200 and len(rows)==2)
            code,_=self.invoke(p,'service-notes');self.check(slug+'_user_cannot_invoke_service_function',code==401)
            code,result=self.invoke(p,'api-ping',token=False)
            self.check(slug+'_explicit_apikey_function',code==200 and result.get('project')==p['project_uuid'])
            for label,kwargs in [('missing_apikey',{'key':''}),('invalid_apikey',{'key':'wrong'}),
                ('foreign_apikey',{'key':self.keys[foreign]['anon']}),('foreign_bearer',{'token':self.sessions[foreign]['access_token']}),
                ('foreign_service',{'token':self.keys[foreign]['service_role']}),('missing_user',{'token':False})]:
                code,_=self.invoke(p,'identity',**kwargs);self.check(slug+'_edge_denies_'+label,code==401)
            for claim,value in [('iss','https://'+other['hostname']+'/auth/v1'),('aud','foreign-audience'),('exp',1),('nbf',int(time.time())+600)]:
                h,part,_=self.sessions[slug]['access_token'].split('.');data=json.loads(base64.urlsafe_b64decode(part+'='*(-len(part)%4)));data[claim]=value
                part=base64.urlsafe_b64encode(json.dumps(data,separators=(',',':')).encode()).decode().rstrip('=');message=h+'.'+part
                forged=message+'.'+base64.urlsafe_b64encode(hmac.digest(self.secret[slug]['jwt'].encode(),message.encode(),'sha256')).decode().rstrip('=')
                code,_=self.invoke(p,'identity',token=forged);self.check(slug+'_edge_denies_wrong_'+claim+'_even_valid_signature',code==401)
            code,result=self.invoke(p,'sandbox')
            self.check(slug+'_edge_actual_sandbox_function',code==200 and isinstance(result,dict))
            for operation,outcome in result.items():self.check(slug+'_native_user_worker_denies_'+operation,outcome.startswith('DENIED:'))
            self.check(slug+'_sandbox_did_not_write_host_file',not pathlib.Path('/tmp/edge-should-not-write').exists())
            code,_=self.invoke(p,'foreign-import');self.check(slug+'_static_import_other_project_refused',code==502)
            code,_=self.invoke(p,'not-registered');self.check(slug+'_unknown_function_refused',code==404)
            code,_=self.invoke(p,'../_internal/health');self.check(slug+'_function_path_cannot_reach_manager',code in (404,400))
            code,_=self.invoke(p,'identity',extra={'Host':other['hostname']});self.check(slug+'_foreign_host_refused',code==421)
            code,result=self.invoke(p,'identity',extra={'X-Dial-Project-ID':other['project_uuid'],'X-Forwarded-Host':edge.project_host(other),'X-Dial-Edge-Gateway':'forged','X-Tenant-ID':other['project_uuid']})
            self.check(slug+'_forged_headers_cannot_change_function_project',code==200 and result['project']==p['project_uuid'])
            origin=self.edge_private['allowed_origins'][p['project_uuid']][0]
            code,_=self.invoke(p,'identity',token=False,key='',method='OPTIONS',extra={'Origin':origin})
            self.check(slug+'_approved_browser_preflight',code==204)
            code,_=self.invoke(p,'identity',extra={'Origin':'https://unapproved.example.invalid'})
            self.check(slug+'_foreign_browser_origin_refused',code==403)
            code,result=self.invoke(p,'echo-body',method='POST',body={'value':'synthetic'})
            self.check(slug+'_function_body_forwarded',code==200 and result['size']>0)
            code,_=self.invoke(p,'echo-body',method='POST',body={'value':'x'*1048576})
            self.check(slug+'_oversize_request_refused',code==413)
            code,_=self.invoke(p,'oversize-response');self.check(slug+'_oversize_function_response_refused',code==502)
            code,_=self.invoke(p,'deadline');self.check(slug+'_function_wall_deadline_bounded',code==504)
            # The HTTP deadline is earlier than the native worker's hard
            # termination. Until the original worker settles, the owner
            # intentionally retains its capacity lease. Wait using only a
            # read-only identity function; never replay a potentially
            # effectful or uncertain invocation to clear capacity.
            capacity=False;last_code=None
            for _ in range(30):
                last_code,_=self.invoke(p,'identity')
                if last_code==200:capacity=True;break
                if last_code!=429:break
                time.sleep(.2)
            self.check(slug+'_native_deadline_worker_capacity_reconciled',capacity)
            code,_=self.invoke(p,'cpu-bounded')
            if code not in (502,504):raise Failure(slug+'_native_cpu_exhaustion_bounded_unexpected_http_'+str(code))
            self.check(slug+'_native_cpu_exhaustion_bounded',True)
            code,result=self.invoke(other,'identity');self.check(slug+'_other_project_survives_failed_worker',code==200 and result['project']==other['project_uuid'])
            code,error=self.invoke(p,'mutate-then-throw')
            self.check(slug+'_unknown_effect_returned_without_secret',code in (500,502) and self.edge_canaries[slug] not in json.dumps(error))
            code,rows=self.api(p,'/rest/v1/notes?select=id&body=eq.edge-write-once',bearer=self.sessions[slug]['access_token'])
            self.check(slug+'_failed_function_effect_not_automatically_replayed',code==200 and len(rows)==1)
        p,other=self.projects
        with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
            first=pool.submit(self.invoke,p,'slow');time.sleep(.2)
            code,_=self.invoke(p,'slow');self.check('same_function_inflight_limit_enforced',code==429)
            second=pool.submit(self.invoke,other,'slow')
            a,bresult=first.result(),second.result()
            self.check('distinct_projects_functions_run_independently',a[0]==200 and bresult[0]==200 and a[1]['project']!=bresult[1]['project'])
        for p in self.projects:
            code,_=request(self.edgeport,'/identity',headers={'Host':edge.project_host(p),'apikey':self.keys[p['slug']]['anon'],'Authorization':'Bearer '+self.sessions[p['slug']]['access_token']})
            self.check(p['slug']+'_direct_runtime_requires_private_ingress_key',code==421)
        code,_=request(self.edgeport,'/_internal/health');self.check('internal_health_is_not_public',code==404)
        self.stop_edge_label('shared-edge-runtime');self.start_edge()
        for p in self.projects:
            code,result=self.invoke(p,'identity');self.check(p['slug']+'_edge_restart_preserves_scoped_identity',code==200 and result['project']==p['project_uuid'])
            code,rows=self.api(p,'/rest/v1/notes?select=body',bearer=self.sessions[p['slug']]['access_token'])
            self.check(p['slug']+'_rest_survives_edge_restart',code==200 and all(x['body']!=p['slug']+'-private-second' for x in rows))
        self.check('edge_does_not_change_legacy_database',self.sql('SELECT value FROM public.sentinel',db='legacy_van').stdout.strip()=='unchanged-fixture')
    def exercise(self):
        super().exercise();self.setup_edge();self.exercise_edge()
    def cleanup(self):
        try:super().cleanup()
        finally:self.edge_temp.cleanup()
    def additional_evidence(self):
        return {'scope':'ONE_SHARED_EDGE_REAL_RUNTIME_PRIVATE_PROJECT_FUNCTIONS_NOT_PRODUCTION',
            'edge_version':edge.VERSION,'edge_upstream_source':edge.SOURCE_COMMIT,
            'edge_runtime_hashes':self.edge_hashes,'edge_services':1,'postgres_servers':1,
            'worker_isolation':'native_user_worker_explicit_env_and_permissions',
            'not_tested':['live VAN','Nissan GTR migration','complete production container/ARM64','Studio','Supavisor','real provider webhooks/OAuth/MFA','production throughput','coordinated off-host recovery']}

if __name__=='__main__':raise SystemExit(main(EdgeRehearsal))
