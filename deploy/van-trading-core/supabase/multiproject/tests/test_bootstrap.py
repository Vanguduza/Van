"""Offline staged bootstrap contract tests; real runtime tests live in rehearse_native.py."""
from __future__ import annotations
import base64
import hashlib
import hmac
import json
import pathlib
import re
import sys
import tempfile
import unittest

BASE=pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0,str(BASE/'tools'))
import bootstrap as b
import render


def projects():
    return render.validate(json.loads((BASE/'projects.rehearsal.json').read_text()))


class BootstrapContract(unittest.TestCase):
    def setUp(self):
        self.projects=projects();self.p=self.projects[0];self.s=b.new_secrets()

    def test_uuid_bound_role_names_fit_pg_identifier(self):
        roles=b.names(self.p)
        self.assertEqual(set(roles),{'owner','auth','rest','migrate'})
        self.assertEqual(len(set(roles.values())),4)
        for value in roles.values():
            self.assertLessEqual(len(value),63)
            self.assertRegex(value,r'^dial_[a-f0-9]{32}_[a-z]+$')
        self.assertFalse(set(roles.values())&set(b.names(self.projects[1]).values()))

    def test_sql_identifier_rejects_injection(self):
        for value in ('x;drop database postgres','x-y','UPPER','x'*64,'','x\x00y'):
            with self.subTest(value=value),self.assertRaises(ValueError):b.ident(value)
        self.assertEqual(b.lit("value'quoted"),"'value''quoted'")
        with self.assertRaises(ValueError):b.lit('\x00')

    def test_new_credentials_are_independent_and_random(self):
        second=b.new_secrets()
        self.assertEqual(len(set(self.s.values())|set(second.values())),8)
        for value in self.s.values():self.assertGreaterEqual(len(value),48)

    def test_scram_verifier_matches_postgres_algorithm(self):
        salt=b'0123456789abcdef';password='test-only-password'
        result=b.scram(password,salt)
        kind,countsalt,keys=result.split('$')
        count,encoded_salt=countsalt.split(':');stored,server=keys.split(':')
        derived=hashlib.pbkdf2_hmac('sha256',password.encode(),salt,int(count))
        self.assertEqual(kind,'SCRAM-SHA-256')
        self.assertEqual(base64.b64decode(encoded_salt),salt)
        self.assertEqual(base64.b64decode(stored),hashlib.sha256(hmac.digest(derived,b'Client Key','sha256')).digest())
        self.assertEqual(base64.b64decode(server),hmac.digest(derived,b'Server Key','sha256'))
        self.assertNotIn(password,result)
        self.assertNotEqual(b.scram(password),b.scram(password))

    def test_jwt_project_scope_signature_and_expiry(self):
        token=b.token(self.p,self.s['jwt'],'anon',now=1000)
        head,body,signature=token.split('.')
        dec=lambda s:base64.urlsafe_b64decode(s+'='*(-len(s)%4))
        claims=json.loads(dec(body))
        self.assertEqual(claims['iss'],'https://'+self.p['hostname']+'/auth/v1')
        self.assertEqual(claims['aud'],'authenticated')
        self.assertEqual(claims['role'],'anon')
        self.assertEqual(claims['project_ref'],self.p['project_uuid'])
        self.assertEqual(claims['exp']-claims['iat'],30*86400)
        self.assertEqual(dec(signature),hmac.digest(self.s['jwt'].encode(),(head+'.'+body).encode(),'sha256'))
        self.assertNotEqual(token,b.token(self.projects[1],b.new_secrets()['jwt'],'anon',now=1000))

    def test_jwt_weak_secret_and_unknown_role_refused(self):
        with self.assertRaises(ValueError):b.token(self.p,'short','anon')
        with self.assertRaises(ValueError):b.token(self.p,self.s['jwt'],'postgres')

    def test_connection_binds_project_login_and_database(self):
        uri=b.connection(self.p,self.s,'rest')
        self.assertIn(b.names(self.p)['rest'],uri)
        self.assertTrue(uri.endswith('@db:5432/'+self.p['database']))
        for host,pn in [('db;extra',5432),('db',True),('db',0),('db',65536)]:
            with self.subTest(host=host,port=pn),self.assertRaises(ValueError):b.connection(self.p,self.s,'rest',host,pn)

    def test_new_roles_quarantined_and_no_global_role_mutation(self):
        sql=b.roles_sql(self.p,self.s)
        self.assertEqual(sql.count('CREATE ROLE '),4)
        self.assertEqual(sql.count(' NOLOGIN NOSUPERUSER '),4)
        self.assertIn('NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS NOINHERIT',sql)
        self.assertIn('STANDARD_API_ROLE_HAS_UNREVIEWED_MEMBERSHIP',sql)
        self.assertIn('DONOR_POSTGRES_ROLE_REQUIRED',sql)
        self.assertIn('PROJECT_DATABASE_ALREADY_EXISTS',sql)
        self.assertIn('PROJECT_ROLE_ALREADY_EXISTS',sql)
        for value in self.s.values():self.assertNotIn(value,sql)
        for name in ('anon','authenticated','service_role','postgres','vati'):
            self.assertNotRegex(sql,r'(CREATE|ALTER) ROLE "?'+name+r'"?\s')

    def test_database_uses_template0_not_van(self):
        sql=b.database_sql(self.p)
        self.assertIn('TEMPLATE template0',sql)
        self.assertNotIn('TEMPLATE postgres',sql)
        self.assertIn('REVOKE ALL ON DATABASE "'+self.p['database']+'" FROM PUBLIC',sql)
        self.assertIn('CONNECTION LIMIT 32',sql)
        self.assertNotRegex(sql,r'(DROP DATABASE|DROP OWNED|ALTER DATABASE "postgres")')

    def test_auth_tables_come_from_real_gotrue_migrations(self):
        sql=b.schema_sql(self.p)
        self.assertNotIn('CREATE TABLE',sql)
        self.assertIn('CREATE SCHEMA auth AUTHORIZATION',sql)
        self.assertIn('WRONG_PROJECT_DATABASE',sql)
        self.assertIn('REVOKE EXECUTE ON FUNCTIONS FROM PUBLIC',sql)

    def test_hba_exact_project_allow_then_foreign_database_reject(self):
        text,expected=b.hba(self.projects,['127.0.0.1/32','172.20.0.0/16','::1/128'])
        self.assertEqual(len(expected),12)
        for index,p in enumerate(self.projects):
            rules=expected[index*6:(index+1)*6]
            self.assertTrue(all(r['database']==[p['database']] and r['auth_method']=='scram-sha-256' for r in rules[:3]))
            self.assertTrue(all(r['database']==['all'] and r['auth_method']=='reject' for r in rules[3:]))
            self.assertEqual(rules[3]['type'],'local')
            self.assertIn(b.names(p)['rest'],text)
        self.assertNotIn(' trust',text)

    def test_hba_broad_public_duplicate_networks_refused(self):
        for cidrs in ([],['0.0.0.0/0'],['::/0'],['8.8.8.8/32'],['192.0.2.0/24'],['127.0.0.1/32']*2,['172.20.0.1/16']):
            with self.subTest(cidrs=cidrs),self.assertRaises(ValueError):b.hba(self.projects,cidrs)

    def test_activation_requires_exact_first_hba_rules_and_reload(self):
        _,expected=b.hba(self.projects,['127.0.0.1/32'])
        sql=b.activate_sql(self.projects,expected)
        self.assertIn('pg_hba_file_rules',sql)
        self.assertIn('ORDER BY rule_number LIMIT 8',sql)
        self.assertIn('EXACT_HBA_PREFIX_REQUIRED',sql)
        self.assertIn('HBA_RELOAD_NOT_OBSERVED',sql)
        self.assertIn('ROLE_NOT_QUARANTINED',sql)
        self.assertEqual(sql.count(' LOGIN;'),6)
        self.assertLess(sql.index('EXACT_HBA_PREFIX_REQUIRED'),sql.index(' LOGIN;'))

    def test_runtime_envs_do_not_use_shared_admin_password(self):
        auth=b.auth_env(self.p,self.s);rest=b.rest_env(self.p,self.s)
        self.assertEqual(auth['GOTRUE_DISABLE_SIGNUP'],'true')
        self.assertEqual(auth['GOTRUE_MAILER_AUTOCONFIRM'],'false')
        self.assertEqual(rest['PGRST_DB_PRE_REQUEST'],'dial_private.guard_request')
        self.assertEqual(rest['PGRST_DB_SCHEMAS'],'public')
        self.assertNotEqual(auth['GOTRUE_DB_DATABASE_URL'],rest['PGRST_DB_URI'])
        self.assertNotIn('postgres:',auth['GOTRUE_DB_DATABASE_URL'])
        self.assertEqual(auth['GOTRUE_JWT_SECRET'],rest['PGRST_JWT_SECRET'])
        for env in (auth,rest):self.assertNotIn('POSTGRES_PASSWORD',env)

    def test_env_injection_refused(self):
        for value in ('x\nNEXT=y','x\rNEXT=y','${OTHER_SECRET}','x\0y'):
            with self.subTest(value=value),self.assertRaises(ValueError):b.env_text({'VALUE':value})

    def test_helpers_use_invoker_and_exact_issuer(self):
        sql=b.helper_sql(self.p)
        self.assertIn('SECURITY INVOKER',sql)
        self.assertNotIn('SECURITY DEFINER',sql)
        self.assertIn('SET search_path=pg_catalog',sql)
        self.assertIn('PROJECT_TOKEN_SCOPE_INVALID',sql)
        self.assertIn('https://'+self.p['hostname']+'/auth/v1',sql)
        self.assertIn("request.jwt.claims",sql)

    def test_gateway_auth_admission_and_unsafe_services_closed(self):
        anon=b.token(self.p,self.s['jwt'],'anon',now=1000)
        service=b.token(self.p,self.s['jwt'],'service_role',now=1000)
        config=b.gateway(self.p,anon,service)
        self.assertIn('map $http_apikey',config)
        self.assertIn('map_hash_bucket_size 1024;',config)
        self.assertIn('variables_hash_bucket_size 128;',config)
        self.assertEqual(config.count('return 401;'),2)
        self.assertIn('proxy_set_header Authorization',config)
        self.assertIn('X-Tenant-ID ""',config)
        for route in ('storage','realtime','functions'):
            self.assertIn('/'+route+'/v1/ { return 503;',config)
        self.assertIn('/auth/v1/callback { return 503;',config)
        self.assertNotIn(self.s['jwt'],config)

    def test_compose_is_an_additive_api_auth_overlay(self):
        text=b.compose(self.projects)
        top=re.findall(r'^  ([a-z0-9-]+):$',text,re.MULTILINE)
        self.assertEqual(len(top),6)
        self.assertNotIn('db',top)
        self.assertNotIn('supabase/postgres',text)
        self.assertNotIn('container_name',text)
        self.assertIn('127.0.0.1:',text)
        self.assertIn('mem_limit:',text)
        self.assertIn('pids_limit:',text)
        self.assertNotIn('-storage:',text)

    def test_safe_writer_traverses_search_only_ancestor_without_listing(self):
        with tempfile.TemporaryDirectory() as td:
            ancestor=pathlib.Path(td)/'execute-only';ancestor.mkdir()
            parent=ancestor/'private';parent.mkdir(mode=0o700)
            ancestor.chmod(0o111)
            try:
                render.write_bundle(parent/'bundle',{'note.txt':'safe'})
                self.assertEqual((parent/'bundle/note.txt').read_text(),'safe')
            finally:ancestor.chmod(0o700)

    def test_private_bundle_contains_exact_hashes_and_secret_permissions(self):
        artifacts=b.bundle(self.projects,['127.0.0.1/32'])
        receipt=json.loads(artifacts['private-bundle-receipt.json'])
        self.assertFalse(receipt['production_deploy_authorized'])
        self.assertFalse(receipt['rea_required'])
        for name,digest in receipt['files'].items():self.assertEqual(hashlib.sha256(artifacts[name].encode()).hexdigest(),digest)
        with tempfile.TemporaryDirectory() as td:
            out=pathlib.Path(td)/'bundle';render.write_bundle(out,artifacts)
            self.assertEqual(out.stat().st_mode&0o777,0o700)
            self.assertTrue(all(p.stat().st_mode&0o777==0o600 for p in out.iterdir()))
            with self.assertRaises(render.CandidateError):render.write_bundle(out,artifacts)


if __name__=='__main__':unittest.main()
