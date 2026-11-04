"""Shared pooler/admin staged contracts; native tests use actual upstream servers."""
import copy
import hashlib
import json
import pathlib
import re
import sys
import tempfile
import unittest
BASE=pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0,str(BASE/'tools'))
import bootstrap as b
import shared_pooler as pool
import shared_admin as admin

class PoolerContracts(unittest.TestCase):
    def setUp(self):
        self.ps=b.render.validate(json.loads((BASE/'projects.rehearsal.json').read_text()))
        self.p=self.ps[0];self.s=pool.new_secrets(self.ps)
    def private(self):
        return {'shared':self.s,'registry_identity':{'host':'db','port':5432,'database':'_supabase','user':'supabase_admin'},
            'database_host':'db','database_port':5432,'client_cidrs':['172.20.0.0/16'],
            'upstream_tls_ca':'-----BEGIN CERTIFICATE-----\nSYNTHETIC_TEST_NOT_VALID_TLS_CERT\n-----END CERTIFICATE-----',
            'enforce_ssl':True}
    def test_one_registry_many_stable_project_ids(self):
        self.assertEqual(len({pool.tenant_id(p) for p in self.ps}),2)
        for p in self.ps:
            for k in ('pool','admin'):
                self.assertLessEqual(len(pool.role(p,k)),63)
                self.assertRegex(pool.role(p,k),r'^dial_[a-f0-9]{32}_(pool|admin)$')
    def test_reserved_registry_collision_refused(self):
        p=copy.deepcopy(self.p);p['database']=pool.CONTROL_DB
        with self.assertRaises(ValueError):pool.checked([p])
    def test_independent_control_and_project_secrets(self):
        values=[self.s[k] for k in ('registry_password','admin_secret','metrics_secret','vault_key','secret_key_base')]
        values += [d[k] for d in self.s['projects'].values() for k in ('pool','admin')]
        self.assertEqual(len(values),len(set(values)))
        self.assertEqual(len(self.s['vault_key'].encode()),32)
    def test_new_roles_quarantined_and_no_global_privilege(self):
        sql=pool.project_roles_sql(self.p,self.s['projects'][self.p['project_uuid']])
        self.assertEqual(sql.count('CREATE ROLE'),2)
        self.assertEqual(sql.count('NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS'),2)
        self.assertIn('POOLER_WRONG_PROJECT',sql)
        self.assertIn('POOLER_ROLE_EXISTS_RECONCILE',sql)
        for password in self.s['projects'][self.p['project_uuid']].values():self.assertNotIn(password,sql)
        self.assertNotIn('pg_read_all_data',sql)
        self.assertNotIn('GRANT service_role',sql)
    def test_project_admin_inherits_only_its_project_owner(self):
        sql=pool.project_roles_sql(self.p,self.s['projects'][self.p['project_uuid']])
        self.assertIn('GRANT "'+b.names(self.p)['owner']+'" TO "'+pool.role(self.p,'admin')+'"',sql)
        self.assertNotIn(b.names(self.ps[1])['owner'],sql)
    def test_role_password_reuse_refused(self):
        d=self.s['projects'][self.p['project_uuid']].copy();d['admin']=d['pool']
        with self.assertRaises(ValueError):pool.project_roles_sql(self.p,d)
    def test_scoped_hba_allows_own_db_then_rejects_every_other(self):
        text,rules=pool.hba(self.ps,['127.0.0.1/32'])
        self.assertEqual(len(rules),12)
        for i,p in enumerate(self.ps):
            self.assertEqual(rules[i*4]['database'],[p['database']])
            self.assertEqual(rules[i*4]['auth_method'],'scram-sha-256')
            self.assertIn(pool.role(p),rules[i*4]['user_name'])
            self.assertIn(pool.role(p,'admin'),rules[i*4]['user_name'])
            self.assertTrue(all(x['auth_method']=='reject' for x in rules[i*4+1:i*4+4]))
        self.assertNotIn(' trust',text)
    def test_existing_registry_mode_does_not_reinitialize_registry(self):
        text,rules=pool.hba(self.ps,['127.0.0.1/32'],include_fresh_registry=False)
        self.assertEqual(len(rules),8);self.assertNotIn(pool.CONTROL_ROLE,text)
        sql=pool.activate_sql(self.ps,rules,include_fresh_registry=False)
        self.assertEqual(sql.count(' LOGIN;'),4);self.assertNotIn('ALTER ROLE '+pool.CONTROL_ROLE,sql)
    def test_activation_requires_observed_exact_first_rules(self):
        _,rules=pool.hba(self.ps,['127.0.0.1/32'])
        sql=pool.activate_sql(self.ps,rules)
        for gate in ('POOLER_HBA_PARSE','POOLER_HBA_RELOAD','POOLER_HBA_PREFIX_MISMATCH','POOLER_ROLE_NOT_QUARANTINED'):
            self.assertIn(gate,sql)
        with self.assertRaises(ValueError):pool.activate_sql(self.ps,[])
    def test_explicit_user_auth_no_global_password_query(self):
        data=pool.registration(self.p,self.s['projects'][self.p['project_uuid']]['pool'],client_cidrs=['127.0.0.1/32'],upstream_ssl=False,enforce_ssl=False)['tenant']
        self.assertTrue(data['require_user']);self.assertIsNone(data['auth_query'])
        self.assertEqual(data['db_database'],self.p['database'])
        self.assertEqual(data['users'][0]['db_user'],pool.role(self.p))
        self.assertFalse(data['users'][0]['is_manager'])
        self.assertEqual(data['users'][0]['pool_size'],2)
    def test_default_upstream_tls_requires_verifiable_ca(self):
        password=self.s['projects'][self.p['project_uuid']]['pool']
        with self.assertRaisesRegex(ValueError,'CA_REQUIRED'):pool.registration(self.p,password,client_cidrs=['127.0.0.1/32'])
        d=pool.registration(self.p,password,client_cidrs=['127.0.0.1/32'],upstream_tls_ca=self.private()['upstream_tls_ca'])['tenant']
        self.assertTrue(d['enforce_ssl']);self.assertTrue(d['upstream_ssl']);self.assertEqual(d['upstream_verify'],'peer')
    def test_public_client_cidr_refused(self):
        with self.assertRaises(ValueError):pool.registration(self.p,self.s['projects'][self.p['project_uuid']]['pool'],client_cidrs=['0.0.0.0/0'],upstream_ssl=False,enforce_ssl=False)
    def test_private_registrations_require_owner_lease_not_claim_create_only(self):
        bundle=pool.compile_bundle(self.ps,self.private())
        data=json.loads(bundle[self.p['slug']+'.tenant-request.private.json'])
        self.assertEqual(data['method'],'PUT');self.assertEqual(data['native_operation_semantics'],'UPSERT')
        self.assertTrue(data['requires_original_owner_exclusive_lease']);self.assertTrue(data['requires_absent_readback']);self.assertFalse(data['executed'])
    def test_bundle_reuses_native_registry_and_vault(self):
        bundle=pool.compile_bundle(self.ps,self.private());receipt=json.loads(bundle['pooler-candidate.json'])
        self.assertEqual(receipt['registry_database'],'_supabase');self.assertEqual(receipt['new_registry_databases'],0)
        self.assertEqual(receipt['postgres_servers_added'],0);self.assertEqual(receipt['pooler_services_added'],0)
        self.assertFalse(receipt['production_deployed'])
        self.assertIn(self.s['vault_key'],bundle['registry.env'])
        self.assertIn('DIAL_POOLER_DATABASE_URL',bundle['pooler.compose.env'])
        self.assertNotIn('CREATE DATABASE', '\n'.join(bundle.values()))
    def test_no_default_tenant_reseeding_in_overlay(self):
        text=pool.overlay();self.assertNotIn('pooler.exs',text);self.assertNotIn('ports:',text)
        self.assertIn('/app/bin/migrate && /app/bin/server',text)
        self.assertIn('supabase/supavisor@'+pool.AMD64_IMAGE,text)
    def test_readback_cannot_leak_native_password_field(self):
        raw={'data':{'external_id':pool.tenant_id(self.p),'db_database':self.p['database'],'require_user':True,
            'users':[{'db_user':pool.role(self.p),'db_password':'SHOULD_NEVER_BE_IN_RECEIPT','pool_size':2,'mode_type':'transaction'}]}}
        safe=pool.safe_readback(self.p,raw)
        self.assertNotIn('SHOULD_NEVER',json.dumps(safe));self.assertTrue(safe['native_management_response_redacted'])
        raw['data']['db_database']=self.ps[1]['database']
        with self.assertRaises(ValueError):pool.safe_readback(self.p,raw)
    def test_bundle_registry_cannot_be_application_database(self):
        x=self.private();x['registry_identity']['database']=self.p['database']
        with self.assertRaises(ValueError):pool.compile_bundle(self.ps,x)
    def test_bundle_forbids_cross_project_password_reuse(self):
        x=self.private();x['shared']['projects'][self.ps[1]['project_uuid']]['pool']=x['shared']['projects'][self.p['project_uuid']]['pool']
        with self.assertRaises(ValueError):pool.compile_bundle(self.ps,x)
    def test_bundle_hashes_every_private_artifact(self):
        out=pool.compile_bundle(self.ps,self.private());m=json.loads(out['pooler-candidate.json'])
        for name,digest in m['files'].items():self.assertEqual(hashlib.sha256(out[name].encode()).hexdigest(),digest)
        with tempfile.TemporaryDirectory() as td:
            path=pathlib.Path(td)/'private';b.render.write_bundle(path,out)
            self.assertTrue(all(f.stat().st_mode&0o777==0o600 for f in path.iterdir()))
            with self.assertRaises(ValueError):b.render.write_bundle(path,out)

class AdministrationContracts(unittest.TestCase):
    def setUp(self):
        self.ps=b.render.validate(json.loads((BASE/'projects.rehearsal.json').read_text()))
        s=pool.new_secrets(self.ps)
        self.p={'passwords':{p['project_uuid']:s['projects'][p['project_uuid']]['admin'] for p in self.ps},
            'origin':'https://admin.example.invalid','meta_url':'http://meta:8080','studio_url':'http://studio:3000',
            'crypto_key':'a'*48,'health_key':'b'*64,'issuer':'https://issuer.example.invalid','audience':'project-admin',
            'public_jwk':{'kty':'OKP','crv':'Ed25519','x':'A'*43},
            'operators':[{'subject':'actual-owner','projects':[p['project_uuid'] for p in self.ps],'can_query':True}]}
    def test_one_native_meta_and_studio_no_per_project_stack(self):
        out=admin.compile_bundle(self.ps,self.p);m=json.loads(out['admin-candidate.json'])
        self.assertEqual(m['studio_instances_added'],0);self.assertEqual(m['postgres_servers_added'],0)
        self.assertFalse(m['adds_identity_issuer']);self.assertFalse(m['full_studio_ui_qualified'])
        self.assertNotIn('ports:',out['project-admin.overlay.yml'])
        self.assertEqual(re.findall(r'^  ([a-z-]+):$',out['project-admin.overlay.yml'],re.MULTILINE),['project-admin'])
    def test_private_key_never_accepted_as_verifier(self):
        self.p['public_jwk']['d']='NEVER_ACCEPT'
        with self.assertRaisesRegex(ValueError,'PUBLIC_VERIFIER'):admin.registry(self.ps,**self.p)
    def test_project_dsn_bound_to_only_own_admin_role(self):
        r=admin.registry(self.ps,**self.p)
        for p,item in zip(self.ps,r['projects']):
            self.assertIn(pool.role(p,'admin'),item['connection'])
            self.assertTrue(item['connection'].endswith('/'+p['database']))
            self.assertNotIn('postgres:',item['connection'])
    def test_operator_scope_not_granted_by_arbitrary_request_claims(self):
        self.p['operators'][0]['projects'].append('00000000-0000-0000-0000-000000000000')
        with self.assertRaises(ValueError):admin.registry(self.ps,**self.p)
    def test_duplicate_operator_rejected(self):
        self.p['operators'].append(copy.deepcopy(self.p['operators'][0]))
        with self.assertRaises(ValueError):admin.registry(self.ps,**self.p)
    def test_explicit_boolean_sql_permission(self):
        self.p['operators'][0]['can_query']='yes'
        with self.assertRaises(ValueError):admin.registry(self.ps,**self.p)
    def test_unsafe_meta_target_refused(self):
        for url in ('https://meta:8080','http://foreign.example:8080','http://meta:8080/path','http://user:password@meta:8080'):
            x=copy.deepcopy(self.p);x['meta_url']=url
            with self.subTest(url=url),self.assertRaises(ValueError):admin.registry(self.ps,**x)
    def test_production_origin_and_issuer_require_https(self):
        for key in ('origin','issuer'):
            x=copy.deepcopy(self.p);x[key]='http://admin.example.invalid'
            with self.assertRaises(ValueError):admin.registry(self.ps,**x)
    def test_missing_project_credentials_refused(self):
        self.p['passwords'].pop(self.ps[0]['project_uuid'])
        with self.assertRaises(ValueError):admin.registry(self.ps,**self.p)
    def test_admin_gateway_does_not_use_default_studio_database_on_unknown_api(self):
        source=(BASE/'admin/server.mjs').read_text()
        self.assertIn("p.startsWith('/api/')",source)
        self.assertIn("PROJECT_API_NOT_QUALIFIED",source)
        self.assertIn("'x-connection-encrypted':encryptConnection(project.connection)",source)
        self.assertNotIn('...req.headers',source)
    def test_native_management_role_and_hba_do_not_use_superuser(self):
        r=admin.registry(self.ps,**self.p)
        self.assertTrue(all(p['database_user'].endswith('_admin') and p['database_user'].startswith('dial_') for p in r['projects']))
    def test_registry_hash_binding_and_private_modes(self):
        out=admin.compile_bundle(self.ps,self.p);m=json.loads(out['admin-candidate.json'])
        self.assertEqual(hashlib.sha256(out['admin-registry.private.json'].encode()).hexdigest(),m['registry_sha256'])
        with tempfile.TemporaryDirectory() as td:
            path=pathlib.Path(td)/'private';b.render.write_bundle(path,out)
            self.assertEqual(path.stat().st_mode&0o777,0o700)
            self.assertTrue(all(f.stat().st_mode&0o777==0o600 for f in path.iterdir()))
    def test_native_gateway_requires_finite_operator_tokens_and_capacity_limits(self):
        s=(BASE/'admin/server.mjs').read_text()
        self.assertIn("algorithms:['EdDSA']",s);self.assertIn("maxTokenAge:'10m'",s)
        self.assertIn('payload.exp-payload.iat>600',s);self.assertIn('global:4,perSubject:2,pending:24,pendingPerSubject:12,waitMs:2500',s)
        self.assertIn('ADMIN_CAPACITY_BUSY_NO_REPLAY',s)
    def test_operator_issuer_may_use_exact_https_oidc_path(self):
        self.p['issuer']='https://issuer.example.invalid/auth/realms/dial'
        value=admin.registry(self.ps,**self.p)
        self.assertEqual(value['issuer'],self.p['issuer'])
        self.p['issuer']='https://issuer.example.invalid/auth?other=value'
        with self.assertRaises(ValueError):admin.registry(self.ps,**self.p)
    def test_admin_project_password_reuse_refused(self):
        self.p['passwords'][self.ps[1]['project_uuid']]=self.p['passwords'][self.ps[0]['project_uuid']]
        with self.assertRaisesRegex(ValueError,'CREDENTIAL_REUSE'):admin.registry(self.ps,**self.p)
    def test_admin_overlay_requires_admitted_nonroot_identity(self):
        text=admin.compile_bundle(self.ps,self.p)['project-admin.overlay.yml']
        self.assertIn('DIAL_PROJECT_ADMIN_UID',text)
        self.assertIn('DIAL_PROJECT_ADMIN_GID',text)
        self.assertIn('read_only: true',text)
        self.assertIn('tmpfs:',text)
    def test_image_context_excludes_private_registry_and_dependencies(self):
        allowed=(BASE/'admin/.dockerignore').read_text().splitlines()
        self.assertEqual(allowed[0],'*')
        self.assertEqual(set(allowed[1:]),{'!Dockerfile','!package.json','!package-lock.json','!server.mjs','!admission.mjs','!health.mjs'})
        docker=(BASE/'admin/Dockerfile').read_text()
        self.assertIn('USER node',docker)
        self.assertIn('npm ci --omit=dev --ignore-scripts',docker)
        self.assertIn('@sha256:',docker)
    def test_static_assets_cannot_fall_through_to_next_data(self):
        text=(BASE/'admin/server.mjs').read_text()
        self.assertIn("p.startsWith('/_next/static/')",text)
        self.assertNotIn("p.startsWith('/_next/')",text)
    def test_private_health_does_not_claim_platform_readiness(self):
        text=(BASE/'admin/health.mjs').read_text()
        self.assertIn('DIAL_PROJECT_ADMIN_REGISTRY_SHA256',text)
        self.assertIn('PRIVATE_ADMIN_CANDIDATE_READY',text)
        self.assertNotIn('console.log',text)
        self.assertIn('info.mode&0o077',text)

    def test_browser_test_never_disables_chromium_sandbox(self):
        s=(BASE/'tests/studio_browser.mjs').read_text()
        self.assertIn('chromiumSandbox:true',s);self.assertNotIn('--no-sandbox',s)

if __name__=='__main__':unittest.main()
