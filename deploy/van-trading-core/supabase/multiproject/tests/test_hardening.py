"""Offline configuration/security regression tests; no VM or database calls."""
import copy
import hashlib
import io
import json
import os
import pathlib
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from unittest.mock import patch
from test_render import DEFAULT, mod


def two_projects():
    data = copy.deepcopy(DEFAULT)
    data['projects'].append(dict(slug='fixture-project', database='fixture_db',
        project_uuid='5238a352-e1e1-4c5a-8e15-b39320fd00ad',
        hostname='fixture-api.example.invalid', loopback_port=18082, status='PLANNED'))
    return data


class ValidationHardening(unittest.TestCase):
    def refused(self, key, values):
        for value in values:
            with self.subTest(key=key, value=value):
                data = copy.deepcopy(DEFAULT)
                data['projects'][0][key] = value
                with self.assertRaises(mod.CandidateError):
                    mod.validate(data)

    def test_hostname_invalid_labels(self):
        self.refused('hostname', ['a..example.com', '-a.example.com', 'a-.example.com',
            'a.' + 'b'*64 + '.com', 'a.example.com.', '*.example.com', 'a.EXAMPLE.com',
            'a_b.example.com', '127.0.0.1', 'a.123', 'a.localhost',
            'a.example.com; return 200;', 'a.example.com\n', '', None, []])

    def test_uuid_noncanonical_or_nonstring(self):
        self.refused('project_uuid', [None, [], 1, True,
            '00000000-0000-0000-0000-000000000000',
            '53D39B5D-BF19-4CF1-9A5B-0904192D90D1', '53d39b5dbf194cf19a5b0904192d90d1'])

    def test_schema_requires_integer_not_bool_or_float(self):
        for value in [True, False, 1.0, '1', None]:
            data = copy.deepcopy(DEFAULT); data['schema_version'] = value
            with self.subTest(value=value), self.assertRaises(mod.CandidateError):
                mod.validate(data)

    def test_all_project_identities_unique(self):
        for field in ('slug','database','project_uuid','hostname','loopback_port'):
            data = two_projects()
            data['projects'][1][field] = data['projects'][0][field]
            with self.subTest(field=field), self.assertRaisesRegex(mod.CandidateError,'DUPLICATE_'):
                mod.validate(data)

    def test_invalid_port_types(self):
        self.refused('loopback_port', [True, 18081.0, '18081', 17999, 19000, [], None])

    def test_manifest_rejects_duplicate_json_keys(self):
        with tempfile.TemporaryDirectory() as td:
            path = pathlib.Path(td)/'manifest.json'
            path.write_text('{"schema_version":1,"schema_version":2}')
            with self.assertRaisesRegex(mod.CandidateError,'DUPLICATE_JSON_KEY'):
                mod.load_manifest(path)

    def test_manifest_size_is_bounded(self):
        with tempfile.TemporaryDirectory() as td:
            path = pathlib.Path(td)/'manifest.json'; path.write_bytes(b' '*1048577)
            with self.assertRaisesRegex(mod.CandidateError,'MANIFEST_TOO_LARGE'):
                mod.load_manifest(path)

    def test_invalid_json_has_no_content_in_error(self):
        with tempfile.TemporaryDirectory() as td:
            path = pathlib.Path(td)/'manifest.json'; path.write_text('secret-value not JSON')
            with self.assertRaisesRegex(mod.CandidateError, '^MANIFEST_INVALID_JSON$'):
                mod.load_manifest(path)

    def test_two_project_outputs_and_ordering(self):
        data = two_projects(); first = mod.validate(data)
        data['projects'].reverse(); second = mod.validate(data)
        self.assertEqual(mod.emit_compose(first), mod.emit_compose(second))
        compose = mod.emit_compose(first)
        import re
        top_services = re.findall(r'^  ([a-z0-9-]+):$', compose, re.MULTILINE)
        self.assertEqual(len(top_services), 8)
        self.assertNotIn('db',top_services)
        self.assertNotIn('container_name',compose)
        self.assertNotIn('image: "supabase/postgres',compose)
        for project in first:
            self.assertIn('127.0.0.1:'+str(project['loopback_port'])+':8080',compose)
            self.assertIn('/projects/'+project['slug']+'/auth.env',compose)

    def test_correct_pinned_donor_environment_contract(self):
        p=DEFAULT['projects'][0]; text=mod.secret_contract(p['slug'],p['database'],p['hostname'])
        self.assertNotIn('GOTRUE_API_EXTERNAL_URL',text)
        self.assertIn('API_EXTERNAL_URL -> https://'+p['hostname']+'/auth/v1',text)
        self.assertIn('AUTH_JWT_SECRET',text)
        self.assertIn('POSTGREST_URL=http://tenant-nissan-gtr-rest:3000',text)
        self.assertIn('ENABLE_IMAGE_TRANSFORMATION=false',text)
        self.assertNotIn('PGRST_JWT_SECRET',text.split('/storage.env')[1])

    def test_router_fails_closed_unqualified_services(self):
        text=mod.emit_nginx(DEFAULT['projects'][0])
        self.assertIn('default_server; server_name _; return 421;',text)
        self.assertIn('UNQUALIFIED_CANDIDATE',text)
        self.assertIn('/functions/v1/ { return 503;',text)
        self.assertIn('/realtime/v1/ { return 503;',text)
        self.assertIn('proxy_set_header X-Tenant-ID "";',text)
        self.assertIn('proxy_set_header Forwarded "";',text)


class OutputHardening(unittest.TestCase):
    def test_new_bundle_private_and_existing_untouched(self):
        with tempfile.TemporaryDirectory() as td:
            out=pathlib.Path(td)/'candidate'
            mod.write_bundle(out,{'a':'first'})
            self.assertEqual(out.stat().st_mode & 0o777,0o700)
            self.assertEqual((out/'a').stat().st_mode & 0o777,0o600)
            with self.assertRaisesRegex(mod.CandidateError,'OUTPUT_ALREADY_EXISTS'):
                mod.write_bundle(out,{'a':'second'})
            self.assertEqual((out/'a').read_text(),'first')

    def test_symlink_destination_refused(self):
        with tempfile.TemporaryDirectory() as td:
            root=pathlib.Path(td); target=root/'target'; target.mkdir()
            link=root/'candidate'; link.symlink_to(target, target_is_directory=True)
            with self.assertRaises(mod.CandidateError):
                mod.write_bundle(link,{'a':'x'})
            self.assertEqual(list(target.iterdir()),[])

    def test_symlink_parent_refused(self):
        with tempfile.TemporaryDirectory() as td:
            root=pathlib.Path(td); target=root/'target'; target.mkdir()
            link=root/'link'; link.symlink_to(target,target_is_directory=True)
            with self.assertRaises(OSError):
                mod.write_bundle(link/'candidate',{'a':'x'})
            self.assertFalse((target/'candidate').exists())

    def test_active_installation_and_relative_paths_refused(self):
        for path in ['/opt/van-trading/supabase/new','/etc/dial-supabase/new',
                     '/srv/dial-supabase/new','relative','/tmp/../tmp/new']:
            with self.subTest(path=path), self.assertRaises(mod.CandidateError):
                mod.write_bundle(pathlib.Path(path),{'a':'x'})

    def test_artifact_traversal_cleanup(self):
        with tempfile.TemporaryDirectory() as td:
            out=pathlib.Path(td)/'candidate'
            with self.assertRaisesRegex(mod.CandidateError,'ARTIFACT_FILENAME_INVALID'):
                mod.write_bundle(out,{'a':'first','../escape':'bad'})
            self.assertFalse(out.exists())
            self.assertFalse((pathlib.Path(td)/'escape').exists())

    def test_partial_failure_has_no_receipt_or_bundle(self):
        with tempfile.TemporaryDirectory() as td:
            out=pathlib.Path(td)/'candidate'
            with patch.object(mod.os,'fsync',side_effect=OSError('fixture-disk-full')):
                with self.assertRaises(OSError):
                    mod.write_bundle(out,{'a':'first','candidate-receipt.json':'{}'})
            self.assertFalse(out.exists())

    def test_cli_receipt_binds_each_artifact(self):
        with tempfile.TemporaryDirectory() as td:
            parent=pathlib.Path(td); manifest=parent/'manifest.json'
            manifest.write_text(json.dumps(two_projects()))
            out=parent/'out'
            with redirect_stdout(io.StringIO()):
                rc=mod.main(['render','--manifest',str(manifest),'--out',str(out)])
            self.assertEqual(rc,0)
            receipt=json.loads((out/'candidate-receipt.json').read_text())
            self.assertFalse(receipt['production_deploy_authorized'])
            self.assertEqual(receipt['readiness'],'UNQUALIFIED_CANDIDATE')
            self.assertEqual(len(receipt['artifact_sha256']),5)
            for name,digest in receipt['artifact_sha256'].items():
                self.assertEqual(hashlib.sha256((out/name).read_bytes()).hexdigest(),digest)
            with redirect_stdout(io.StringIO()),redirect_stderr(io.StringIO()):
                self.assertEqual(mod.main(['render','--manifest',str(manifest),'--out',str(out)]),2)


if __name__=='__main__':
    unittest.main()
