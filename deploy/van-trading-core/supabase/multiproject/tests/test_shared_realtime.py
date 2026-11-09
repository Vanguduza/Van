"""Staged configuration/source contracts; native proof is rehearse_realtime.py."""
import base64
import copy
import hashlib
import hmac
import json
import pathlib
import re
import sys
import unittest
from unittest.mock import patch
BASE=pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0,str(BASE/'tools'))
import bootstrap as b
import shared_storage as st
import shared_realtime as rt
import patch_realtime as pr

class RealtimeContracts(unittest.TestCase):
    def setUp(self):
        self.ps=b.render.validate(json.loads((BASE/'projects.rehearsal.json').read_text()))
        self.p=self.ps[0];self.shared=rt.new_secrets(self.ps);self.credentials={}
        for p in self.ps:
            s=b.new_secrets()
            self.credentials[p['project_uuid']]={'project_uuid':p['project_uuid'],'jwt_secret':s['jwt'],
                'anon_key':b.token(p,s['jwt'],'anon'),'service_role_key':b.token(p,s['jwt'],'service_role')}
        self.c=self.credentials[self.p['project_uuid']]
    def test_security_patched_upstream_pin_and_schema(self):
        self.assertEqual(rt.VERSION,'2.152.0')
        self.assertRegex(rt.SOURCE_COMMIT,r'^[a-f0-9]{40}$')
        self.assertRegex(rt.SCHEMA_SHA256,r'^[a-f0-9]{64}$')
        self.assertIn('@sha256:',rt.BASE_AMD64_IMAGE)
    def test_stable_distinct_runtime_and_cdc_slot_identities(self):
        self.assertNotEqual(rt.role(self.ps[0]),rt.role(self.ps[1]))
        self.assertNotEqual(rt.cdc_slot(self.ps[0]),rt.cdc_slot(self.ps[1]))
        for p in self.ps:
            self.assertLessEqual(len(rt.role(p)),63);self.assertLessEqual(len(rt.cdc_slot(p)),63)
            self.assertEqual(rt.tenant_id(p),p['project_uuid'].replace('-',''))
    def test_namespace_rejects_published_cross_tenant_collision(self):
        for name in ('victim-private','victim:room','../tenant','','x'*64):
            with self.subTest(name=name),self.assertRaises(ValueError):rt.native_id(name)
        self.assertEqual(rt.native_id('original-realtime'),'original-realtime')
    def test_duplicate_project_and_control_db_collision_refused(self):
        with self.assertRaises(ValueError):rt.projects_checked([self.p,self.p])
        p=copy.deepcopy(self.p);p['database']=rt.CONTROL_DB
        with self.assertRaises(ValueError):rt.projects_checked([p])
    def test_distinct_shared_and_project_secrets(self):
        values=[v for k,v in self.shared.items() if isinstance(v,str)]+list(self.shared['projects'].values())
        self.assertEqual(len(set(values)),len(values))
        self.assertEqual(len(self.shared['db_encryption_key']),16)
    def test_management_jwt_is_separate_and_bounded(self):
        tok=rt.admin_token(self.shared['admin_jwt_secret'],now=1000)
        head,body,sig=tok.split('.');dec=lambda x:base64.urlsafe_b64decode(x+'='*(-len(x)%4))
        claims=json.loads(dec(body))
        self.assertEqual(claims['role'],'dial_realtime_admin');self.assertEqual(claims['exp']-claims['iat'],3600)
        self.assertEqual(dec(sig),hmac.digest(self.shared['admin_jwt_secret'].encode(),(head+'.'+body).encode(),'sha256'))
        self.assertNotEqual(tok,self.c['service_role_key'])
    def test_runtime_roles_quarantined_and_not_cluster_admin(self):
        sql=rt.role_sql(self.p,self.shared['projects'][rt.tenant_id(self.p)])
        self.assertIn('NOLOGIN INHERIT NOSUPERUSER NOCREATEDB NOCREATEROLE REPLICATION NOBYPASSRLS',sql)
        self.assertIn('CANONICAL_REALTIME_ROLE_REQUIRED',sql)
        self.assertIn('CANONICAL_REALTIME_PARAMETER_PERMISSION_REQUIRED',sql)
        self.assertNotIn(self.shared['projects'][rt.tenant_id(self.p)],sql)
        self.assertNotRegex(sql,r'GRANT (postgres|supabase_admin|dashboard_user) TO')
        self.assertNotIn('CREATE ROLE supabase_realtime_admin',sql)
    def test_weak_runtime_password_refused(self):
        with self.assertRaises(ValueError):rt.role_sql(self.p,'short')
    def test_registry_is_nonreplication_role_and_private_new_database(self):
        role,db=rt.control_sql(self.shared['control_password'])
        self.assertIn('NOREPLICATION',role);self.assertIn('NOLOGIN',role)
        self.assertIn('TEMPLATE template0',db);self.assertIn('FROM PUBLIC',db)
        self.assertNotIn('DROP',db);self.assertNotIn('ALTER DATABASE "postgres"',db)
    def test_registry_schema_is_bound_to_control_database(self):
        sql=rt.control_schema_sql()
        self.assertIn(rt.CONTROL_DB,sql);self.assertIn('WRONG_REALTIME_REGISTRY_DATABASE',sql)
        self.assertIn('CREATE SCHEMA _realtime',sql)
    def test_native_schema_must_match_exact_digest(self):
        with self.assertRaises(ValueError):rt.fresh_schema_sql(self.p,'-- arbitrary schema')
    def test_schema_guard_preserves_existing_state(self):
        fixture='-- exact synthetic schema fixture\n'
        with patch.object(rt,'SCHEMA_SHA256',hashlib.sha256(fixture.encode()).hexdigest()):
            sql=rt.fresh_schema_sql(self.p,fixture)
        self.assertIn('REALTIME_SCHEMA_EXISTS_RECONCILE',sql)
        self.assertIn('REALTIME_PROJECT_IDENTITY_MISMATCH',sql)
        self.assertIn(self.p['project_uuid'],sql)
        self.assertNotIn('DROP',sql)
    def test_publication_requires_explicit_application_tables(self):
        for tables in ([],[('auth','users')],[('public','notes'),('public','notes')],[('public','x;drop')]):
            with self.subTest(tables=tables),self.assertRaises(ValueError):rt.publication_sql(self.p,tables)
        sql=rt.publication_sql(self.p,[('public','notes')])
        self.assertIn('FOR TABLE "public"."notes"',sql)
        self.assertNotIn('FOR ALL TABLES',sql)
        self.assertIn('WRONG_REALTIME_PUBLICATION_DATABASE',sql)
    def test_complete_hba_preserves_preexisting_storage_and_auth_prefix(self):
        text,rules=rt.hba(self.ps,['127.0.0.1/32'])
        old,oldrules=st.hba(self.ps,['127.0.0.1/32'])
        self.assertTrue(text.endswith(old));self.assertEqual(rules[-len(oldrules):],oldrules)
    def test_physical_replication_rejected_before_database_allow(self):
        _,rules=rt.hba(self.ps,['127.0.0.1/32'],include_storage=False)
        for n,p in enumerate(self.ps):
            own=rules[n*7:n*7+7]
            self.assertTrue(all(x['database']==['replication'] and x['auth_method']=='reject' for x in own[:3]))
            self.assertEqual(own[3]['database'],[p['database']]);self.assertEqual(own[3]['auth_method'],'scram-sha-256')
            self.assertTrue(all(x['database']==['all'] and x['auth_method']=='reject' for x in own[4:]))
            self.assertTrue(all(x['user_name']==[rt.role(p)] for x in own))
    def test_global_network_hba_refused(self):
        for networks in (['0.0.0.0/0'],['::/0'],['8.8.8.8/32'],[]):
            with self.subTest(networks=networks),self.assertRaises(ValueError):rt.hba(self.ps,networks)
    def test_activation_checks_reload_and_exact_roles(self):
        _,rules=rt.hba(self.ps,['127.0.0.1/32']);sql=rt.activation_sql(self.ps,rules)
        self.assertIn('REALTIME_EXACT_HBA_PREFIX_REQUIRED',sql)
        self.assertIn('REALTIME_HBA_RELOAD_REQUIRED',sql)
        self.assertIn('rolreplication=true',sql);self.assertIn('rolreplication=false',sql)
        self.assertEqual(sql.count(' LOGIN;'),3)
    def test_empty_activation_refused(self):
        with self.assertRaises(ValueError):rt.activation_sql(self.ps,[])
    def test_environment_never_reseeds_tenants(self):
        env=rt.environment(self.shared)
        self.assertEqual(env['SEED_SELF_HOST'],'false');self.assertEqual(env['DB_USER'],rt.CONTROL_ROLE)
        self.assertEqual(env['DB_NAME'],rt.CONTROL_DB);self.assertEqual(env['RUN_JANITOR'],'true')
        self.assertNotEqual(env['API_JWT_SECRET'],env['METRICS_JWT_SECRET'])
        self.assertEqual(env['DB_POOL_SIZE'],'2')
    def test_environment_key_length_and_reused_control_secret_refused(self):
        bad=copy.deepcopy(self.shared);bad['db_encryption_key']='wrong'
        with self.assertRaises(ValueError):rt.environment(bad)
        bad=copy.deepcopy(self.shared);bad['metrics_jwt_secret']=bad['admin_jwt_secret']
        with self.assertRaises(ValueError):rt.environment(bad)
    def test_registration_exact_original_credentials_and_scoped_slots(self):
        value=rt.registration(self.p,self.c,self.shared,90)['tenant']
        self.assertEqual(value['external_id'],rt.tenant_id(self.p))
        self.assertEqual(value['jwt_secret'],self.c['jwt_secret'])
        self.assertTrue(value['private_only']);self.assertTrue(value['presence_enabled'])
        settings=value['extensions'][0]['settings']
        self.assertEqual(settings['db_user'],rt.role(self.p));self.assertEqual(settings['db_name'],self.p['database'])
        self.assertEqual(settings['slot_name'],rt.cdc_slot(self.p));self.assertEqual(settings['publication'],'supabase_realtime')
    def test_registration_wrong_project_jwt_refused(self):
        with self.assertRaises(ValueError):rt.registration(self.ps[1],self.c,self.shared,90)
    def test_registration_no_invented_migration_count(self):
        for count in (0,-1,True,1.0,1001):
            with self.subTest(count=count),self.assertRaises(ValueError):rt.registration(self.p,self.c,self.shared,count)
    def test_legacy_native_tenant_identity_can_be_preserved(self):
        reg=rt.registration(self.p,self.c,self.shared,90,preserved_tenant_id='realtime-dev')
        self.assertEqual(reg['tenant']['external_id'],'realtime-dev')
    def test_gateway_native_socket_and_explicit_http_route_only(self):
        text=rt.gateway(self.p,self.c['anon_key'],self.c['service_role_key'])
        self.assertIn('/realtime/v1/websocket',text);self.assertIn('http://realtime:4000/socket/websocket;',text)
        self.assertIn('proxy_http_version 1.1',text);self.assertIn('Upgrade $http_upgrade',text)
        self.assertIn('/realtime/v1/api/broadcast',text);self.assertIn('/realtime/v1/ { return 404; }',text)
        self.assertNotIn('proxy_pass http://realtime:4000/api/tenants',text)
    def test_gateway_header_query_keys_must_match(self):
        text=rt.gateway(self.p,self.c['anon_key'],self.c['service_role_key'])
        a=self.c['anon_key'];s=self.c['service_role_key']
        for pair in (a+':',':'+a,a+':'+a,s+':',':'+s,s+':'+s):self.assertIn('"'+pair+'"',text)
        self.assertNotIn('"'+a+':'+s+'"',text)
        self.assertIn('default "";',text)
    def test_gateway_regex_names_fit_pcre_and_strip_spoofed_identity(self):
        text=rt.gateway(self.p,self.c['anon_key'],self.c['service_role_key'])
        names=re.findall(r'\(\?<([^>]+)>',text)
        self.assertTrue(names and all(len(n)<=32 for n in names))
        self.assertIn('X-API-Key $dial_',text);self.assertIn('X-Tenant-ID ""',text)
        self.assertIn(rt.tenant_id(self.p)+'.realtime.internal',text)
    def test_gateway_preserves_storage_when_combined(self):
        storage=st.gateway(self.p,self.c['anon_key'],self.c['service_role_key'])
        both=rt.gateway(self.p,self.c['anon_key'],self.c['service_role_key'],base_config=storage)
        self.assertIn('http://storage:5000/',both);self.assertIn('http://realtime:4000/socket/websocket',both)
        self.assertIn('/functions/v1/ { return 503; }',both)
    def test_gateway_rejects_double_patch_and_untrusted_upstream(self):
        text=rt.gateway(self.p,self.c['anon_key'],self.c['service_role_key'])
        with self.assertRaises(ValueError):rt.gateway(self.p,self.c['anon_key'],self.c['service_role_key'],base_config=text)
        for upstream in ('http://evil:4000','realtime:0','realtime:65536','realtime:4000;bad'):
            with self.subTest(upstream=upstream),self.assertRaises(ValueError):rt.gateway(self.p,self.c['anon_key'],self.c['service_role_key'],upstream)
    def test_overlay_refuses_unpatched_and_mutable_images(self):
        for image in (rt.BASE_AMD64_IMAGE,'supabase/realtime:v2.152.0','supabase/realtime:latest'):
            with self.subTest(image=image),self.assertRaises(ValueError):rt.overlay(image)
        text=rt.overlay('registry.invalid/dial/realtime@sha256:'+'1'*64)
        self.assertEqual(re.findall(r'^  ([a-z0-9_-]+):$',text,re.MULTILINE),['realtime'])
        self.assertNotIn('ports:',text);self.assertIn('SEED_SELF_HOST: "false"',text)
        self.assertIn('RUN_JANITOR: "true"',text);self.assertIn('DIAL_REALTIME_API_JWT_SECRET:?',text)
    def observation(self):
        return {'server_version_num':170011,'wal_level':'logical','max_replication_slots':16,'used_slots':1,
          'max_wal_senders':16,'active_senders':1,'max_connections':100,'used_connections':20,
          'output_plugin_libraries':'pgoutput, wal2json','max_slot_wal_keep_size':'64MB'}
    def test_preflight_readonly_and_bounded_slots(self):
        query=rt.cluster_preflight_sql(2)
        self.assertNotIn('ALTER',query);self.assertIn("'required_new_slots',4",query)
        rt.verify_cluster_observation(self.observation(),2)
    def test_preflight_denies_old_minor_missing_plugins_and_unbounded_wal(self):
        for values in ({'server_version_num':170006},{'wal_level':'replica'},{'output_plugin_libraries':'pgoutput'},
                       {'max_slot_wal_keep_size':'-1'},{'max_replication_slots':4,'used_slots':2},
                       {'max_connections':32,'used_connections':10},{'max_wal_senders':2,'active_senders':1}):
            o=self.observation();o.update(values)
            with self.subTest(values=values),self.assertRaises(ValueError):rt.verify_cluster_observation(o,2)
    def test_preflight_strict_types(self):
        for count in (0,-1,33,True,1.0):
            with self.subTest(count=count),self.assertRaises(ValueError):rt.cluster_preflight_sql(count)
        o=self.observation();o['max_connections']=True
        with self.assertRaises(ValueError):rt.verify_cluster_observation(o,2)

class SlotPatchContracts(unittest.TestCase):
    def synthetic_source(self):
        return ('    slot_name = replication_slot_name(@schema, @table)\n'
            '    replication_slot_name = replication_slot_name(@schema, @table)\n'
            '  defp slot_suffix, do: Application.get_env(:realtime, :slot_name_suffix)\n')
    def test_foreign_source_refused(self):
        with self.assertRaises(ValueError):pr.patched_source(self.synthetic_source())
    def test_both_original_runtime_calls_scoped(self):
        source=self.synthetic_source()
        with patch.object(pr,'UPSTREAM_SHA256',hashlib.sha256(source.encode()).hexdigest()):patched=pr.patched_source(source)
        self.assertIn('replication_slot_name(@schema, @table, tenant_id)',patched)
        self.assertIn('replication_slot_name(@schema, @table, state.tenant_id)',patched)
        self.assertIn(':crypto.hash(:sha256, scope)',patched)
        self.assertNotIn('= replication_slot_name(@schema, @table)\n',patched)
    def test_missing_and_repeated_calls_refused(self):
        for source in (self.synthetic_source().replace('    slot_name =','    other ='),self.synthetic_source()*2):
            with patch.object(pr,'UPSTREAM_SHA256',hashlib.sha256(source.encode()).hexdigest()),self.assertRaises(ValueError):pr.patched_source(source)
    def test_reference_slots_are_stable_distinct_and_bounded(self):
        slots=[pr.expected_slot('realtime','messages',t) for t in ('a','b','a-private')]
        self.assertEqual(len(set(slots)),3)
        self.assertTrue(all(len(x)<=63 and re.fullmatch('[a-z0-9_]+',x) for x in slots))
        self.assertEqual(slots[0],pr.expected_slot('realtime','messages','a'))
        self.assertNotEqual(slots[0],pr.expected_slot('realtime','messages','a','other-release'))
    def test_empty_or_ambiguous_slot_scope_refused(self):
        with self.assertRaises(ValueError):pr.expected_slot('realtime','messages','')
        with self.assertRaises(ValueError):pr.expected_slot('realtime','messages','a\0b')

if __name__=='__main__':unittest.main()
