"""One shared Edge Runtime: exact project/key/worker scope and staged-only contracts."""
import copy
import hashlib
import json
import pathlib
import sys
import tempfile
import unittest
BASE=pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0,str(BASE/'tools'))
import bootstrap as b
import shared_edge as e

class EdgeContracts(unittest.TestCase):
    def setUp(self):
        self.ps=b.render.validate(json.loads((BASE/'projects.rehearsal.json').read_text()))
        self.shared=e.runtime_secrets(self.ps)
        self.credentials={}
        self.api={}
        self.origins={}
        self.functions={}
        for p in self.ps:
            s=b.new_secrets();uuid=p['project_uuid']
            self.credentials[uuid]={'project_uuid':uuid,'jwt_secret':s['jwt'],
                'anon_key':b.token(p,s['jwt'],'anon'),'service_role_key':b.token(p,s['jwt'],'service_role')}
            self.api[uuid]='http://tenant-'+p['slug']+'-api:8080'
            self.origins[uuid]=['https://'+p['hostname']]
            self.functions[uuid]=[{'name':'identify','source':"Deno.serve(()=>Response.json({ok:true}));",
                'auth':'user','env':{'CANARY':'synthetic-fixture'},
                'net_allow':[],'memory_mb':64,'timeout_ms':2000,'cpu_ms':250,'allow_service_role':False}]
        self.private={'credentials':self.credentials,'shared':self.shared,'functions':self.functions,
                      'api_endpoints':self.api,'allowed_origins':self.origins,
                      'worker_root':'/home/deno/private-workers'}
    def registry(self):return e.registry(self.ps,**self.private)
    def test_stable_distinct_project_names(self):
        self.assertNotEqual(e.project_host(self.ps[0]),e.project_host(self.ps[1]))
        self.assertTrue(all(x.endswith('.edge.internal') for x in map(e.project_host,self.ps)))
    def test_random_gateway_secrets_and_control_distinct(self):
        values=list(self.shared['gateway_keys'].values())+[self.shared['health_key']]
        self.assertEqual(len(values),len(set(values)))
        self.assertTrue(all(len(v)>=48 for v in values))
    def test_registry_binds_real_scoped_jwt_keys(self):
        record=self.registry()
        self.assertEqual(len(record['projects']),2)
        for p in record['projects']:
            self.assertEqual(p['issuer'],'https://'+p['hostname']+'/auth/v1')
            self.assertEqual(p['internal_host'],p['project_uuid'].replace('-','')+'.edge.internal')
            self.assertEqual(p['anon_key'],self.credentials[p['project_uuid']]['anon_key'])
            self.assertNotEqual(p['gateway_key'],self.shared['health_key'])
    def test_runtime_revision_binds_code_and_permissions(self):
        p=self.ps[0];uid=p['project_uuid'];f=self.functions[uid][0]
        a=e.function(p,self.credentials[uid],f,self.api[uid])
        changed=copy.deepcopy(f);changed['cpu_ms']+=1
        newer=e.function(p,self.credentials[uid],changed,self.api[uid])
        self.assertNotEqual(a['revision'],newer['revision'])
        self.assertEqual(a['source_sha256'],hashlib.sha256(f['source'].encode()).hexdigest())
        self.assertNotIn('SUPABASE_SERVICE_ROLE_KEY',a['env'])
    def test_explicit_service_role_grant_only(self):
        p=self.ps[0];uid=p['project_uuid'];f=copy.deepcopy(self.functions[uid][0])
        f['allow_service_role']=True
        x=e.function(p,self.credentials[uid],f,self.api[uid])
        self.assertEqual(x['env']['SUPABASE_SERVICE_ROLE_KEY'],self.credentials[uid]['service_role_key'])
    def test_extra_or_missing_authority_field_refused(self):
        p=self.ps[0];uid=p['project_uuid']
        for bad in [{'allow_service_role':False,'arbitrary':True},{'auth':'unknown'}]:
            f=copy.deepcopy(self.functions[uid][0]);f.update(bad)
            with self.subTest(bad=bad),self.assertRaises(ValueError):e.function(p,self.credentials[uid],f,self.api[uid])
        f=copy.deepcopy(self.functions[uid][0]);f.pop('allow_service_role')
        with self.assertRaises(ValueError):e.function(p,self.credentials[uid],f,self.api[uid])
    def test_env_cannot_override_project_identity_or_native_flags(self):
        p=self.ps[0];uid=p['project_uuid']
        for name in ('SUPABASE_SERVICE_ROLE_KEY','SUPABASE_URL','DIAL_PROJECT_ID','DENO_FLAGS','NODE_OPTIONS','LD_PRELOAD','DIAL_EDGE_REGISTRY'):
            f=copy.deepcopy(self.functions[uid][0]);f['env'][name]='unexpected'
            with self.subTest(name=name),self.assertRaises(ValueError):e.function(p,self.credentials[uid],f,self.api[uid])
    def test_function_limits_fail_closed(self):
        p=self.ps[0];uid=p['project_uuid']
        for key,bad in [('timeout_ms',20000),('cpu_ms',1),('memory_mb',256),('timeout_ms',True)]:
            f=copy.deepcopy(self.functions[uid][0]);f[key]=bad
            with self.subTest(key=key,value=bad),self.assertRaises(ValueError):e.function(p,self.credentials[uid],f,self.api[uid])
    def test_internal_and_ip_egress_refused(self):
        p=self.ps[0];uid=p['project_uuid']
        for addr in ('127.0.0.1:8080','db:5432','tenant-neighbor-api:8080','metadata.internal:80','storage:5000','192.168.1.2:8080'):
            f=copy.deepcopy(self.functions[uid][0]);f['net_allow']=[addr]
            with self.subTest(addr=addr),self.assertRaises(ValueError):e.function(p,self.credentials[uid],f,self.api[uid])
    def test_private_api_endpoint_is_exact(self):
        p=self.ps[0];uid=p['project_uuid']
        for address in ('https://example.com','http://db:5432','http://tenant-'+p['slug']+'-api:8080/bad','http://127.0.0.1:0'):
            with self.subTest(address=address),self.assertRaises(ValueError):e.function(p,self.credentials[uid],self.functions[uid][0],address)
    def test_unreviewed_origin_refused(self):
        p=self.ps[0];uid=p['project_uuid']
        for origin in ('http://'+p['hostname'],'https://*.example.com','https://example.com/extra','https://user:pass@example.com'):
            self.origins[uid]=[origin]
            with self.subTest(origin=origin),self.assertRaises(ValueError):self.registry()
        self.origins[uid]=['https://'+p['hostname']]
    def test_project_credential_mix_refused(self):
        a,c=self.ps;aa=a['project_uuid'];cc=c['project_uuid']
        self.credentials[aa]=copy.deepcopy(self.credentials[cc]);self.credentials[aa]['project_uuid']=aa
        with self.assertRaises(ValueError):self.registry()
    def test_signer_reuse_refused(self):
        a,c=self.ps;aa=a['project_uuid'];cc=c['project_uuid']
        self.credentials[cc]['jwt_secret']=self.credentials[aa]['jwt_secret']
        with self.assertRaises(ValueError):self.registry()
    def test_duplicate_function_name_refused(self):
        p=self.ps[0];uid=p['project_uuid']
        self.functions[uid].append(copy.deepcopy(self.functions[uid][0]))
        with self.assertRaises(ValueError):self.registry()
    def test_missing_or_extra_project_binding_refused(self):
        p=self.ps[0];uid=p['project_uuid']
        self.api.pop(uid)
        with self.assertRaises(ValueError):self.registry()
    def test_worker_root_must_not_traverse(self):
        self.private['worker_root']='/private/../etc'
        with self.assertRaises(ValueError):self.registry()
    def test_gateway_fails_closed_without_required_route(self):
        p=self.ps[0];uid=p['project_uuid']
        with self.assertRaises(ValueError):e.gateway(p,self.credentials[uid],self.shared['gateway_keys'][uid],self.api[uid],base_config='server {}')
    def test_gateway_keeps_manager_private_and_removes_spoof_headers(self):
        p=self.ps[0];uid=p['project_uuid'];value=e.gateway(p,self.credentials[uid],self.shared['gateway_keys'][uid],self.api[uid])
        self.assertIn('proxy_set_header X-Dial-Edge-Gateway',value)
        self.assertIn('proxy_set_header X-Tenant-ID ""',value)
        self.assertIn('proxy_set_header X-Dial-Edge-Health ""',value)
        self.assertIn('proxy_pass http://functions:9000/',value)
        self.assertNotIn('location ^~ /functions/v1/ { return 503; }',value)
    def test_bundle_is_staged_only_and_adds_no_postgres(self):
        output=e.compile_bundle(self.ps,self.private)
        j=json.loads(output['edge-candidate.json'])
        self.assertFalse(j['production_deploy_authorized'])
        self.assertEqual(j['postgres_servers_added'],0)
        self.assertEqual(j['edge_runtime_services_added'],0)
        self.assertIn('    security_opt: ["no-new-privileges:true"]',output['shared-edge.overlay.yml'])
        self.assertIn('supabase/edge-runtime@'+e.AMD64_IMAGE_DIGEST,output['shared-edge.overlay.yml'])
        self.assertNotIn('ports:',output['shared-edge.overlay.yml'])
        self.assertEqual(hashlib.sha256(output['registry.json'].encode()).hexdigest(),j['registry_sha256'])
    def test_private_candidate_can_only_write_new_directory(self):
        output=e.compile_bundle(self.ps,self.private)
        with tempfile.TemporaryDirectory() as td:
            f=pathlib.Path(td)/'private'
            b.render.write_bundle(f,output)
            self.assertEqual(f.stat().st_mode&0o777,0o700)
            self.assertTrue(all(x.stat().st_mode&0o777==0o600 for x in f.iterdir()))
            with self.assertRaises(ValueError):b.render.write_bundle(f,output)
    def test_direct_cli_denies_nonprivate_json(self):
        with tempfile.TemporaryDirectory() as td:
            root=pathlib.Path(td);m=root/'projects.json';j=root/'input.json'
            m.write_text((BASE/'projects.rehearsal.json').read_text())
            j.write_text(json.dumps(self.private));j.chmod(0o644)
            self.assertEqual(e.main(['--manifest',str(m),'--private-input',str(j),'--out',str(root/'out')]),2)
            self.assertFalse((root/'out').exists())

if __name__=='__main__':unittest.main()
