#!/usr/bin/env python3
"""Combined real Auth/REST/shared Storage/shared Realtime on ONE temporary PG.

The native standalone proofs remain separate. This adds same-gateway and
same-database integration evidence without production connections or effects.
"""
import hashlib
import pathlib
from rehearse_native import BASE,main,Failure
from rehearse_storage import StorageRehearsal
from rehearse_realtime import RealtimeRehearsal
import shared_storage as st
import shared_realtime as rt


class SharedFabricRehearsal(RealtimeRehearsal,StorageRehearsal):
    with_storage=True
    def __init__(self,args):
        super().__init__(args)
        self.source_hashes[str(pathlib.Path(__file__).relative_to(BASE))]=hashlib.sha256(pathlib.Path(__file__).read_bytes()).hexdigest()
    def install_gateway(self,p):
        # The existing Storage route stays enabled while adding only Realtime.
        self.stop(p['slug']+'-nginx')
        txt=st.gateway(p,self.keys[p['slug']]['anon'],self.keys[p['slug']]['service_role'],
            f'127.0.0.1:{self.storage_port}',preserved_tenant_id=self.native_tenants[p['slug']])
        txt=rt.gateway(p,self.keys[p['slug']]['anon'],self.keys[p['slug']]['service_role'],
            f'127.0.0.1:{self.rtport}',base_config=txt,preserved_tenant_id=self.native_ids[p['slug']])
        ep=self.endpoints[p['slug']]
        txt=txt.replace('listen 8080','listen 127.0.0.1:'+str(ep['api']))
        for kind,pn in [('auth',9999),('rest',3000)]:
            txt=txt.replace('tenant-'+p['slug']+'-'+kind+':'+str(pn),'127.0.0.1:'+str(ep[kind]))
        cfg=self.work/(p['slug']+'-nginx.conf');buffers=self.work/(p['slug']+'-buffers')
        temp='\n'.join(k+'_temp_path '+str(buffers/k)+';' for k in ('client_body','proxy','fastcgi','uwsgi','scgi'))
        cfg.write_text('\n'.join(['daemon off;','master_process off;','pid '+str(self.work/(p['slug']+'.pid'))+';',
            'error_log '+str(self.work/(p['slug']+'-nginx-error.log'))+';',
            'events { worker_connections 128; }','http { access_log off;',temp,txt,'}']))
        checked=self.run([self.args.nginx,'-t','-p',str(self.work)+'/', '-c',cfg])
        if checked.returncode:(self.work/'combined-gateway-error.txt').write_text(checked.stderr)
        self.check(p['slug']+'_combined_storage_realtime_gateway_valid',checked.returncode==0)
        child=self.spawn([self.args.nginx,'-p',str(self.work)+'/', '-c',cfg],{},p['slug']+'-nginx')
        self.wait_http(child,ep['api'],'/rest/v1/notes',{'Host':p['hostname'],'apikey':self.keys[p['slug']]['service_role']})
    def exercise(self):
        # MRO runs Core -> Storage -> Realtime once each, on one fixture.
        super().exercise()
        for p in self.projects:
            code,body,_=self.storage(p,'/object/authenticated/private-fixture/same.txt')
            self.check(p['slug']+'_storage_still_works_with_realtime_active',code==200 and body==self.payloads[p['slug']])
            code,body,_=self.storage(p,self.signed[p['slug']],anonymous=True)
            self.check(p['slug']+'_signed_storage_download_after_realtime_restart',code==200 and body==self.payloads[p['slug']])
            other=next(q for q in self.projects if q!=p)
            denied=self.sql('SELECT 1',db=other['database'],role=st.role(p),password=self.shared['projects'][st.tenant_id(p)],tcp=True,fail_ok=True)
            self.check(p['slug']+'_storage_hba_boundary_survives_realtime_prefix',denied.returncode!=0 and 'pg_hba.conf rejects' in denied.stderr)
            code,rows=self.api(p,'/rest/v1/notes?select=body&order=id',bearer=self.sessions[p['slug']]['access_token'])
            self.check(p['slug']+'_rest_rls_survives_shared_service_integration',code==200 and all(row['body']!='other-user-private-cdc' for row in rows))
        self.check('one_shared_storage_and_one_shared_realtime_alive',
            self.process_by_label['shared-storage'].poll() is None and self.process_by_label['shared-realtime'].poll() is None)
    def additional_evidence(self):
        value=StorageRehearsal.additional_evidence(self)
        realtime=RealtimeRehearsal.additional_evidence(self)
        value.update(realtime)
        value['scope']='ONE_POSTGRES_AUTH_REST_SHARED_STORAGE_REALTIME_INTEGRATION_NOT_PRODUCTION'
        value['realtime_registry_separate_from_storage_registry']=rt.CONTROL_DB!=st.CONTROL_DB
        value['not_tested']=['live VAN','Nissan GTR migration','production container/ARM64','Edge Functions','Studio','Supavisor','TLS/CORS','coordinated production database/object disaster recovery','production credential rotation']
        return value

if __name__=='__main__':raise SystemExit(main(SharedFabricRehearsal))
