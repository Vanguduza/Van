#!/usr/bin/env python3
"""Real one-service Realtime across two fresh databases in one temporary PG17.

Reuses the actual Auth/REST fixture; no production endpoints, credentials,
Docker daemon, root changes or existing database paths are accepted.
"""
from __future__ import annotations
import base64
import hashlib
import json
import os
import pathlib
import secrets
import signal
import socket
import subprocess
import sys
import time
from urllib.parse import quote
from rehearse_native import Rehearsal, Failure, BASE, port, request, main
sys.path.insert(0,str(BASE/'tools'))
import bootstrap as b
import shared_realtime as rt
import patch_realtime


class RealtimeRehearsal(Rehearsal):
    def __init__(self,args):
        super().__init__(args)
        self.release=pathlib.Path(os.environ['DIAL_REHEARSAL_REALTIME_RELEASE'])
        self.runtime_lib=pathlib.Path(os.environ['DIAL_REHEARSAL_REALTIME_LIB'])
        self.websocket_lib=pathlib.Path(os.environ['DIAL_REHEARSAL_WEBSOCKET_LIB'])
        if not all(p.is_absolute() and p.is_dir() for p in (self.release,self.runtime_lib,self.websocket_lib)):
            raise Failure('EXACT_STAGED_REALTIME_RUNTIME_REQUIRED')
        sys.path.insert(0,str(self.websocket_lib))
        import websocket
        self.websocket=websocket;self.sockets=[];self.frames={};self.message_ref=0
        self.rtport=port();self.rpcport=port();self.rt_shared=rt.new_secrets(self.projects)
        self.rt_admin_token=rt.admin_token(self.rt_shared['admin_jwt_secret'])
        self.native_ids={p['slug']:rt.tenant_id(p) for p in self.projects}
        self.credentials={p['slug']:{'project_uuid':p['project_uuid'],'jwt_secret':self.secret[p['slug']]['jwt'],
            'anon_key':self.keys[p['slug']]['anon'],'service_role_key':self.keys[p['slug']]['service_role']} for p in self.projects}
        for path in (BASE/'tools/shared_realtime.py',BASE/'tools/patch_realtime.py',pathlib.Path(__file__)):
            self.source_hashes[str(path.relative_to(BASE))]=hashlib.sha256(path.read_bytes()).hexdigest()
        self.beam=self.release/'lib/realtime-2.152.0/ebin/Elixir.Realtime.Tenants.ReplicationConnection.beam'
        self.dump=self.release/'lib/realtime-2.152.0/priv/repo/tenant_db_dump_17.sql'
        self.runtime_hashes={'patched_replication_beam':hashlib.sha256(self.beam.read_bytes()).hexdigest(),
            'native_schema':hashlib.sha256(self.dump.read_bytes()).hexdigest()}
    def start_pg(self):
        super().start_pg()
        with (self.data/'postgresql.conf').open('a') as f:
            f.write("\nmax_connections=96\nwal_level=logical\nmax_wal_senders=16\nmax_replication_slots=16\nmax_slot_wal_keep_size='64MB'\nmax_wal_size='128MB'\noutput_plugin_libraries='pgoutput,wal2json'\n")
            f.write("dynamic_library_path='"+str(self.args.pg_bin.parent/'lib')+":$libdir'\n")
        r=self.run([self.args.pg_bin/'pg_ctl','-D',self.data,'-l',self.work/'postgres.log','-w','restart'],timeout=30)
        self.check('fixture_logical_wal_enabled',r.returncode==0 and self.sql('SHOW wal_level').stdout.strip()=='logical')
    def stop(self,label):
        p=self.process_by_label[label]
        if p.poll() is None:
            os.killpg(p.pid,signal.SIGTERM)
            try:p.wait(timeout=10)
            except subprocess.TimeoutExpired:
                os.killpg(p.pid,signal.SIGKILL);p.wait(timeout=5)
    def admin_call(self,path,method='GET',body=None,token=None):
        return request(self.rtport,path,method,body,{'Host':'management.realtime.internal','Authorization':'Bearer '+(self.rt_admin_token if token is None else token)})
    def runtime_env(self):
        env=rt.environment(self.rt_shared,'127.0.0.1',self.pgport)
        env.update(PORT=str(self.rtport),GEN_RPC_TCP_SERVER_PORT=str(self.rpcport),GEN_RPC_TCP_CLIENT_PORT=str(self.rpcport),
            GEN_RPC_SOCKET_IP='127.0.0.1',APP_NAME='dial_realtime_fixture_'+str(os.getpid()),
            LD_LIBRARY_PATH=str(self.runtime_lib),NUM_ACCEPTORS='2',REALTIME_IP_VERSION='ipv4',
            ERL_CRASH_DUMP=str(self.work/'realtime-crash.dump'),CONNECT_ERROR_BACKOFF_MS='1',CHANNEL_ERROR_BACKOFF_MS='1',
            CLIENT_JOINS_PER_SECOND='30')
        return env
    def start_realtime(self):
        # Restrict the native HTTP listener to loopback before starting the app.
        # This is a test-only transport override; no upstream auth/RLS change.
        expr='''cfg = Application.fetch_env!(:realtime, RealtimeWeb.Endpoint)
http = Keyword.fetch!(cfg, :http)
transport = Keyword.get(http, :transport_options, []) |> Keyword.put(:socket_opts, [:inet, {:ip, {127,0,0,1}}])
http = Keyword.put(http, :transport_options, transport)
Application.put_env(:realtime, RealtimeWeb.Endpoint, Keyword.put(cfg, :http, http))
{:ok, _} = Application.ensure_all_started(:realtime)
Process.sleep(:infinity)'''
        child=self.spawn([self.release/'bin/realtime','eval',expr],self.runtime_env(),'shared-realtime',self.release)
        self.wait_http(child,self.rtport,'/healthcheck')
        self.check('shared_realtime_real_process_ready',True)
        self.check('registry_migrations_are_native',int(self.sql('SELECT count(*) FROM _realtime.schema_migrations',db=rt.CONTROL_DB).stdout)>10)
    def install_gateway(self,p):
        self.stop(p['slug']+'-nginx')
        cfg=self.work/(p['slug']+'-nginx.conf');old=cfg.read_text()
        # Rebuild only the existing synthetic project gateway, keeping Auth/REST.
        text=rt.gateway(p,self.keys[p['slug']]['anon'],self.keys[p['slug']]['service_role'],upstream='127.0.0.1:'+str(self.rtport))
        ep=self.endpoints[p['slug']]
        text=text.replace('listen 8080','listen 127.0.0.1:'+str(ep['api']))
        for kind,pn in [('auth',9999),('rest',3000)]:
            text=text.replace('tenant-'+p['slug']+'-'+kind+':'+str(pn),'127.0.0.1:'+str(ep[kind]))
        buffers=self.work/(p['slug']+'-buffers')
        temp='\n'.join(k+'_temp_path '+str(buffers/k)+';' for k in ('client_body','proxy','fastcgi','uwsgi','scgi'))
        cfg.write_text('\n'.join(['daemon off;','master_process off;','pid '+str(self.work/(p['slug']+'.pid'))+';',
            'error_log '+str(self.work/(p['slug']+'-nginx-error.log'))+';','events { worker_connections 128; }','http { access_log off;',temp,text,'}']))
        result=self.run([self.args.nginx,'-t','-p',str(self.work)+'/', '-c',cfg])
        if result.returncode:
            (self.work/'nginx-config-error.txt').write_text(result.stderr)
        self.check(p['slug']+'_realtime_gateway_native_config',result.returncode==0)
        self.spawn([self.args.nginx,'-p',str(self.work)+'/', '-c',cfg],{},p['slug']+'-nginx')
    def setup_realtime(self):
        # Canonical donor identities only in this fresh synthetic cluster.
        self.sql('CREATE ROLE supabase_admin NOLOGIN; CREATE ROLE dashboard_user NOLOGIN; CREATE ROLE supabase_realtime_admin NOLOGIN NOINHERIT NOSUPERUSER NOCREATEROLE NOCREATEDB NOREPLICATION NOBYPASSRLS; GRANT anon,authenticated,service_role TO supabase_realtime_admin WITH INHERIT FALSE; GRANT SET ON PARAMETER log_min_messages TO supabase_realtime_admin;')
        first,second=rt.control_sql(self.rt_shared['control_password']);self.sql(first);self.sql(second)
        self.sql(rt.control_schema_sql(),db=rt.CONTROL_DB)
        self.migration_counts={}
        for p in self.projects:
            self.sql(rt.role_sql(p,self.rt_shared['projects'][rt.tenant_id(p)]))
            self.sql(rt.fresh_schema_sql(p,self.dump.read_text()),db=p['database'])
            self.sql(rt.publication_sql(p,[('public','notes')]),db=p['database'])
            self.migration_counts[p['slug']]=int(self.sql('SELECT count(*) FROM realtime.schema_migrations',db=p['database']).stdout)
            self.check(p['slug']+'_exact_native_realtime_schema_loaded',self.migration_counts[p['slug']]>70)
            uid=self.users[p['slug']]
            self.sql("CREATE POLICY fixture_realtime_read ON realtime.messages FOR SELECT TO authenticated USING (auth.uid()="+b.lit(uid)+"::uuid AND realtime.topic()='same-room'); CREATE POLICY fixture_realtime_write ON realtime.messages FOR INSERT TO authenticated WITH CHECK (auth.uid()="+b.lit(uid)+"::uuid AND realtime.topic()='same-room');",db=p['database'])
        prefix,rules=rt.hba(self.projects,['127.0.0.1/32'],include_storage=getattr(self,'with_storage',False))
        refused=self.sql(rt.activation_sql(self.projects,rules),fail_ok=True)
        self.check('realtime_activation_refuses_old_hba',refused.returncode!=0)
        (self.data/'pg_hba.conf').write_text(prefix+self.original_hba_suffix)
        self.run([self.args.pg_bin/'pg_ctl','-D',self.data,'reload']);time.sleep(.2)
        self.sql(rt.activation_sql(self.projects,rules))
        self.check('realtime_activation_after_exact_hba',True)
        self.check('realtime_activation_replay_denied',self.sql(rt.activation_sql(self.projects,rules),fail_ok=True).returncode!=0)
        for p in self.projects:
            name=rt.role(p);password=self.rt_shared['projects'][rt.tenant_id(p)]
            own=self.sql('SELECT current_database()',db=p['database'],role=name,password=password,tcp=True)
            self.check(p['slug']+'_realtime_login_own_database',own.stdout.strip()==p['database'])
            for target in [rt.CONTROL_DB,'postgres','legacy_van']+[q['database'] for q in self.projects if q!=p]:
                denied=self.sql('SELECT 1',db=target,role=name,password=password,tcp=True,fail_ok=True)
                self.check(p['slug']+'_realtime_login_denies_'+target,denied.returncode!=0 and 'pg_hba.conf rejects' in denied.stderr)
            physical=self.run([self.args.pg_bin/'psql','-X','-qAt','-d',f'host=127.0.0.1 port={self.pgport} user={name} replication=true','-c','IDENTIFY_SYSTEM'],env={'PGPASSWORD':password})
            self.check(p['slug']+'_physical_replication_denied',physical.returncode!=0 and 'pg_hba.conf rejects' in physical.stderr)
            denied=self.sql('SET ROLE supabase_admin',db=p['database'],role=name,password=password,tcp=True,fail_ok=True)
            self.check(p['slug']+'_cannot_become_cluster_admin',denied.returncode!=0)
        for p in self.projects:
            denied=self.sql('SELECT 1',db=p['database'],role=rt.CONTROL_ROLE,password=self.rt_shared['control_password'],tcp=True,fail_ok=True)
            self.check('registry_cannot_connect_'+p['slug'],denied.returncode!=0)
        migration=self.run([self.release/'bin/realtime','eval','Realtime.Release.migrate'],env=self.runtime_env(),timeout=45)
        if migration.returncode:(self.work/'registry-migration-error.txt').write_text(migration.stdout+migration.stderr)
        self.check('native_realtime_registry_migrations',migration.returncode==0)
        self.start_realtime()
        for p in self.projects:
            body=rt.registration(p,self.credentials[p['slug']],self.rt_shared,self.migration_counts[p['slug']],'127.0.0.1',self.pgport)
            code,_=self.admin_call('/api/tenants/'+rt.tenant_id(p))
            self.check(p['slug']+'_native_tenant_absent_before_create',code==404)
            code,value=self.admin_call('/api/tenants','POST',body)
            if code!=201:(self.work/'tenant-registration-error.json').write_text(json.dumps({'status':code,'body':value}))
            self.check(p['slug']+'_native_tenant_registered',code==201)
            self.install_gateway(p)
        time.sleep(.3)
    def connect(self,p,*,key=None,token=None,extra=None,direct=False,host=None):
        api_key=self.keys[p['slug']]['anon'] if key is None else key
        endpoint=self.rtport if direct else self.endpoints[p['slug']]['api']
        path='/socket/websocket' if direct else '/realtime/v1/websocket'
        url=f'ws://127.0.0.1:{endpoint}{path}?apikey={quote(api_key)}&vsn=1.0.0'
        hdr=dict(extra or {})
        if token is not None:hdr['Authorization']='Bearer '+token
        target_host=host or (self.native_ids[p['slug']]+'.realtime.internal' if direct else p['hostname'])
        sock=self.websocket.create_connection(url,timeout=8,host=target_host,header=hdr,suppress_origin=True,http_no_proxy=['127.0.0.1'])
        self.sockets.append(sock);self.frames[sock]=[];return sock
    def send(self,sock,event,payload,topic='realtime:same-room'):
        self.message_ref+=1;ref=str(self.message_ref)
        sock.send(json.dumps({'topic':topic,'event':event,'payload':payload,'ref':ref}));return ref
    def receive(self,sock,predicate,timeout=8,allow_timeout=False):
        queue=self.frames[sock]
        for i,frame in enumerate(queue):
            if predicate(frame):return queue.pop(i)
        deadline=time.monotonic()+timeout
        while time.monotonic()<deadline:
            sock.settimeout(max(.02,deadline-time.monotonic()))
            try:
                raw=sock.recv()
                if not raw:raise Failure('REALTIME_SOCKET_CLOSED')
                frame=json.loads(raw)
            except self.websocket.WebSocketTimeoutException:
                break
            if predicate(frame):return frame
            queue.append(frame)
        if allow_timeout:return None
        raise Failure('REALTIME_EXPECTED_FRAME_NOT_RECEIVED')
    def join(self,sock,p,*,token=None,postgres=False,room='same-room',private=True):
        payload={'config':{'broadcast':{'ack':True,'self':True},'presence':{'key':p['slug']},
            'postgres_changes':[{'event':'*','schema':'public','table':'notes'}] if postgres else [],'private':private},
            'access_token':self.sessions[p['slug']]['access_token'] if token is None else token}
        ref=self.send(sock,'phx_join',payload,'realtime:'+room)
        frame=self.receive(sock,lambda m:m.get('event')=='phx_reply' and m.get('ref')==ref,timeout=25)
        if frame.get('payload',{}).get('status')!='ok':
            (self.work/'last-join-error.json').write_text(json.dumps(frame))
        return frame
    def denied_handshake(self,p,**kwargs):
        try:
            sock=self.connect(p,**kwargs);sock.close();return False
        except self.websocket.WebSocketBadStatusException as exc:
            return exc.status_code in (400,401,403,404,421)
    def exercise_realtime(self):
        live={}
        for p in self.projects:
            sock=self.connect(p);frame=self.join(sock,p,postgres=True)
            # Upstream connection availability precedes async partition setup.
            # Reconcile that specific read-only startup condition, not an
            # arbitrary failed operation; repeat no write or provisioning call.
            if frame.get('payload',{}).get('response',{}).get('reason','').startswith('MissingPartition:'):
                deadline=time.monotonic()+10
                while time.monotonic()<deadline:
                    partitions=int(self.sql("SELECT count(*) FROM pg_inherits WHERE inhparent='realtime.messages'::regclass",db=p['database']).stdout)
                    if partitions>=3:break
                    time.sleep(.2)
                self.check(p['slug']+'_native_partition_startup_observed',partitions>=3)
                frame=self.join(sock,p,postgres=True)
            self.check(p['slug']+'_private_websocket_join',frame.get('payload',{}).get('status')=='ok')
            live[p['slug']]=sock
            # PostgreSQL Changes joins report their own asynchronous native verdict.
            system=self.receive(sock,lambda m:m.get('event')=='system' and m.get('payload',{}).get('extension')=='postgres_changes',timeout=25)
            if system.get('payload',{}).get('status')!='ok':(self.work/'cdc-start-error.json').write_text(json.dumps(system))
            self.check(p['slug']+'_native_postgres_changes_subscribed',system.get('payload',{}).get('status')=='ok')
        for p in self.projects:
            sock=live[p['slug']];other=next(q for q in self.projects if q!=p);alien=live[other['slug']]
            payload={'type':'broadcast','event':'client-isolation','payload':{'project':p['slug'],'nonce':secrets.token_hex(6)}}
            ref=self.send(sock,'broadcast',payload)
            message=self.receive(sock,lambda m:m.get('event')=='broadcast' and m.get('payload',{}).get('event')=='client-isolation')
            self.check(p['slug']+'_private_client_broadcast',message['payload']['payload']==payload['payload'])
            leaked=self.receive(alien,lambda m:m.get('event')=='broadcast' and m.get('payload',{}).get('event')=='client-isolation',timeout=.4,allow_timeout=True)
            self.check(p['slug']+'_same_room_other_project_no_broadcast',leaked is None)
            self.send(sock,'presence',{'type':'presence','event':'track','payload':{'project':p['slug']}})
            presence=self.receive(sock,lambda m:m.get('event')=='presence_diff' and bool(m.get('payload',{}).get('joins')),timeout=8)
            self.check(p['slug']+'_native_presence_track',p['slug'] in presence.get('payload',{}).get('joins',{}))
            leaked=self.receive(alien,lambda m:m.get('event')=='presence_diff' and p['slug'] in m.get('payload',{}).get('joins',{}),timeout=.3,allow_timeout=True)
            self.check(p['slug']+'_presence_stays_project_scoped',leaked is None)
            uid=self.users[p['slug']]
            self.sql("INSERT INTO public.notes VALUES (10,"+b.lit(uid)+"::uuid,"+b.lit(p['slug']+'-cdc')+");",db=p['database'])
            changed=self.receive(sock,lambda m:m.get('event')=='postgres_changes' and m.get('payload',{}).get('data',{}).get('record',{}).get('id')==10,timeout=12)
            self.check(p['slug']+'_real_insert_cdc_delivered',changed['payload']['data']['record']['body']==p['slug']+'-cdc')
            leaked=self.receive(alien,lambda m:m.get('event')=='postgres_changes' and m.get('payload',{}).get('data',{}).get('record',{}).get('body')==p['slug']+'-cdc',timeout=.4,allow_timeout=True)
            self.check(p['slug']+'_cdc_not_delivered_to_other_project',leaked is None)
            self.sql('INSERT INTO public.notes SELECT 11,owner_id,\'other-user-private-cdc\' FROM public.notes WHERE id=2;',db=p['database'])
            denied=self.receive(sock,lambda m:m.get('event')=='postgres_changes' and m.get('payload',{}).get('data',{}).get('record',{}).get('id')==11,timeout=.6,allow_timeout=True)
            self.check(p['slug']+'_cdc_rls_hides_other_user',denied is None)
            self.sql("SELECT realtime.send("+b.lit(json.dumps({'project':p['slug'],'source':'database'}))+"::jsonb,'database-origin','same-room',true);",db=p['database'])
            broadcast=self.receive(sock,lambda m:m.get('event')=='broadcast' and m.get('payload',{}).get('event')=='database-origin',timeout=10)
            self.check(p['slug']+'_database_triggered_broadcast',broadcast['payload']['payload'].get('project')==p['slug'])
            leaked=self.receive(alien,lambda m:m.get('event')=='broadcast' and m.get('payload',{}).get('event')=='database-origin',timeout=.3,allow_timeout=True)
            self.check(p['slug']+'_database_broadcast_no_cross_project',leaked is None)
        rows=self.sql("SELECT json_agg(json_build_object('slot',slot_name,'database',database,'plugin',plugin,'temporary',temporary)) FROM pg_replication_slots;").stdout.strip()
        slots=json.loads(rows);self.slot_evidence=slots
        self.check('four_distinct_native_replication_slots',len(slots)==4 and len({s['slot'] for s in slots})==4)
        for p in self.projects:
            mine=[s for s in slots if s['database']==p['database']]
            self.check(p['slug']+'_cdc_and_broadcast_slots_bound_to_database',len(mine)==2 and {s['plugin'] for s in mine}=={'wal2json','pgoutput'} and all(s['temporary'] for s in mine))
            expected=patch_realtime.expected_slot('realtime','messages',self.native_ids[p['slug']])
            self.check(p['slug']+'_patched_broadcast_slot_exact_tenant_scope',any(s['slot']==expected for s in mine))
        for p in self.projects:
            other=next(q for q in self.projects if q!=p)
            self.check(p['slug']+'_foreign_query_key_denied',self.denied_handshake(p,key=self.keys[other['slug']]['anon']))
            self.check(p['slug']+'_foreign_bearer_denied',self.denied_handshake(p,token=self.sessions[other['slug']]['access_token']))
            self.check(p['slug']+'_foreign_host_denied',self.denied_handshake(p,host=other['hostname']))
            self.check(p['slug']+'_unknown_native_tenant_denied',self.denied_handshake(p,direct=True,host='unknown.realtime.internal'))
            sock=self.connect(p,extra={'X-Tenant-ID':other['project_uuid'],'X-API-Key':self.keys[other['slug']]['service_role'],'X-Forwarded-Host':self.native_ids[other['slug']]+'.realtime.internal'})
            frame=self.join(sock,p)
            self.check(p['slug']+'_spoofed_headers_cannot_select_foreign_tenant',frame.get('payload',{}).get('status')=='ok');sock.close()
            sock=self.connect(p);frame=self.join(sock,p,token=self.sessions[other['slug']]['access_token'])
            self.check(p['slug']+'_foreign_join_token_denied',frame.get('payload',{}).get('status')=='error');sock.close()
            sock=self.connect(p);frame=self.join(sock,p,room='forbidden-room')
            self.check(p['slug']+'_private_channel_rls_denies_unlisted_room',frame.get('payload',{}).get('status')=='error');sock.close()
            sock=self.connect(p);frame=self.join(sock,p,private=False)
            self.check(p['slug']+'_public_channel_disabled',frame.get('payload',{}).get('status')=='error');sock.close()
            code,_=self.api(p,'/realtime/v1/api/tenants',bearer=self.rt_admin_token)
            self.check(p['slug']+'_gateway_cannot_access_management',code==404)
            code,_=self.admin_call('/api/tenants',token=self.keys[p['slug']]['service_role'])
            self.check(p['slug']+'_project_service_key_not_management_key',code in (401,403))
        code,_=self.admin_call('/api/tenants',token='')
        self.check('realtime_management_requires_separate_signed_token',code in (401,403))
        # Patched upstream's anti-collision tenant validation is tested, not inferred.
        body=rt.registration(self.projects[0],self.credentials[self.projects[0]['slug']],self.rt_shared,self.migration_counts[self.projects[0]['slug']],'127.0.0.1',self.pgport)
        for bad in ('some-victim-private','victim:room'):
            body['tenant']['external_id']=bad
            code,_=self.admin_call('/api/tenants','POST',body)
            self.check('native_invalid_tenant_namespace_rejected_'+bad,code in (400,422))
        for sock in self.sockets:
            try:sock.close()
            except Exception:pass
        self.sockets=[]
        self.stop('shared-realtime')
        deadline=time.monotonic()+5
        while time.monotonic()<deadline:
            if self.sql('SELECT count(*) FROM pg_replication_slots').stdout.strip()=='0':break
            time.sleep(.1)
        self.check('temporary_replication_slots_released_on_stop',self.sql('SELECT count(*) FROM pg_replication_slots').stdout.strip()=='0')
        self.start_realtime()
        for p in self.projects:
            sock=self.connect(p);frame=self.join(sock,p)
            self.check(p['slug']+'_private_channel_recovers_after_shared_restart',frame.get('payload',{}).get('status')=='ok')
            self.send(sock,'broadcast',{'type':'broadcast','event':'after-restart','payload':{'project':p['slug']}})
            response=self.receive(sock,lambda m:m.get('event')=='broadcast' and m.get('payload',{}).get('event')=='after-restart')
            self.check(p['slug']+'_broadcast_after_shared_restart',response['payload']['payload']['project']==p['slug'])
        self.check('legacy_fixture_unchanged_by_realtime',self.sql('SELECT value FROM public.sentinel',db='legacy_van').stdout.strip()=='unchanged-fixture' and self.sql("SELECT coalesce(datacl::text,'NULL') FROM pg_database WHERE datname='legacy_van'").stdout==self.legacy_acl)
    def exercise(self):
        super().exercise();self.setup_realtime();self.exercise_realtime()
    def cleanup(self):
        for sock in self.sockets:
            try:sock.close()
            except Exception:pass
        self.sockets=[]
        super().cleanup()
    def additional_evidence(self):
        return {'scope':'REAL_SHARED_REALTIME_TWO_DATABASE_REHEARSAL_NOT_PRODUCTION',
            'upstream_version':rt.VERSION,'upstream_source':rt.SOURCE_COMMIT,'derivative_patch':'TENANT_SCOPED_INTERNAL_BROADCAST_SLOT',
            'runtime_hashes':self.runtime_hashes,'slots':getattr(self,'slot_evidence',[]),'realtime_processes':1,'postgres_servers':1,
            'not_tested':['live VAN','Nissan GTR migration','complete production container/ARM64','Edge Functions','Studio','Supavisor','TLS/CORS/production throughput','coordinated physical disaster recovery']}

if __name__=='__main__':raise SystemExit(main(RealtimeRehearsal))
