#!/usr/bin/env python3
"""Generate a PRIVATE, staged database/Auth/REST bundle; never deploy it.

One existing PostgreSQL cluster; project-specific logins, databases and signing.
Shared standard Supabase API roles are retained for RLS compatibility. Therefore
an exact first-match pg_hba prefix is mandatory, including denial of other DBs.
Only the separate disposable rehearsal creates/runs services automatically.
"""
from __future__ import annotations
import argparse
import base64
import hashlib
import hmac
import ipaddress
import json
import pathlib
import re
import secrets
import time
from urllib.parse import quote
import render

API_ROLES = ('anon', 'authenticated', 'service_role')

def lit(value: str) -> str:
    if '\0' in value: raise ValueError('NUL_IN_SQL_LITERAL')
    return "'" + value.replace("'", "''") + "'"

def ident(value: str) -> str:
    if not re.fullmatch(r'[a-z][a-z0-9_]{0,62}', value):
        raise ValueError('INVALID_SQL_IDENTIFIER')
    return '"' + value + '"'

def names(p: dict) -> dict[str, str]:
    prefix = 'dial_' + p['project_uuid'].replace('-', '')
    return {kind: prefix + '_' + kind for kind in ('owner', 'auth', 'rest', 'migrate')}

def new_secrets() -> dict[str, str]:
    return {key: secrets.token_urlsafe(48) for key in ('auth', 'rest', 'migrate', 'jwt')}

def scram(password: str, salt: bytes | None = None) -> str:
    salt = salt or secrets.token_bytes(16)
    salted = hashlib.pbkdf2_hmac('sha256', password.encode(), salt, 16384)
    stored = hashlib.sha256(hmac.digest(salted, b'Client Key', 'sha256')).digest()
    server = hmac.digest(salted, b'Server Key', 'sha256')
    b64 = lambda b: base64.b64encode(b).decode()
    return f'SCRAM-SHA-256$16384:{b64(salt)}${b64(stored)}:{b64(server)}'

def token(p: dict, secret: str, role: str, now: int | None = None) -> str:
    if role not in API_ROLES: raise ValueError('INVALID_API_ROLE')
    if not isinstance(secret,str) or len(secret.encode()) < 32: raise ValueError('STRONG_SIGNING_SECRET_REQUIRED')
    now = int(time.time()) if now is None else now
    enc = lambda obj: base64.urlsafe_b64encode(json.dumps(obj, separators=(',', ':'), sort_keys=True).encode()).decode().rstrip('=')
    body = enc({'alg':'HS256', 'typ':'JWT'}) + '.' + enc({
        'role':role, 'aud':'authenticated', 'iss':'https://' + p['hostname'] + '/auth/v1',
        'iat':now, 'exp':now + 86400 * 30, 'project_ref':p['project_uuid']})
    signature = base64.urlsafe_b64encode(hmac.digest(secret.encode(), body.encode(), 'sha256')).decode().rstrip('=')
    return body + '.' + signature

def connection(p: dict, s: dict, kind: str, host: str = 'db', port: int = 5432) -> str:
    if not re.fullmatch(r'[a-zA-Z0-9_.-]+', host) or type(port) is not int or not 1 <= port <= 65535:
        raise ValueError('INVALID_DATABASE_ENDPOINT')
    return f'postgresql://{names(p)[kind]}:{quote(s[kind], safe="")}@{host}:{port}/{p["database"]}'

def roles_sql(p: dict, s: dict) -> str:
    ns = names(p)
    sql = ["\\set ON_ERROR_STOP on", 'BEGIN;', 'SET LOCAL log_statement = none;',
           "SET LOCAL log_min_error_statement = panic;", "SET LOCAL log_parameter_max_length = 0;",
           'DO $check$ BEGIN',
           "IF current_setting('server_version_num')::int NOT BETWEEN 170000 AND 179999 THEN RAISE EXCEPTION 'POSTGRES_17_REQUIRED'; END IF;",
           "IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname='postgres') THEN RAISE EXCEPTION 'DONOR_POSTGRES_ROLE_REQUIRED'; END IF;",
           f"IF EXISTS (SELECT FROM pg_database WHERE datname={lit(p['database'])}) THEN RAISE EXCEPTION 'PROJECT_DATABASE_ALREADY_EXISTS'; END IF;"]
    for name in ns.values():
        sql.append(f"IF EXISTS (SELECT FROM pg_roles WHERE rolname={lit(name)}) THEN RAISE EXCEPTION 'PROJECT_ROLE_ALREADY_EXISTS'; END IF;")
    for role in API_ROLES:
        bypass = 'true' if role == 'service_role' else 'false'
        sql += [f"IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname={lit(role)} AND NOT rolcanlogin AND NOT rolsuper AND NOT rolcreatedb AND NOT rolcreaterole AND NOT rolreplication AND rolbypassrls={bypass}) THEN RAISE EXCEPTION 'STANDARD_API_ROLE_INVALID'; END IF;",
                f"IF EXISTS (SELECT FROM pg_auth_members m JOIN pg_roles r ON r.oid=m.member WHERE r.rolname={lit(role)}) THEN RAISE EXCEPTION 'STANDARD_API_ROLE_HAS_UNREVIEWED_MEMBERSHIP'; END IF;"]
    sql.append('END $check$;')
    for kind, name in ns.items():
        sql.append(f'CREATE ROLE {ident(name)} NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS NOINHERIT CONNECTION LIMIT 8' + (f' PASSWORD {lit(scram(s[kind]))}' if kind != 'owner' else '') + ';')
    sql += [f'GRANT anon, authenticated, service_role TO {ident(ns["rest"])};',
            f'GRANT {ident(ns["owner"])} TO {ident(ns["migrate"])};',
            f'ALTER ROLE {ident(ns["auth"])} SET search_path=auth,pg_catalog;',
            f'ALTER ROLE {ident(ns["rest"])} SET statement_timeout=15000;',
            f'ALTER ROLE {ident(ns["rest"])} SET idle_in_transaction_session_timeout=15000;',
            'COMMIT;']
    return '\n'.join(sql) + '\n'

def database_sql(p: dict) -> str:
    ns = names(p); db = ident(p['database'])
    return '\n'.join(["\\set ON_ERROR_STOP on",
        f'CREATE DATABASE {db} OWNER {ident(ns["owner"])} TEMPLATE template0 ENCODING \'UTF8\' CONNECTION LIMIT 32;',
        f'REVOKE ALL ON DATABASE {db} FROM PUBLIC;',
        f'GRANT CONNECT ON DATABASE {db} TO '+', '.join(ident(ns[k]) for k in ('auth','rest','migrate'))+';',
        f'ALTER DATABASE {db} SET search_path=public,extensions;',
        f'ALTER DATABASE {db} SET idle_in_transaction_session_timeout=30000;', ''])

def schema_sql(p: dict) -> str:
    ns = names(p)
    return '\n'.join(["\\set ON_ERROR_STOP on", 'BEGIN;',
        f"DO $check$ BEGIN IF current_database() <> {lit(p['database'])} THEN RAISE EXCEPTION 'WRONG_PROJECT_DATABASE'; END IF; END $check$;",
        f'ALTER SCHEMA public OWNER TO {ident(ns["owner"])};',
        'REVOKE ALL ON SCHEMA public FROM PUBLIC;',
        f'CREATE SCHEMA auth AUTHORIZATION {ident(ns["auth"])};',
        f'CREATE SCHEMA extensions AUTHORIZATION {ident(ns["owner"])};',
        f'CREATE SCHEMA dial_private AUTHORIZATION {ident(ns["owner"])};',
        'REVOKE ALL ON SCHEMA dial_private FROM PUBLIC;',
        'GRANT USAGE ON SCHEMA public, auth TO anon, authenticated, service_role;',
        f'ALTER DEFAULT PRIVILEGES FOR ROLE {ident(ns["owner"])} REVOKE EXECUTE ON FUNCTIONS FROM PUBLIC;',
        f'ALTER DEFAULT PRIVILEGES FOR ROLE {ident(ns["auth"])} IN SCHEMA auth REVOKE EXECUTE ON FUNCTIONS FROM PUBLIC;',
        'COMMIT;', ''])

def helper_sql(p: dict) -> str:
    """Run after GoTrue's own migrations: no copied/fabricated auth table schema."""
    ns = names(p); issuer = lit('https://' + p['hostname'] + '/auth/v1')
    sql = ["\\set ON_ERROR_STOP on", 'BEGIN;',
           f"DO $check$ BEGIN IF current_database() <> {lit(p['database'])} THEN RAISE EXCEPTION 'WRONG_PROJECT_DATABASE'; END IF; END $check$;",
           "CREATE OR REPLACE FUNCTION auth.jwt() RETURNS jsonb LANGUAGE sql STABLE SET search_path=pg_catalog AS $$ SELECT COALESCE(NULLIF(current_setting('request.jwt.claims',true),''),'{}')::jsonb $$;",
           "CREATE OR REPLACE FUNCTION auth.uid() RETURNS uuid LANGUAGE sql STABLE SET search_path=pg_catalog AS $$ SELECT COALESCE(NULLIF(current_setting('request.jwt.claim.sub',true),''),auth.jwt()->>'sub')::uuid $$;",
           "CREATE OR REPLACE FUNCTION auth.role() RETURNS text LANGUAGE sql STABLE SET search_path=pg_catalog AS $$ SELECT COALESCE(NULLIF(current_setting('request.jwt.claim.role',true),''),auth.jwt()->>'role') $$;",
           "CREATE OR REPLACE FUNCTION auth.email() RETURNS text LANGUAGE sql STABLE SET search_path=pg_catalog AS $$ SELECT COALESCE(NULLIF(current_setting('request.jwt.claim.email',true),''),auth.jwt()->>'email') $$;",
           'CREATE OR REPLACE FUNCTION dial_private.guard_request() RETURNS void LANGUAGE plpgsql STABLE SECURITY INVOKER SET search_path=pg_catalog AS $guard$',
           "DECLARE claims jsonb := COALESCE(NULLIF(current_setting('request.jwt.claims',true),''),'{}')::jsonb; BEGIN",
           f"IF claims->>'iss' IS DISTINCT FROM {issuer} OR COALESCE(claims->>'role','') NOT IN ('anon','authenticated','service_role') THEN RAISE EXCEPTION 'PROJECT_TOKEN_SCOPE_INVALID' USING ERRCODE='42501'; END IF;",
           'END $guard$;',
           f'ALTER FUNCTION dial_private.guard_request() OWNER TO {ident(ns["owner"])};',
           'REVOKE ALL ON FUNCTION dial_private.guard_request() FROM PUBLIC;',
           'GRANT USAGE ON SCHEMA dial_private TO anon, authenticated, service_role;',
           'GRANT EXECUTE ON FUNCTION dial_private.guard_request() TO anon, authenticated, service_role;']
    for fn in ('jwt','uid','role','email'):
        sql += [f'ALTER FUNCTION auth.{fn}() OWNER TO {ident(ns["auth"])};',
                f'REVOKE ALL ON FUNCTION auth.{fn}() FROM PUBLIC;',
                f'GRANT EXECUTE ON FUNCTION auth.{fn}() TO anon, authenticated, service_role;']
    return '\n'.join(sql + ['COMMIT;', ''])

def hba(projects: list[dict], cidrs: list[str]) -> tuple[str, list[dict]]:
    networks = [ipaddress.ip_network(c, strict=True) for c in cidrs]
    allowed = [ipaddress.ip_network(c) for c in ('10.0.0.0/8','172.16.0.0/12','192.168.0.0/16','127.0.0.0/8','fc00::/7','::1/128')]
    if not networks or len(set(networks)) != len(networks) or any(not any(n.version == a.version and n.subnet_of(a) for a in allowed) for n in networks):
        raise ValueError('HBA_PRIVATE_EXPLICIT_CIDRS_REQUIRED')
    lines = ['# REQUIRED FIRST RULES: preserve existing rules after this prefix.']
    expected = []
    def add(kind, db, users, method, network=None):
        addr = str(network.network_address) if network else None
        mask = str(network.netmask) if network else None
        expected.append({'type':kind,'database':[db],'user_name':users,'address':addr,'netmask':mask,'auth_method':method})
        lines.append(' '.join([kind,db,','.join(users)] + ([str(network)] if network else []) + [method]))
    for p in projects:
        ns=names(p); users=[ns[k] for k in ('auth','rest','migrate')]
        for net in networks: add('host',p['database'],users,'scram-sha-256',net)
        add('local','all',users,'reject')
        add('host','all',users,'reject',ipaddress.ip_network('0.0.0.0/0'))
        add('host','all',users,'reject',ipaddress.ip_network('::/0'))
    return '\n'.join(lines)+'\n', expected

def activate_sql(projects: list[dict], expected: list[dict]) -> str:
    check = lit(json.dumps(expected, separators=(',', ':')))
    out = ["\\set ON_ERROR_STOP on", 'BEGIN;',
        'DO $check$ DECLARE observed jsonb; BEGIN',
        "IF EXISTS (SELECT FROM pg_hba_file_rules WHERE error IS NOT NULL) THEN RAISE EXCEPTION 'HBA_PARSE_ERROR'; END IF;",
        "IF pg_conf_load_time() < (pg_stat_file(current_setting('hba_file'))).modification THEN RAISE EXCEPTION 'HBA_RELOAD_NOT_OBSERVED'; END IF;",
        f"SELECT jsonb_agg(jsonb_build_object('type',type,'database',database,'user_name',user_name,'address',address,'netmask',netmask,'auth_method',auth_method) ORDER BY rule_number) INTO observed FROM (SELECT * FROM pg_hba_file_rules ORDER BY rule_number LIMIT {len(expected)}) x;",
        f"IF observed IS DISTINCT FROM {check}::jsonb THEN RAISE EXCEPTION 'EXACT_HBA_PREFIX_REQUIRED'; END IF;",
        'END $check$;']
    for p in projects:
        for kind, name in names(p).items():
            if kind == 'owner': continue
            out += [f"DO $check$ BEGIN IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname={lit(name)} AND NOT rolcanlogin AND NOT rolsuper AND NOT rolcreatedb AND NOT rolcreaterole AND NOT rolreplication AND NOT rolbypassrls) THEN RAISE EXCEPTION 'ROLE_NOT_QUARANTINED'; END IF; END $check$;",
                    f'ALTER ROLE {ident(name)} LOGIN;']
    return '\n'.join(out+['COMMIT;', ''])

def auth_env(p: dict, s: dict, host='db', port=5432) -> dict[str,str]:
    return {'GOTRUE_API_HOST':'0.0.0.0','GOTRUE_API_PORT':'9999',
        'API_EXTERNAL_URL':'https://'+p['hostname']+'/auth/v1',
        'GOTRUE_SITE_URL':'https://'+p['hostname'], 'GOTRUE_URI_ALLOW_LIST':'',
        'GOTRUE_DB_DRIVER':'postgres','GOTRUE_DB_DATABASE_URL':connection(p,s,'auth',host,port),
        'GOTRUE_DB_NAMESPACE':'auth','DB_NAMESPACE':'auth','GOTRUE_DB_MAX_POOL_SIZE':'4',
        'GOTRUE_JWT_SECRET':s['jwt'],'GOTRUE_JWT_ISSUER':'https://'+p['hostname']+'/auth/v1',
        'GOTRUE_JWT_AUD':'authenticated','GOTRUE_JWT_DEFAULT_GROUP_NAME':'authenticated',
        'GOTRUE_JWT_ADMIN_ROLES':'service_role','GOTRUE_JWT_EXP':'3600',
        'GOTRUE_DISABLE_SIGNUP':'true','GOTRUE_EXTERNAL_EMAIL_ENABLED':'true',
        'GOTRUE_EXTERNAL_PHONE_ENABLED':'false','GOTRUE_MAILER_AUTOCONFIRM':'false',
        'GOTRUE_LOG_LEVEL':'error'}

def rest_env(p: dict, s: dict, host='db', port=5432) -> dict[str,str]:
    return {'PGRST_DB_URI':connection(p,s,'rest',host,port),'PGRST_DB_SCHEMAS':'public',
        'PGRST_DB_ANON_ROLE':'anon','PGRST_JWT_SECRET':s['jwt'],'PGRST_JWT_AUD':'authenticated',
        'PGRST_DB_PRE_REQUEST':'dial_private.guard_request','PGRST_DB_POOL':'4',
        'PGRST_DB_MAX_ROWS':'1000','PGRST_LOG_LEVEL':'error','PGRST_DB_EXTRA_SEARCH_PATH':'extensions'}

def env_text(env: dict[str,str]) -> str:
    if any('\n' in v or '\r' in v or '$' in v or '\0' in v for v in env.values()):
        raise ValueError('UNSAFE_ENV_VALUE')
    return ''.join(f'{k}={v}\n' for k,v in sorted(env.items()))

def gateway(p: dict, anon: str, service: str) -> str:
    var='dial_'+p['project_uuid'].replace('-','')
    for key in (anon,service):
        if not re.fullmatch(r'[A-Za-z0-9_.-]+',key): raise ValueError('INVALID_API_KEY')
    base=render.emit_nginx(p)
    base=base.replace('proxy_set_header Host ', f'if (${var}_key = "") {{ return 401; }}\n        proxy_set_header Authorization ${var}_authorization;\n        proxy_set_header Host ')
    start=base.index('    location ^~ /storage/v1/')
    end=base.index('    location ^~ /functions/v1/',start)
    base=base[:start]+'    location ^~ /storage/v1/ { return 503; }\n'+base[end:]
    for path in ('callback','authorize','verify','sso/saml/acs','sso/saml/metadata'):
        base=base.replace('    location ^~ /auth/v1/',f'    location = /auth/v1/{path} {{ return 503; }}\n    location ^~ /auth/v1/',1)
    return '\n'.join([
        '# PRIVATE: contains project API keys. Store 0600. Never publish this file.',
        'map_hash_bucket_size 1024;',
        'variables_hash_bucket_size 128;',
        f'map $http_apikey ${var}_key {{ default ""; "{anon}" "{anon}"; "{service}" "{service}"; }}',
        f'map $http_authorization ${var}_authorization {{ "" "Bearer ${var}_key"; default $http_authorization; }}',
        base])

def compose(projects: list[dict]) -> str:
    lines=['# API/AUTH REHEARSAL CANDIDATE. Not a complete Supabase production release.','services:']
    for p in projects:
        slug=p['slug']; prefix='tenant-'+slug; root='/etc/dial-supabase/projects/'+slug
        for kind,image,cap in [('auth','supabase/gotrue:v2.196.0','256m'),('rest','postgrest/postgrest:v14.17','192m')]:
            lines += [f'  {prefix}-{kind}:',f'    image: "{image}"','    restart: unless-stopped',
                '    security_opt: ["no-new-privileges:true"]','    cap_drop: ["ALL"]',
                f'    mem_limit: {cap}','    pids_limit: 128','    cpus: 0.5',
                '    depends_on:', '      db:', '        condition: service_healthy',
                '    env_file:',f'      - "{root}/{kind}.env"']
        lines += [f'  {prefix}-api:', '    image: "nginx:1.27.5-alpine"','    restart: unless-stopped',
            '    mem_limit: 96m','    pids_limit: 64','    cpus: 0.25',
            '    security_opt: ["no-new-privileges:true"]',
            '    ports:',f'      - "127.0.0.1:{p["loopback_port"]}:8080"','    volumes:',
            f'      - "{root}/nginx.conf:/etc/nginx/conf.d/default.conf:ro"',
            '    depends_on:',f'      - {prefix}-auth',f'      - {prefix}-rest']
    return '\n'.join(lines)+'\n'

def bundle(projects: list[dict], cidrs: list[str]) -> dict[str,str]:
    artifacts={}; metadata=[]
    for p in projects:
        s=new_secrets(); anon=token(p,s['jwt'],'anon'); service=token(p,s['jwt'],'service_role'); slug=p['slug']
        for name,content in [('01-roles.sql',roles_sql(p,s)),('02-database.sql',database_sql(p)),
            ('03-schema.sql',schema_sql(p)),('05-helpers.sql',helper_sql(p)),
            ('auth.env',env_text(auth_env(p,s))),('rest.env',env_text(rest_env(p,s))),
            ('nginx.conf',gateway(p,anon,service))]: artifacts[slug+'.'+name]=content
        artifacts[slug+'.credentials.json']=json.dumps({'project_uuid':p['project_uuid'],
            'database':p['database'],'roles':names(p),'passwords':{k:s[k] for k in ('auth','rest','migrate')},
            'jwt_secret':s['jwt'],'anon_key':anon,'service_role_key':service},sort_keys=True,indent=2)+'\n'
        metadata.append({'slug':slug,'project_uuid':p['project_uuid'],'database':p['database'],'qualified':False})
    fragment,expected=hba(projects,cidrs)
    artifacts['00-hba-prefix.conf']=fragment
    artifacts['04-activate-after-hba.sql']=activate_sql(projects,expected)
    artifacts['projects.api-auth.overlay.yml']=compose(projects)
    artifacts['private-bundle-receipt.json']=json.dumps({'schema_version':1,
        'state':'PRIVATE_REHEARSAL_CANDIDATE','production_deploy_authorized':False,
        'projects':metadata,'rea_required':False,
        'files':{n:hashlib.sha256(c.encode()).hexdigest() for n,c in artifacts.items()}},indent=2,sort_keys=True)+'\n'
    return artifacts

def main(argv=None) -> int:
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest',type=pathlib.Path,required=True)
    parser.add_argument('--client-cidr',action='append',required=True)
    parser.add_argument('--out',type=pathlib.Path,required=True)
    a=parser.parse_args(argv)
    try:
        projects,_=render.load_manifest(a.manifest)
        render.write_bundle(a.out,bundle(projects,a.client_cidr))
        print('PRIVATE_BUNDLE_CREATED__NOT_DEPLOYED')
        return 0
    except (ValueError,TypeError,OSError,KeyError):
        print('REFUSED_PRIVATE_BUNDLE_GENERATION')
        return 2

if __name__=='__main__': raise SystemExit(main())
