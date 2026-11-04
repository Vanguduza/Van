#!/usr/bin/env python3
"""Verify the candidate merges into the retained donor model. No Docker daemon.

Uses only `docker compose config`, synthetic credentials and private temp files.
No containers, services, live env files or VM configuration are read or changed.
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


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo',type=pathlib.Path,required=True)
    parser.add_argument('--donor-ref',required=True)
    parser.add_argument('--report',type=pathlib.Path,required=True)
    args=parser.parse_args()
    if not re.fullmatch(r'[a-f0-9]{40}',args.donor_ref):raise ValueError('IMMUTABLE_DONOR_REF_REQUIRED')
    if not args.report.is_absolute() or args.report.exists():raise ValueError('NEW_REPORT_REQUIRED')
    projects=b.render.validate(json.loads((BASE/'projects.rehearsal.json').read_text()))
    shared=st.new_secrets(projects)
    def original(path):
        return subprocess.check_output(['git','-C',str(args.repo),'show',args.donor_ref+':'+path],text=True,timeout=15)
    with tempfile.TemporaryDirectory(prefix='dial-storage-compose-') as td:
        w=pathlib.Path(td)
        donor=original('deploy/van-trading-core/supabase/docker-compose.yml')
        override=original('deploy/van-trading-core/supabase/docker-compose.override.yml')
        (w/'base.yml').write_text(donor);(w/'override.yml').write_text(override)
        settings={k:'fixture-value' for k in re.findall(r'\$\{([A-Z0-9_]+)',donor+override)}
        settings.update(POSTGRES_PORT='5432',POSTGRES_HOST='db',POSTGRES_DB='postgres',
            API_GW_HTTP_PORT='8000',POOLER_PROXY_PORT_TRANSACTION='6543',JWT_EXPIRY='3600',
            GLOBAL_S3_BUCKET='original-bucket',STORAGE_TENANT_ID='original-tenant')
        (w/'donor.env').write_text(''.join(k+'='+v+'\n' for k,v in settings.items()))
        env=st.environment(shared,object_bucket='original-bucket',preserved_tenants=['original-tenant'])
        (w/'storage.env').write_text(st.storage_env_text(env))
        (w/'storage.yml').write_text(st.overlay().replace('/etc/dial-supabase/shared-storage/storage.env',str(w/'storage.env')))
        def config(files):
            command=['docker','compose','--project-name','dial-storage-config-check','--env-file',str(w/'donor.env')]
            for f in files:command+=['-f',str(w/f)]
            r=subprocess.run(command+['config','--format','json'],capture_output=True,text=True,timeout=20)
            if r.returncode:raise RuntimeError('COMPOSE_CONFIG_FAILED')
            return json.loads(r.stdout)
        old=config(['base.yml','override.yml']);new=config(['base.yml','override.yml','storage.yml'])
        old_storage=old['services']['storage'];storage=new['services']['storage'];effective=storage['environment']
        # `compose config` escapes literal '$' to '$$' in its re-consumable
        # output. The exact expected canonical representation is compared;
        # do not weaken or strip other pattern bytes.
        expected_pattern=env['REQUEST_X_FORWARDED_HOST_REGEXP'].replace('$','$$')
        checks={
            'service_names_preserved':set(old['services'])==set(new['services']),
            'one_existing_storage_service':list(new['services']).count('storage')==1,
            'postgres_service_unchanged':old['services']['db']==new['services']['db'],
            'storage_volume_mount_unchanged':old_storage.get('volumes')==storage.get('volumes'),
            'no_storage_published_ports':not storage.get('ports'),
            'private_tenant_pattern_exact_canonical_literal':effective['REQUEST_X_FORWARDED_HOST_REGEXP']==expected_pattern,
            'multitenant_true':effective['MULTI_TENANT']=='true',
            'legacy_bucket_preserved':effective['GLOBAL_S3_BUCKET']==effective['STORAGE_S3_BUCKET']=='original-bucket',
            'legacy_single_credentials_not_used':all(effective[k]=='' for k in ('DATABASE_URL','ANON_KEY','SERVICE_KEY','AUTH_JWT_SECRET')),
            'image_transform_explicitly_disabled':effective['ENABLE_IMAGE_TRANSFORMATION']==effective['IMAGE_TRANSFORMATION_ENABLED']=='false',
            'every_other_service_unchanged':all(old['services'][k]==new['services'][k] for k in old['services'] if k!='storage')}
        envoy=original('deploy/van-trading-core/supabase/volumes/api/envoy/lds.template.yaml')
        changed,receipt=st.legacy_envoy_candidate(envoy,hashlib.sha256(envoy.encode()).hexdigest(),'original-tenant')
        checks['legacy_envoy_candidate_exact_source_bound']=receipt['other_routes_byte_preserved'] and 'original-tenant.storage.internal' in changed
        version=subprocess.check_output(['docker','compose','version'],text=True,timeout=10).strip()
        result={'state':'PASS' if all(checks.values()) else 'FAIL','check_count':len(checks),'checks':checks,
            'docker_daemon_used':False,'containers_started':False,'native_envoy_validation':False,
            'donor_commit':args.donor_ref,'compose_version':version,
            'source_sha256':{str(p.relative_to(BASE)):hashlib.sha256(p.read_bytes()).hexdigest() for p in (BASE/'tools/shared_storage.py',pathlib.Path(__file__))},
            'envoy_candidate':receipt}
        fd=os.open(args.report,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
        with os.fdopen(fd,'w') as handle:handle.write(json.dumps(result,indent=2,sort_keys=True)+'\n')
        print('COMPOSE_MODEL_CHECK_'+result['state']+' '+str(len(checks)))
        return 0 if all(checks.values()) else 1

if __name__=='__main__':raise SystemExit(main())
