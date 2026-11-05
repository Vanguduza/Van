#!/usr/bin/env python3
"""Staged one-service Realtime configuration; never execute or deploy it.

Per-project DB logins, JWTs and WAL slots; one shared control database/runtime.
Requires patched >=2.146 upstream for GHSA-2rcv-vpjw-5g6c, plus the exact DIAL
single-cluster slot-name fix. No production runtime or canonical role is edited.
"""
from __future__ import annotations
import base64
import hashlib
import hmac
import ipaddress
import json
import pathlib
import re
import secrets
import time
import bootstrap as b
import shared_storage as storage

VERSION='2.152.0'
SOURCE_COMMIT='c8b27c7a37a5c60fee5b5a11632231d8e2c0a8c9'
BASE_AMD64_IMAGE='supabase/realtime@sha256:6769b99a2a9d2e028f1bce6e99d9e9ef5ac0b8141c53f2c8bdc1e9eb3a952cc9'
SCHEMA_SHA256='1c03ab307e3df0799040e839cf696a9e316a2c432c42c85a2135b57764ba2efe'
CONTROL_DB='dial_realtime_control'
CONTROL_ROLE='dial_realtime_registry'
CANONICAL_ROLES=('postgres','supabase_admin','dashboard_user','supabase_realtime_admin')

def projects_checked(projects: list[dict]) -> list[dict]:
    ps=storage.validate_projects(projects)
    if any(p['database']==CONTROL_DB for p in ps):raise ValueError('REALTIME_CONTROL_DATABASE_COLLISION')
    return ps

def tenant_id(p: dict) -> str:
    projects_checked([p]);return p['project_uuid'].replace('-','')

def native_id(value: str) -> str:
    storage.native_id(value)
    if value.endswith('-private') or ':' in value:raise ValueError('REALTIME_TENANT_NAMESPACE_COLLISION')
    return value

def role(p: dict) -> str:
    return 'dial_'+tenant_id(p)+'_realtime'

def cdc_slot(p: dict) -> str:
    return 'dial_rt_cdc_'+tenant_id(p)

def new_secrets(projects: list[dict]) -> dict:
    return {'control_password':secrets.token_urlsafe(48),'admin_jwt_secret':secrets.token_urlsafe(48),
        'metrics_jwt_secret':secrets.token_urlsafe(48),'secret_key_base':secrets.token_urlsafe(64),
        'db_encryption_key':secrets.token_hex(8),'cookie':secrets.token_hex(32),
        'projects':{tenant_id(p):secrets.token_urlsafe(48) for p in projects_checked(projects)}}

def admin_token(secret: str, now: int|None=None) -> str:
    storage.strong_secret(secret);now=int(time.time()) if now is None else now
    enc=lambda obj:base64.urlsafe_b64encode(json.dumps(obj,separators=(',',':'),sort_keys=True).encode()).decode().rstrip('=')
    body=enc({'alg':'HS256','typ':'JWT'})+'.'+enc({'role':'dial_realtime_admin','iat':now,'exp':now+3600})
    return body+'.'+base64.urlsafe_b64encode(hmac.digest(secret.encode(),body.encode(),'sha256')).decode().rstrip('=')

def role_sql(p: dict,password: str) -> str:
    projects_checked([p]);storage.strong_secret(password);name=role(p)
    return '\n'.join(['\\set ON_ERROR_STOP on','BEGIN;',
        'SET LOCAL log_statement=none;','SET LOCAL log_min_error_statement=panic;',
        f"DO $check$ BEGIN IF EXISTS (SELECT FROM pg_roles WHERE rolname={b.lit(name)}) THEN RAISE EXCEPTION 'REALTIME_ROLE_EXISTS_RECONCILE'; END IF;",
        "IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname='supabase_realtime_admin' AND NOT rolsuper AND NOT rolcanlogin AND NOT rolcreaterole AND NOT rolcreatedb AND NOT rolreplication AND NOT rolbypassrls) THEN RAISE EXCEPTION 'CANONICAL_REALTIME_ROLE_REQUIRED'; END IF; IF NOT has_parameter_privilege('supabase_realtime_admin','log_min_messages','SET') THEN RAISE EXCEPTION 'CANONICAL_REALTIME_PARAMETER_PERMISSION_REQUIRED'; END IF; END $check$;",
        f'CREATE ROLE {b.ident(name)} NOLOGIN INHERIT NOSUPERUSER NOCREATEDB NOCREATEROLE REPLICATION NOBYPASSRLS CONNECTION LIMIT 16 PASSWORD {b.lit(b.scram(password))};',
        f'GRANT supabase_realtime_admin TO {b.ident(name)};',
        f'GRANT CONNECT ON DATABASE {b.ident(p["database"])} TO {b.ident(name)};',
        f'ALTER ROLE {b.ident(name)} SET search_path=realtime,public,extensions;',
        f'ALTER ROLE {b.ident(name)} SET statement_timeout=15000;','COMMIT;',''])

def control_sql(password: str) -> tuple[str,str]:
    storage.strong_secret(password)
    roles='\n'.join(['\\set ON_ERROR_STOP on','BEGIN;','SET LOCAL log_statement=none;',
        'SET LOCAL log_min_error_statement=panic;',
        f'CREATE ROLE {b.ident(CONTROL_ROLE)} NOLOGIN NOINHERIT NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS CONNECTION LIMIT 8 PASSWORD {b.lit(b.scram(password))};','COMMIT;',''])
    db='\n'.join(['\\set ON_ERROR_STOP on',f'CREATE DATABASE {b.ident(CONTROL_DB)} OWNER {b.ident(CONTROL_ROLE)} TEMPLATE template0 CONNECTION LIMIT 12;',
        f'REVOKE ALL ON DATABASE {b.ident(CONTROL_DB)} FROM PUBLIC;',f'GRANT CONNECT ON DATABASE {b.ident(CONTROL_DB)} TO {b.ident(CONTROL_ROLE)};',''])
    return roles,db

def control_schema_sql() -> str:
    return '\n'.join(['\\set ON_ERROR_STOP on','BEGIN;',
        f"DO $check$ BEGIN IF current_database()<>{b.lit(CONTROL_DB)} THEN RAISE EXCEPTION 'WRONG_REALTIME_REGISTRY_DATABASE'; END IF; END $check$;",
        f'CREATE SCHEMA _realtime AUTHORIZATION {b.ident(CONTROL_ROLE)};',
        'REVOKE ALL ON SCHEMA public FROM PUBLIC;','COMMIT;',''])

def fresh_schema_sql(p: dict,upstream_dump: str) -> str:
    projects_checked([p])
    if hashlib.sha256(upstream_dump.encode()).hexdigest()!=SCHEMA_SHA256:
        raise ValueError('REALTIME_EXACT_UPSTREAM_SCHEMA_REQUIRED')
    checks=['\\set ON_ERROR_STOP on','BEGIN;',
        f"DO $check$ BEGIN IF current_database()<>{b.lit(p['database'])} THEN RAISE EXCEPTION 'WRONG_REALTIME_PROJECT_DATABASE'; END IF;",
        "IF EXISTS(SELECT FROM pg_namespace WHERE nspname='realtime') THEN RAISE EXCEPTION 'REALTIME_SCHEMA_EXISTS_RECONCILE'; END IF;",
        f"IF NOT EXISTS(SELECT FROM dial_private.project_identity WHERE project_uuid={b.lit(p['project_uuid'])}::uuid) THEN RAISE EXCEPTION 'REALTIME_PROJECT_IDENTITY_MISMATCH'; END IF;"]
    for r in CANONICAL_ROLES:
        checks.append(f"IF NOT EXISTS(SELECT FROM pg_roles WHERE rolname={b.lit(r)}) THEN RAISE EXCEPTION 'CANONICAL_REALTIME_ROLES_REQUIRED'; END IF;")
    checks+=['END $check$;',upstream_dump,
        f'GRANT SELECT ON realtime.schema_migrations TO {b.ident(role(p))};',
        f'GRANT USAGE ON SCHEMA public,auth,extensions,realtime TO {b.ident(role(p))};',
        'COMMIT;','']
    return '\n'.join(checks)

def publication_sql(p: dict,tables: list[tuple[str,str]]) -> str:
    projects_checked([p])
    if not tables or len(tables)>100 or len(set(tables))!=len(tables):raise ValueError('EXPLICIT_REALTIME_TABLES_REQUIRED')
    for schema,table in tables:
        b.ident(schema);b.ident(table)
        if schema!='public':raise ValueError('REALTIME_ONLY_REVIEWED_PUBLIC_TABLES')
    selected=', '.join(b.ident(s)+'.'+b.ident(t) for s,t in tables)
    return '\n'.join(['\\set ON_ERROR_STOP on','BEGIN;',
        f"DO $check$ BEGIN IF current_database()<>{b.lit(p['database'])} THEN RAISE EXCEPTION 'WRONG_REALTIME_PUBLICATION_DATABASE'; END IF; END $check$;",
        f'CREATE PUBLICATION supabase_realtime FOR TABLE {selected} WITH (publish=\'insert,update,delete\');',
        'CREATE PUBLICATION supabase_realtime_messages_publication FOR TABLE realtime.messages;',
        f'GRANT SELECT ON {selected} TO {b.ident(role(p))};','COMMIT;',''])

def hba(projects: list[dict],cidrs: list[str],*,include_storage: bool=True) -> tuple[str,list[dict]]:
    projects=projects_checked(projects)
    old,tail=(storage.hba(projects,cidrs) if include_storage else b.hba(projects,cidrs))
    nets=[ipaddress.ip_network(c,strict=True) for c in cidrs]
    lines=['# First-match Realtime prefix; explicitly prohibit physical replication.'];expected=[]
    def add(kind,db,users,method,net=None):
        expected.append({'type':kind,'database':[db],'user_name':users,'address':str(net.network_address) if net else None,'netmask':str(net.netmask) if net else None,'auth_method':method})
        lines.append(' '.join([kind,db,','.join(users)]+([str(net)] if net else [])+[method]))
    for p in projects:
        users=[role(p)]
        add('local','replication',users,'reject')
        add('host','replication',users,'reject',ipaddress.ip_network('0.0.0.0/0'))
        add('host','replication',users,'reject',ipaddress.ip_network('::/0'))
        for net in nets:add('host',p['database'],users,'scram-sha-256',net)
        add('local','all',users,'reject')
        add('host','all',users,'reject',ipaddress.ip_network('0.0.0.0/0'))
        add('host','all',users,'reject',ipaddress.ip_network('::/0'))
    for net in nets:add('host',CONTROL_DB,[CONTROL_ROLE],'scram-sha-256',net)
    add('local','all',[CONTROL_ROLE],'reject')
    add('host','all',[CONTROL_ROLE],'reject',ipaddress.ip_network('0.0.0.0/0'))
    add('host','all',[CONTROL_ROLE],'reject',ipaddress.ip_network('::/0'))
    return '\n'.join(lines)+'\n'+old,expected+tail

def activation_sql(projects: list[dict],expected: list[dict]) -> str:
    projects=projects_checked(projects)
    if not expected:raise ValueError('REALTIME_HBA_RULES_REQUIRED')
    encoded=b.lit(json.dumps(expected,separators=(',',':')))
    out=['\\set ON_ERROR_STOP on','BEGIN;','DO $check$ DECLARE actual jsonb; BEGIN',
        "IF EXISTS(SELECT FROM pg_hba_file_rules WHERE error IS NOT NULL) THEN RAISE EXCEPTION 'REALTIME_HBA_PARSE_ERROR'; END IF;",
        "IF pg_conf_load_time()<(pg_stat_file(current_setting('hba_file'))).modification THEN RAISE EXCEPTION 'REALTIME_HBA_RELOAD_REQUIRED'; END IF;",
        f"SELECT jsonb_agg(jsonb_build_object('type',type,'database',database,'user_name',user_name,'address',address,'netmask',netmask,'auth_method',auth_method) ORDER BY rule_number) INTO actual FROM (SELECT * FROM pg_hba_file_rules ORDER BY rule_number LIMIT {len(expected)}) r;",
        f"IF actual IS DISTINCT FROM {encoded}::jsonb THEN RAISE EXCEPTION 'REALTIME_EXACT_HBA_PREFIX_REQUIRED'; END IF;",'END $check$;']
    for name,replication in [(role(p),True) for p in projects]+[(CONTROL_ROLE,False)]:
        out.extend([f"DO $check$ BEGIN IF NOT EXISTS(SELECT FROM pg_roles WHERE rolname={b.lit(name)} AND NOT rolcanlogin AND NOT rolsuper AND NOT rolcreaterole AND NOT rolcreatedb AND NOT rolbypassrls AND rolreplication={str(replication).lower()}) THEN RAISE EXCEPTION 'REALTIME_ROLE_NOT_QUARANTINED'; END IF; END $check$;",f'ALTER ROLE {b.ident(name)} LOGIN;'])
    return '\n'.join(out+['COMMIT;',''])

def environment(shared: dict,host='db',port=5432) -> dict[str,str]:
    storage.dsn(CONTROL_DB,CONTROL_ROLE,shared['control_password'],host,port)
    for key in ('control_password','admin_jwt_secret','metrics_jwt_secret','secret_key_base','cookie'):storage.strong_secret(shared[key])
    if not isinstance(shared['db_encryption_key'],str) or len(shared['db_encryption_key'].encode())!=16:raise ValueError('REALTIME_ENCRYPTION_KEY_MUST_BE_16_BYTES')
    if len({shared[k] for k in ('control_password','admin_jwt_secret','metrics_jwt_secret','secret_key_base','cookie')})!=5:raise ValueError('REALTIME_SECRETS_MUST_BE_DISTINCT')
    return {'PORT':'4000','DB_HOST':host,'DB_PORT':str(port),'DB_NAME':CONTROL_DB,'DB_USER':CONTROL_ROLE,
        'DB_PASSWORD':shared['control_password'],'DB_AFTER_CONNECT_QUERY':'SET search_path TO _realtime',
        'DB_POOL_SIZE':'2','DB_REPLICA_POOL_SIZE':'1','DB_IP_VERSION':'ipv4','DB_SSL':'false',
        'DB_ENC_KEY':shared['db_encryption_key'],'API_JWT_SECRET':shared['admin_jwt_secret'],
        'METRICS_JWT_SECRET':shared['metrics_jwt_secret'],'SECRET_KEY_BASE':shared['secret_key_base'],
        'RELEASE_COOKIE':shared['cookie'],'APP_NAME':'dial_realtime','REGION':'local','SEED_SELF_HOST':'false',
        'RUN_JANITOR':'true','JANITOR_SCHEDULE_TIMER_IN_MS':'3600000','JANITOR_SCHEDULE_RANDOMIZE':'false','JANITOR_CHUNK_SIZE':'1','DISABLE_HEALTHCHECK_LOGGING':'true','LOG_LEVEL':'error',
        'ERL_AFLAGS':'-proto_dist inet_tcp','ERL_FLAGS':'+S 2:2 +SDcpu 1 +SDio 1',
        'DNS_NODES':'','BROADCAST_POOL_SIZE':'2','MIGRATION_PARTITION_SLOTS':'2',
        'MAX_CONNECTIONS':'128','TENANT_MAX_USERS':'64','METRICS_PUSHER_ENABLED':'false',
        'TENANT_METRICS_PUSHER_ENABLED':'false','RUN_LATENCY_PINGER':'false'}

def registration(p: dict,credentials: dict,shared: dict,migrations_count: int,host='db',port=5432,*,preserved_tenant_id: str|None=None) -> dict:
    projects_checked([p]);storage.validate_credential_keys(p,credentials)
    if type(migrations_count) is not int or not 1<=migrations_count<=1000:raise ValueError('NATIVE_MIGRATION_COUNT_REQUIRED')
    tid=native_id(preserved_tenant_id) if preserved_tenant_id is not None else tenant_id(p)
    storage.dsn(p['database'],role(p),shared['projects'][tenant_id(p)],host,port)
    return {'tenant':{'name':p['slug'],'external_id':tid,'jwt_secret':credentials['jwt_secret'],
        'postgres_cdc_default':'postgres_cdc_rls','migrations_ran':migrations_count,
        'max_concurrent_users':64,'max_events_per_second':100,'max_presence_events_per_second':100,
        'max_bytes_per_second':1048576,'max_channels_per_client':12,'max_joins_per_second':30,
        'presence_enabled':True,'private_only':True,'broadcast_adapter':'phoenix',
        'extensions':[{'type':'postgres_cdc_rls','settings':{'db_host':host,'db_port':str(port),
            'db_name':p['database'],'db_user':role(p),'db_password':shared['projects'][tenant_id(p)],
            'region':'local','ssl_enforced':False,'db_pool':1,'subs_pool_size':1,'subcriber_pool_size':1,
            'poll_interval_ms':100,'poll_max_changes':50,'poll_max_record_bytes':1048576,
            'publication':'supabase_realtime','slot_name':cdc_slot(p)}}]}}

def gateway(p: dict,anon: str,service: str,upstream='realtime:4000',*,base_config: str|None=None,preserved_tenant_id: str|None=None) -> str:
    projects_checked([p])
    if not re.fullmatch(r'[a-z0-9.-]+:[0-9]{1,5}',upstream) or not 1<=int(upstream.rsplit(':',1)[1])<=65535:raise ValueError('FIXED_REALTIME_UPSTREAM_REQUIRED')
    tid=native_id(preserved_tenant_id) if preserved_tenant_id is not None else tenant_id(p)
    for key in (anon,service):
        if not re.fullmatch(r'[A-Za-z0-9_.-]+',key):raise ValueError('INVALID_REALTIME_API_KEY')
    text=base_config if base_config is not None else b.gateway(p,anon,service)
    var='dial_'+tenant_id(p)
    maps=[f'map "$http_apikey:$arg_apikey" ${var}_rt_key {{ default "";']
    for key in (anon,service):
        for pair in (key+':',':'+key,key+':'+key):maps.append(f'  "{pair}" "{key}";')
    capture='rtb_'+hashlib.sha256(p['project_uuid'].encode()).hexdigest()[:24]
    maps.extend(['}',f'map $http_authorization ${var}_rt_token {{ "" ${var}_rt_key; ~^Bearer\\ (?<{capture}>[A-Za-z0-9_.-]+)$ ${capture}; default ""; }}',
        f'map $http_upgrade ${var}_rt_upgrade {{ default close; ~*^websocket$ upgrade; }}',''])
    anchor='variables_hash_bucket_size 128;\n'
    if text.count(anchor)!=1:raise ValueError('REALTIME_GATEWAY_BASE_HASH_CHANGED')
    text=text.replace(anchor,anchor+'\n'.join(maps),1)
    header=[f'        if (${var}_rt_key = "") {{ return 401; }}',
        f'        proxy_set_header Host {tid}.realtime.internal;',f'        proxy_set_header X-Forwarded-Host {tid}.realtime.internal;',
        '        proxy_set_header X-Forwarded-Proto https;','        proxy_set_header X-Forwarded-Prefix /realtime/v1;',
        '        proxy_set_header X-Forwarded-Path "";','        proxy_set_header Forwarded "";',
        '        proxy_set_header X-Tenant-ID "";','        proxy_set_header X-Project-ID "";',
        f'        proxy_set_header X-Dial-Project-ID {p["project_uuid"]};',
        f'        proxy_set_header X-API-Key ${var}_rt_token;',f'        proxy_set_header Authorization ${var}_authorization;',
        '        proxy_set_header X-Forwarded-For $remote_addr;','        proxy_http_version 1.1;',
        '        proxy_connect_timeout 5s;','        proxy_read_timeout 75s;']
    routes=['    location = /realtime/v1/websocket {',*header,
        '        proxy_set_header Upgrade $http_upgrade;',f'        proxy_set_header Connection ${var}_rt_upgrade;',
        f'        proxy_pass http://{upstream}/socket/websocket;','    }',
        '    location = /realtime/v1/api/broadcast {',*header,
        f'        proxy_pass http://{upstream}/api/broadcast;','    }',
        '    location ^~ /realtime/v1/ { return 404; }']
    old='    location ^~ /realtime/v1/ { return 503; }'
    if text.count(old)!=1:raise ValueError('REALTIME_GATEWAY_ALREADY_CHANGED')
    return text.replace(old,'\n'.join(routes))

def overlay(qualified_image: str) -> str:
    if not re.fullmatch(r'[a-z0-9./_-]+@sha256:[a-f0-9]{64}',qualified_image):raise ValueError('REALTIME_PATCHED_IMAGE_DIGEST_REQUIRED')
    if qualified_image==BASE_AMD64_IMAGE:raise ValueError('UPSTREAM_IMAGE_LACKS_TENANT_SLOT_PATCH')
    return '\n'.join(['# CANDIDATE ONLY: requires independently qualified patched image.','services:','  realtime:',
        f'    image: "{qualified_image}"','    env_file:','      - /etc/dial-supabase/shared-realtime/realtime.env',
        '    environment:','      DB_USER: "dial_realtime_registry"','      DB_NAME: "dial_realtime_control"',
        '      SEED_SELF_HOST: "false"','      RUN_JANITOR: "true"',
        '      API_JWT_SECRET: "${DIAL_REALTIME_API_JWT_SECRET:?reserved management secret required}"',
        '      METRICS_JWT_SECRET: "${DIAL_REALTIME_METRICS_JWT_SECRET:?reserved metrics secret required}"',
        '      DB_PASSWORD: "${DIAL_REALTIME_CONTROL_PASSWORD:?reserved registry password required}"',
        '      DB_ENC_KEY: "${DIAL_REALTIME_DB_ENC_KEY:?reserved registry encryption key required}"',
        '      SECRET_KEY_BASE: "${DIAL_REALTIME_SECRET_KEY_BASE:?reserved endpoint secret required}"',
        '    mem_limit: 384m','    pids_limit: 128','    cpus: 1.0',
        '    healthcheck:','      test: ["CMD", "curl", "-f", "http://127.0.0.1:4000/healthcheck"]',''])


def cluster_preflight_sql(project_count: int) -> str:
    if type(project_count) is not int or not 1<=project_count<=32:
        raise ValueError('REALTIME_PROJECT_COUNT_INVALID')
    # Read-only inventory. Admission must compare free connection/slot/WAL and
    # workload budgets, not turn this descriptor into permission to reconfigure.
    return """SELECT json_build_object(
      'server_version_num',current_setting('server_version_num')::int,
      'wal_level',current_setting('wal_level'),
      'max_replication_slots',current_setting('max_replication_slots')::int,
      'used_slots',(SELECT count(*) FROM pg_replication_slots),
      'max_wal_senders',current_setting('max_wal_senders')::int,
      'active_senders',(SELECT count(*) FROM pg_stat_replication),
      'max_connections',current_setting('max_connections')::int,
      'used_connections',(SELECT count(*) FROM pg_stat_activity),
      'output_plugin_libraries',current_setting('output_plugin_libraries',true),
      'max_slot_wal_keep_size',current_setting('max_slot_wal_keep_size'),
      'required_new_slots',%s);
""" % (2*project_count)


def verify_cluster_observation(observed: dict,project_count: int) -> None:
    cluster_preflight_sql(project_count)
    if not isinstance(observed,dict) or observed.get('wal_level')!='logical':raise ValueError('REALTIME_LOGICAL_WAL_REQUIRED')
    if type(observed.get('server_version_num')) is not int or not 170011<=observed['server_version_num']<180000:
        raise ValueError('REALTIME_SECURITY_PATCHED_PG17_REQUIRED')
    plugins=observed.get('output_plugin_libraries')
    if not isinstance(plugins,str) or not {'pgoutput','wal2json'}<=set(p.strip() for p in plugins.split(',')):
        raise ValueError('REALTIME_EXPLICIT_TRUSTED_OUTPUT_PLUGINS_REQUIRED')
    for maximum,used,required in [('max_replication_slots','used_slots',2*project_count),('max_wal_senders','active_senders',project_count),('max_connections','used_connections',12*project_count+4)]:
        if any(type(observed.get(k)) is not int or observed[k]<0 for k in (maximum,used)) or observed[maximum]-observed[used]<required:
            raise ValueError('REALTIME_INSUFFICIENT_'+maximum.upper())
    if str(observed.get('max_slot_wal_keep_size','')) in ('','-1'):
        raise ValueError('REALTIME_BOUNDED_WAL_RETENTION_REQUIRED')


def compile_bundle(projects: list[dict],credentials: dict,shared: dict,cidrs: list[str],
                   upstream_dump: str,*,patched_image: str,preserved_tenants: dict[str,str],
                   published_tables: dict[str,list[tuple[str,str]]],storage_gateways: dict[str,str]|None=None) -> dict[str,str]:
    ps=projects_checked(projects);ids={p['project_uuid'] for p in ps}
    if set(credentials)!=ids or set(published_tables)!=ids or not set(preserved_tenants)<=ids:
        raise ValueError('REALTIME_EXACT_PROJECT_BINDINGS_REQUIRED')
    if set(shared['projects'])!={tenant_id(p) for p in ps}:raise ValueError('REALTIME_EXACT_DATABASE_CREDENTIALS_REQUIRED')
    if len({storage.strong_secret(credentials[i]['jwt_secret']) for i in ids})!=len(ids):raise ValueError('REALTIME_PROJECT_SIGNING_SECRETS_MUST_DIFFER')
    if len({storage.strong_secret(v) for v in shared['projects'].values()})!=len(ids):raise ValueError('REALTIME_DATABASE_PASSWORDS_MUST_DIFFER')
    tenants={p['project_uuid']:native_id(preserved_tenants.get(p['project_uuid'],tenant_id(p))) for p in ps}
    if len(set(tenants.values()))!=len(ps):raise ValueError('REALTIME_NATIVE_TENANT_COLLISION')
    if storage_gateways is not None and set(storage_gateways)!=ids:raise ValueError('REALTIME_STORAGE_GATEWAY_BINDING_MISMATCH')
    if hashlib.sha256(upstream_dump.encode()).hexdigest()!=SCHEMA_SHA256:raise ValueError('REALTIME_EXACT_SCHEMA_REQUIRED')
    count=len(re.findall(r'INSERT INTO realtime\."schema_migrations" \(version\)',upstream_dump))
    if count<70:raise ValueError('REALTIME_NATIVE_SCHEMA_HISTORY_INCOMPLETE')
    role_sql_text,db_sql=control_sql(shared['control_password'])
    out={'registry-role.sql':role_sql_text,'registry-database.sql':db_sql,'registry-schema.sql':control_schema_sql(),
        'shared-realtime.env':storage.storage_env_text(environment(shared)),
        'shared-realtime.compose.env':storage.storage_env_text({
            'DIAL_REALTIME_API_JWT_SECRET':shared['admin_jwt_secret'],
            'DIAL_REALTIME_METRICS_JWT_SECRET':shared['metrics_jwt_secret'],
            'DIAL_REALTIME_CONTROL_PASSWORD':shared['control_password'],
            'DIAL_REALTIME_DB_ENC_KEY':shared['db_encryption_key'],
            'DIAL_REALTIME_SECRET_KEY_BASE':shared['secret_key_base']}),
        'shared-realtime.overlay.yml':overlay(patched_image),
        'cluster-preflight.readonly.sql':cluster_preflight_sql(len(ps))}
    for p in ps:
        c=credentials[p['project_uuid']];storage.validate_credential_keys(p,c)
        slug=p['slug'];tid=tenants[p['project_uuid']]
        out[slug+'.realtime-role.sql']=role_sql(p,shared['projects'][tenant_id(p)])
        out[slug+'.realtime-schema.sql']=fresh_schema_sql(p,upstream_dump)
        out[slug+'.publications.sql']=publication_sql(p,published_tables[p['project_uuid']])
        out[slug+'.tenant-registration.private.json']=json.dumps({'path':'/api/tenants','method':'POST',
            'body':registration(p,c,shared,count,preserved_tenant_id=tid),
            'upstream_post_is_upsert':True,'existing_tenant_action':'REFUSE_AND_RECONCILE',
            'requires_original_owner_exclusive_reservation':True,'executed':False},indent=2,sort_keys=True)+'\n'
        out[slug+'.nginx.conf']=gateway(p,c['anon_key'],c['service_role_key'],
            base_config=storage_gateways[p['project_uuid']] if storage_gateways is not None else None,
            preserved_tenant_id=tid)
    prefix,rules=hba(ps,cidrs,include_storage=storage_gateways is not None)
    out['realtime-projects.hba-prefix.conf']=prefix;out['realtime-activate.sql']=activation_sql(ps,rules)
    out['shared-realtime-candidate.json']=json.dumps({'schema_version':1,'kind':'REALTIME_STAGED_PRIVATE_CANDIDATE',
        'upstream_source':SOURCE_COMMIT,'upstream_version':VERSION,'patched_image':patched_image,
        'tenant_ids':tenants,'native_migrations':count,'realtime_services_added':0,'postgres_servers_added':0,
        'production_deploy_authorized':False,'files':{k:hashlib.sha256(v.encode()).hexdigest() for k,v in out.items()}},indent=2,sort_keys=True)+'\n'
    return out


def main(argv=None) -> int:
    import argparse
    import recovery
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest',type=pathlib.Path,required=True)
    parser.add_argument('--private-input',type=pathlib.Path,required=True)
    parser.add_argument('--upstream-schema',type=pathlib.Path,required=True)
    parser.add_argument('--patched-image',required=True)
    parser.add_argument('--client-cidr',action='append',required=True)
    parser.add_argument('--out',type=pathlib.Path,required=True)
    args=parser.parse_args(argv)
    try:
        projects,_=b.render.load_manifest(args.manifest)
        value=recovery.load_private_json(args.private_input)
        required={'credentials','shared','preserved_tenants','published_tables'}
        if not isinstance(value,dict) or not required<=set(value) or set(value)-required-{'storage_gateways'}:
            raise ValueError('REALTIME_PRIVATE_INPUT_FIELDS_INVALID')
        with args.upstream_schema.open('rb') as handle:raw=handle.read(1048577)
        if len(raw)>1048576:raise ValueError('REALTIME_SCHEMA_INPUT_TOO_LARGE')
        tables={key:[tuple(pair) for pair in rows] for key,rows in value['published_tables'].items()}
        artifacts=compile_bundle(projects,value['credentials'],value['shared'],args.client_cidr,raw.decode(),
            patched_image=args.patched_image,preserved_tenants=value['preserved_tenants'],published_tables=tables,
            storage_gateways=value.get('storage_gateways'))
        b.render.write_bundle(args.out,artifacts)
        print(json.dumps({'state':'PRIVATE_REALTIME_CANDIDATE_WRITTEN_NOT_DEPLOYED','project_count':len(projects),
            'candidate_sha256':hashlib.sha256(artifacts['shared-realtime-candidate.json'].encode()).hexdigest()}))
        return 0
    except (ValueError,TypeError,KeyError,OSError,UnicodeError):
        print('REFUSED_SHARED_REALTIME_CANDIDATE')
        return 2

if __name__=='__main__':raise SystemExit(main())
