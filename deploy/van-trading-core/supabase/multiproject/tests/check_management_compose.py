#!/usr/bin/env python3
"""Parse the complete one-installation candidate model, never start containers.

Core+Storage+Realtime+Edge+Supavisor+Studio/Meta project-admin gateway.
Uses synthetic credentials, original registry identity and placeholder unbuilt
control/Realtime image refs. This does not grant production deployment.
"""
import argparse
import hashlib
import json
import os
import pathlib
import re
import secrets
import subprocess
import sys
import tempfile
BASE=pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0,str(BASE/'tools'))
import bootstrap as b
import shared_storage as st
import shared_realtime as rt
import shared_edge as edge
import shared_pooler as pool
import shared_admin as admin


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--repo',type=pathlib.Path,required=True);p.add_argument('--donor-ref',required=True)
    p.add_argument('--upstream-schema',type=pathlib.Path,required=True);p.add_argument('--report',type=pathlib.Path,required=True)
    a=p.parse_args()
    if not re.fullmatch('[a-f0-9]{40}',a.donor_ref) or not a.report.is_absolute() or a.report.exists():raise ValueError('EXACT_SOURCE_NEW_REPORT_REQUIRED')
    projects=b.render.validate(json.loads((BASE/'projects.rehearsal.json').read_text()))
    core=b.bundle(projects,['127.0.0.1/32']);credentials={}
    for item in projects:
        c=json.loads(core[item['slug']+'.credentials.json']);credentials[item['project_uuid']]={k:c[k] for k in ('project_uuid','jwt_secret','anon_key','service_role_key')}
    ss=st.new_secrets(projects);storage=st.compile_bundle(projects,credentials,ss,['127.0.0.1/32'],object_bucket='original-bucket',object_path='/var/lib/storage',preserved_tenants={projects[0]['project_uuid']:'original-storage'})
    rs=rt.new_secrets(projects);rt_image='registry.invalid/dial/realtime-placeholder@sha256:'+'1'*64
    realtime=rt.compile_bundle(projects,credentials,rs,['127.0.0.1/32'],a.upstream_schema.read_text(),patched_image=rt_image,
        preserved_tenants={projects[0]['project_uuid']:'realtime-dev'},published_tables={x['project_uuid']:[('public','notes')] for x in projects},
        storage_gateways={x['project_uuid']:storage[x['slug']+'.nginx.conf'] for x in projects})
    es=edge.runtime_secrets(projects)
    edge_private={'credentials':credentials,'shared':es,
        'functions':{x['project_uuid']:[{'name':'identity','source':'Deno.serve(()=>Response.json({ok:true}));','auth':'user','env':{},'net_allow':[],'memory_mb':64,'timeout_ms':2000,'cpu_ms':250,'allow_service_role':False}] for x in projects},
        'api_endpoints':{x['project_uuid']:'http://tenant-'+x['slug']+'-api:8080' for x in projects},
        'allowed_origins':{x['project_uuid']:['https://'+x['hostname']] for x in projects},'worker_root':'/home/deno/private-workers'}
    functions=edge.compile_bundle(projects,edge_private,{x['project_uuid']:realtime[x['slug']+'.nginx.conf'] for x in projects})
    ps=pool.new_secrets(projects)
    pooler=pool.compile_bundle(projects,{'shared':ps,'registry_identity':{'host':'db','port':5432,'database':'_supabase','user':'supabase_admin'},
        'database_host':'db','database_port':5432,'client_cidrs':['127.0.0.1/32'],'enforce_ssl':True,
        'upstream_tls_ca':'-----BEGIN CERTIFICATE-----\nFIXTURE_NOT_A_TRUSTED_TLS_CERT\n-----END CERTIFICATE-----'})
    crypto=secrets.token_urlsafe(48)
    control=admin.compile_bundle(projects,{'passwords':{x['project_uuid']:ps['projects'][x['project_uuid']]['admin'] for x in projects},
        'origin':'https://admin.example.invalid','meta_url':'http://meta:8080','studio_url':'http://studio:3000',
        'crypto_key':crypto,'health_key':secrets.token_urlsafe(48),'issuer':'https://issuer.example.invalid','audience':'dial-project-admin',
        'public_jwk':{'kty':'OKP','crv':'Ed25519','x':'A'*43},
        'operators':[{'subject':'existing-operator-fixture','projects':[x['project_uuid'] for x in projects],'can_query':True}]})
    def original(path):return subprocess.check_output(['git','-C',str(a.repo),'show',a.donor_ref+':'+path],text=True,timeout=15)
    with tempfile.TemporaryDirectory(prefix='dial-full-model-') as td:
        w=pathlib.Path(td);donor=original('deploy/van-trading-core/supabase/docker-compose.yml');override=original('deploy/van-trading-core/supabase/docker-compose.override.yml')
        (w/'base.yml').write_text(donor);(w/'override.yml').write_text(override)
        settings={k:'fixture-value' for k in re.findall(r'\$\{([A-Z0-9_]+)',donor+override)}
        settings.update(POSTGRES_PORT='5432',POSTGRES_HOST='db',POSTGRES_DB='postgres',API_GW_HTTP_PORT='8000',POOLER_PROXY_PORT_TRANSACTION='6543',JWT_EXPIRY='3600',GLOBAL_S3_BUCKET='original-bucket',
            POSTGRES_PASSWORD=ps['registry_password'],VAULT_ENC_KEY=ps['vault_key'],SECRET_KEY_BASE=ps['secret_key_base'],PG_META_CRYPTO_KEY=crypto)
        (w/'donor.env').write_text(b.env_text(settings))
        (w/'rt.env').write_text(realtime['shared-realtime.env']);(w/'rt-compose.env').write_text(realtime['shared-realtime.compose.env'])
        (w/'storage.env').write_text(storage['shared-storage.env']);(w/'edge-compose.env').write_text(functions['shared-edge.compose.env'])
        (w/'pool.env').write_text(pooler['registry.env']);(w/'pool-compose.env').write_text(pooler['pooler.compose.env'])
        (w/'admin.env').write_text(control['admin.env'])
        admin_image='registry.invalid/dial/admin-placeholder@sha256:'+'2'*64
        (w/'admin-compose.env').write_text('DIAL_PROJECT_ADMIN_IMAGE='+admin_image+'\nDIAL_PROJECT_ADMIN_UID=1000\nDIAL_PROJECT_ADMIN_GID=1000\n')
        core_overlay=core['projects.api-auth.overlay.yml']
        for item in projects:
            for kind in ('auth','rest'):
                f=w/(item['slug']+'.'+kind+'.env');f.write_text(core[item['slug']+'.'+kind+'.env'])
                core_overlay=core_overlay.replace('/etc/dial-supabase/projects/'+item['slug']+'/'+kind+'.env',str(f))
        overlays={'core.yml':core_overlay,
            'storage.yml':storage['shared-storage.overlay.yml'].replace('/etc/dial-supabase/shared-storage/storage.env',str(w/'storage.env')),
            'realtime.yml':realtime['shared-realtime.overlay.yml'].replace('/etc/dial-supabase/shared-realtime/realtime.env',str(w/'rt.env')),
            'edge.yml':functions['shared-edge.overlay.yml'],
            'pool.yml':pooler['pooler.overlay.yml'].replace('/etc/dial-supabase/pooler/registry.env',str(w/'pool.env')),
            'admin.yml':control['project-admin.overlay.yml'].replace('/etc/dial-supabase/admin/admin.env',str(w/'admin.env'))}
        for name,text in overlays.items():(w/name).write_text(text)
        def config(files):
            command=['docker','compose','-p','dial-one-installation-model']
            for env in ('donor.env','rt-compose.env','edge-compose.env','pool-compose.env','admin-compose.env'):command+=['--env-file',str(w/env)]
            for file in files:command+=['-f',str(w/file)]
            result=subprocess.run(command+['config','--format','json'],capture_output=True,text=True,timeout=20)
            if result.returncode:raise ValueError('FULL_MODEL_PARSE_FAILED')
            return json.loads(result.stdout)
        old=config(['base.yml','override.yml'])['services'];new=config(['base.yml','override.yml',*overlays])['services']
        expected={'tenant-'+x['slug']+'-'+kind for x in projects for kind in ('auth','rest','api')}|{'project-admin'}
        gateway=lambda x:functions[x['slug']+'.nginx.conf']
        checks={
            'all_original_services_retained':set(old)<=set(new),
            'only_project_auth_rest_routers_and_one_admin_added':set(new)-set(old)==expected,
            'original_postgresql_unchanged':new['db']==old['db'],
            'original_studio_unchanged':new['studio']==old['studio'],
            'original_pg_meta_unchanged':new['meta']==old['meta'],
            'other_original_services_unchanged':all(new[k]==old[k] for k in old if k not in ('storage','realtime','functions','supavisor')),
            'one_storage_realtime_functions_pooler_service':all(sum(sub in s.get('image','') for s in new.values())==1 for sub in ('storage-api','/realtime','/edge-runtime','/supavisor')),
            'pooler_original_registry_url_preserved':new['supavisor']['environment']['DATABASE_URL']==old['supavisor']['environment']['DATABASE_URL'],
            'pooler_original_vault_key_preserved':new['supavisor']['environment']['VAULT_ENC_KEY']==old['supavisor']['environment']['VAULT_ENC_KEY'],
            'pooler_default_tenant_not_reseeded':'pooler.exs' not in ' '.join(new['supavisor']['command']),
            'pooler_original_port_bindings_preserved':new['supavisor'].get('ports')==old['supavisor'].get('ports'),
            'pooler_original_volumes_preserved':new['supavisor'].get('volumes')==old['supavisor'].get('volumes'),
            'meta_crypto_key_preserved_for_native_envelope':new['meta']['environment']['CRYPTO_KEY']==crypto,
            'new_admin_gateway_has_no_published_ports':not new['project-admin'].get('ports'),
            'studio_meta_original_port_bindings_preserved':all(new[k].get('ports')==old[k].get('ports') for k in ('studio','meta')),
            'studio_meta_original_bindings_remain_loopback':all(all(p.get('host_ip') in ('127.0.0.1','::1') for p in new[k].get('ports',[])) for k in ('studio','meta')),
            'shared_functions_storage_realtime_not_public':all(not new[k].get('ports') for k in ('functions','storage','realtime')),
            'edge_registry_hash_bound':new['functions']['environment']['DIAL_EDGE_REGISTRY_SHA256']==hashlib.sha256(functions['registry.json'].encode()).hexdigest(),
            'project_gateways_loopback_only':all(all(v.get('host_ip')=='127.0.0.1' for v in new['tenant-'+x['slug']+'-api']['ports']) for x in projects),
            'project_gateways_include_all_three_shared_routes':all('http://storage:5000/' in gateway(x) and '/socket/websocket' in gateway(x) and 'http://functions:9000/' in gateway(x) for x in projects),
            'admin_gateway_nonroot_readonly_candidate':new['project-admin'].get('user')=='1000:1000' and new['project-admin'].get('read_only') is True,
            'admin_gateway_source_image_not_claimed_built':new['project-admin']['image']==admin_image,
            'realtime_derivative_image_not_claimed_built':new['realtime']['image']==rt_image,
            'supavisor_and_edge_exact_tested_amd64_digests':new['supavisor']['image'].endswith(pool.AMD64_IMAGE) and new['functions']['image'].endswith(edge.AMD64_IMAGE_DIGEST),
            'new_component_limits_present':all(new[k].get('mem_limit') and new[k].get('pids_limit') for k in ('project-admin','supavisor','functions','realtime')),
            'existing_registry_compiler_creates_no_database':'CREATE DATABASE' not in '\n'.join(pooler.values()),
        }
        result={'state':'PASS' if all(checks.values()) else 'FAIL','check_count':len(checks),'checks':checks,'donor_ref':a.donor_ref,
            'service_count':len(new),'docker_daemon_used':False,'containers_started':False,'simultaneous_native_runtime_test':False,
            'production_deployed':False,'placeholder_images_unbuilt':True,'admin_port_bindings':{k:new[k].get('ports',[]) for k in ('project-admin','studio','meta')},
            'source_sha256':{str(f.relative_to(BASE)):hashlib.sha256(f.read_bytes()).hexdigest() for f in [BASE/'tools'/n for n in ('bootstrap.py','shared_storage.py','shared_realtime.py','shared_edge.py','shared_pooler.py','shared_admin.py')]+[pathlib.Path(__file__)]}}
        fd=os.open(a.report,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
        with os.fdopen(fd,'w') as f:f.write(json.dumps(result,sort_keys=True,indent=2)+'\n')
        print('FULL_COMPOSE_MODEL_'+result['state']+' '+str(len(checks)))
        if not all(checks.values()):print('FAILED_CHECKS '+','.join(k for k,v in checks.items() if not v))
        return 0 if all(checks.values()) else 1

if __name__=='__main__':raise SystemExit(main())
