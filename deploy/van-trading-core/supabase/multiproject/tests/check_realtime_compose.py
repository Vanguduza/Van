#!/usr/bin/env python3
"""Effective one-installation model: core + shared Storage + patched Realtime.

Runs Docker Compose's parser only; no daemon, build, container, VM or real
credential access. The derivative image is an explicitly invalid fixture ref.
"""
import argparse
import hashlib
import json
import os
import pathlib
import re
import subprocess
import sys
import tempfile
BASE=pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0,str(BASE/'tools'))
import bootstrap as b
import shared_storage as st
import shared_realtime as rt



def mem_bytes(value):
    # Compose JSON can preserve a size expression, e.g. 384m, rather than
    # exposing an integer. Compare the actual effective bytes, not Python types.
    if type(value) is int:return value
    if not isinstance(value,str):return 0
    match=re.fullmatch(r'([1-9][0-9]*)([kmg]?)',value.lower())
    if not match:return 0
    return int(match.group(1))*{'':1,'k':1024,'m':1024**2,'g':1024**3}[match.group(2)]

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo',type=pathlib.Path,required=True)
    parser.add_argument('--donor-ref',required=True)
    parser.add_argument('--upstream-schema',type=pathlib.Path,required=True)
    parser.add_argument('--report',type=pathlib.Path,required=True)
    a=parser.parse_args()
    if not re.fullmatch('[a-f0-9]{40}',a.donor_ref) or not a.report.is_absolute() or a.report.exists():raise ValueError('IMMUTABLE_DONOR_AND_NEW_REPORT_REQUIRED')
    ps=b.render.validate(json.loads((BASE/'projects.rehearsal.json').read_text()))
    def original(path):return subprocess.check_output(['git','-C',str(a.repo),'show',a.donor_ref+':'+path],text=True,timeout=15)
    core=b.bundle(ps,['127.0.0.1/32']);credentials={}
    for p in ps:
        c=json.loads(core[p['slug']+'.credentials.json'])
        credentials[p['project_uuid']]={k:c[k] for k in ('project_uuid','jwt_secret','anon_key','service_role_key')}
    storage_secrets=st.new_secrets(ps);realtime_secrets=rt.new_secrets(ps)
    storage=st.compile_bundle(ps,credentials,storage_secrets,['127.0.0.1/32'],object_bucket='original-bucket',object_path='/var/lib/storage',preserved_tenants={ps[0]['project_uuid']:'original-storage'})
    fake_image='registry.invalid/dial/realtime-tested-placeholder@sha256:'+'1'*64
    realtime=rt.compile_bundle(ps,credentials,realtime_secrets,['127.0.0.1/32'],a.upstream_schema.read_text(),patched_image=fake_image,
        preserved_tenants={ps[0]['project_uuid']:'realtime-dev'},published_tables={p['project_uuid']:[('public','notes')] for p in ps},
        storage_gateways={p['project_uuid']:storage[p['slug']+'.nginx.conf'] for p in ps})
    with tempfile.TemporaryDirectory(prefix='dial-combined-compose-') as td:
        w=pathlib.Path(td)
        donor=original('deploy/van-trading-core/supabase/docker-compose.yml');override=original('deploy/van-trading-core/supabase/docker-compose.override.yml')
        (w/'base.yml').write_text(donor);(w/'override.yml').write_text(override)
        settings={k:'fixture-value' for k in re.findall(r'\$\{([A-Z0-9_]+)',donor+override)}
        settings.update(POSTGRES_PORT='5432',POSTGRES_HOST='db',POSTGRES_DB='postgres',API_GW_HTTP_PORT='8000',POOLER_PROXY_PORT_TRANSACTION='6543',JWT_EXPIRY='3600',GLOBAL_S3_BUCKET='original-bucket')
        (w/'donor.env').write_text(''.join(k+'='+v+'\n' for k,v in settings.items()))
        (w/'rt-compose.env').write_text(realtime['shared-realtime.compose.env'])
        (w/'rt.env').write_text(realtime['shared-realtime.env']);(w/'storage.env').write_text(storage['shared-storage.env'])
        core_overlay=core['projects.api-auth.overlay.yml']
        for p in ps:
            for kind in ('auth','rest'):
                private=w/(p['slug']+'.'+kind+'.env');private.write_text(core[p['slug']+'.'+kind+'.env'])
                core_overlay=core_overlay.replace('/etc/dial-supabase/projects/'+p['slug']+'/'+kind+'.env',str(private))
        (w/'core.yml').write_text(core_overlay)
        (w/'storage.yml').write_text(storage['shared-storage.overlay.yml'].replace('/etc/dial-supabase/shared-storage/storage.env',str(w/'storage.env')))
        (w/'rt.yml').write_text(realtime['shared-realtime.overlay.yml'].replace('/etc/dial-supabase/shared-realtime/realtime.env',str(w/'rt.env')))
        def config(files):
            argv=['docker','compose','-p','dial-combined-config-test','--env-file',str(w/'donor.env'),'--env-file',str(w/'rt-compose.env')]
            for f in files:argv+=['-f',str(w/f)]
            r=subprocess.run(argv+['config','--format','json'],capture_output=True,text=True,timeout=20)
            if r.returncode:raise RuntimeError('COMBINED_COMPOSE_CONFIG_FAILED')
            return json.loads(r.stdout)
        old=config(['base.yml','override.yml']);new=config(['base.yml','override.yml','core.yml','storage.yml','rt.yml'])
        services=new['services'];env=services['realtime']['environment'];before=old['services']
        added={'tenant-'+p['slug']+'-'+suffix for p in ps for suffix in ('auth','rest','api')}
        checks={
          'only_expected_project_auth_rest_router_services_added':set(services)-set(before)==added,
          'all_existing_services_retained':set(before)<=set(services),
          'postgres_service_unchanged':services['db']==before['db'],
          'every_other_original_service_unchanged':all(services[k]==before[k] for k in before if k not in ('storage','realtime')),
          'single_storage_and_realtime_service':sum('storage-api' in s.get('image','') for s in services.values())==1 and sum('realtime' in s.get('image','') for s in services.values())==1,
          'storage_mount_preserved':services['storage'].get('volumes')==before['storage'].get('volumes'),
          'shared_services_have_no_published_ports':not services['storage'].get('ports') and not services['realtime'].get('ports'),
          'realtime_selected_derivative_image':services['realtime']['image']==fake_image,
          'realtime_does_not_reseed':env['SEED_SELF_HOST']=='false',
          'realtime_registry_login_not_donor_admin':env['DB_USER']==rt.CONTROL_ROLE and env['DB_NAME']==rt.CONTROL_DB,
          'realtime_registry_password_precedence_correct':env['DB_PASSWORD']==realtime_secrets['control_password'],
          'management_jwt_not_legacy_donor_jwt':env['API_JWT_SECRET']==realtime_secrets['admin_jwt_secret'] and env['API_JWT_SECRET']!=settings['JWT_SECRET'],
          'metrics_secret_independent':env['METRICS_JWT_SECRET']!=env['API_JWT_SECRET'],
          'native_partition_maintenance_enabled':env['RUN_JANITOR']=='true',
          'realtime_resource_limits_present':mem_bytes(services['realtime'].get('mem_limit'))>=384*1024*1024 and services['realtime'].get('pids_limit')==128,
          'project_gateways_loopback_only':all(all(item.get('host_ip')=='127.0.0.1' for item in services['tenant-'+p['slug']+'-api']['ports']) for p in ps),
          'compiled_gateways_keep_storage_and_websocket':all('http://storage:5000/' in realtime[p['slug']+'.nginx.conf'] and '/socket/websocket' in realtime[p['slug']+'.nginx.conf'] for p in ps),
          'compiled_hba_preserves_storage_logins':all(st.role(p) in realtime['realtime-projects.hba-prefix.conf'] for p in ps)}
        report={'state':'PASS' if all(checks.values()) else 'FAIL','check_count':len(checks),'checks':checks,
            'donor_ref':a.donor_ref,'service_count':len(services),'containers_started':False,'docker_daemon_used':False,
            'derivative_image_placeholder_only':True,'production_image_built':False,
            'compose_version':subprocess.check_output(['docker','compose','version'],text=True,timeout=10).strip(),
            'source_sha256':{str(p.relative_to(BASE)):hashlib.sha256(p.read_bytes()).hexdigest() for p in (BASE/'tools/shared_realtime.py',BASE/'tools/shared_storage.py',pathlib.Path(__file__))}}
        fd=os.open(a.report,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
        with os.fdopen(fd,'w') as f:f.write(json.dumps(report,indent=2,sort_keys=True)+'\n')
        print('COMBINED_COMPOSE_MODEL_'+report['state']+' '+str(len(checks)))
        return 0 if all(checks.values()) else 1

if __name__=='__main__':raise SystemExit(main())
