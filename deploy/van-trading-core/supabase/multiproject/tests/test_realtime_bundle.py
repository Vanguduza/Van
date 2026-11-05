"""Offline private compiler tests with explicitly synthetic migration bytes."""
import copy
import hashlib
import io
import json
import pathlib
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch
import test_shared_realtime as realtime_fixture
BASE=pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0,str(BASE/'tools'))
import shared_realtime as rt
import shared_storage as st


class RealtimeBundleContracts(unittest.TestCase):
    def setUp(self):
        fixture=realtime_fixture.RealtimeContracts();fixture.setUp()
        self.ps=fixture.ps;self.shared=fixture.shared;self.credentials=fixture.credentials
        self.schema='\n'.join(f'INSERT INTO realtime."schema_migrations" (version) VALUES ({i});' for i in range(80))+'\n'
        self.digest=hashlib.sha256(self.schema.encode()).hexdigest()
        self.image='registry.invalid/dial/realtime@sha256:'+'1'*64
        self.tables={p['project_uuid']:[('public','notes')] for p in self.ps}
    def generate(self,**extra):
        with patch.object(rt,'SCHEMA_SHA256',self.digest):
            return rt.compile_bundle(self.ps,self.credentials,self.shared,['127.0.0.1/32'],self.schema,
                patched_image=self.image,preserved_tenants={},published_tables=self.tables,**extra)
    def test_private_artifact_hashes_and_no_deployment_claim(self):
        files=self.generate();receipt=json.loads(files['shared-realtime-candidate.json'])
        self.assertFalse(receipt['production_deploy_authorized'])
        self.assertEqual(receipt['native_migrations'],80)
        self.assertEqual(receipt['realtime_services_added'],0);self.assertEqual(receipt['postgres_servers_added'],0)
        for name,digest in receipt['files'].items():self.assertEqual(hashlib.sha256(files[name].encode()).hexdigest(),digest)
    def test_native_upsert_effect_is_explicit_and_not_executed(self):
        files=self.generate()
        for p in self.ps:
            record=json.loads(files[p['slug']+'.tenant-registration.private.json'])
            self.assertTrue(record['upstream_post_is_upsert'])
            self.assertTrue(record['requires_original_owner_exclusive_reservation'])
            self.assertEqual(record['existing_tenant_action'],'REFUSE_AND_RECONCILE')
            self.assertFalse(record['executed'])
    def test_combined_gateways_retain_storage_and_add_websocket(self):
        gateways={p['project_uuid']:st.gateway(p,self.credentials[p['project_uuid']]['anon_key'],self.credentials[p['project_uuid']]['service_role_key']) for p in self.ps}
        files=self.generate(storage_gateways=gateways)
        for p in self.ps:
            text=files[p['slug']+'.nginx.conf']
            self.assertIn('http://storage:5000/',text)
            self.assertIn('http://realtime:4000/socket/websocket',text)
            self.assertIn(st.role(p),files['realtime-projects.hba-prefix.conf'])
    def test_missing_project_and_gateway_bindings_refused(self):
        other=self.ps[0]['project_uuid'];removed=self.credentials.pop(other)
        with self.assertRaises(ValueError):self.generate()
        self.credentials[other]=removed
        with self.assertRaises(ValueError):self.generate(storage_gateways={})
    def test_reused_project_signing_secrets_refused(self):
        a,c=self.ps;self.credentials[c['project_uuid']]['jwt_secret']=self.credentials[a['project_uuid']]['jwt_secret']
        with self.assertRaisesRegex(ValueError,'SIGNING_SECRETS_MUST_DIFFER'):self.generate()
    def test_private_cli_output_and_permissions(self):
        with tempfile.TemporaryDirectory() as td:
            root=pathlib.Path(td);manifest=root/'manifest.json';private=root/'private.json';schema=root/'schema.sql'
            manifest.write_text((BASE/'projects.rehearsal.json').read_text());schema.write_text(self.schema)
            private.write_text(json.dumps({'credentials':self.credentials,'shared':self.shared,'preserved_tenants':{},'published_tables':self.tables}));private.chmod(0o600)
            argv=['--manifest',str(manifest),'--private-input',str(private),'--upstream-schema',str(schema),
                '--patched-image',self.image,'--client-cidr','127.0.0.1/32','--out',str(root/'out')]
            with patch.object(rt,'SCHEMA_SHA256',self.digest),redirect_stdout(io.StringIO()) as stdout:
                self.assertEqual(rt.main(argv),0)
            self.assertIn('NOT_DEPLOYED',stdout.getvalue());self.assertNotIn(self.shared['admin_jwt_secret'],stdout.getvalue())
            self.assertEqual((root/'out').stat().st_mode&0o777,0o700)
            self.assertTrue(all(f.stat().st_mode&0o777==0o600 for f in (root/'out').iterdir()))
            with patch.object(rt,'SCHEMA_SHA256',self.digest),redirect_stdout(io.StringIO()):self.assertEqual(rt.main(argv),2)
    def test_nonprivate_input_denied_before_output(self):
        with tempfile.TemporaryDirectory() as td:
            root=pathlib.Path(td);manifest=root/'manifest.json';private=root/'private.json';schema=root/'schema.sql'
            manifest.write_text((BASE/'projects.rehearsal.json').read_text());private.write_text('{}');private.chmod(0o644);schema.write_text(self.schema)
            with redirect_stdout(io.StringIO()):
                rc=rt.main(['--manifest',str(manifest),'--private-input',str(private),'--upstream-schema',str(schema),'--patched-image',self.image,'--client-cidr','127.0.0.1/32','--out',str(root/'out')])
            self.assertEqual(rc,2);self.assertFalse((root/'out').exists())
    def test_container_recipe_is_pinned_and_unprivileged(self):
        text=(BASE/'realtime-image/Dockerfile').read_text()
        self.assertIn('FROM '+rt.BASE_AMD64_IMAGE,text)
        self.assertIn('USER nobody',text)
        self.assertNotIn('RUN apk',text);self.assertNotIn('apt-get',text)
        self.assertNotIn('latest',text)
        compile=(BASE/'realtime-image/compile_patch.exs').read_text()
        self.assertIn('DIAL_REALTIME_PATCH_SOURCE_MISMATCH',compile)
        self.assertIn('DIAL_REALTIME_BASE_MODULE_MISMATCH',compile)
        self.assertIn('production_qualified: false',compile)
        self.assertNotIn('Application.ensure_all_started',compile)

if __name__=='__main__':unittest.main()
