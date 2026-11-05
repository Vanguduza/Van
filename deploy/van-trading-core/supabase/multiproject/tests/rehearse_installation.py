#!/usr/bin/env python3
"""All native services concurrently on ONE new private PostgreSQL fixture.

No production endpoint, authority, network change or budget increase is accepted.
Includes real original Studio HTTP/Meta, not a browser-render/load qualification.
Independent component runs remain separate evidence, never summed as acceptance.
"""
from __future__ import annotations
import concurrent.futures
import hashlib
import json
import os
import pathlib
import signal
import threading
import time
from rehearse_native import BASE,Rehearsal,Failure,main,request
from rehearse_edge import EdgeRehearsal
from rehearse_admin import AdminRehearsal
from rehearse_pooler import PoolerRehearsal
from rehearse_storage import StorageRehearsal
from rehearse_realtime import RealtimeRehearsal
from rehearse_shared_fabric import SharedFabricRehearsal
import bootstrap as b
import shared_storage as st
import shared_realtime as rt
import shared_edge as edge
import shared_pooler as pool

CROSS_SERVICE = r'''Deno.serve(async req=>{
  const input=await req.json();
  if(!Number.isInteger(input.id)||input.id<800000||input.id>900000||typeof input.label!=='string'||!/^[a-z0-9-]+$/.test(input.label))return new Response('bad fixture',{status:400});
  const auth=req.headers.get('authorization');
  const encoded=auth.slice(7).split('.')[1];
  const user=JSON.parse(atob(encoded.replaceAll('-','+').replaceAll('_','/'))).sub;
  const base=Deno.env.get('SUPABASE_URL');
  const key=Deno.env.get('SUPABASE_ANON_KEY');
  const headers={Authorization:auth,apikey:key,'Content-Type':'application/json'};
  const row=await fetch(base+'/rest/v1/notes',{method:'POST',headers,
    body:JSON.stringify({id:input.id,owner_id:user,body:input.label})});
  if(row.status!==201)return Response.json({stage:'database',status:row.status},{status:502});
  const name='flow-'+input.id+'.txt';
  const object=await fetch(base+'/storage/v1/object/private-fixture/'+name,{method:'POST',
    headers:{Authorization:auth,apikey:key,'Content-Type':'text/plain'},body:input.label});
  if(!object.ok)return Response.json({stage:'storage',database_effect:true,status:object.status},{status:502});
  return Response.json({project:Deno.env.get('DIAL_PROJECT_ID'),id:input.id,object:name,written:true});
});'''


def read_budget():
    line=next(x for x in pathlib.Path('/proc/self/cgroup').read_text().splitlines() if x.startswith('0::'))
    group=pathlib.Path('/sys/fs/cgroup')/line[3:].lstrip('/')
    candidates=[]
    for path in [group,*group.parents]:
        cap=path/'memory.max'
        if cap.exists() and cap.read_text().strip().isdigit():
            candidates.append((int(cap.read_text()),path))
    if not candidates:raise Failure('FINITE_EXISTING_CGROUP_BUDGET_REQUIRED')
    limit,path=min(candidates,key=lambda x:x[0])
    return limit,path


class InstallationRehearsal(EdgeRehearsal,AdminRehearsal,SharedFabricRehearsal):
    def __init__(self,args):
        super().__init__(args)
        self.source_hashes[str(pathlib.Path(__file__).relative_to(BASE))]=hashlib.sha256(pathlib.Path(__file__).read_bytes()).hexdigest()
        self.budget_limit,self.budget_path=read_budget()
        self.monitor_stop=threading.Event();self.memory_record={'limit_bytes':self.budget_limit,'budget_changed':False,'peak_current_bytes':0,'peak_anon_kernel_bytes':0,'sample_count':0,'guard_tripped':False}
        self.monitor=None;self.old_handler=None;self.phase='not_started';self.phase_observations=[]
        self.coexistence=[];self.workflow_receipts=[]
        self.initial_memory_events=self.events()
    def events(self):
        return {k:int(v) for k,v in (line.split() for line in (self.budget_path/'memory.events').read_text().splitlines())}
    def budget_sample(self):
        current=int((self.budget_path/'memory.current').read_text())
        stat={k:int(v) for k,v in (x.split() for x in (self.budget_path/'memory.stat').read_text().splitlines())}
        working=stat.get('anon',0)+stat.get('kernel',0)+stat.get('shmem',0)
        self.memory_record['peak_current_bytes']=max(current,self.memory_record['peak_current_bytes'])
        self.memory_record['peak_anon_kernel_bytes']=max(working,self.memory_record['peak_anon_kernel_bytes'])
        self.memory_record['sample_count']+=1
        return current,working
    def begin_monitor(self):
        current,working=self.budget_sample()
        if working>self.budget_limit-160*1024*1024:raise Failure('INSUFFICIENT_EXISTING_NONRECLAIMABLE_HEADROOM')
        self.old_handler=signal.getsignal(signal.SIGUSR1)
        def trip(sig,frame):raise Failure('EXISTING_MEMORY_BUDGET_GUARD_ABORT_'+self.phase)
        signal.signal(signal.SIGUSR1,trip)
        def watch():
            while not self.monitor_stop.wait(.1):
                try:
                    current,working=self.budget_sample()
                    if working>self.budget_limit-64*1024*1024:
                        self.memory_record['guard_tripped']=True
                        os.kill(os.getpid(),signal.SIGUSR1);return
                except OSError:
                    self.memory_record['guard_tripped']=True
                    os.kill(os.getpid(),signal.SIGUSR1);return
        self.monitor=threading.Thread(target=watch,daemon=True);self.monitor.start()
    def setup(self):
        self.begin_monitor();self.phase='core_setup'
        super().setup()
    def checkpoint(self,name):
        self.phase=name
        current,working=self.budget_sample()
        self.phase_observations.append({'phase':name,'current_bytes':current,'anon_kernel_bytes':working})
        self.check('phase_'+name+'_within_existing_budget',not self.memory_record['guard_tripped'])
    def install_edge_gateway(self,p):
        self.stop_edge_label(p['slug']+'-nginx')
        txt=st.gateway(p,self.keys[p['slug']]['anon'],self.keys[p['slug']]['service_role'],
            f'127.0.0.1:{self.storage_port}',preserved_tenant_id=self.native_tenants[p['slug']]) if 'shared-storage' in self.process_by_label else None
        if txt is not None and 'shared-realtime' in self.process_by_label:
            txt=rt.gateway(p,self.keys[p['slug']]['anon'],self.keys[p['slug']]['service_role'],
                f'127.0.0.1:{self.rtport}',base_config=txt,preserved_tenant_id=self.native_ids[p['slug']])
        txt=edge.gateway(p,self.edge_credentials[p['project_uuid']],self.edge_shared['gateway_keys'][p['project_uuid']],
            self.edge_api[p['project_uuid']],base_config=txt,upstream=f'127.0.0.1:{self.edgeport}')
        self.launch_edge_gateway(p,txt)
    def install_gateway(self,p):
        # Realtime integration must preserve both the Storage and Edge routes.
        self.install_edge_gateway(p)
    def extend_edge_workflow(self):
        self.stop_edge_label('shared-edge-runtime')
        for p in self.projects:
            self.edge_private['functions'][p['project_uuid']].append(self.descriptor('cross-service',CROSS_SERVICE,timeout=8000,cpu=1000))
        self.edge_config=edge.registry(self.projects,**self.edge_private)
        self.edge_registry.write_text(edge.canonical(self.edge_config)+'\n');self.edge_registry.chmod(0o600)
        self.edge_config_hash=hashlib.sha256(self.edge_registry.read_bytes()).hexdigest()
        self.start_edge()
    def live_labels(self):
        return ['shared-storage','shared-realtime','shared-edge-runtime','shared-pooler','shared-meta','shared-studio','shared-project-admin']+[
            p['slug']+'-'+kind for p in self.projects for kind in ('auth','rest','nginx')]
    def assert_all_alive(self,stage):
        snapshot={label:self.process_by_label[label].pid for label in self.live_labels() if label in self.process_by_label and self.process_by_label[label].poll() is None}
        self.check(stage+'_all_13_service_processes_alive',set(snapshot)==set(self.live_labels()))
        self.check(stage+'_same_one_postgres_server',self.sql('SELECT current_setting(\'data_directory\')').stdout.strip()==str(self.data))
        self.coexistence.append({'stage':stage,'service_pids':snapshot,'one_postgres':True})
        return snapshot
    def cross_service(self,p,number):
        slug=p['slug'];uid=p['project_uuid'];other=next(q for q in self.projects if q!=p)
        sock=self.connect(p);frame=self.join(sock,p,postgres=True)
        self.check(slug+'_end_to_end_join',frame.get('payload',{}).get('status')=='ok')
        system=self.receive(sock,lambda m:m.get('event')=='system' and m.get('payload',{}).get('extension')=='postgres_changes',timeout=25)
        self.check(slug+'_end_to_end_subscription_ready',system.get('payload',{}).get('status')=='ok')
        label='one-installation-'+slug
        code,result=self.invoke(p,'cross-service',method='POST',body={'id':number,'label':label})
        self.check(slug+'_edge_writes_db_and_storage_via_own_api',code==200 and result.get('written') and result.get('project')==uid)
        event=self.receive(sock,lambda m:m.get('event')=='postgres_changes' and m.get('payload',{}).get('data',{}).get('record',{}).get('id')==number,timeout=25)
        self.check(slug+'_realtime_observes_edge_database_write',event['payload']['data']['record']['body']==label)
        code,content,_=self.storage(p,'/object/authenticated/private-fixture/'+result['object'])
        self.check(slug+'_storage_returns_edge_written_bytes',code==200 and content==label.encode())
        code,_,_=self.storage(other,'/object/authenticated/private-fixture/'+result['object'],bearer=self.sessions[slug]['access_token'])
        self.check(slug+'_edge_created_object_foreign_project_denied',code in (400,401,403,404))
        # Dedicated backend/operator roles do not inherit authenticated-user
        # RLS. Grant a fixture-only read policy for the exact enrolled user;
        # do not bypass RLS or turn a project login into a superuser.
        for kind in ('pool','admin'):
            login=pool.role(p,kind)
            self.sql('GRANT SELECT ON public.notes TO '+b.ident(login)+'; CREATE POLICY '+b.ident('fixture_flow_'+kind)+' ON public.notes FOR SELECT TO '+b.ident(login)+' USING(owner_id='+b.lit(self.users[slug])+'::uuid);',db=p['database'])
        observed=self.pooled(p,'SELECT body FROM public.notes WHERE id='+str(number)+';')
        self.check(slug+'_pooler_reads_same_project_edge_write',observed.stdout.strip()==label)
        self.check(slug+'_pooled_backend_rls_still_hides_other_user',self.pooled(p,'SELECT count(*) FROM public.notes WHERE owner_id<>'+b.lit(self.users[slug])+'::uuid;').stdout.strip()=='0')
        code,rows,_=self.admin_http('/api/platform/pg-meta/'+uid+'/query','POST',{'query':'SELECT body FROM public.notes WHERE id='+str(number)})
        self.check(slug+'_meta_admin_reads_same_project_edge_write',code==200 and rows==[{'body':label}])
        code,rows,_=self.admin_http('/api/platform/pg-meta/'+uid+'/query','POST',{'query':'SELECT count(*)::int AS n FROM public.notes WHERE owner_id<>'+b.lit(self.users[slug])+'::uuid'})
        self.check(slug+'_meta_fixture_policy_retains_row_boundary',code==200 and rows==[{'n':0}])
        code,_,html=self.admin_http('/project/'+uid+'/editor')
        self.check(slug+'_original_studio_http_available_during_data_flow',code==200 and b'__next' in html.lower())
        if p==self.projects[0]:
            code,_,_=self.admin_http('/api/platform/pg-meta/'+other['project_uuid']+'/query','POST',{'query':'SELECT 1'},token=self.tokens['one-project'])
            self.check('one_project_operator_cannot_change_full_flow_target',code==404)
        sock.close()
        self.workflow_receipts.append({'project':uid,'edge_to_rest':True,'database_to_realtime':True,'edge_to_storage':True,'pooler_same_row':True,'meta_same_row':True,'original_studio_http':True,'no_mutation_replay':True})
    def coexistence_rounds(self):
        for round_number in range(3):
            before=self.assert_all_alive('round_'+str(round_number)+'_before')
            jobs=[]
            for p in self.projects:
                jobs += [(p,'edge'),(p,'storage'),(p,'pool'),(p,'meta'),(p,'rest'),(p,'studio')]
            def probe(job):
                p,kind=job;uid=p['project_uuid']
                if kind=='edge':
                    code,val=self.invoke(p,'identity');return code==200 and val.get('project')==uid
                if kind=='storage':
                    code,data,_=self.storage(p,'/object/authenticated/private-fixture/same.txt');return code==200 and data==self.payloads[p['slug']]
                if kind=='pool':return self.pooled(p,'SELECT current_database()').stdout.strip()==p['database']
                if kind=='meta':
                    code,val,_=self.admin_http('/api/platform/pg-meta/'+uid+'/query','POST',{'query':'SELECT current_database() AS db'});return code==200 and val==[{'db':p['database']}]
                if kind=='studio':return self.admin_http('/project/'+uid+'/editor')[0]==200
                code,rows=self.api(p,'/rest/v1/notes?select=body',bearer=self.sessions[p['slug']]['access_token']);return code==200 and all(x['body']!='other-user-private-cdc' for x in rows)
            with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
                answers=list(executor.map(probe,jobs))
            self.check('concurrent_six_paths_both_projects_round_'+str(round_number),all(answers))
            for p in self.projects:
                sock=self.connect(p);self.check(p['slug']+'_private_channel_remains_live_round_'+str(round_number),self.join(sock,p).get('payload',{}).get('status')=='ok');sock.close()
            after=self.assert_all_alive('round_'+str(round_number)+'_after')
            self.check('no_service_substituted_or_stopped_round_'+str(round_number),before==after)
    def shared_failure_boundaries(self):
        for label,restart in [('shared-edge-runtime',self.start_edge),('shared-pooler',self.start_pooler)]:
            before=self.assert_all_alive(label+'_before_failure')
            self.stop_edge_label(label)
            self.check(label+'_original_process_stopped',self.process_by_label[label].poll() is not None)
            for p in self.projects:
                code,data,_=self.storage(p,'/object/authenticated/private-fixture/same.txt')
                self.check(p['slug']+'_storage_available_during_'+label+'_outage',code==200 and data==self.payloads[p['slug']])
                code,rows=self.api(p,'/rest/v1/notes?select=id',bearer=self.sessions[p['slug']]['access_token'])
                self.check(p['slug']+'_rest_available_during_'+label+'_outage',code==200 and bool(rows))
                code,rows,_=self.admin_http('/api/platform/pg-meta/'+p['project_uuid']+'/query','POST',{'query':'SELECT current_database() AS db'})
                self.check(p['slug']+'_meta_available_during_'+label+'_outage',code==200 and rows==[{'db':p['database']}])
                sock=self.connect(p);joined=self.join(sock,p);sock.close()
                self.check(p['slug']+'_private_realtime_available_during_'+label+'_outage',joined.get('payload',{}).get('status')=='ok')
                if label=='shared-edge-runtime':
                    code,_=self.invoke(p,'identity')
                    self.check(p['slug']+'_edge_unavailable_not_rerouted',code in (502,503))
                    self.check(p['slug']+'_pool_available_during_edge_outage',self.pooled(p,'SELECT current_database()').stdout.strip()==p['database'])
                else:
                    denied=self.pooled(p,'SELECT 1',fail_ok=True)
                    self.check(p['slug']+'_pool_outage_not_rerouted',denied.returncode!=0)
                    code,result=self.invoke(p,'identity')
                    self.check(p['slug']+'_edge_available_during_pool_outage',code==200 and result.get('project')==p['project_uuid'])
            restart()
            after=self.assert_all_alive(label+'_after_restart')
            self.check(label+'_only_original_service_pid_replaced',before[label]!=after[label] and all(before[k]==after[k] for k in before if k!=label))
            for p in self.projects:
                code,result=self.invoke(p,'identity')
                self.check(p['slug']+'_edge_scoped_after_'+label+'_restart',code==200 and result.get('project')==p['project_uuid'])
                self.check(p['slug']+'_pooled_database_after_'+label+'_restart',self.pooled(p,'SELECT current_database()').stdout.strip()==p['database'])

    def exercise(self):
        Rehearsal.exercise(self)
        self.checkpoint('pooling')
        self.setup_pooler();self.exercise_pooler()
        # Preserve the pool/admin first-match rules when later shared-service
        # prefixes are installed, rather than silently reverting to base HBA.
        self.original_hba_suffix=(self.data/'pg_hba.conf').read_text()
        self.checkpoint('edge')
        self.setup_edge();self.exercise_edge()
        self.checkpoint('storage')
        self.setup_storage();self.exercise_storage()
        self.exercise_object_ownership_and_mutations();self.exercise_object_restore()
        self.checkpoint('realtime')
        self.setup_realtime();self.exercise_realtime()
        self.checkpoint('management')
        self.setup_admin();self.exercise_admin()
        for p in self.projects:
            self.sql('GRANT SELECT ON public.notes TO '+b.ident(pool.role(p,'admin'))+';',db=p['database'])
        self.extend_edge_workflow()
        self.checkpoint('all_services_live')
        self.assert_all_alive('full_installation')
        for i,p in enumerate(self.projects):self.cross_service(p,810000+i)
        self.coexistence_rounds()
        self.shared_failure_boundaries()
        self.check('legacy_database_unchanged_after_complete_integration',self.sql('SELECT value FROM public.sentinel',db='legacy_van').stdout.strip()=='unchanged-fixture')
        self.check('existing_cgroup_limit_unchanged',int((self.budget_path/'memory.max').read_text())==self.budget_limit)
        self.check('no_oom_event_during_complete_integration',all(self.events().get(k,0)==self.initial_memory_events.get(k,0) for k in ('oom','oom_kill')))
    def cleanup(self):
        self.monitor_stop.set()
        if self.monitor:self.monitor.join(timeout=2)
        if self.old_handler is not None:signal.signal(signal.SIGUSR1,self.old_handler)
        super().cleanup()
    def additional_evidence(self):
        # Keep each upstream identity in its own namespace. Combining generic
        # fields would misattribute Realtime's version to Supavisor's source.
        component_records={}
        for name,klass in [('storage',StorageRehearsal),('realtime',RealtimeRehearsal),('edge',EdgeRehearsal),('pooler',PoolerRehearsal)]:
            component_records[name]={k:v for k,v in klass.additional_evidence(self).items() if k not in ('scope','not_tested')}
        from shared_admin import META_SOURCE,STUDIO_IMAGE
        component_records['administration']={'meta_source':META_SOURCE,'studio_image':STUDIO_IMAGE,'observations':self.admin_record}
        return {'scope':'ONE_POSTGRES_ALL_SHARED_SERVICES_SIMULTANEOUS_NATIVE_HTTP_NO_BROWSER_NOT_PRODUCTION',
            'components':component_records,'all_service_observations':self.coexistence,'workflows':self.workflow_receipts,
            'memory_observation':self.memory_record,'phase_observations':self.phase_observations,
            'full_browser_interaction':False,'original_studio_http_only':True,
            'not_tested':['live VAN','target container/ARM64','production load or soak','real operator issuer/login/revocation','all-services simultaneous browser rendering','coordinated off-host recovery','Nissan GTR migration']}


if __name__=='__main__':raise SystemExit(main(InstallationRehearsal))
