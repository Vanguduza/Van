#!/usr/bin/env python3
"""Staged ONE-runtime Edge Functions registry/gateway compiler; never deploys.

Runtime source must be pre-bundled/self-contained. New deployments are immutable
and worker identity includes code, secret, authority and permission digests.
The private registry contains actual project credentials; never publish it.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import pathlib
import re
import secrets
from urllib.parse import urlsplit
import bootstrap as b
import shared_storage as st
import recovery

VERSION='1.76.2'
SOURCE_COMMIT='db47af5264be7a6e649d9488cc4f3f0da16ff875'
AMD64_IMAGE_DIGEST='sha256:b331c6422f4f4bebd6052357da5f3c87610128c8cb530390ca024eb68cf4bf2e'
KIND='DIAL_SHARED_EDGE_PRIVATE_REGISTRY_V1'
NAME=re.compile(r'^[a-z][a-z0-9-]{1,47}$')
ENV=re.compile(r'^[A-Z][A-Z0-9_]{0,63}$')
FUNCTION_FIELDS={'name','source','auth','env','net_allow','memory_mb','timeout_ms','cpu_ms','allow_service_role'}
RESERVED={'SUPABASE_URL','SUPABASE_ANON_KEY','SUPABASE_SERVICE_ROLE_KEY','DIAL_PROJECT_ID'}


def canonical(value):
    return json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False)


def project_host(p):
    b.render.validate({'schema_version':1,'target_installation':b.render.ROOT,
        'allowed_postgres_service':'db','projects':[p]})
    return p['project_uuid'].replace('-','')+'.edge.internal'


def runtime_secrets(projects):
    ps=st.validate_projects(projects)
    return {'health_key':secrets.token_urlsafe(48),
        'gateway_keys':{p['project_uuid']:secrets.token_urlsafe(48) for p in ps}}


def endpoint(p,url):
    if not isinstance(url,str):raise ValueError('EDGE_API_ENDPOINT_REQUIRED')
    u=urlsplit(url)
    if (u.scheme!='http' or u.username or u.password or u.query or u.fragment or
        u.path not in ('','/') or u.hostname not in ('tenant-'+p['slug']+'-api','127.0.0.1') or
        u.port is None or not 1<=u.port<=65535):raise ValueError('EDGE_EXACT_PROJECT_API_ENDPOINT_REQUIRED')
    return f'{u.hostname}:{u.port}'


def origins_checked(origins):
    if not isinstance(origins,list) or len(origins)>16 or len(set(origins))!=len(origins):
        raise ValueError('EDGE_ORIGIN_ALLOWLIST_INVALID')
    for origin in origins:
        u=urlsplit(origin)
        if u.scheme!='https' or u.username or u.password or u.path or u.query or u.fragment or not u.hostname:
            raise ValueError('EDGE_ORIGIN_ALLOWLIST_INVALID')
        if origin!='https://'+u.netloc or '*' in origin:raise ValueError('EDGE_ORIGIN_ALLOWLIST_INVALID')
    return origins


def function(p,credentials,descriptor,api_url):
    if not isinstance(descriptor,dict) or set(descriptor)!=FUNCTION_FIELDS:raise ValueError('EDGE_FUNCTION_FIELDS_INVALID')
    f=dict(descriptor)
    if not isinstance(f['name'],str) or not NAME.fullmatch(f['name']):raise ValueError('EDGE_FUNCTION_NAME_INVALID')
    if not isinstance(f['source'],str) or not 1<=len(f['source'].encode())<=1048576 or '\0' in f['source']:
        raise ValueError('EDGE_BUNDLED_SOURCE_INVALID')
    if f['auth'] not in ('user','service_role','apikey'):raise ValueError('EDGE_AUTH_MODE_NOT_QUALIFIED')
    for field,low,high in [('memory_mb',32,128),('timeout_ms',250,10000),('cpu_ms',50,2000)]:
        if type(f[field]) is not int or not low<=f[field]<=high:raise ValueError('EDGE_LIMIT_INVALID')
    if type(f['allow_service_role']) is not bool:raise ValueError('EDGE_SERVICE_CAPABILITY_EXPLICIT_BOOL_REQUIRED')
    if not isinstance(f['env'],dict) or len(f['env'])>48:raise ValueError('EDGE_FUNCTION_ENV_INVALID')
    env={}
    for k,v in f['env'].items():
        if (not isinstance(k,str) or not ENV.fullmatch(k) or k in RESERVED or
            k.startswith(('DENO_','LD_','NODE_','DIAL_EDGE_')) or
            not isinstance(v,str) or len(v.encode())>16384 or '\0' in v):raise ValueError('EDGE_FUNCTION_ENV_INVALID')
        env[k]=v
    api=endpoint(p,api_url)
    env.update(DIAL_PROJECT_ID=p['project_uuid'],SUPABASE_URL=api_url.rstrip('/'),SUPABASE_ANON_KEY=credentials['anon_key'])
    if f.pop('allow_service_role'):env['SUPABASE_SERVICE_ROLE_KEY']=credentials['service_role_key']
    if not isinstance(f['net_allow'],list) or len(f['net_allow'])>15:raise ValueError('EDGE_EGRESS_ALLOWLIST_INVALID')
    for n in f['net_allow']:
        if not isinstance(n,str) or not re.fullmatch(r'[a-z0-9][a-z0-9.-]*:[1-9][0-9]{0,4}',n) or int(n.rsplit(':',1)[1])>65535:
            raise ValueError('EDGE_EGRESS_ALLOWLIST_INVALID')
        # Extra targets are explicit owner-reviewed public DNS hosts only. No
        # loopback, cluster service, private IP or sibling project auto access.
        host=n.rsplit(':',1)[0]
        import ipaddress
        try:ipaddress.ip_address(host);raise ValueError('EDGE_RAW_IP_EGRESS_REFUSED')
        except ValueError as exc:
            if str(exc)=='EDGE_RAW_IP_EGRESS_REFUSED':raise
        if host in ('localhost','db','functions','meta','storage','realtime') or host.endswith(('.internal','.local')) or host.startswith('tenant-'):
            raise ValueError('EDGE_SIBLING_INTERNAL_EGRESS_REFUSED')
    f['net_allow']=sorted(set([api]+f['net_allow']));f['env']=env
    f['source_sha256']=hashlib.sha256(f['source'].encode()).hexdigest()
    f['revision']=hashlib.sha256(canonical({'project_uuid':p['project_uuid'],**f}).encode()).hexdigest()
    return f


def registry(projects,credentials,shared,functions,api_endpoints,allowed_origins,worker_root):
    ps=st.validate_projects(projects);ids={p['project_uuid'] for p in ps}
    if (not isinstance(shared,dict) or set(shared)!={'health_key','gateway_keys'} or
        any(set(x)!=ids for x in (credentials,shared['gateway_keys'],functions,api_endpoints,allowed_origins))):
        raise ValueError('EDGE_EXACT_PROJECT_BINDINGS_REQUIRED')
    values=[st.strong_secret(shared['health_key'])]+[st.strong_secret(x) for x in shared['gateway_keys'].values()]
    if len(set(values))!=len(values):raise ValueError('EDGE_CONTROL_SECRETS_MUST_DIFFER')
    if not isinstance(worker_root,str) or not worker_root.startswith('/') or '..' in pathlib.PurePosixPath(worker_root).parts or '\0' in worker_root:
        raise ValueError('EDGE_PRIVATE_WORKER_ROOT_REQUIRED')
    result=[];signers=set()
    for p in ps:
        ident=p['project_uuid'];c=credentials[ident]
        if not isinstance(c,dict) or set(c)!={'project_uuid','jwt_secret','anon_key','service_role_key'} or c['project_uuid']!=ident:
            raise ValueError('EDGE_PROJECT_CREDENTIAL_FIELDS_INVALID')
        st.validate_credential_keys(p,c)
        if c['jwt_secret'] in signers:raise ValueError('EDGE_PROJECT_SIGNER_REUSE_REFUSED')
        signers.add(c['jwt_secret'])
        if not isinstance(functions[ident],list) or not 1<=len(functions[ident])<=32:raise ValueError('EDGE_FUNCTION_COUNT_INVALID')
        fs=[function(p,c,f,api_endpoints[ident]) for f in functions[ident]]
        if len({x['name'] for x in fs})!=len(fs):raise ValueError('EDGE_DUPLICATE_FUNCTION')
        result.append({'project_uuid':ident,'hostname':p['hostname'],'internal_host':project_host(p),
            'gateway_key':shared['gateway_keys'][ident],'jwt_secret':c['jwt_secret'],
            'anon_key':c['anon_key'],'service_role_key':c['service_role_key'],
            'issuer':'https://'+p['hostname']+'/auth/v1','audience':'authenticated',
            'allowed_origins':origins_checked(allowed_origins[ident]),'functions':sorted(fs,key=lambda x:x['name'])})
    out={'schema_version':1,'kind':KIND,'worker_root':worker_root,'health_key':shared['health_key'],'projects':result}
    if len(canonical(out).encode())>16777216:raise ValueError('EDGE_REGISTRY_TOO_LARGE')
    return out


def gateway(p,credentials,gateway_key,api_url,base_config=None,upstream='functions:9000'):
    st.validate_credential_keys(p,credentials);st.strong_secret(gateway_key)
    if not re.fullmatch(r'[A-Za-z0-9_-]{48,128}',gateway_key):raise ValueError('EDGE_INGRESS_SECRET_INVALID')
    if not re.fullmatch(r'[a-z0-9][a-z0-9.-]*:[1-9][0-9]{0,4}',upstream) or int(upstream.rsplit(':',1)[1])>65535:
        raise ValueError('EDGE_UPSTREAM_INVALID')
    text=base_config if base_config is not None else b.gateway(p,credentials['anon_key'],credentials['service_role_key'])
    marker='    location ^~ /functions/v1/ { return 503; }'
    if text.count(marker)!=1:raise ValueError('EDGE_BASE_ROUTE_NOT_UNQUALIFIED')
    internal=endpoint(p,api_url).split(':')[0]
    old='    server_name '+p['hostname']+';'
    if text.count(old)!=1:raise ValueError('EDGE_PROJECT_GATEWAY_IDENTITY_DRIFT')
    text=text.replace(old,'    server_name '+p['hostname']+' '+internal+';',1)
    old_pattern='^'+re.escape(p['hostname'])+'(?::[0-9]{1,5})?$'
    new_pattern='^(?:'+re.escape(p['hostname'])+'|'+re.escape(internal)+')(?::[0-9]{1,5})?$'
    if text.count(old_pattern)!=1:raise ValueError('EDGE_GATEWAY_HOST_GUARD_DRIFT')
    text=text.replace(old_pattern,new_pattern,1)
    lines=['    location ^~ /functions/v1/ {','        proxy_http_version 1.1;',
        '        proxy_set_header Connection "";',
        '        proxy_set_header Host '+project_host(p)+';',
        '        proxy_set_header X-Dial-Edge-Gateway '+gateway_key+';',
        '        proxy_set_header X-Tenant-ID "";','        proxy_set_header X-Project-ID "";',
        '        proxy_set_header X-Dial-Project-ID "";','        proxy_set_header Forwarded "";',
        '        proxy_set_header X-Forwarded-Host "";','        proxy_set_header X-Forwarded-Path "";',
        '        proxy_set_header X-Forwarded-Prefix "";','        proxy_set_header X-Dial-Edge-Health "";',
        '        client_max_body_size 1m;','        proxy_connect_timeout 5s;','        proxy_read_timeout 15s;',
        '        proxy_pass http://'+upstream+'/;', '    }']
    return text.replace(marker,'\n'.join(lines),1)


def overlay():
    return '\n'.join(['# Candidate only: preserve original functions by explicit registration before rollout.',
        'services:','  functions:',f'    image: supabase/edge-runtime@{AMD64_IMAGE_DIGEST}',
        '    mem_limit: 512m','    cpus: 1.0','    pids_limit: 128',
        '    security_opt: ["no-new-privileges:true"]','    cap_drop: ["ALL"]',
        '    environment:',
        '      DIAL_EDGE_REGISTRY: /etc/dial-supabase/edge/registry.json',
        '      DIAL_EDGE_REGISTRY_SHA256: "${DIAL_EDGE_REGISTRY_SHA256:?exact private registry hash required}"',
        *['      '+k+': ""' for k in ('JWT_SECRET','SUPABASE_JWKS','SUPABASE_URL','SUPABASE_PUBLIC_URL','SUPABASE_ANON_KEY','SUPABASE_SERVICE_ROLE_KEY','SUPABASE_PUBLISHABLE_KEYS','SUPABASE_SECRET_KEYS','SUPABASE_DB_URL','VERIFY_JWT')],
        '    volumes:','      - /etc/dial-supabase/edge/registry.json:/etc/dial-supabase/edge/registry.json:ro',
        '      - /opt/dial-supabase/edge/main:/home/deno/dial-main:ro',
        '    command: ["start", "--main-service", "/home/deno/dial-main", "--policy", "per_worker", "--max-parallelism", "4", "--request-wait-timeout", "2000", "--user-worker-request-idle-timeout", "11000", "--request-read-timeout", "5000"]',''])


def compile_bundle(projects,private,base_gateways=None):
    required={'credentials','shared','functions','api_endpoints','allowed_origins','worker_root'}
    if not isinstance(private,dict) or set(private)!=required:raise ValueError('EDGE_PRIVATE_INPUT_FIELDS_INVALID')
    config=registry(projects,**private)
    raw=canonical(config)+'\n';digest=hashlib.sha256(raw.encode()).hexdigest()
    outputs={'registry.json':raw,'shared-edge.overlay.yml':overlay(),
        'shared-edge.compose.env':'DIAL_EDGE_REGISTRY_SHA256='+digest+'\n'}
    for p in st.validate_projects(projects):
        pid=p['project_uuid']
        outputs[p['slug']+'.nginx.conf']=gateway(p,private['credentials'][pid],private['shared']['gateway_keys'][pid],private['api_endpoints'][pid],None if base_gateways is None else base_gateways[pid])
    outputs['edge-candidate.json']=json.dumps({'kind':'EDGE_PRIVATE_CANDIDATE_NOT_DEPLOYED','registry_sha256':digest,
        'project_uuids':[p['project_uuid'] for p in projects],'edge_runtime_services_added':0,'postgres_servers_added':0,
        'production_deploy_authorized':False,'upstream_version':VERSION,'upstream_source_commit':SOURCE_COMMIT,
        'files':{n:hashlib.sha256(t.encode()).hexdigest() for n,t in outputs.items()}},indent=2,sort_keys=True)+'\n'
    return outputs


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest',type=pathlib.Path,required=True)
    parser.add_argument('--private-input',type=pathlib.Path,required=True)
    parser.add_argument('--out',type=pathlib.Path,required=True)
    a=parser.parse_args(argv)
    try:
        projects,_=b.render.load_manifest(a.manifest);private=recovery.load_private_json(a.private_input)
        out=compile_bundle(projects,private);b.render.write_bundle(a.out,out)
        print('PRIVATE_EDGE_CANDIDATE_WRITTEN_NOT_DEPLOYED')
        return 0
    except (ValueError,KeyError,TypeError,OSError):
        print('REFUSED_EDGE_CANDIDATE')
        return 2

if __name__=='__main__':raise SystemExit(main())
