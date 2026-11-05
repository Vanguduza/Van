#!/usr/bin/env python3
"""Staged shared Supavisor 2.9.12 project registrations; never installs or applies.

New SQL logins are trusted backend/operator credentials, NOT end-user Auth JWTs.
One existing PostgreSQL server and one pooler; preserve its existing registry.
"""
from __future__ import annotations
import base64
import hashlib
import hmac
import ipaddress
import json
import re
import secrets
import time
from urllib.parse import quote
import bootstrap as b
import shared_storage as st

VERSION='2.9.12'
SOURCE_COMMIT='e8719d9ac5a43604c46d2d9e15bb34c76dea8f12'
AMD64_IMAGE='sha256:68ec476a3cfed150fb067995e12bd751b4dd5872acb9f7d9ce762d63ffd4f64d'
CONTROL_DB='dial_pooler_control'
CONTROL_ROLE='dial_pooler_registry'


def checked(projects):
    ps=st.validate_projects(projects)
    if any(p['database']==CONTROL_DB for p in ps):raise ValueError('POOLER_REGISTRY_COLLISION')
    return ps


def role(p,kind='pool'):
    checked([p])
    if kind not in ('pool','admin'):raise ValueError('POOLER_ROLE_KIND_INVALID')
    return 'dial_'+p['project_uuid'].replace('-','')+'_'+kind


def tenant_id(p):
    checked([p]);return p['project_uuid'].replace('-','')


def new_secrets(projects):
    ps=checked(projects)
    return {'registry_password':secrets.token_urlsafe(48),
        'vault_key':secrets.token_hex(16),'secret_key_base':secrets.token_urlsafe(64),
        'admin_secret':secrets.token_urlsafe(48),'metrics_secret':secrets.token_urlsafe(48),
        'projects':{p['project_uuid']:{k:secrets.token_urlsafe(48) for k in ('pool','admin')} for p in ps}}


def management_token(secret,now=None):
    st.strong_secret(secret);now=int(time.time()) if now is None else now
    encode=lambda v:base64.urlsafe_b64encode(json.dumps(v,separators=(',',':'),sort_keys=True).encode()).decode().rstrip('=')
    data=encode({'alg':'HS256','typ':'JWT'})+'.'+encode({'iss':'dial-supabase-pooler','role':'pooler_admin','iat':now,'exp':now+600})
    return data+'.'+base64.urlsafe_b64encode(hmac.digest(secret.encode(),data.encode(),'sha256')).decode().rstrip('=')


def project_roles_sql(p,s):
    checked([p])
    if set(s)!={'pool','admin'} or len(set(s.values()))!=2:raise ValueError('POOLER_DISTINCT_CREDENTIALS_REQUIRED')
    out=['\\set ON_ERROR_STOP on','BEGIN;',"SET LOCAL log_statement=none;","SET LOCAL log_min_error_statement=panic;",
        f"DO $c$ BEGIN IF current_database()<>{b.lit(p['database'])} OR NOT EXISTS(SELECT FROM dial_private.project_identity WHERE project_uuid={b.lit(p['project_uuid'])}::uuid) THEN RAISE EXCEPTION 'POOLER_WRONG_PROJECT'; END IF; END $c$;"]
    for kind in ('pool','admin'):
        name=role(p,kind);st.strong_secret(s[kind])
        out += [f"DO $c$ BEGIN IF EXISTS(SELECT FROM pg_roles WHERE rolname={b.lit(name)}) THEN RAISE EXCEPTION 'POOLER_ROLE_EXISTS_RECONCILE'; END IF; END $c$;",
            f'CREATE ROLE {b.ident(name)} NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS '+('INHERIT' if kind=='admin' else 'NOINHERIT')+f' CONNECTION LIMIT 8 PASSWORD {b.lit(b.scram(s[kind]))};',
            f'GRANT CONNECT ON DATABASE {b.ident(p["database"])} TO {b.ident(name)};',
            f'GRANT USAGE ON SCHEMA public,extensions TO {b.ident(name)};',
            f'ALTER ROLE {b.ident(name)} SET statement_timeout=5000;',
            f'ALTER ROLE {b.ident(name)} SET idle_in_transaction_session_timeout=5000;']
    out += [f'GRANT {b.ident(b.names(p)["owner"])} TO {b.ident(role(p,"admin"))};','COMMIT;']
    return '\n'.join(out)+'\n'


def fresh_registry_sql(password):
    st.strong_secret(password)
    return ('\\set ON_ERROR_STOP on\nBEGIN;\nSET LOCAL log_statement=none;\nSET LOCAL log_min_error_statement=panic;\n'
        f'CREATE ROLE {CONTROL_ROLE} NOLOGIN NOINHERIT NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS CONNECTION LIMIT 8 PASSWORD {b.lit(b.scram(password))};\nCOMMIT;\n',
        f'\\set ON_ERROR_STOP on\nCREATE DATABASE {CONTROL_DB} OWNER {CONTROL_ROLE} TEMPLATE template0 CONNECTION LIMIT 12;\nREVOKE ALL ON DATABASE {CONTROL_DB} FROM PUBLIC;\nGRANT CONNECT ON DATABASE {CONTROL_DB} TO {CONTROL_ROLE};\n')


def hba(projects,cidrs,*,include_fresh_registry=True):
    ps=checked(projects);b.hba(ps,cidrs)
    networks=[ipaddress.ip_network(c,strict=True) for c in cidrs]
    lines=['# Insert before existing rules; preserve legacy rules; no live apply.'];expected=[]
    def rules(db,users):
        for net in networks:
            lines.append('host '+db+' '+','.join(users)+' '+str(net)+' scram-sha-256')
            expected.append({'type':'host','database':[db],'user_name':users,'address':str(net.network_address),'netmask':str(net.netmask),'auth_method':'scram-sha-256'})
        for typ,net in [('local',None),('host',ipaddress.ip_network('0.0.0.0/0')),('host',ipaddress.ip_network('::/0'))]:
            lines.append(' '.join([typ,'all',','.join(users)]+([str(net)] if net else [])+['reject']))
            expected.append({'type':typ,'database':['all'],'user_name':users,'address':str(net.network_address) if net else None,'netmask':str(net.netmask) if net else None,'auth_method':'reject'})
    for p in ps:rules(p['database'],[b.names(p)[k] for k in ('auth','rest','migrate')]+[role(p,k) for k in ('pool','admin')])
    if include_fresh_registry:rules(CONTROL_DB,[CONTROL_ROLE])
    return '\n'.join(lines)+'\n',expected


def activate_sql(projects,expected,*,include_fresh_registry=True):
    checked(projects)
    if not expected:raise ValueError('POOLER_EXACT_HBA_REQUIRED')
    out=['\\set ON_ERROR_STOP on','BEGIN;','DO $c$ DECLARE observed jsonb; BEGIN',
        "IF EXISTS(SELECT FROM pg_hba_file_rules WHERE error IS NOT NULL) THEN RAISE EXCEPTION 'POOLER_HBA_PARSE'; END IF;",
        "IF pg_conf_load_time()<(pg_stat_file(current_setting('hba_file'))).modification THEN RAISE EXCEPTION 'POOLER_HBA_RELOAD'; END IF;",
        f"SELECT jsonb_agg(jsonb_build_object('type',type,'database',database,'user_name',user_name,'address',address,'netmask',netmask,'auth_method',auth_method) ORDER BY rule_number) INTO observed FROM (SELECT * FROM pg_hba_file_rules ORDER BY rule_number LIMIT {len(expected)}) x;",
        f"IF observed IS DISTINCT FROM {b.lit(json.dumps(expected,separators=(',',':')))}::jsonb THEN RAISE EXCEPTION 'POOLER_HBA_PREFIX_MISMATCH'; END IF; END $c$;"]
    for name in [role(p,k) for p in projects for k in ('pool','admin')]+([CONTROL_ROLE] if include_fresh_registry else []):
        out += [f"DO $c$ BEGIN IF NOT EXISTS(SELECT FROM pg_roles WHERE rolname={b.lit(name)} AND NOT rolcanlogin AND NOT rolsuper AND NOT rolcreatedb AND NOT rolcreaterole AND NOT rolreplication AND NOT rolbypassrls) THEN RAISE EXCEPTION 'POOLER_ROLE_NOT_QUARANTINED'; END IF; END $c$;",f'ALTER ROLE {b.ident(name)} LOGIN;']
    return '\n'.join(out+['COMMIT;'])+'\n'


def registration(p,password,*,db_host='db',db_port=5432,client_cidrs,upstream_ssl=True,enforce_ssl=True,upstream_tls_ca=None):
    checked([p]);st.strong_secret(password);b.hba([p],client_cidrs)
    if not re.fullmatch(r'[a-z0-9][a-z0-9.-]*',db_host) or type(db_port) is not int or not 1<=db_port<=65535:raise ValueError('POOLER_DATABASE_ENDPOINT_INVALID')
    if type(upstream_ssl) is not bool or type(enforce_ssl) is not bool:raise ValueError('POOLER_EXPLICIT_TLS_POLICY_REQUIRED')
    if upstream_ssl and (not isinstance(upstream_tls_ca,str) or '-----BEGIN CERTIFICATE-----' not in upstream_tls_ca or '-----END CERTIFICATE-----' not in upstream_tls_ca):raise ValueError('POOLER_UPSTREAM_CA_REQUIRED')
    result={'tenant':{'external_id':tenant_id(p),'db_host':db_host,'db_port':db_port,
        'db_database':p['database'],'ip_version':'v4','upstream_ssl':upstream_ssl,
        'enforce_ssl':enforce_ssl,'require_user':True,'auth_query':None,
        'default_pool_size':2,'default_max_clients':8,'client_idle_timeout':5000,
        'allow_list':client_cidrs,'default_parameter_status':{'server_version':'17.11'},
        'users':[{'db_user':role(p),'db_password':password,'mode_type':'transaction',
            'pool_size':2,'max_clients':8,'pool_checkout_timeout':2000,'is_manager':False}]}}
    if upstream_ssl:result['tenant'].update(upstream_verify='peer',upstream_tls_ca=upstream_tls_ca)
    return result


def environment(s,*,registry_host,registry_port,registry_database,registry_user):
    # Explicit original registry identity; never reset the real donor registry.
    for key in ('registry_password','secret_key_base','admin_secret','metrics_secret'):st.strong_secret(s[key])
    if len(s['vault_key'].encode())!=32:raise ValueError('POOLER_VAULT_32_BYTES_REQUIRED')
    if s['admin_secret']==s['metrics_secret']:raise ValueError('POOLER_MANAGEMENT_METRICS_SEPARATE')
    if registry_database!='_supabase':b.ident(registry_database)
    b.ident(registry_user)
    if not re.fullmatch(r'[a-z0-9][a-z0-9.-]*',registry_host) or type(registry_port) is not int or not 1<=registry_port<=65535:raise ValueError('POOLER_REGISTRY_ENDPOINT_INVALID')
    return {'DATABASE_URL':f'ecto://{registry_user}:{quote(s["registry_password"],safe="")}@{registry_host}:{registry_port}/{registry_database}',
        'SECRET_KEY_BASE':s['secret_key_base'],'VAULT_ENC_KEY':s['vault_key'],
        'API_JWT_SECRET':s['admin_secret'],'METRICS_JWT_SECRET':s['metrics_secret'],
        'REGION':'local','DB_POOL_SIZE':'2','NUM_ACCEPTORS':'2','MAX_CONNECTIONS':'32',
        'SUPAVISOR_DB_IP_VERSION':'ipv4','ADDR_TYPE':'inet','NODE_IP':'127.0.0.1',
        'JWT_CLAIM_VALIDATORS':'{"iss":"dial-supabase-pooler","role":"pooler_admin"}'}


def overlay():
    return '\n'.join(['# Source candidate: preserve original registry and vault; never reseed default tenant.',
        'services:','  supavisor:',f'    image: supabase/supavisor@{AMD64_IMAGE}',
        '    mem_limit: 256m','    cpus: 0.5','    pids_limit: 128',
        '    security_opt: ["no-new-privileges:true"]',
        '    env_file: ["/etc/dial-supabase/pooler/registry.env"]',
        '    environment:',
        *['      '+k+': "${DIAL_POOLER_'+k+':?original qualified pooler value required}"' for k in ('DATABASE_URL','VAULT_ENC_KEY','API_JWT_SECRET','METRICS_JWT_SECRET','SECRET_KEY_BASE')],
        '      CLUSTER_POSTGRES: "true"','      DB_POOL_SIZE: "2"',
        '    command: ["/bin/sh", "-c", "/app/bin/migrate && /app/bin/server"]',''])


def safe_readback(p,value):
    """Native management responses contain passwords. Never relay/log them."""
    checked([p]);data=value.get('data') if isinstance(value,dict) else None
    if not isinstance(data,dict) or data.get('external_id')!=tenant_id(p) or data.get('db_database')!=p['database']:
        raise ValueError('POOLER_NATIVE_READBACK_SCOPE_MISMATCH')
    users=data.get('users')
    if not isinstance(users,list) or len(users)!=1 or users[0].get('db_user')!=role(p):
        raise ValueError('POOLER_NATIVE_READBACK_USER_MISMATCH')
    return {'project_uuid':p['project_uuid'],'tenant_id':tenant_id(p),
        'database':p['database'],'database_user':role(p),'require_user':data.get('require_user'),
        'pool_mode':users[0].get('mode_type'),'pool_size':users[0].get('pool_size'),
        'native_management_response_redacted':True,'production_qualified':False}


def compile_bundle(projects,private):
    """Existing-registry candidate only. No HTTP/SQL execution or reseeding.

    Supavisor's native PUT is an UPSERT. A protected original-owner lease,
    absent-record readback and unknown-outcome reconciliation are mandatory.
    Caller booleans never confer that authority; this emits unapproved inputs.
    """
    fields={'shared','registry_identity','database_host','database_port','client_cidrs','upstream_tls_ca','enforce_ssl'}
    if not isinstance(private,dict) or set(private)!=fields:raise ValueError('POOLER_PRIVATE_FIELDS_INVALID')
    ps=checked(projects);s=private['shared'];identity=private['registry_identity'];ids={p['project_uuid'] for p in ps}
    if not isinstance(identity,dict) or set(identity)!={'host','port','database','user'}:raise ValueError('POOLER_ORIGINAL_REGISTRY_IDENTITY_REQUIRED')
    if identity['database'] in {p['database'] for p in ps}:raise ValueError('POOLER_REGISTRY_APPLICATION_COLLISION')
    if set(s['projects'])!=ids:raise ValueError('POOLER_PROJECT_CREDENTIAL_SET_MISMATCH')
    passwords=[s['registry_password']]+[s['projects'][x][k] for x in ids for k in ('pool','admin')]
    if len(set(passwords))!=len(passwords):raise ValueError('POOLER_DATABASE_CREDENTIAL_REUSE')
    env=environment(s,registry_host=identity['host'],registry_port=identity['port'],registry_database=identity['database'],registry_user=identity['user'])
    outputs={'registry.env':st.storage_env_text(env),'pooler.overlay.yml':overlay()}
    # Compose environment entries take precedence over env_file; bind the
    # ORIGINAL registry and Vault via exact private compose interpolation.
    outputs['pooler.compose.env']=st.storage_env_text({'DIAL_POOLER_'+k:env[k] for k in ('DATABASE_URL','VAULT_ENC_KEY','API_JWT_SECRET','METRICS_JWT_SECRET','SECRET_KEY_BASE')})
    prefix,expected=hba(ps,private['client_cidrs'],include_fresh_registry=False)
    outputs['pooler-projects.hba-prefix.conf']=prefix
    outputs['pooler-projects.activate.sql']=activate_sql(ps,expected,include_fresh_registry=False)
    for p in ps:
        slug=p['slug'];uid=p['project_uuid']
        outputs[slug+'.new-project-roles.sql']=project_roles_sql(p,s['projects'][uid])
        body=registration(p,s['projects'][uid]['pool'],db_host=private['database_host'],db_port=private['database_port'],client_cidrs=private['client_cidrs'],upstream_ssl=True,enforce_ssl=private['enforce_ssl'],upstream_tls_ca=private['upstream_tls_ca'])
        outputs[slug+'.tenant-request.private.json']=json.dumps({'method':'PUT','path':'/api/tenants/'+tenant_id(p),'body':body,
            'native_operation_semantics':'UPSERT','requires_absent_readback':True,
            'requires_original_owner_exclusive_lease':True,'unknown_outcome_replay_forbidden':True,'executed':False},sort_keys=True,indent=2)+'\n'
    outputs['pooler-candidate.json']=json.dumps({'kind':'EXISTING_SHARED_SUPAVISOR_CANDIDATE','source':SOURCE_COMMIT,
        'registry_database':identity['database'],'registry_user':identity['user'],'new_registry_databases':0,
        'postgres_servers_added':0,'pooler_services_added':0,'production_deployed':False,
        'files':{n:hashlib.sha256(v.encode()).hexdigest() for n,v in outputs.items()}},sort_keys=True,indent=2)+'\n'
    return outputs
