#!/usr/bin/env python3
"""Actual shared Supabase Storage on the disposable two-project PG17 fixture.

Uses one unmodified pinned upstream Storage runtime, independent tenant DBs and
one registry DB on the SAME PG server. No Docker or production database access.
Storage source and Node are explicit staged paths. No fake Storage responses.
"""
from __future__ import annotations
import concurrent.futures
import hashlib
import http.client
import json
import os
import pathlib
import signal
import shutil
import secrets
import base64
import stat
import subprocess
import time
from urllib.parse import urlsplit
import rehearse_native as native
from rehearse_native import Rehearsal,Failure,BASE,port,request,b
import shared_storage as st


def raw_http(pn,path,method='GET',body=None,headers=None):
    conn=http.client.HTTPConnection('127.0.0.1',pn,timeout=15)
    try:
        data=json.dumps(body).encode() if isinstance(body,(dict,list)) else body
        hd={'Content-Type':'application/json' if isinstance(body,(dict,list)) else 'application/octet-stream',**(headers or {})}
        conn.request(method,path,data,hd);r=conn.getresponse();content=r.read(2*1024*1024)
        try:value=json.loads(content)
        except (UnicodeError,ValueError):value=content
        return r.status,value,dict(r.getheaders())
    finally:conn.close()


class StorageRehearsal(Rehearsal):
    def __init__(self,args):
        super().__init__(args)
        self.node=pathlib.Path(os.environ.get('DIAL_REHEARSAL_STORAGE_NODE',''))
        self.storage_source=pathlib.Path(os.environ.get('DIAL_REHEARSAL_STORAGE_SOURCE',''))
        if not self.node.is_absolute() or not self.node.is_file() or not os.access(self.node,os.X_OK):raise Failure('EXACT_STORAGE_NODE_REQUIRED')
        if not self.storage_source.is_absolute() or not (self.storage_source/'dist/start/server.js').is_file():raise Failure('BUILT_UPSTREAM_STORAGE_REQUIRED')
        rev=self.run(['git','-C',self.storage_source,'rev-parse','HEAD']).stdout.strip()
        dirty=self.run(['git','-C',self.storage_source,'status','--porcelain','--untracked-files=no']).stdout.strip()
        if rev!=st.STORAGE_REF or dirty:raise Failure('PINNED_UNCHANGED_UPSTREAM_STORAGE_REQUIRED')
        self.storage_tree_hash=self.tree_hash(self.storage_source/'dist')
        self.storage_lock_hash=hashlib.sha256((self.storage_source/'package-lock.json').read_bytes()).hexdigest()
        for path in (BASE/'tools/shared_storage.py',pathlib.Path(__file__)):
            self.source_hashes[str(path.relative_to(BASE))]=hashlib.sha256(path.read_bytes()).hexdigest()
        self.storage_port=port();self.admin_port=port();self.objects=self.work/'objects';self.objects.mkdir()
        self.shared=st.new_secrets(self.projects)
        self.native_tenants={p['slug']:("legacy-stub" if i==0 else st.tenant_id(p)) for i,p in enumerate(self.projects)}
        self.object_bucket='preserved-fixture-bucket'
    @staticmethod
    def tree_hash(root):
        h=hashlib.sha256()
        for p in sorted(root.rglob('*')):
            if p.is_file():
                h.update(str(p.relative_to(root)).encode()+b'\0'+hashlib.sha256(p.read_bytes()).digest())
        return h.hexdigest()
    def stop_label(self,label):
        p=self.process_by_label[label]
        if p.poll() is None:
            os.killpg(p.pid,signal.SIGTERM)
            try:p.wait(timeout=12)
            except subprocess.TimeoutExpired:raise Failure('FIXTURE_PROCESS_DID_NOT_STOP_'+label)
    def admin(self,path,method='GET',body=None,key=None):
        return raw_http(self.admin_port,path,method,body,{'apikey':self.shared['admin_key'] if key is None else key})
    def storage(self,p,path,method='GET',body=None,bearer=None,key=None,anonymous=False,extra=None):
        headers={'Host':p['hostname']}
        if not anonymous:
            headers['apikey']=self.keys[p['slug']]['anon'] if key is None else key
            headers['Authorization']='Bearer '+(bearer or self.sessions[p['slug']]['access_token'])
        if extra:headers.update(extra)
        return raw_http(self.endpoints[p['slug']]['api'],'/storage/v1'+path,method,body,headers)
    def start_storage(self):
        env=st.environment(self.shared,str(self.objects),'127.0.0.1',self.pgport,object_bucket=self.object_bucket,preserved_tenants=self.native_tenants.values())
        env.update(SERVER_HOST='127.0.0.1',SERVER_PORT=str(self.storage_port),SERVER_ADMIN_PORT=str(self.admin_port),
            NODE_ENV='production',NODE_OPTIONS='--max-old-space-size=256',UV_THREADPOOL_SIZE='2')
        self.storage_env=env
        proc=self.spawn([self.node,self.storage_source/'dist/start/server.js'],env,'shared-storage',self.storage_source)
        self.wait_http(proc,self.admin_port,'/status')
        self.check('one_actual_multitenant_storage_process_started',proc.poll() is None)
    def configure_gateways(self):
        for p in self.projects:
            self.stop_label(p['slug']+'-nginx')
            ep=self.endpoints[p['slug']]
            txt=st.gateway(p,self.keys[p['slug']]['anon'],self.keys[p['slug']]['service_role'],f'127.0.0.1:{self.storage_port}',preserved_tenant_id=self.native_tenants[p['slug']])
            txt=txt.replace('listen 8080','listen 127.0.0.1:'+str(ep['api']))
            for kind,pn in [('auth',9999),('rest',3000)]:txt=txt.replace('tenant-'+p['slug']+'-'+kind+':'+str(pn),'127.0.0.1:'+str(ep[kind]))
            cfg=self.work/(p['slug']+'-nginx.conf');buffers=self.work/(p['slug']+'-buffers')
            temp_settings='\n'.join(k+'_temp_path '+str(buffers/k)+';' for k in ('client_body','proxy','fastcgi','uwsgi','scgi'))
            cfg.write_text('\n'.join(['daemon off;','master_process off;','pid '+str(self.work/(p['slug']+'.pid'))+';','error_log '+str(self.work/(p['slug']+'-nginx-error.log'))+';','events { worker_connections 64; }','http { access_log off;',temp_settings,txt,'}']))
            checked=self.run([self.args.nginx,'-t','-p',str(self.work)+'/', '-c',cfg])
            self.check(p['slug']+'_shared_storage_gateway_syntax',checked.returncode==0)
            proc=self.spawn([self.args.nginx,'-p',str(self.work)+'/', '-c',cfg],{},p['slug']+'-nginx')
            self.wait_http(proc,ep['api'],'/rest/v1/notes',{'Host':p['hostname'],'apikey':self.keys[p['slug']]['service_role']})
    def make_legacy_single_tenant(self):
        p=self.projects[0];slug=p['slug']
        env=st.environment(self.shared,str(self.objects),'127.0.0.1',self.pgport,object_bucket=self.object_bucket,preserved_tenants=self.native_tenants.values())
        env.update(MULTI_TENANT='false',PROJECT_REF=self.native_tenants[slug],TENANT_ID=self.native_tenants[slug],
            DATABASE_URL=st.dsn(p['database'],st.role(p),self.shared['projects'][st.tenant_id(p)],'127.0.0.1',self.pgport),
            ANON_KEY=self.keys[slug]['anon'],SERVICE_KEY=self.keys[slug]['service_role'],AUTH_JWT_SECRET=self.secret[slug]['jwt'],
            SERVER_HOST='127.0.0.1',SERVER_PORT=str(self.storage_port),NODE_ENV='production',NODE_OPTIONS='--max-old-space-size=256',UV_THREADPOOL_SIZE='2')
        proc=self.spawn([self.node,self.storage_source/'dist/start/server.js'],env,'legacy-single-storage',self.storage_source)
        self.wait_http(proc,self.storage_port,'/status')
        self.check('original_single_tenant_storage_started_with_preserved_namespace',proc.poll() is None)
        h={'Authorization':'Bearer '+self.keys[slug]['service_role']}
        code,_,_=raw_http(self.storage_port,'/bucket','POST',{'id':'original-vati','name':'original-vati','public':False},h)
        self.check('original_single_tenant_bucket_created',code in (200,201))
        code,_,_=raw_http(self.storage_port,'/object/original-vati/ledger-proof.txt','POST',b'original-namespace-preserved',h)
        self.check('original_single_tenant_object_written',code in (200,201))
        code,body,_=raw_http(self.storage_port,'/object/sign/original-vati/ledger-proof.txt','POST',{'expiresIn':180},h)
        self.check('original_single_tenant_signed_url_issued',code==200 and bool(body.get('signedURL')))
        self.legacy_signed_url=body['signedURL']
        self.legacy_object_hashes={str(f.relative_to(self.objects)):hashlib.sha256(f.read_bytes()).hexdigest() for f in self.objects.rglob('*') if f.is_file()}
        self.check('legacy_object_path_contains_original_native_tenant',bool(self.legacy_object_hashes) and all('/legacy-stub/' in '/'+x for x in self.legacy_object_hashes))
        self.stop_label('legacy-single-storage')

    def verify_legacy_preserved(self):
        p=self.projects[0];slug=p['slug']
        for name,digest in self.legacy_object_hashes.items():
            f=self.objects/name
            self.check('original_object_bytes_unchanged_after_mode_conversion',f.is_file() and hashlib.sha256(f.read_bytes()).hexdigest()==digest)
        code,data,_=self.storage(p,'/object/authenticated/original-vati/ledger-proof.txt',bearer=self.keys[slug]['service_role'])
        self.check('legacy_credentials_and_object_work_after_single_to_multi_conversion',code==200 and data==b'original-namespace-preserved')
        code,data,_=self.storage(p,self.legacy_signed_url,anonymous=True)
        self.check('original_preconversion_signed_url_remains_valid',code==200 and data==b'original-namespace-preserved')
        other=self.projects[1]
        code,_,_=self.storage(other,self.legacy_signed_url,anonymous=True)
        self.check('legacy_signed_url_cannot_cross_to_new_project',code not in (200,206))

    def setup_storage(self):
        self.sql(st.control_roles_sql(self.shared['control_password']));self.sql(st.control_database_sql())
        for p in self.projects:
            self.sql(st.roles_sql(p,self.shared['projects'][st.tenant_id(p)]));self.sql(st.schema_sql(p),db=p['database'])
        fragment,expected=st.hba(self.projects,['127.0.0.1/32'])
        activate=st.activation_sql(self.projects,expected)
        r=self.sql(activate,fail_ok=True)
        self.check('storage_activation_refuses_old_hba',r.returncode!=0 and 'STORAGE_EXACT_HBA_PREFIX_REQUIRED' in r.stderr)
        (self.data/'pg_hba.conf').write_text(fragment+self.original_hba_suffix)
        self.run([self.args.pg_bin/'pg_ctl','-D',self.data,'reload']);time.sleep(.3)
        self.sql(activate);self.check('storage_roles_activated_after_exact_hba',True)
        self.check('storage_activation_replay_refused',self.sql(activate,fail_ok=True).returncode!=0)
        for p in self.projects:
            login=st.role(p);password=self.shared['projects'][st.tenant_id(p)]
            self.check(p['slug']+'_storage_login_own_db',self.sql('SELECT current_database()',db=p['database'],role=login,password=password,tcp=True).stdout.strip()==p['database'])
            for db in ['postgres','legacy_van',st.CONTROL_DB]+[q['database'] for q in self.projects if q!=p]:
                r=self.sql('SELECT 1',db=db,role=login,password=password,tcp=True,fail_ok=True)
                self.check(p['slug']+'_storage_login_other_db_denied_'+db,r.returncode!=0 and 'pg_hba.conf rejects' in r.stderr)
        for p in self.projects:
            r=self.sql('SELECT 1',db=p['database'],role=st.CONTROL_ROLE,password=self.shared['control_password'],tcp=True,fail_ok=True)
            self.check('storage_registry_login_cannot_enter_'+p['slug'],r.returncode!=0)
        self.make_legacy_single_tenant()
        self.start_storage()
        code,_,_=self.admin('/tenants',key='invalid');self.check('storage_admin_wrong_key_denied',code in (401,403))
        for p in self.projects:
            reg=st.registration(p,self.secret[p['slug']],self.shared,self.keys[p['slug']],'127.0.0.1',self.pgport)
            code,body,_=self.admin('/tenants/'+self.native_tenants[p['slug']],'POST',reg)
            if code!=201:(self.work/'storage-register-error.json').write_text(json.dumps({'status':code,'response':body}))
            self.check(p['slug']+'_actual_storage_tenant_registered',code==201)
            ready=False;deadline=time.monotonic()+25
            while time.monotonic()<deadline:
                code,body,_=self.admin('/tenants/'+self.native_tenants[p['slug']])
                if code==200 and body.get('migrationStatus')=='COMPLETED':ready=True;break
                time.sleep(.25)
            if not ready:(self.work/'storage-migration-state.json').write_text(json.dumps(body))
            self.check(p['slug']+'_actual_storage_migrations_completed',ready)
            self.check(p['slug']+'_admin_tenant_read_hides_credentials',not any(k in body for k in ('jwtSecret','serviceKey','anonKey','databaseUrl','databasePoolUrl')))
            # RLS policy is an application policy, not fabricated Storage internals.
            self.sql("CREATE POLICY own_storage_objects ON storage.objects TO authenticated USING (owner_id=(SELECT auth.uid())::text) WITH CHECK (owner_id=(SELECT auth.uid())::text);",db=p['database'])
        self.configure_gateways()
        self.verify_legacy_preserved()
    def exercise_storage(self):
        self.signed={};self.payloads={}
        for p in self.projects:
            slug=p['slug'];service=self.keys[slug]['service_role'];payload=('private-'+slug).encode();self.payloads[slug]=payload
            for bucket,pub in [('private-fixture',False),('public-fixture',True)]:
                code,body,_=self.storage(p,'/bucket','POST',{'id':bucket,'name':bucket,'public':pub},bearer=service)
                if code not in (200,201):(self.work/'storage-api-error.json').write_text(json.dumps({'code':code,'body':body}))
                self.check(slug+'_real_bucket_create_'+bucket,code in (200,201))
            code,body,_=self.storage(p,'/object/private-fixture/same.txt','POST',payload,extra={'Content-Type':'text/plain'})
            if code not in (200,201):(self.work/'storage-upload-error.json').write_text(json.dumps({'code':code,'body':body}))
            self.check(slug+'_real_owned_object_upload',code in (200,201))
            code,data,_=self.storage(p,'/object/authenticated/private-fixture/same.txt')
            self.check(slug+'_real_owned_object_download',code==200 and data==payload)
            code,rows,_=self.storage(p,'/object/list/private-fixture','POST',{'prefix':'','limit':10})
            self.check(slug+'_real_owned_object_list',code==200 and len(rows)==1 and rows[0]['name']=='same.txt')
            code,body,_=self.storage(p,'/object/sign/private-fixture/same.txt','POST',{'expiresIn':60})
            self.check(slug+'_real_signed_url_create',code==200 and bool(body.get('signedURL')))
            self.signed[slug]=body['signedURL']
            code,data,_=self.storage(p,self.signed[slug],anonymous=True)
            self.check(slug+'_signed_download_without_api_key',code==200 and data==payload)
            code,_,_=self.storage(p,'/object/public/private-fixture/same.txt',anonymous=True)
            self.check(slug+'_private_object_not_public',code not in (200,206))
            code,_,_=self.storage(p,'/object/public-fixture/same.txt','POST',('public-'+slug).encode(),bearer=service,extra={'Content-Type':'text/plain'})
            self.check(slug+'_public_object_upload',code in (200,201))
            code,data,_=self.storage(p,'/object/public/public-fixture/same.txt',anonymous=True)
            self.check(slug+'_public_download_no_key',code==200 and data==('public-'+slug).encode())
        for p,other in (self.projects, self.projects[::-1]):
            slug=p['slug'];alien=other['slug'];path='/object/authenticated/private-fixture/same.txt'
            code,_,_=self.storage(p,path,bearer=self.sessions[alien]['access_token'])
            self.check(slug+'_storage_foreign_user_token_denied',code not in (200,206))
            code,_,_=self.storage(p,path,bearer=self.keys[alien]['service_role'])
            self.check(slug+'_storage_foreign_service_token_denied',code not in (200,206))
            code,_,_=self.storage(p,path,key=self.keys[alien]['anon'])
            self.check(slug+'_storage_foreign_api_key_denied',code==401)
            code,data,_=self.storage(p,path,extra={'X-Forwarded-Host':st.tenant_id(other)+'.storage.internal','X-Tenant-ID':st.tenant_id(other),'X-Project-ID':other['project_uuid'],'X-Dial-Project-ID':other['project_uuid']})
            self.check(slug+'_storage_spoofed_tenant_headers_replaced',code==200 and data==self.payloads[slug])
            code,_,_=self.storage(p,self.signed[alien],anonymous=True)
            self.check(slug+'_foreign_signed_url_denied',code not in (200,206))
            # Mutate a meaningful signature byte, not base64url's unused
            # trailing padding bits (which may decode to the same signature).
            signed=self.signed[slug];index=signed.rfind('.')+1
            if index<=0 or index>=len(signed):raise Failure('SIGNED_URL_FORMAT_CHANGED')
            tampered=signed[:index]+('A' if signed[index]!='A' else 'B')+signed[index+1:]
            code,_,_=self.storage(p,tampered,anonymous=True)
            self.check(slug+'_tampered_signed_url_denied',code not in (200,206))
            code,_,_=self.storage(p,path,anonymous=True)
            self.check(slug+'_private_download_no_key_denied',code==401)
            for adminpath in ('/tenants','/tenants/'+self.native_tenants[p['slug']],'/migrations'):
                code,_,_=self.storage(p,adminpath,bearer=self.keys[slug]['service_role'])
                self.check(slug+'_public_router_does_not_expose_admin_'+adminpath,code in (400,404))
        def pooled(n):
            p=self.projects[n%2];code,data,_=self.storage(p,'/object/authenticated/private-fixture/same.txt')
            return code==200 and data==self.payloads[p['slug']]
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
            self.check('shared_storage_concurrent_40_requests_isolated',all(pool.map(pooled,range(40))))
        self.stop_label('shared-storage');self.start_storage()
        for p in self.projects:
            code,data,_=self.storage(p,'/object/authenticated/private-fixture/same.txt')
            self.check(p['slug']+'_metadata_and_object_survive_shared_storage_restart',code==200 and data==self.payloads[p['slug']])
            code,data,_=self.storage(p,self.signed[p['slug']],anonymous=True)
            self.check(p['slug']+'_signed_url_survives_storage_restart',code==200 and data==self.payloads[p['slug']])
        self.check('shared_storage_did_not_mutate_legacy_data',self.sql('SELECT value FROM public.sentinel',db='legacy_van').stdout.strip()=='unchanged-fixture')
        self.check('upstream_storage_generated_bytes_unchanged_during_test',self.tree_hash(self.storage_source/'dist')==self.storage_tree_hash)
    def exercise_object_ownership_and_mutations(self):
        for p in self.projects:
            slug=p['slug'];pw=secrets.token_urlsafe(32)
            code,user=self.api(p,'/auth/v1/admin/users','POST',{'email':'storage-other@fixture.invalid','password':pw,'email_confirm':True},bearer=self.keys[slug]['service_role'])
            self.check(slug+'_second_storage_user_created',code in (200,201) and 'id' in user)
            code,login=self.api(p,'/auth/v1/token?grant_type=password','POST',{'email':'storage-other@fixture.invalid','password':pw})
            self.check(slug+'_second_storage_user_authenticated',code==200 and bool(login.get('access_token')))
            second=login['access_token']
            for method,path,body in [('GET','/object/authenticated/private-fixture/same.txt',None),
                ('PUT','/object/private-fixture/same.txt',b'forbidden-replacement'),
                ('POST','/object/sign/private-fixture/same.txt',{'expiresIn':60})]:
                code,_,_=self.storage(p,path,method,body,bearer=second)
                self.check(slug+'_same_project_other_user_denied_'+method+'_'+path,code in (400,401,403,404))
            code,rows,_=self.storage(p,'/object/list/private-fixture','POST',{'prefix':'','limit':20},bearer=second)
            self.check(slug+'_same_project_other_user_list_empty',code==200 and rows==[])
            code,data,_=self.storage(p,'/object/authenticated/private-fixture/same.txt')
            self.check(slug+'_denied_update_did_not_change_bytes',code==200 and data==self.payloads[slug])
            code,_,_=self.storage(p,'/object/private-fixture/second.txt','POST',b'second-user-private',bearer=second)
            self.check(slug+'_second_user_own_upload',code in (200,201))
            code,_,_=self.storage(p,'/object/authenticated/private-fixture/second.txt')
            self.check(slug+'_first_user_cannot_read_second_user_object',code in (400,401,403,404))
            code,data,_=self.storage(p,'/object/authenticated/private-fixture/second.txt',bearer=self.keys[slug]['service_role'])
            self.check(slug+'_service_role_can_read_within_own_project',code==200 and data==b'second-user-private')
            code,_,_=self.storage(p,'/object/private-fixture','DELETE',{'prefixes':['same.txt']},bearer=second)
            code,data,_=self.storage(p,'/object/authenticated/private-fixture/same.txt')
            self.check(slug+'_other_user_delete_does_not_remove_object',code==200 and data==self.payloads[slug])
            code,_,_=self.storage(p,'/object/private-fixture/change.txt','POST',b'original-mutable',extra={'Content-Type':'text/plain'})
            self.check(slug+'_mutable_object_create',code in (200,201))
            code,_,_=self.storage(p,'/object/private-fixture/change.txt','PUT',b'updated-mutable',extra={'Content-Type':'text/plain'})
            self.check(slug+'_owner_can_update_object',code in (200,201))
            code,data,_=self.storage(p,'/object/authenticated/private-fixture/change.txt')
            self.check(slug+'_updated_object_bytes_match',code==200 and data==b'updated-mutable')
            code,_,_=self.storage(p,'/object/private-fixture','DELETE',{'prefixes':['change.txt']})
            self.check(slug+'_owner_can_delete_object',code==200)
            code,_,_=self.storage(p,'/object/authenticated/private-fixture/change.txt')
            self.check(slug+'_deleted_object_unavailable',code in (400,404))
            # Download-signed tokens must not authorize a write to the same key.
            signed=self.signed[slug]
            code,_,_=self.storage(p,signed,'PUT',b'no-token-scope-escalation',anonymous=True)
            self.check(slug+'_download_url_cannot_authorize_upload',code in (400,401,403,404,405))
            code,data,_=self.storage(p,'/object/authenticated/private-fixture/same.txt')
            self.check(slug+'_signed_read_replay_preserves_bytes',code==200 and data==self.payloads[slug])
            code,short,_=self.storage(p,'/object/sign/private-fixture/same.txt','POST',{'expiresIn':1})
            self.check(slug+'_short_lived_signed_url_created',code==200 and bool(short.get('signedURL')))
            time.sleep(2)
            code,_,_=self.storage(p,short['signedURL'],anonymous=True)
            self.check(slug+'_expired_signed_download_denied',code in (400,401,403))
            code,_,_=self.storage(p,'/object/private-fixture/anonymous.txt','POST',b'no-public-write',anonymous=True)
            self.check(slug+'_anonymous_upload_denied',code==401)
        code,_,_=self.admin('/tenants',key='')
        self.check('shared_admin_without_secret_denied',code in (401,403))
        code,_,_=self.admin('/tenants',key=self.keys[self.projects[0]['slug']]['service_role'])
        self.check('project_service_key_is_not_shared_admin_key',code in (401,403))
        code,_,_=raw_http(self.storage_port,'/bucket',headers={'X-Forwarded-Host':'unknown.storage.internal','Authorization':'Bearer '+self.keys[self.projects[0]['slug']]['service_role']})
        self.check('unknown_native_storage_tenant_denied',code in (400,401,403,404))

    @staticmethod
    def object_snapshot(root):
        # Fixture-only observation: bytes plus every extended attribute. This
        # test helper is not an admitted production backup or restore tool.
        out={}
        for p in sorted(root.rglob('*')):
            info=p.lstat()
            if stat.S_ISLNK(info.st_mode) or not (stat.S_ISREG(info.st_mode) or stat.S_ISDIR(info.st_mode)):
                raise Failure('FIXTURE_OBJECT_TREE_NONREGULAR')
            if p.is_file():
                out[str(p.relative_to(root))]={'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),
                    'bytes':info.st_size,'xattrs':{k:base64.b64encode(os.getxattr(p,k)).decode() for k in sorted(os.listxattr(p))}}
        return out

    def exercise_object_restore(self):
        selected=next(p for p in self.projects if p['slug']=='nissan-gtr')
        neighbor=next(p for p in self.projects if p!=selected)
        paths={p['slug']:self.objects/self.object_bucket/self.native_tenants[p['slug']] for p in self.projects}
        for p in self.projects:
            self.check(p['slug']+'_objects_in_distinct_native_namespace',paths[p['slug']].is_dir())
        code,body,headers=self.storage(selected,'/object/authenticated/private-fixture/same.txt')
        self.check('pre_restore_real_object_and_metadata_read',code==200 and body==self.payloads[selected['slug']])
        old_headers={k.lower():v for k,v in headers.items() if k.lower() in ('content-type','cache-control','etag')}
        self.stop_label('shared-storage')
        self.check('shared_storage_quiesced_for_local_object_drill',self.process_by_label['shared-storage'].poll() is not None)
        before=self.object_snapshot(paths[selected['slug']]);other=self.object_snapshot(paths[neighbor['slug']])
        self.check('real_storage_objects_have_preserved_extended_attributes',bool(before) and any('user.supabase.content-type' in x['xattrs'] for x in before.values()))
        snapshot=self.work/'selected-object-snapshot';shutil.copytree(paths[selected['slug']],snapshot,copy_function=shutil.copy2)
        self.check('local_object_copy_matches_bytes_and_xattrs',self.object_snapshot(snapshot)==before)
        digest=hashlib.sha256(json.dumps(before,sort_keys=True).encode()).hexdigest()
        victim=next(p for p in snapshot.rglob('*') if p.is_file());original=victim.read_bytes();victim.write_bytes(b'corrupted-fixture')
        self.check('corrupted_object_snapshot_detected',hashlib.sha256(json.dumps(self.object_snapshot(snapshot),sort_keys=True).encode()).hexdigest()!=digest)
        victim.write_bytes(original)
        self.check('original_object_snapshot_reverified',self.object_snapshot(snapshot)==before)
        # Retain the original; restore into a new empty namespace, never copy
        # over an active or existing destination. All paths are temporary.
        retained=self.work/'retained-original-object-tree';paths[selected['slug']].rename(retained)
        shutil.copytree(snapshot,paths[selected['slug']],copy_function=shutil.copy2)
        self.check('selected_object_tree_restored_to_empty_target',self.object_snapshot(paths[selected['slug']])==before)
        self.check('object_restore_retains_original_source',self.object_snapshot(retained)==before)
        self.check('neighbor_object_tree_unchanged_by_restore',self.object_snapshot(paths[neighbor['slug']])==other)
        self.start_storage()
        code,data,after_headers=self.storage(selected,'/object/authenticated/private-fixture/same.txt')
        self.check('real_api_reads_restored_object_bytes',code==200 and data==self.payloads[selected['slug']])
        normalized={k.lower():v for k,v in after_headers.items() if k.lower() in old_headers}
        self.check('restored_object_type_cache_and_etag_match',normalized==old_headers)
        code,data,_=self.storage(selected,self.signed[selected['slug']],anonymous=True)
        self.check('pre_restore_signed_url_reads_restored_object',code==200 and data==self.payloads[selected['slug']])
        code,data,_=self.storage(neighbor,'/object/authenticated/private-fixture/same.txt')
        self.check('neighbor_api_reads_original_bytes_after_restore',code==200 and data==self.payloads[neighbor['slug']])
        code,_,_=self.storage(selected,'/object/authenticated/private-fixture/same.txt',bearer=self.sessions[neighbor['slug']]['access_token'])
        self.check('cross_project_denial_survives_object_restore',code in (400,401,403,404))
        self.object_restore_evidence={'selected_namespace_files':len(before),'selected_snapshot_sha256':digest,
            'preserved_xattrs':True,'neighbor_unchanged':True,'fixture_only':True,
            'consistent_live_database_and_object_backup_qualified':False,'shared_storage_outage_during_restore':True}

    def exercise(self):
        super().exercise()
        self.setup_storage();self.exercise_storage()
        self.exercise_object_ownership_and_mutations();self.exercise_object_restore()
    def additional_evidence(self):
        return {'scope':'REAL_SHARED_STORAGE_PLUS_TWO_PROJECT_AUTH_REST_DISPOSABLE_PG17',
            'storage_source_commit':st.STORAGE_REF,'storage_source_tag':'v1.74.0',
            'storage_dist_sha256':self.storage_tree_hash,'storage_lock_sha256':self.storage_lock_hash,
            'node_binary_sha256':hashlib.sha256(self.node.read_bytes()).hexdigest(),
            'storage_instances':1,'postgres_instances':1,'object_restore':getattr(self,'object_restore_evidence',{}),
            'not_tested':['live VAN single-to-multi Storage conversion (synthetic transition tested)','Storage donor container/ARM64','Realtime','Edge Functions','Studio','Supavisor','OAuth/MFA/SMTP','GTR migration','off-host backup','consistent production database-and-object recovery']}

if __name__=='__main__':raise SystemExit(native.main(StorageRehearsal))
