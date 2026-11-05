#!/usr/bin/env python3
"""Staged shared Supabase Storage integration; no install/apply operation.

One upstream Storage service, one small registry database in the SAME PostgreSQL
cluster, project-specific database logins and original upstream tenant metadata.
The existing production single-tenant service must NOT be switched until its
original tenant, keys, metadata and object-path mapping have been preserved.
"""
from __future__ import annotations
import hashlib
import ipaddress
import json
import pathlib
import re
import secrets
import bootstrap as b

STORAGE_REF='01c95148a981a88b5f7e9014571a2926567b51e3'
STORAGE_IMAGE='supabase/storage-api:v1.74.0'
CONTROL_DB='dial_storage_control'
CONTROL_ROLE='dial_storage_control'


def tenant_id(p: dict) -> str:
    # Enforce original manifest identity, not caller supplied tenant headers.
    b.render.validate({'schema_version':1,'target_installation':b.render.ROOT,
        'allowed_postgres_service':'db','projects':[p]})
    return p['project_uuid'].replace('-','')


def native_id(value: str) -> str:
    if not isinstance(value,str) or not re.fullmatch(r'[a-z0-9][a-z0-9-]{0,62}',value):
        raise ValueError('UNSAFE_NATIVE_STORAGE_TENANT_ID')
    return value


def role(p: dict) -> str:
    return 'dial_'+tenant_id(p)+'_storage'


def validate_projects(projects: list[dict]) -> list[dict]:
    result=b.render.validate({'schema_version':1,'target_installation':b.render.ROOT,
        'allowed_postgres_service':'db','projects':projects})
    if any(p['database']==CONTROL_DB for p in result):raise ValueError('STORAGE_CONTROL_DATABASE_COLLISION')
    return result


def strong_secret(value: str) -> str:
    if not isinstance(value,str) or len(value)<32 or any(x in value for x in ('\n','\r','\0')):
        raise ValueError('STORAGE_STRONG_SECRET_REQUIRED')
    return value


def new_secrets(projects: list[dict]) -> dict:
    projects=validate_projects(projects)
    return {'control_password':secrets.token_urlsafe(48),
        'encryption_key':secrets.token_urlsafe(48),'admin_key':secrets.token_urlsafe(48),
        'projects':{tenant_id(p):secrets.token_urlsafe(48) for p in projects}}


def roles_sql(p: dict, password: str) -> str:
    validate_projects([p]);strong_secret(password)
    name=role(p);db=b.ident(p['database'])
    return '\n'.join(['\\set ON_ERROR_STOP on','BEGIN;',
        'SET LOCAL log_statement=none; SET LOCAL log_min_error_statement=panic;',
        f'CREATE ROLE {b.ident(name)} NOLOGIN NOINHERIT NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS CONNECTION LIMIT 6 PASSWORD {b.lit(b.scram(password))};',
        f'GRANT anon,authenticated,service_role TO {b.ident(name)};',
        f'GRANT CONNECT ON DATABASE {db} TO {b.ident(name)};',
        f'ALTER ROLE {b.ident(name)} SET search_path=storage,public,extensions;',
        f'ALTER ROLE {b.ident(name)} SET statement_timeout=15000;',
        'COMMIT;',''])


def schema_sql(p: dict) -> str:
    name=b.ident(role(p))
    return '\n'.join(['\\set ON_ERROR_STOP on','BEGIN;',
        f"DO $guard$ BEGIN IF current_database()<>{b.lit(p['database'])} OR NOT EXISTS(SELECT FROM dial_private.project_identity WHERE singleton AND project_uuid={b.lit(p['project_uuid'])}::uuid AND issuer={b.lit('https://'+p['hostname']+'/auth/v1')}) THEN RAISE EXCEPTION 'STORAGE_PROJECT_IDENTITY_MISMATCH'; END IF; END $guard$;",
        f'CREATE SCHEMA storage AUTHORIZATION {name};',
        'REVOKE ALL ON SCHEMA storage FROM PUBLIC;',
        'GRANT USAGE ON SCHEMA storage,public,extensions,auth TO anon,authenticated,service_role;',
        f'GRANT USAGE ON SCHEMA auth TO {name};',
        f'ALTER DEFAULT PRIVILEGES FOR ROLE {name} IN SCHEMA storage GRANT ALL ON TABLES TO service_role;',
        f'ALTER DEFAULT PRIVILEGES FOR ROLE {name} IN SCHEMA storage GRANT ALL ON SEQUENCES TO service_role;',
        'COMMIT;',''])


def control_roles_sql(password: str) -> str:
    strong_secret(password)
    return '\n'.join(['\\set ON_ERROR_STOP on','BEGIN;',
        'SET LOCAL log_statement=none; SET LOCAL log_min_error_statement=panic;',
        f'CREATE ROLE {b.ident(CONTROL_ROLE)} NOLOGIN NOINHERIT NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS CONNECTION LIMIT 6 PASSWORD {b.lit(b.scram(password))};',
        'COMMIT;',''])


def control_database_sql() -> str:
    return '\n'.join(['\\set ON_ERROR_STOP on',
        f'CREATE DATABASE {b.ident(CONTROL_DB)} OWNER {b.ident(CONTROL_ROLE)} TEMPLATE template0 CONNECTION LIMIT 12;',
        f'REVOKE ALL ON DATABASE {b.ident(CONTROL_DB)} FROM PUBLIC;',
        f'GRANT CONNECT ON DATABASE {b.ident(CONTROL_DB)} TO {b.ident(CONTROL_ROLE)};',''])


def hba(projects: list[dict], cidrs: list[str]) -> tuple[str,list[dict]]:
    # Reuse strict private-network validation. All existing rules follow this
    # complete reviewed prefix; do not infer the deployed manifest is complete.
    projects=validate_projects(projects)
    b.hba(projects,cidrs)
    records=[(p['database'],[b.names(p)[k] for k in ('auth','rest','migrate')]+[role(p)]) for p in projects]
    records.append((CONTROL_DB,[CONTROL_ROLE]))
    lines=['# Shared Storage + project logins; append ORIGINAL retained HBA rules.'];expected=[]
    for database,users in records:
        specs=[('host',database,ipaddress.ip_network(c),'scram-sha-256') for c in cidrs]
        specs += [('local','all',None,'reject'),('host','all',ipaddress.ip_network('0.0.0.0/0'),'reject'),('host','all',ipaddress.ip_network('::/0'),'reject')]
        for typ,db,net,method in specs:
            lines.append(' '.join([typ,db,','.join(users)]+([str(net)] if net else [])+[method]))
            expected.append({'type':typ,'database':[db],'user_name':users,
                'address':str(net.network_address) if net else None,'netmask':str(net.netmask) if net else None,'auth_method':method})
    return '\n'.join(lines)+'\n',expected


def activation_sql(projects: list[dict], expected: list[dict]) -> str:
    # Only these NEW storage/control logins are enabled; existing Auth/REST
    # logins are neither re-keyed nor relabelled.
    projects=validate_projects(projects)
    if not expected:raise ValueError('STORAGE_HBA_RULES_REQUIRED')
    checked=b.lit(json.dumps(expected,separators=(',',':')))
    lines=['\\set ON_ERROR_STOP on','BEGIN;','DO $guard$ DECLARE found jsonb; BEGIN',
        "IF EXISTS(SELECT FROM pg_hba_file_rules WHERE error IS NOT NULL) THEN RAISE EXCEPTION 'STORAGE_HBA_PARSE_ERROR'; END IF;",
        "IF pg_conf_load_time()<(pg_stat_file(current_setting('hba_file'))).modification THEN RAISE EXCEPTION 'STORAGE_HBA_RELOAD_REQUIRED'; END IF;",
        f"SELECT jsonb_agg(jsonb_build_object('type',type,'database',database,'user_name',user_name,'address',address,'netmask',netmask,'auth_method',auth_method) ORDER BY rule_number) INTO found FROM (SELECT * FROM pg_hba_file_rules ORDER BY rule_number LIMIT {len(expected)}) t;",
        f"IF found IS DISTINCT FROM {checked}::jsonb THEN RAISE EXCEPTION 'STORAGE_EXACT_HBA_PREFIX_REQUIRED'; END IF; END $guard$;"]
    for name in [*(role(p) for p in projects),CONTROL_ROLE]:
        lines += [f"DO $guard$ BEGIN IF NOT EXISTS(SELECT FROM pg_roles WHERE rolname={b.lit(name)} AND NOT rolcanlogin AND NOT rolsuper AND NOT rolcreatedb AND NOT rolcreaterole AND NOT rolreplication AND NOT rolbypassrls) THEN RAISE EXCEPTION 'STORAGE_ROLE_NOT_QUARANTINED'; END IF; END $guard$;",
                  f'ALTER ROLE {b.ident(name)} LOGIN;']
    return '\n'.join(lines+['COMMIT;',''])


def dsn(database: str, login: str, password: str, host='db', port=5432) -> str:
    b.ident(database);b.ident(login)
    if not re.fullmatch(r'[a-zA-Z0-9_.-]+',host) or type(port) is not int or not 1<=port<=65535:
        raise ValueError('STORAGE_DATABASE_ENDPOINT_INVALID')
    strong_secret(password)
    return f'postgresql://{login}:{b.quote(password,safe="")}@{host}:{port}/{database}'


def environment(secrets: dict, object_path='/var/lib/storage',host='db',port=5432, *, object_bucket: str, preserved_tenants=()) -> dict[str,str]:
    if not pathlib.Path(object_path).is_absolute() or '..' in pathlib.Path(object_path).parts:
        raise ValueError('ABSOLUTE_STORAGE_OBJECT_PATH_REQUIRED')
    for key in ('control_password','encryption_key','admin_key'):strong_secret(secrets.get(key))
    if len(set(secrets[k] for k in ('control_password','encryption_key','admin_key')))!=3:raise ValueError('STORAGE_SECRETS_MUST_BE_DISTINCT')
    if not isinstance(secrets.get('projects'),dict):raise ValueError('STORAGE_TENANT_BINDINGS_REQUIRED')
    native_id(object_bucket)
    ids=sorted(set(native_id(x) for x in [*secrets['projects'],*preserved_tenants]))
    if not ids:raise ValueError('STORAGE_TENANT_BINDINGS_REQUIRED')
    return {'MULTI_TENANT':'true','SERVER_HOST':'0.0.0.0','SERVER_PORT':'5000','SERVER_ADMIN_PORT':'5001',
        'SERVER_REGION':'dial','SERVER_ADMIN_API_KEYS':secrets['admin_key'],
        'AUTH_ENCRYPTION_KEY':secrets['encryption_key'],'ADMIN_RETURN_TENANT_SENSITIVE_DATA':'false',
        'DATABASE_MULTITENANT_URL':dsn(CONTROL_DB,CONTROL_ROLE,secrets['control_password'],host,port),
        'DATABASE_MULTITENANT_MAX_CONNECTIONS':'4','DATABASE_MAX_CONNECTIONS':'4',
        'DATABASE_FREE_POOL_AFTER_INACTIVITY':'10000','DATABASE_POOL_DRAIN_TIMEOUT':'10000',
        'DATABASE_STATEMENT_TIMEOUT':'15000','DB_INSTALL_ROLES':'false','DB_SUPER_USER':'service_role',
        'DB_ALLOW_MIGRATION_REFRESH':'false','DB_MIGRATIONS_STRATEGY':'on_request',
        'REQUEST_X_FORWARDED_HOST_REGEXP':'^('+ '|'.join(re.escape(x) for x in ids) +r')\.storage\.internal$',
        'REQUEST_ALLOW_X_FORWARDED_PATH':'true','STORAGE_BACKEND':'file',
        'STORAGE_FILE_BACKEND_PATH':object_path,'STORAGE_S3_BUCKET':object_bucket,
        'UPLOAD_FILE_SIZE_LIMIT':'10485760','UPLOAD_FILE_SIZE_LIMIT_STANDARD':'10485760',
        'IMAGE_TRANSFORMATION_ENABLED':'false','PG_QUEUE_ENABLE':'false','STORAGE_LIFECYCLE_ENABLED':'false',
        'VECTOR_BUCKETS_ENABLED':'false','VECTOR_STORE_MIGRATIONS_ENABLED':'false',
        'OTEL_METRICS_ENABLED':'false','PROMETHEUS_METRICS_ENABLED':'false','LOG_LEVEL':'error',
        'LOGFLARE_ENABLED':'false','WORKERS_NUM':'1','EXPOSE_DOCS':'false'}


def registration(p: dict, project_secrets: dict, shared: dict, keys: dict,host='db',port=5432) -> dict:
    validate_projects([p]);strong_secret(project_secrets['jwt'])
    if set(keys)!={'anon','service_role'}:raise ValueError('STORAGE_EXACT_PROJECT_API_KEYS_REQUIRED')
    validate_credential_keys(p,{'project_uuid':p['project_uuid'],'jwt_secret':project_secrets['jwt'],'anon_key':keys['anon'],'service_role_key':keys['service_role']})
    for value in keys.values():
        if not isinstance(value,str) or not re.fullmatch(r'[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+',value):raise ValueError('STORAGE_PROJECT_JWT_KEYS_REQUIRED')
    return {'anonKey':keys['anon'],'serviceKey':keys['service_role'],'jwtSecret':project_secrets['jwt'],
        'databaseUrl':dsn(p['database'],role(p),shared['projects'][tenant_id(p)],host,port),
        'maxConnections':4,'fileSizeLimit':10485760,'features':{'imageTransformation':{'enabled':False},
            's3Protocol':{'enabled':False},'icebergCatalog':{'enabled':False},'vectorBuckets':{'enabled':False}}}


def gateway(p: dict, anon: str, service: str, upstream='storage:5000', *, preserved_tenant_id: str | None = None) -> str:
    if not re.fullmatch(r'[a-z0-9.-]+:[0-9]{1,5}',upstream):raise ValueError('FIXED_STORAGE_UPSTREAM_REQUIRED')
    if not 1<=int(upstream.rsplit(':',1)[1])<=65535:raise ValueError('FIXED_STORAGE_UPSTREAM_REQUIRED')
    text=b.gateway(p,anon,service)
    var='dial_'+tenant_id(p)
    routing_tenant=native_id(preserved_tenant_id) if preserved_tenant_id is not None else tenant_id(p)
    # Signed/public GETs must work without an API-key header. Upstream validates
    # signed URLs and bucket visibility; this does not authorize arbitrary APIs.
    maps='\n'.join([
        f'map "$request_method:$uri" ${var}_storage_public {{ default 0; ~^(GET|HEAD):/storage/v1/object/(sign|public)/ 1; }}',
        f'map "${var}_key:${var}_storage_public" ${var}_storage_admit {{ default 1; ":0" 0; }}',''])
    # Hash configuration must precede EVERY map: nginx initializes defaults
    # at the first map, so prepending maps makes later hash directives invalid.
    anchor='variables_hash_bucket_size 128;\n'
    if text.count(anchor)!=1:raise ValueError('STORAGE_GATEWAY_HASH_CONFIG_CHANGED')
    text=text.replace(anchor,anchor+maps,1)
    headers=[f'        proxy_set_header Host {p["hostname"]};',
        f'        proxy_set_header X-Forwarded-Host {routing_tenant}.storage.internal;',
        '        proxy_set_header X-Forwarded-Proto https;','        proxy_set_header X-Forwarded-Port 443;',
        '        proxy_set_header X-Forwarded-Prefix /storage/v1;','        proxy_set_header X-Forwarded-Path "";',
        '        proxy_set_header X-Forwarded-For $remote_addr;','        proxy_set_header X-Real-IP $remote_addr;',
        '        proxy_set_header Forwarded "";','        proxy_set_header X-Tenant-ID "";',
        '        proxy_set_header X-Project-ID "";',f'        proxy_set_header X-Dial-Project-ID {p["project_uuid"]};',
        f'        proxy_set_header Authorization ${var}_authorization;',
        '        proxy_connect_timeout 5s;','        proxy_read_timeout 30s;']
    block='\n'.join(['    location ^~ /storage/v1/ {',f'        if (${var}_storage_admit = 0) {{ return 401; }}',*headers,
        f'        proxy_pass http://{upstream}/;','    }'])
    old='    location ^~ /storage/v1/ { return 503; }'
    if text.count(old)!=1:raise ValueError('STORAGE_GATEWAY_BASE_CHANGED')
    return text.replace(old,block)


def overlay() -> str:
    return '\n'.join(['# STAGED: replaces configuration of EXISTING storage service only.',
        '# Preserve original VAN tenant/object path before activating multi-tenant mode.',
        'services:','  storage:',f'    image: {STORAGE_IMAGE}',
        '    env_file: ["/etc/dial-supabase/shared-storage/storage.env"]',
        '    environment:',
        '      MULTI_TENANT: "true"',
        '      IMAGE_TRANSFORMATION_ENABLED: "false"',
        '      ENABLE_IMAGE_TRANSFORMATION: "false"',
        '      IS_MULTITENANT: "true"','      TENANT_ID: ""','      DATABASE_URL: ""','      DATABASE_POOL_URL: ""',
        '      ANON_KEY: ""','      SERVICE_KEY: ""','      AUTH_JWT_SECRET: ""',
        '    mem_limit: 512m','    pids_limit: 192','    cpus: 0.75',
        '    security_opt: ["no-new-privileges:true"]',
        '# No new PostgreSQL server or per-project Storage service.',''])


def compile_bundle(projects: list[dict], credentials: dict, shared: dict,
                   cidrs: list[str], *, object_bucket: str, object_path: str,
                   preserved_tenants: dict[str,str]) -> dict[str,str]:
    """Private staged inputs only. Preserve legacy native IDs explicitly.

    This does not discover or attest existing VAN state. It has no network,
    SQL execution, tenant-upsert, service-restart or deployment side effects.
    Credentials must be the ORIGINAL project values, not regenerated.
    """
    projects=validate_projects(projects)
    ids={p['project_uuid'] for p in projects}
    if not isinstance(credentials,dict) or not isinstance(preserved_tenants,dict) or set(credentials)!=ids or not set(preserved_tenants)<=ids:
        raise ValueError('STORAGE_EXACT_PROJECT_CREDENTIAL_BINDING_REQUIRED')
    if len({strong_secret(credentials[x]['jwt_secret']) for x in ids})!=len(ids):raise ValueError('STORAGE_PROJECT_SIGNING_SECRETS_MUST_BE_DISTINCT')
    if set(shared['projects'])!={tenant_id(p) for p in projects}:raise ValueError('STORAGE_PROJECT_DB_CREDENTIAL_SET_MISMATCH')
    passwords=[strong_secret(x) for x in shared['projects'].values()]+[strong_secret(shared['control_password'])]
    if len(set(passwords))!=len(passwords):raise ValueError('STORAGE_DATABASE_PASSWORDS_MUST_BE_DISTINCT')
    native={p['project_uuid']:native_id(preserved_tenants.get(p['project_uuid'],tenant_id(p))) for p in projects}
    if len(set(native.values()))!=len(native):raise ValueError('STORAGE_NATIVE_TENANT_COLLISION')
    env=environment(shared,object_path,object_bucket=object_bucket,preserved_tenants=native.values())
    outputs={'shared-storage.env':storage_env_text(env),'shared-storage.overlay.yml':overlay(),
        'control-role.sql':control_roles_sql(shared['control_password']),
        'control-database.sql':control_database_sql()}
    for p in projects:
        c=credentials[p['project_uuid']]
        if set(c)!={'project_uuid','jwt_secret','anon_key','service_role_key'} or c['project_uuid']!=p['project_uuid']:
            raise ValueError('STORAGE_PROJECT_CREDENTIALS_INVALID')
        # Project JWT values and claims are verified before sending secrets to a
        # tenant registration API. A caller label never proves credential scope.
        validate_credential_keys(p,c)
        keys={'anon':c['anon_key'],'service_role':c['service_role_key']}
        slug=p['slug'];tid=native[p['project_uuid']]
        outputs[slug+'.storage-role.sql']=roles_sql(p,shared['projects'][tenant_id(p)])
        outputs[slug+'.storage-schema.sql']=schema_sql(p)
        outputs[slug+'.nginx.conf']=gateway(p,keys['anon'],keys['service_role'],preserved_tenant_id=tid)
        outputs[slug+'.tenant-registration.private.json']=json.dumps({
            'method':'POST','private_admin_path':'/tenants/'+tid,
            'body':registration(p,{'jwt':c['jwt_secret']},shared,keys),
            'existing_tenant_action':'REFUSE_AND_RECONCILE_NO_UPSERT',
            'executed':False},indent=2,sort_keys=True)+'\n'
    prefix,expected=hba(projects,cidrs)
    outputs['storage-projects.hba-prefix.conf']=prefix
    outputs['storage-activate.sql']=activation_sql(projects,expected)
    outputs['shared-storage-candidate.json']=json.dumps({
        'schema_version':1,'kind':'SHARED_STORAGE_PRIVATE_CANDIDATE_NOT_DEPLOYED',
        'storage_source_commit':STORAGE_REF,'postgres_instances_added':0,'storage_services_added':0,
        'project_native_tenants':native,'preserved_object_bucket':object_bucket,
        'preserved_object_path':object_path,'files':{n:hashlib.sha256(c.encode()).hexdigest() for n,c in outputs.items()},
        'production_deploy_authorized':False},indent=2,sort_keys=True)+'\n'
    return outputs


def validate_credential_keys(p: dict, c: dict) -> None:
    import base64,hmac,time
    secret=strong_secret(c['jwt_secret'])
    decode=lambda s:base64.urlsafe_b64decode(s+'='*(-len(s)%4))
    for role,key in (('anon',c['anon_key']),('service_role',c['service_role_key'])):
        try:
            head,body,signature=key.split('.')
            claims=json.loads(decode(body),object_pairs_hook=b.render.unique_object)
            algorithm=json.loads(decode(head),object_pairs_hook=b.render.unique_object)
            signed=hmac.digest(secret.encode(),(head+'.'+body).encode(),'sha256')
            if not hmac.compare_digest(signed,decode(signature)) or algorithm.get('alg')!='HS256':raise ValueError()
            if claims.get('role')!=role or claims.get('iss')!='https://'+p['hostname']+'/auth/v1' or claims.get('aud')!='authenticated':raise ValueError()
            if type(claims.get('exp')) not in (int,float) or not claims['exp']>time.time():raise ValueError()
            if claims.get('project_ref')!=p['project_uuid']:raise ValueError()
        except (ValueError,TypeError,KeyError,UnicodeError):
            raise ValueError('STORAGE_PROJECT_SIGNING_CREDENTIAL_MISMATCH') from None


def storage_env_text(env: dict[str,str]) -> str:
    # Compose env_file single-quoted values are literal: preserve the required
    # regex end anchor ($), without enabling variable interpolation.
    for key,value in env.items():
        if not re.fullmatch(r'[A-Z][A-Z0-9_]*',key) or not isinstance(value,str) or any(c in value for c in ("'","\n","\r","\0")):
            raise ValueError('STORAGE_ENV_LITERAL_INVALID')
    return ''.join(key+"='"+value+"'\n" for key,value in sorted(env.items()))


def legacy_envoy_candidate(source: str, expected_source_sha256: str,
                           original_tenant_id: str) -> tuple[str,dict]:
    """Patch ONLY the original donor Storage route in an exact reviewed template.

    The original public VAN Auth/REST API and all other Envoy routes are retained.
    Original keys, DB and native object namespace must already be registered.
    This returns a candidate; it neither writes nor reloads the actual gateway.
    """
    tid=native_id(original_tenant_id)
    if not re.fullmatch(r'[a-f0-9]{64}',expected_source_sha256) or hashlib.sha256(source.encode()).hexdigest()!=expected_source_sha256:
        raise ValueError('LEGACY_GATEWAY_SOURCE_DIGEST_MISMATCH')
    anchor='                      - match:\n                          prefix: /storage/v1/\n'
    if source.count(anchor)!=1:raise ValueError('EXACT_LEGACY_STORAGE_ROUTE_REQUIRED')
    start=source.index(anchor);end=source.find('\n                      - match:',start+len(anchor))
    if end<0:raise ValueError('LEGACY_ROUTE_BOUNDARY_UNOBSERVED')
    end+=1  # Include the final route newline, even when headers are its last field.
    block=source[start:end]
    if 'request_headers_to_remove:' in block or 'key: X-Forwarded-Host' in block:
        raise ValueError('LEGACY_ROUTE_ALREADY_MODIFIED_RECONCILE')
    old=('                        request_headers_to_add:\n'
         '                          - header:\n'
         '                              key: X-Forwarded-Prefix\n'
         '                              value: /storage/v1\n'
         '                            append_action: ADD_IF_ABSENT\n')
    if block.count(old)!=1:raise ValueError('LEGACY_HEADER_CONTRACT_CHANGED')
    new=old.replace('ADD_IF_ABSENT','OVERWRITE_IF_EXISTS_OR_ADD')
    new+=('                          - header:\n'
          '                              key: X-Forwarded-Host\n'
          '                              value: '+tid+'.storage.internal\n'
          '                            append_action: OVERWRITE_IF_EXISTS_OR_ADD\n'
          '                        request_headers_to_remove:\n'
          '                          - x-tenant-id\n'
          '                          - x-project-id\n'
          '                          - x-dial-project-id\n'
          '                          - x-forwarded-path\n'
          '                          - forwarded\n')
    revised=source[:start]+block.replace(old,new,1)+source[end:]
    return revised,{'schema_version':1,'kind':'LEGACY_STORAGE_GATEWAY_CANDIDATE_ONLY',
        'source_sha256':expected_source_sha256,'result_sha256':hashlib.sha256(revised.encode()).hexdigest(),
        'preserved_native_tenant_id':tid,'changed_route':'/storage/v1/',
        'other_routes_byte_preserved':True,'deployed':False,
        'requires':['original_tenant_and_keys_registered','original_object_bucket_and_mount_preserved','Envoy_native_config_validation','owner_release_admission']}


def main(argv=None) -> int:
    import argparse
    import recovery
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest',type=pathlib.Path,required=True)
    parser.add_argument('--private-input',type=pathlib.Path,required=True)
    parser.add_argument('--client-cidr',action='append',required=True)
    parser.add_argument('--out',type=pathlib.Path,required=True)
    args=parser.parse_args(argv)
    try:
        projects,_=b.render.load_manifest(args.manifest)
        value=recovery.load_private_json(args.private_input)
        if not isinstance(value,dict) or set(value)!={'credentials','shared','object_bucket','object_path','preserved_tenants'}:
            raise ValueError('STORAGE_PRIVATE_INPUT_FIELDS_INVALID')
        outputs=compile_bundle(projects,value['credentials'],value['shared'],args.client_cidr,
            object_bucket=value['object_bucket'],object_path=value['object_path'],preserved_tenants=value['preserved_tenants'])
        b.render.write_bundle(args.out,outputs)
        print(json.dumps({'state':'PRIVATE_STORAGE_CANDIDATE_WRITTEN_NOT_DEPLOYED',
            'project_count':len(projects),'candidate_sha256':hashlib.sha256(outputs['shared-storage-candidate.json'].encode()).hexdigest()}))
        return 0
    except (ValueError,TypeError,KeyError,OSError):
        print('REFUSED_SHARED_STORAGE_CANDIDATE')
        return 2

if __name__=='__main__':raise SystemExit(main())
