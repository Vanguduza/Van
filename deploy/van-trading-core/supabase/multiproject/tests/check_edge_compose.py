#!/usr/bin/env python3
"""Read-only Docker Compose model test for one shared Edge Runtime.

Does not contact the Docker daemon or create any containers. Never reads
production credentials, services or files; uses a fixed immutable donor ref.
"""
from __future__ import annotations
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
import shared_edge as e

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo',type=pathlib.Path,required=True)
    parser.add_argument('--donor-ref',required=True)
    parser.add_argument('--report',type=pathlib.Path,required=True)
    args=parser.parse_args()
    if not re.fullmatch(r'[a-f0-9]{40}',args.donor_ref):raise ValueError('EXACT_DONOR_REF_REQUIRED')
    if not args.report.is_absolute() or args.report.exists():raise ValueError('NEW_REPORT_REQUIRED')
    projects=b.render.validate(json.loads((BASE/'projects.rehearsal.json').read_text()))
    shared=e.runtime_secrets(projects)
    creds={};funcs={};apis={};origins={}
    for p in projects:
        uid=p['project_uuid'];s=b.new_secrets()
        creds[uid]={'project_uuid':uid,'jwt_secret':s['jwt'],
                    'anon_key':b.token(p,s['jwt'],'anon'),
                    'service_role_key':b.token(p,s['jwt'],'service_role')}
        funcs[uid]=[{'name':'identity','source':"Deno.serve(()=>Response.json({ok:true}));",
                     'auth':'user','env':{},'net_allow':[],'memory_mb':64,
                     'timeout_ms':2000,'cpu_ms':250,'allow_service_role':False}]
        apis[uid]='http://tenant-'+p['slug']+'-api:8080'
        origins[uid]=['https://'+p['hostname']]
    artifacts=e.compile_bundle(projects,{'credentials':creds,'shared':shared,'functions':funcs,
                  'api_endpoints':apis,'allowed_origins':origins,
                  'worker_root':'/home/deno/private-workers'})
    def original(path):
        return subprocess.check_output(['git','-C',str(args.repo),'show',args.donor_ref+':'+path],
                                       text=True,timeout=15)
    with tempfile.TemporaryDirectory(prefix='dial-supa-edge-compose-') as td:
        work=pathlib.Path(td)
        donor=original('deploy/van-trading-core/supabase/docker-compose.yml')
        override=original('deploy/van-trading-core/supabase/docker-compose.override.yml')
        (work/'base.yml').write_text(donor)
        (work/'override.yml').write_text(override)
        values={k:'fixture-value' for k in re.findall(r'\$\{([A-Z0-9_]+)',donor+override)}
        values.update(POSTGRES_PORT='5432',POSTGRES_HOST='db',POSTGRES_DB='postgres',
            API_GW_HTTP_PORT='8000',POOLER_PROXY_PORT_TRANSACTION='6543',
            JWT_EXPIRY='3600')
        (work/'donor.env').write_text(''.join(k+'='+v+'\n' for k,v in values.items()))
        (work/'edge.yml').write_text(artifacts['shared-edge.overlay.yml'])
        (work/'edge-extra.env').write_text(artifacts['shared-edge.compose.env'])
        def parsed(filenames):
            argv=['docker','compose','--project-name','dial-supa-edge-model',
                '--env-file',str(work/'donor.env'),'--env-file',str(work/'edge-extra.env')]
            for f in filenames:argv+=['-f',str(work/f)]
            result=subprocess.run(argv+['config','--format','json'],text=True,
                                  capture_output=True,timeout=20)
            if result.returncode:raise ValueError('EDGE_COMPOSE_CONFIGURATION_REFUSED')
            return json.loads(result.stdout)
        prior=parsed(['base.yml','override.yml'])
        updated=parsed(['base.yml','override.yml','edge.yml'])
        old=prior['services'];new=updated['services'];o=old['functions'];n=new['functions']
        original_vols={v['target']:v for v in o.get('volumes',[])}
        current_vols={v['target']:v for v in n.get('volumes',[])}
        unchanged_keys=('db','storage','realtime','auth','rest','api-gw')
        env=n['environment']
        verified={
            'original_services_preserved_exactly':set(new)==set(old),
            'no_new_postgres_or_functions_service':list(new).count('db')==1 and list(new).count('functions')==1,
            'other_services_byte_semantics_unchanged':all(old[k]==new[k] for k in old if k!='functions'),
            'original_volume_targets_preserved':all(current_vols.get(t)==v for t,v in original_vols.items()),
            'private_edge_registry_mount_readonly':any(v['target']=='/etc/dial-supabase/edge/registry.json' and v['read_only'] for v in current_vols.values()),
            'main_worker_mount_readonly':any(v['target']=='/home/deno/dial-main' and v['read_only'] for v in current_vols.values()),
            'edge_runtime_image_digest_pinned':n['image']=='supabase/edge-runtime@'+e.AMD64_IMAGE_DIGEST,
            'no_public_function_ports':not n.get('ports'),
            'original_function_healthcheck_preserved':n.get('healthcheck')==o.get('healthcheck'),
            'main_worker_launch_explicit':n['command'][:3]==['start','--main-service','/home/deno/dial-main'],
            'registry_hash_bound':env['DIAL_EDGE_REGISTRY_SHA256']==hashlib.sha256(artifacts['registry.json'].encode()).hexdigest(),
            'legacy_single_project_signing_disabled':all(env[k]=='' for k in ('JWT_SECRET','SUPABASE_JWKS','SUPABASE_ANON_KEY','SUPABASE_SERVICE_ROLE_KEY','VERIFY_JWT')),
            'legacy_shared_database_credential_not_in_edge':env['SUPABASE_DB_URL']=='',
            'resource_limits_present':str(n.get('mem_limit')).lower() in ('512m','536870912') and n.get('pids_limit')==128,
            'native_security_constraints_retained':n.get('security_opt')==['no-new-privileges:true'] and n.get('cap_drop')==['ALL'],
            'private_project_registry_is_staged_only':json.loads(artifacts['edge-candidate.json'])['production_deploy_authorized'] is False
        }
        result={'state':'PASS' if all(verified.values()) else 'FAIL',
                'checks':verified,'check_count':len(verified),
                'donor_ref':args.donor_ref,'service_count':len(new),
                'docker_daemon_used':False,'containers_started':False,
                'production_image_executed':False,'production_arm64_qualified':False,
                'source_sha256':{str(f.relative_to(BASE)):hashlib.sha256(f.read_bytes()).hexdigest()
                  for f in (BASE/'tools/shared_edge.py',pathlib.Path(__file__))}}
        fd=os.open(args.report,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
        with os.fdopen(fd,'w') as handle:handle.write(json.dumps(result,sort_keys=True,indent=2)+'\n')
        print('EDGE_COMPOSE_MODEL_'+result['state']+' '+str(len(verified)))
        if not all(verified.values()):
            print('FAILED_ASSERTIONS '+','.join(k for k,v in verified.items() if not v))
        return 0 if all(verified.values()) else 1

if __name__=='__main__':raise SystemExit(main())
