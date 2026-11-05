#!/usr/bin/env python3
"""Private Studio-compatible project routing, using one existing pg-meta service.

No issuer, account database, superuser credential, install or deploy operation.
Existing DIAL/IdP operator identity must sign the short-lived accepted tokens.
"""
import hashlib
import json
import re
import secrets
from urllib.parse import quote,urlsplit
import bootstrap as b
import shared_storage as st
import shared_pooler as pool

META_VERSION='0.99.0'
META_SOURCE='f380cc5be21edef4e77d9838c732d1f20af0b3c0'
STUDIO_IMAGE='2026.09.07-sha-7996410'
STUDIO_AMD64_DIGEST='sha256:0f797270d236090c79fd26a97a1e5d1cf7ec5f36e93b9b4c3c453e1cb1aeadab'


def private_url(value,hosts):
    if not isinstance(value,str):raise ValueError('ADMIN_PRIVATE_ENDPOINT_REQUIRED')
    u=urlsplit(value)
    if u.scheme!='http' or u.hostname not in hosts or u.username or u.password or u.query or u.fragment or u.path not in ('','/') or u.port is None or not 1024<=u.port<=65535:raise ValueError('ADMIN_PRIVATE_ENDPOINT_REQUIRED')
    return value.rstrip('/')


def registry(projects,passwords,*,origin,meta_url,studio_url,crypto_key,health_key,issuer,audience,public_jwk,operators,db_host='db',db_port=5432):
    ps=pool.checked(projects);ids={p['project_uuid'] for p in ps}
    if set(passwords)!=ids:raise ValueError('ADMIN_EXACT_CREDENTIAL_SCOPE_REQUIRED')
    for value in (origin,issuer):
        u=urlsplit(value)
        if u.scheme!='https' or u.username or u.password or u.query or u.fragment or not u.hostname:raise ValueError('ADMIN_HTTPS_ORIGIN_ISSUER_REQUIRED')
    if urlsplit(origin).path or origin!='https://'+urlsplit(origin).netloc:raise ValueError('ADMIN_HTTPS_ORIGIN_ISSUER_REQUIRED')
    if any(x in issuer for x in ('\n','\r','\0')):raise ValueError('ADMIN_HTTPS_ORIGIN_ISSUER_REQUIRED')
    selected_passwords=[st.strong_secret(v) for v in passwords.values()]
    if len(set(selected_passwords+[crypto_key,health_key]))!=len(selected_passwords)+2:raise ValueError('ADMIN_PROJECT_CREDENTIAL_REUSE')
    if not isinstance(audience,str) or not 5<=len(audience)<=128:raise ValueError('ADMIN_AUDIENCE_REQUIRED')
    st.strong_secret(crypto_key);st.strong_secret(health_key)
    if crypto_key==health_key:raise ValueError('ADMIN_SECRET_REUSE')
    if not isinstance(public_jwk,dict) or public_jwk.get('kty')!='OKP' or public_jwk.get('crv')!='Ed25519' or 'd' in public_jwk or not re.fullmatch('[A-Za-z0-9_-]{43}',public_jwk.get('x','')):raise ValueError('ADMIN_PUBLIC_VERIFIER_ONLY')
    if not isinstance(operators,list) or not 1<=len(operators)<=32:raise ValueError('ADMIN_OPERATOR_SCOPE_REQUIRED')
    subjects=set()
    for item in operators:
        if set(item)!={'subject','projects','can_query'} or not isinstance(item['subject'],str) or not 1<=len(item['subject'])<=160 or item['subject'] in subjects or type(item['can_query']) is not bool or not isinstance(item['projects'],list) or not item['projects'] or not set(item['projects'])<=ids or len(set(item['projects']))!=len(item['projects']):raise ValueError('ADMIN_OPERATOR_SCOPE_INVALID')
        subjects.add(item['subject'])
    if not re.fullmatch('[a-z0-9][a-z0-9.-]*',db_host) or db_host not in ('db','127.0.0.1') or type(db_port) is not int or not 1<=db_port<=65535:raise ValueError('ADMIN_DATABASE_ENDPOINT_INVALID')
    result=[]
    for p in ps:
        st.strong_secret(passwords[p['project_uuid']])
        result.append({'ref':p['project_uuid'],'name':p['slug'],'database':p['database'],'database_user':pool.role(p,'admin'),
            'connection':f'postgresql://{pool.role(p,"admin")}:{quote(passwords[p["project_uuid"]],safe="")}@{db_host}:{db_port}/{p["database"]}',
            'rest_url':'https://'+p['hostname']+'/rest/v1/'})
    return {'schema_version':1,'origin':origin,'meta_url':private_url(meta_url,('meta','127.0.0.1')),
        'studio_url':private_url(studio_url,('studio','127.0.0.1')),'crypto_key':crypto_key,'health_key':health_key,
        'issuer':issuer,'audience':audience,'public_jwk':public_jwk,'operators':operators,'projects':result}


def compile_bundle(projects,private):
    config=registry(projects,**private)
    raw=json.dumps(config,sort_keys=True,separators=(',',':'))+'\n';digest=hashlib.sha256(raw.encode()).hexdigest()
    env={'DIAL_PROJECT_ADMIN_REGISTRY':'/etc/dial-supabase/admin/registry.json','DIAL_PROJECT_ADMIN_REGISTRY_SHA256':digest,'DIAL_PROJECT_ADMIN_HOST':'0.0.0.0','DIAL_PROJECT_ADMIN_PORT':'9090'}
    return {'admin-registry.private.json':raw,'admin.env':b.env_text(env),
        'project-admin.overlay.yml':'\n'.join(['# Add ONE private administration gateway, reuse Studio and Meta unchanged.','services:','  project-admin:',
            '    image: "${DIAL_PROJECT_ADMIN_IMAGE:?exact admitted admin image required}"',
            '    restart: unless-stopped',
            '    user: "${DIAL_PROJECT_ADMIN_UID:?admitted non-root uid required}:${DIAL_PROJECT_ADMIN_GID:?admitted non-root gid required}"',
            '    read_only: true','    tmpfs: ["/tmp:size=16m,mode=1777"]','    mem_limit: 192m','    pids_limit: 64','    cpus: 0.5',
            '    security_opt: ["no-new-privileges:true"]','    cap_drop: ["ALL"]',
            '    env_file: ["/etc/dial-supabase/admin/admin.env"]',
            '    volumes: ["/etc/dial-supabase/admin/registry.json:/etc/dial-supabase/admin/registry.json:ro"]',
            '    depends_on: [meta, studio]','']),
        'admin-candidate.json':json.dumps({'kind':'STUDIO_COMPATIBLE_ADMIN_ROUTING_CANDIDATE','project_refs':[p['ref'] for p in config['projects']],
            'registry_sha256':digest,'adds_identity_issuer':False,'postgres_servers_added':0,'studio_instances_added':0,
            'production_deployed':False,'full_studio_ui_qualified':False},sort_keys=True,indent=2)+'\n'}
