#!/usr/bin/env python3
"""Compile a guarded canonical lifecycle for the EXISTING vati-supabase unit.

No systemctl/Docker invocation, file deployment, secrets issuance or authority.
The original Root owner must attest the actual Compose project and input bytes,
admit the release, install private files atomically, and verify the real host.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import pathlib
import re
import shlex
import recovery
import render

INSTALL='/opt/van-trading/supabase'
UNIT='vati-supabase.service'
UNIT_PATH='/etc/systemd/system/'+UNIT
BASE_FILES=[INSTALL+'/docker-compose.yml',INSTALL+'/docker-compose.override.yml']
COMPONENTS=('core','storage','realtime','edge','pooler','admin')
ENVS=('base','realtime','edge','pooler','admin')
DONOR_SERVICES={'studio','api-gw','auth','rest','realtime','storage','imgproxy','meta','functions','db','supavisor'}
SHA=re.compile(r'^[a-f0-9]{64}$')
SAFE_PATH=re.compile(r'^/[a-zA-Z0-9_./-]+$')
SPEC_FIELDS={'schema_version','kind','release_id','source_sha','original_unit_sha256','observed_project_name','observed_daemon_socket','base_files','overlays','environment_files','protected_files','projects','effective_services'}


def canonical(value):return json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False)+'\n'


def path_checked(value):
    if not isinstance(value,str) or not SAFE_PATH.fullmatch(value) or '..' in pathlib.PurePosixPath(value).parts or '//' in value or '/./' in value or value.endswith('/'):
        raise ValueError('UNSAFE_LIFECYCLE_PATH')
    return value


def binding(value):
    if not isinstance(value,dict) or set(value)!={'path','sha256'}:raise ValueError('EXACT_FILE_BINDING_REQUIRED')
    path=path_checked(value['path'])
    if not isinstance(value['sha256'],str) or not SHA.fullmatch(value['sha256']):raise ValueError('EXACT_FILE_DIGEST_REQUIRED')
    return path,value['sha256']


def verify_donor_unit(source,digest):
    if hashlib.sha256(source.encode()).hexdigest()!=digest:raise ValueError('ORIGINAL_UNIT_DIGEST_MISMATCH')
    section=None;service={}
    for line in source.splitlines():
        line=line.strip()
        if not line or line.startswith(('#',';')):continue
        if line.startswith('[') and line.endswith(']'):section=line[1:-1];continue
        if section=='Service':
            key,sep,value=line.partition('=')
            if not sep or key in service or '\\' in value:raise ValueError('ORIGINAL_UNIT_REQUIRES_INDEPENDENT_REVIEW')
            service[key]=value
    expected={'Type':'oneshot','RemainAfterExit':'true','WorkingDirectory':INSTALL,'TimeoutStartSec':'600',
        'ExecStart':'/usr/bin/docker compose -f '+BASE_FILES[0]+' -f '+BASE_FILES[1]+' --env-file '+INSTALL+'/.env up -d --remove-orphans',
        'ExecStop':'/usr/bin/docker compose -f '+BASE_FILES[0]+' -f '+BASE_FILES[1]+' --env-file '+INSTALL+'/.env stop'}
    if service!=expected:raise ValueError('ORIGINAL_LIFECYCLE_NOT_EXACT_REVIEWED_DONOR')


def validate(spec,source):
    if not isinstance(spec,dict) or set(spec)!=SPEC_FIELDS or type(spec.get('schema_version')) is not int or spec['schema_version']!=1:
        raise ValueError('LIFECYCLE_FIELDS_MISMATCH')
    if spec['kind']!='DIAL_SUPABASE_LIFECYCLE_INPUT_V1':raise ValueError('LIFECYCLE_KIND_INVALID')
    if not isinstance(spec['release_id'],str) or not re.fullmatch(r'[a-z0-9][a-z0-9-]{7,63}',spec['release_id']):raise ValueError('INVALID_RELEASE_ID')
    if not isinstance(spec['source_sha'],str) or not re.fullmatch('[a-f0-9]{40}',spec['source_sha']):raise ValueError('IMMUTABLE_SOURCE_REQUIRED')
    if not isinstance(spec['observed_project_name'],str) or not re.fullmatch('[a-z0-9][a-z0-9_-]{0,62}',spec['observed_project_name']):
        raise ValueError('OBSERVED_EXISTING_COMPOSE_PROJECT_REQUIRED')
    if not isinstance(spec['original_unit_sha256'],str) or not SHA.fullmatch(spec['original_unit_sha256']):raise ValueError('ORIGINAL_UNIT_DIGEST_REQUIRED')
    if spec['observed_daemon_socket']!='/var/run/docker.sock':raise ValueError('OBSERVED_LOCAL_DOCKER_SOCKET_REQUIRED')
    verify_donor_unit(source,spec['original_unit_sha256'])
    root='/etc/dial-supabase/releases/'+spec['release_id']
    if not isinstance(spec['base_files'],list) or len(spec['base_files'])!=2 or [binding(v)[0] for v in spec['base_files']]!=BASE_FILES:
        raise ValueError('BOTH_ORIGINAL_COMPOSE_FILES_REQUIRED')
    if not isinstance(spec['overlays'],dict) or set(spec['overlays'])!=set(COMPONENTS):raise ValueError('COMPLETE_SHARED_SERVICE_OVERLAYS_REQUIRED')
    if not isinstance(spec['environment_files'],dict) or set(spec['environment_files'])!=set(ENVS):raise ValueError('COMPLETE_ENVIRONMENT_MODEL_REQUIRED')
    files=list(spec['base_files'])
    for component in COMPONENTS:
        value=spec['overlays'][component];path,_=binding(value)
        if not path.startswith(root+'/') or not path.endswith('.yml'):raise ValueError('OVERLAY_OUTSIDE_EXACT_RELEASE')
        files.append(value)
    for name in ENVS:
        value=spec['environment_files'][name];path,_=binding(value)
        if name=='base':
            if path!=INSTALL+'/.env':raise ValueError('ORIGINAL_ENV_FILE_REQUIRED')
        elif not path.startswith(root+'/') or not path.endswith('.env'):raise ValueError('ENV_FILE_OUTSIDE_EXACT_RELEASE')
        files.append(value)
    if not isinstance(spec['protected_files'],list) or not 1<=len(spec['protected_files'])<=512:raise ValueError('PRIVATE_RUNTIME_FILE_BINDINGS_REQUIRED')
    for value in spec['protected_files']:
        path,_=binding(value)
        if not any(path.startswith(x) for x in ('/etc/dial-supabase/','/opt/dial-supabase/edge/')):raise ValueError('PROTECTED_FILE_OUTSIDE_SCOPE')
        files.append(value)
    paths=[binding(v)[0] for v in files]
    if len(paths)!=len(set(paths)) or UNIT_PATH in paths:raise ValueError('DUPLICATE_FILE_PATH')
    if not isinstance(spec['projects'],list) or not spec['projects'] or len(set(spec['projects']))!=len(spec['projects']):raise ValueError('EXACT_PROJECT_SET_REQUIRED')
    for slug in spec['projects']:
        if not isinstance(slug,str) or not render.SLUG_RE.fullmatch(slug) or slug in render.BLOCKED_NAMES:raise ValueError('PROJECT_SLUG_REFUSED')
    expected=DONOR_SERVICES|{'project-admin'}|{'tenant-'+slug+'-'+suffix for slug in spec['projects'] for suffix in ('auth','rest','api')}
    if not isinstance(spec['effective_services'],list) or len(spec['effective_services'])!=len(set(spec['effective_services'])) or set(spec['effective_services'])!=expected:
        raise ValueError('INCOMPLETE_OR_UNEXPECTED_EFFECTIVE_SERVICE_MODEL')
    return root,files


def compile_bundle(spec,original_unit):
    root,files=validate(spec,original_unit)
    argv=['/usr/bin/docker','--host','unix://'+spec['observed_daemon_socket'],'compose','--project-directory',INSTALL,'--project-name',spec['observed_project_name']]
    for name in ENVS:argv+=['--env-file',spec['environment_files'][name]['path']]
    for value in spec['base_files']:argv+=['-f',value['path']]
    for name in COMPONENTS:argv+=['-f',spec['overlays'][name]['path']]
    # All arguments are strict path/name characters; nevertheless serialize using
    # the same quoted command syntax rather than interpolating a shell command.
    command=shlex.join(argv)
    checks=root+'/lifecycle-inputs.sha256'
    checksum='/usr/bin/sha256sum --check --strict --status '+checks
    dropin='\n'.join([
        '# CANDIDATE ONLY: original Root admission and atomic private installation required.',
        '# Same existing unit/project/volumes; NEVER a second Compose project.',
        '[Service]',
        'UnsetEnvironment=DOCKER_HOST DOCKER_CONTEXT COMPOSE_FILE COMPOSE_PROJECT_NAME COMPOSE_PROFILES COMPOSE_ENV_FILES COMPOSE_REMOVE_ORPHANS COMPOSE_IGNORE_ORPHANS',
        'ExecStartPre='+checksum,
        'ExecStartPre='+command+' config --quiet',
        'ExecStart=',
        'ExecStart='+command+' up -d --remove-orphans',
        'ExecStop=',
        'ExecStop='+checksum,
        'ExecStop='+command+' stop',
        ''])
    bindings=[{'path':UNIT_PATH,'sha256':spec['original_unit_sha256']}]+files
    text=''.join(v['sha256']+'  '+v['path']+'\n' for v in bindings)
    record={'schema_version':1,'kind':'EXISTING_SUPABASE_CANONICAL_LIFECYCLE_CANDIDATE',
        'unit':UNIT,'release_id':spec['release_id'],'source_sha':spec['source_sha'],
        'project_name':spec['observed_project_name'],'docker_socket':spec['observed_daemon_socket'],'target_installation':INSTALL,
        'start_argv':argv+['up','-d','--remove-orphans'],'stop_argv':argv+['stop'],
        'validate_argv':argv+['config','--quiet'],
        'effective_services':sorted(spec['effective_services']),
        'file_bindings':bindings,'source_unit_sha256':spec['original_unit_sha256'],
        'target_paths':{'dropin':'/etc/systemd/system/'+UNIT+'.d/90-dial-multiproject.conf','checksums':checks},
        'production_deployed':False,'authorizes_execution':False,
        'limitations':['Actual Root-owned unit/project/container labels and all referenced runtime files must be independently observed and admitted.',
            'Checksums provide integrity only, not authentication, Root authority or live health.',
            'This generator never installs, reloads, starts, stops or restores a service.',
            'An invalid/missing pinned input refuses start AND stop; only the existing scoped Root owner may reconcile that original operation.'],
        'artifacts_sha256':{'90-dial-multiproject.conf':hashlib.sha256(dropin.encode()).hexdigest(),'lifecycle-inputs.sha256':hashlib.sha256(text.encode()).hexdigest()}}
    return {'90-dial-multiproject.conf':dropin,'lifecycle-inputs.sha256':text,'lifecycle-candidate.json':json.dumps(record,indent=2,sort_keys=True)+'\n'}


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--private-input',type=pathlib.Path,required=True)
    parser.add_argument('--original-unit',type=pathlib.Path,required=True)
    parser.add_argument('--out',type=pathlib.Path,required=True)
    args=parser.parse_args(argv)
    try:
        spec=recovery.load_private_json(args.private_input)
        with args.original_unit.open('rb') as f:source=f.read(65537)
        if len(source)>65536:raise ValueError('UNIT_SIZE_LIMIT')
        artifacts=compile_bundle(spec,source.decode('utf-8'))
        render.write_bundle(args.out,artifacts)
        print('LIFECYCLE_CANDIDATE_WRITTEN_NO_DEPLOYMENT')
        return 0
    except (ValueError,TypeError,KeyError,OSError):
        print('REFUSED_LIFECYCLE_CANDIDATE')
        return 2

if __name__=='__main__':raise SystemExit(main())
