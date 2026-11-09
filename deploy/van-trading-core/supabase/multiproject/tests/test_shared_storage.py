"""Shared-service generation contracts. Real Storage proof: rehearse_storage.py."""
import copy
import hashlib
import json
import pathlib
import re
import sys
import tempfile
import io
from contextlib import redirect_stdout
import unittest
BASE=pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0,str(BASE/'tools'))
import bootstrap as b
import shared_storage as st

class SharedStorageContracts(unittest.TestCase):
    def setUp(self):
        self.ps=b.render.validate(json.loads((BASE/'projects.rehearsal.json').read_text()))
        self.p=self.ps[0];self.shared=st.new_secrets(self.ps)
        self.credentials={}
        for p in self.ps:
            sec=b.new_secrets()
            self.credentials[p['project_uuid']]={'project_uuid':p['project_uuid'],'jwt_secret':sec['jwt'],
                'anon_key':b.token(p,sec['jwt'],'anon'),'service_role_key':b.token(p,sec['jwt'],'service_role')}
    def bundle(self):
        return st.compile_bundle(self.ps,self.credentials,self.shared,['127.0.0.1/32'],
            object_bucket='original-bucket',object_path='/var/lib/storage',
            preserved_tenants={self.p['project_uuid']:'original-tenant'})
    def test_unique_stable_native_ids_and_roles(self):
        self.assertNotEqual(st.tenant_id(self.ps[0]),st.tenant_id(self.ps[1]))
        for p in self.ps:
            self.assertRegex(st.tenant_id(p),r'^[a-f0-9]{32}$')
            self.assertLessEqual(len(st.role(p)),63)
    def test_manifest_validation_not_header_identity(self):
        bad=copy.deepcopy(self.p);bad['hostname']='x; injected'
        with self.assertRaises(ValueError):st.tenant_id(bad)
    def test_duplicate_projects_refused(self):
        with self.assertRaises(ValueError):st.new_secrets([self.p,self.p])
    def test_control_database_collision_refused(self):
        p=copy.deepcopy(self.p);p['database']=st.CONTROL_DB
        with self.assertRaisesRegex(ValueError,'COLLISION'):st.new_secrets([p])
    def test_native_namespace_traversal_and_injection_refused(self):
        for value in ('../van','x/y','x.y','X','x;drop','x\n','', 'x'*64,None):
            with self.subTest(value=value),self.assertRaises(ValueError):st.native_id(value)
    def test_independent_high_entropy_control_secrets(self):
        values=[self.shared[k] for k in ('control_password','encryption_key','admin_key')]+list(self.shared['projects'].values())
        self.assertEqual(len(set(values)),5)
        self.assertTrue(all(len(v)>=48 for v in values))
    def test_storage_roles_start_quarantined_without_privilege(self):
        text=st.roles_sql(self.p,self.shared['projects'][st.tenant_id(self.p)])
        self.assertIn('NOLOGIN NOINHERIT NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS',text)
        self.assertIn('CONNECTION LIMIT 6',text)
        self.assertNotIn(self.shared['projects'][st.tenant_id(self.p)],text)
        self.assertNotIn('ALTER ROLE service_role',text)
        self.assertNotIn('DROP ',text)
    def test_weak_or_unsafe_passwords_refused(self):
        for secret in ('short','a'*32+'\n','a'*32+'\0',None):
            with self.subTest(secret=secret),self.assertRaises(ValueError):st.roles_sql(self.p,secret)
            with self.assertRaises(ValueError):st.control_roles_sql(secret)
    def test_schema_uses_observed_project_identity(self):
        text=st.schema_sql(self.p)
        self.assertIn('dial_private.project_identity',text)
        self.assertIn(self.p['project_uuid'],text)
        self.assertIn('STORAGE_PROJECT_IDENTITY_MISMATCH',text)
        self.assertNotIn('CREATE TABLE',text)
        self.assertIn('CREATE SCHEMA storage AUTHORIZATION',text)
    def test_control_db_is_same_server_and_not_public(self):
        text=st.control_database_sql()
        self.assertIn('TEMPLATE template0',text)
        self.assertIn('CONNECTION LIMIT 12',text)
        self.assertIn('FROM PUBLIC',text)
        self.assertNotIn('CREATE SERVER',text)
    def test_hba_retains_auth_rest_and_adds_storage_and_control(self):
        _,rules=st.hba(self.ps,['127.0.0.1/32'])
        self.assertEqual(len(rules),12)
        for i,p in enumerate(self.ps):
            own=rules[i*4]
            self.assertEqual(own['database'],[p['database']])
            self.assertEqual(set(own['user_name']),{b.names(p)[k] for k in ('auth','rest','migrate')}|{st.role(p)})
            self.assertEqual(own['auth_method'],'scram-sha-256')
            self.assertTrue(all(x['auth_method']=='reject' for x in rules[i*4+1:i*4+4]))
        self.assertEqual(rules[-4]['database'],[st.CONTROL_DB])
        self.assertEqual(rules[-4]['user_name'],[st.CONTROL_ROLE])
    def test_hba_global_and_public_network_refused(self):
        for cidrs in (['0.0.0.0/0'],['8.8.8.8/32'],['::/0'],[]):
            with self.subTest(cidrs=cidrs),self.assertRaises(ValueError):st.hba(self.ps,cidrs)
    def test_activation_checks_exact_prefix_and_only_new_roles(self):
        _,rules=st.hba(self.ps,['127.0.0.1/32']);text=st.activation_sql(self.ps,rules)
        self.assertIn('STORAGE_EXACT_HBA_PREFIX_REQUIRED',text)
        self.assertIn('STORAGE_HBA_RELOAD_REQUIRED',text)
        self.assertIn('STORAGE_ROLE_NOT_QUARANTINED',text)
        self.assertEqual(text.count(' LOGIN;'),3)
        for p in self.ps:self.assertNotIn('ALTER ROLE "'+b.names(p)['auth']+'" LOGIN',text)
    def test_empty_hba_activation_refused(self):
        with self.assertRaises(ValueError):st.activation_sql(self.ps,[])
    def test_endpoint_validation_and_password_encoding(self):
        self.assertIn('%3A',st.dsn('fixture_db','fixture_role','a'*32+':'))
        for host,port in [('db;bad',5432),('db',True),('db',0),('db',65536)]:
            with self.subTest(host=host,port=port),self.assertRaises(ValueError):st.dsn('fixture_db','fixture_role','a'*32,host,port)
    def test_environment_requires_explicit_original_bucket(self):
        with self.assertRaises(TypeError):st.environment(self.shared)
        env=st.environment(self.shared,object_bucket='original',preserved_tenants=['legacy-vati'])
        self.assertEqual(env['STORAGE_S3_BUCKET'],'original')
        self.assertEqual(env['STORAGE_FILE_BACKEND_PATH'],'/var/lib/storage')
        self.assertIn('legacy\\-vati',env['REQUEST_X_FORWARDED_HOST_REGEXP'])
    def test_environment_exact_tenant_pattern(self):
        env=st.environment(self.shared,object_bucket='original')
        rx=re.compile(env['REQUEST_X_FORWARDED_HOST_REGEXP'])
        for p in self.ps:self.assertEqual(rx.fullmatch(st.tenant_id(p)+'.storage.internal').group(1),st.tenant_id(p))
        self.assertIsNone(rx.fullmatch('other.storage.internal'))
        self.assertIsNone(rx.fullmatch(st.tenant_id(self.p)+'.storage.internal.evil'))
    def test_environment_no_shared_superuser_or_public_management(self):
        env=st.environment(self.shared,object_bucket='original')
        self.assertEqual(env['DB_INSTALL_ROLES'],'false')
        self.assertEqual(env['ADMIN_RETURN_TENANT_SENSITIVE_DATA'],'false')
        self.assertEqual(env['DB_ALLOW_MIGRATION_REFRESH'],'false')
        self.assertNotIn('postgres:',env['DATABASE_MULTITENANT_URL'])
        self.assertEqual(env['IMAGE_TRANSFORMATION_ENABLED'],'false')
    def test_environment_reused_control_secrets_refused(self):
        bad=copy.deepcopy(self.shared);bad['admin_key']=bad['encryption_key']
        with self.assertRaises(ValueError):st.environment(bad,object_bucket='original')
    def test_environment_unsafe_object_path_refused(self):
        for path in ('relative','/var/../root'):
            with self.subTest(path=path),self.assertRaises(ValueError):st.environment(self.shared,path,object_bucket='original')
    def test_registration_binds_own_database_secret(self):
        c=self.credentials[self.p['project_uuid']];keys={'anon':c['anon_key'],'service_role':c['service_role_key']}
        reg=st.registration(self.p,{'jwt':c['jwt_secret']},self.shared,keys)
        self.assertTrue(reg['databaseUrl'].endswith('/'+self.p['database']))
        self.assertIn(st.role(self.p),reg['databaseUrl'])
        self.assertEqual(reg['jwtSecret'],c['jwt_secret'])
        self.assertFalse(reg['features']['s3Protocol']['enabled'])
    def test_gateway_replaces_client_identity(self):
        c=self.credentials[self.p['project_uuid']];text=st.gateway(self.p,c['anon_key'],c['service_role_key'])
        self.assertIn('X-Forwarded-Host '+st.tenant_id(self.p)+'.storage.internal',text)
        self.assertIn('X-Tenant-ID ""',text)
        self.assertIn('X-Forwarded-Path ""',text)
        self.assertIn('proxy_pass http://storage:5000/',text)
        self.assertNotIn('5001',text)
    def test_signed_url_exception_is_only_public_read(self):
        c=self.credentials[self.p['project_uuid']];text=st.gateway(self.p,c['anon_key'],c['service_role_key'])
        self.assertIn('~^(GET|HEAD):/storage/v1/object/(sign|public)/',text)
        self.assertIn('default 0;',text)
        self.assertIn('":0" 0;',text)
        self.assertLess(text.index('map_hash_bucket_size'),text.index('map "$request_method'))
    def test_legacy_native_tenant_preserved_without_uuid_rewrite(self):
        c=self.credentials[self.p['project_uuid']];text=st.gateway(self.p,c['anon_key'],c['service_role_key'],preserved_tenant_id='legacy-vati')
        self.assertIn('legacy-vati.storage.internal',text)
        self.assertIn('X-Dial-Project-ID '+self.p['project_uuid'],text)
    def test_gateway_upstream_and_namespace_injection_refused(self):
        c=self.credentials[self.p['project_uuid']]
        for up in ('http://storage:5000','storage:65536','storage:0','storage:5000; bad'):
            with self.subTest(up=up),self.assertRaises(ValueError):st.gateway(self.p,c['anon_key'],c['service_role_key'],up)
    def test_overlay_modifies_existing_service_not_new_stack(self):
        text=st.overlay()
        self.assertEqual(re.findall(r'^  ([a-z_-]+):$',text,re.MULTILINE),['storage'])
        self.assertNotIn('ports:',text)
        self.assertNotIn('volumes:',text)
        self.assertNotIn('supabase/postgres',text)
        self.assertIn('MULTI_TENANT: "true"',text)
        self.assertIn('ENABLE_IMAGE_TRANSFORMATION: "false"',text)
    def test_environment_regex_end_anchor_remains_literal(self):
        env=st.environment(self.shared,object_bucket='original')
        text=st.storage_env_text(env)
        self.assertIn("REQUEST_X_FORWARDED_HOST_REGEXP='^(",text)
        self.assertIn("internal$'\n",text)
        for value in ("x'bad",'x\nBAD=y'):
            with self.assertRaises(ValueError):st.storage_env_text({'EXAMPLE':value})

    def test_complete_bundle_is_private_non_executing(self):
        artifacts=self.bundle();receipt=json.loads(artifacts['shared-storage-candidate.json'])
        self.assertFalse(receipt['production_deploy_authorized'])
        self.assertEqual(receipt['storage_services_added'],0)
        self.assertEqual(receipt['postgres_instances_added'],0)
        for n,d in receipt['files'].items():self.assertEqual(hashlib.sha256(artifacts[n].encode()).hexdigest(),d)
        with tempfile.TemporaryDirectory() as td:
            target=pathlib.Path(td)/'bundle';b.render.write_bundle(target,artifacts)
            self.assertTrue(all(p.stat().st_mode&0o777==0o600 for p in target.iterdir()))
    def test_tenant_registration_is_create_only_not_upsert(self):
        artifacts=self.bundle()
        for p in self.ps:
            d=json.loads(artifacts[p['slug']+'.tenant-registration.private.json'])
            self.assertEqual(d['method'],'POST')
            self.assertFalse(d['executed'])
            self.assertEqual(d['existing_tenant_action'],'REFUSE_AND_RECONCILE_NO_UPSERT')
    def test_wrong_project_credentials_refused(self):
        c=self.credentials[self.ps[0]['project_uuid']]
        with self.assertRaisesRegex(ValueError,'SIGNING_CREDENTIAL'):st.validate_credential_keys(self.ps[1],c)
    def test_wrong_secret_and_expired_keys_refused(self):
        c=copy.deepcopy(self.credentials[self.p['project_uuid']]);c['jwt_secret']='a'*64
        with self.assertRaises(ValueError):st.validate_credential_keys(self.p,c)
        c=copy.deepcopy(self.credentials[self.p['project_uuid']]);c['anon_key']=b.token(self.p,c['jwt_secret'],'anon',now=100)
        with self.assertRaises(ValueError):st.validate_credential_keys(self.p,c)
    def test_missing_original_project_credential_refused(self):
        self.credentials.pop(self.p['project_uuid'])
        with self.assertRaises(ValueError):self.bundle()
    def test_duplicate_preserved_namespace_refused(self):
        with self.assertRaisesRegex(ValueError,'COLLISION'):
            st.compile_bundle(self.ps,self.credentials,self.shared,['127.0.0.1/32'],object_bucket='x',object_path='/var/lib/storage',preserved_tenants={p['project_uuid']:'same' for p in self.ps})

    def test_reused_project_signing_secret_refused(self):
        a,c=self.ps;self.credentials[c['project_uuid']]['jwt_secret']=self.credentials[a['project_uuid']]['jwt_secret']
        with self.assertRaisesRegex(ValueError,'SIGNING_SECRETS_MUST_BE_DISTINCT'):self.bundle()
    def test_reused_database_password_refused(self):
        self.shared['control_password']=self.shared['projects'][st.tenant_id(self.p)]
        with self.assertRaisesRegex(ValueError,'DATABASE_PASSWORDS_MUST_BE_DISTINCT'):self.bundle()
    def test_wrong_registration_signature_refused(self):
        c=self.credentials[self.p['project_uuid']]
        with self.assertRaisesRegex(ValueError,'SIGNING_CREDENTIAL'):
            st.registration(self.p,{'jwt':'x'*64},self.shared,{'anon':c['anon_key'],'service_role':c['service_role_key']})
    def test_legacy_envoy_other_routes_are_byte_preserved(self):
        source=('head-unchanged\n                      - match:\n                          prefix: /storage/v1/\n'
          '                        route:\n                          cluster: storage\n'
          '                        request_headers_to_add:\n'
          '                          - header:\n                              key: X-Forwarded-Prefix\n'
          '                              value: /storage/v1\n                            append_action: ADD_IF_ABSENT\n'
          '                      - match:\n                          prefix: /rest/v1/\ntail-unchanged\n')
        digest=hashlib.sha256(source.encode()).hexdigest()
        changed,receipt=st.legacy_envoy_candidate(source,digest,'original-native-id')
        self.assertTrue(changed.startswith('head-unchanged\n'))
        self.assertTrue(changed.endswith('prefix: /rest/v1/\ntail-unchanged\n'))
        self.assertIn('original-native-id.storage.internal',changed)
        self.assertIn('OVERWRITE_IF_EXISTS_OR_ADD',changed)
        self.assertFalse(receipt['deployed'])
        self.assertEqual(receipt['result_sha256'],hashlib.sha256(changed.encode()).hexdigest())
        with self.assertRaises(ValueError):st.legacy_envoy_candidate(source,'0'*64,'original-native-id')
        with self.assertRaises(ValueError):st.legacy_envoy_candidate(changed,receipt['result_sha256'],'original-native-id')
        with self.assertRaises(ValueError):st.legacy_envoy_candidate(source+source,hashlib.sha256((source+source).encode()).hexdigest(),'original-native-id')
    def test_cli_private_inputs_and_output_no_secrets(self):
        with tempfile.TemporaryDirectory() as td:
            root=pathlib.Path(td);manifest=root/'projects.json';private=root/'input.json'
            manifest.write_text((BASE/'projects.rehearsal.json').read_text())
            private.write_text(json.dumps({'credentials':self.credentials,'shared':self.shared,
                'object_bucket':'original','object_path':'/var/lib/storage','preserved_tenants':{}}))
            private.chmod(0o600)
            args=['--manifest',str(manifest),'--private-input',str(private),'--client-cidr','127.0.0.1/32','--out',str(root/'bundle')]
            stream=io.StringIO()
            with redirect_stdout(stream):self.assertEqual(st.main(args),0)
            self.assertNotIn(self.shared['admin_key'],stream.getvalue())
            self.assertIn('NOT_DEPLOYED',stream.getvalue())
            with redirect_stdout(io.StringIO()):self.assertEqual(st.main(args),2)
    def test_cli_nonprivate_credentials_refused(self):
        with tempfile.TemporaryDirectory() as td:
            root=pathlib.Path(td);manifest=root/'projects.json';private=root/'input.json'
            manifest.write_text((BASE/'projects.rehearsal.json').read_text());private.write_text('{}');private.chmod(0o644)
            with redirect_stdout(io.StringIO()):
                result=st.main(['--manifest',str(manifest),'--private-input',str(private),'--client-cidr','127.0.0.1/32','--out',str(root/'out')])
            self.assertEqual(result,2);self.assertFalse((root/'out').exists())

if __name__=='__main__':unittest.main()
