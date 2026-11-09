"""Canonical lifecycle source contracts; no systemd or Docker effects."""
import copy
import hashlib
import io
import json
import pathlib
import shlex
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
BASE=pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0,str(BASE/'tools'))
import compose_lifecycle as life


def donor_unit():
    return '\n'.join(['[Unit]','Description=Van local Supabase (PostgreSQL authority store + studio, loopback only)',
        'Requires=docker.service','After=docker.service network-online.target','','[Service]',
        'Type=oneshot','RemainAfterExit=true','WorkingDirectory='+life.INSTALL,
        'ExecStart=/usr/bin/docker compose -f '+life.BASE_FILES[0]+' -f '+life.BASE_FILES[1]+' --env-file '+life.INSTALL+'/.env up -d --remove-orphans',
        'ExecStop=/usr/bin/docker compose -f '+life.BASE_FILES[0]+' -f '+life.BASE_FILES[1]+' --env-file '+life.INSTALL+'/.env stop',
        'TimeoutStartSec=600','','[Install]','WantedBy=multi-user.target',''])


def fixture_spec(unit=None):
    unit=donor_unit() if unit is None else unit
    root='/etc/dial-supabase/releases/fixture-release-0001'
    bind=lambda path:{'path':path,'sha256':hashlib.sha256(path.encode()).hexdigest()}
    slugs=['fixture-project','nissan-gtr']
    return {'schema_version':1,'kind':'DIAL_SUPABASE_LIFECYCLE_INPUT_V1','release_id':'fixture-release-0001',
        'source_sha':'348bb5ace86dce85410978cdd4c458a928843354','observed_project_name':'original-supabase',
        'observed_daemon_socket':'/var/run/docker.sock','original_unit_sha256':hashlib.sha256(unit.encode()).hexdigest(),
        'base_files':[bind(x) for x in life.BASE_FILES],
        'overlays':{k:bind(root+'/'+k+'.yml') for k in life.COMPONENTS},
        'environment_files':{k:bind(life.INSTALL+'/.env' if k=='base' else root+'/'+k+'.env') for k in life.ENVS},
        'protected_files':[bind('/etc/dial-supabase/admin/registry.json'),bind('/etc/dial-supabase/edge/registry.json')],
        'projects':slugs,'effective_services':sorted(life.DONOR_SERVICES|{'project-admin'}|{'tenant-'+slug+'-'+s for slug in slugs for s in ('auth','rest','api')})}


class LifecycleContracts(unittest.TestCase):
    def setUp(self):self.unit=donor_unit();self.spec=fixture_spec(self.unit)
    def compile(self):return life.compile_bundle(self.spec,self.unit)
    def test_same_existing_installation_and_project_for_start_stop(self):
        out=self.compile();m=json.loads(out['lifecycle-candidate.json'])
        self.assertEqual(m['start_argv'][:-3],m['stop_argv'][:-1])
        self.assertEqual(m['start_argv'][-3:],['up','-d','--remove-orphans'])
        self.assertEqual(m['stop_argv'][-1:],[ 'stop'])
        self.assertEqual(m['project_name'],'original-supabase')
        self.assertEqual(m['start_argv'][1:4],['--host','unix:///var/run/docker.sock','compose'])
        self.assertEqual(m['start_argv'].count('-f'),8)
        self.assertEqual(m['start_argv'].count('--env-file'),5)
    def test_dropin_resets_original_exec_lists_and_pins_inputs(self):
        out=self.compile();lines=out['90-dial-multiproject.conf'].splitlines()
        self.assertEqual(lines.count('ExecStart='),1);self.assertEqual(lines.count('ExecStop='),1)
        stops=[l[len('ExecStop='):] for l in lines if l.startswith('ExecStop=') and l!='ExecStop=']
        self.assertTrue(stops[0].startswith('/usr/bin/sha256sum --check --strict --status '))
        self.assertTrue(stops[1].endswith(' stop'))
        self.assertIn('ExecStartPre=/usr/bin/sha256sum --check --strict --status ',out['90-dial-multiproject.conf'])
        self.assertIn(' config --quiet',out['90-dial-multiproject.conf'])
    def test_all_file_and_original_unit_hashes_retained(self):
        out=self.compile();m=json.loads(out['lifecycle-candidate.json'])
        self.assertEqual(m['file_bindings'][0],{'path':life.UNIT_PATH,'sha256':hashlib.sha256(self.unit.encode()).hexdigest()})
        for record in m['file_bindings']:self.assertIn(record['sha256']+'  '+record['path']+'\n',out['lifecycle-inputs.sha256'])
        for name,digest in m['artifacts_sha256'].items():self.assertEqual(hashlib.sha256(out[name].encode()).hexdigest(),digest)
    def test_no_authority_claim_or_install_effect(self):
        m=json.loads(self.compile()['lifecycle-candidate.json'])
        self.assertFalse(m['production_deployed']);self.assertFalse(m['authorizes_execution'])
        self.assertNotIn('daemon-reload',''.join(self.compile().values()))
    def test_original_unit_digest_mismatch_refused(self):
        self.spec['original_unit_sha256']='0'*64
        with self.assertRaisesRegex(ValueError,'DIGEST_MISMATCH'):self.compile()
    def test_old_unit_semantic_drift_even_with_matching_hash_refused(self):
        self.unit=self.unit.replace('--remove-orphans','--remove-orphans --force-recreate')
        self.spec['original_unit_sha256']=hashlib.sha256(self.unit.encode()).hexdigest()
        with self.assertRaisesRegex(ValueError,'NOT_EXACT'):self.compile()
    def test_unobserved_original_pre_hook_refused(self):
        self.unit=self.unit.replace('Type=oneshot','ExecStartPre=/usr/bin/true\nType=oneshot')
        self.spec['original_unit_sha256']=hashlib.sha256(self.unit.encode()).hexdigest()
        with self.assertRaisesRegex(ValueError,'NOT_EXACT'):self.compile()
    def test_missing_shared_service_overlay_refused(self):
        for name in life.COMPONENTS:
            bad=copy.deepcopy(self.spec);del bad['overlays'][name]
            with self.subTest(name=name),self.assertRaisesRegex(ValueError,'COMPLETE_SHARED'):life.compile_bundle(bad,self.unit)
    def test_missing_environment_overlay_refused(self):
        for name in life.ENVS:
            bad=copy.deepcopy(self.spec);del bad['environment_files'][name]
            with self.subTest(name=name),self.assertRaisesRegex(ValueError,'COMPLETE_ENV'):life.compile_bundle(bad,self.unit)
    def test_original_files_order_and_identity_must_remain(self):
        self.spec['base_files'].reverse()
        with self.assertRaisesRegex(ValueError,'ORIGINAL_COMPOSE'):self.compile()
    def test_release_cross_reference_refused(self):
        self.spec['overlays']['edge']['path']='/etc/dial-supabase/releases/some-other-release/edge.yml'
        with self.assertRaisesRegex(ValueError,'OUTSIDE_EXACT_RELEASE'):self.compile()
    def test_original_environment_cannot_be_replaced(self):
        self.spec['environment_files']['base']['path']='/etc/dial-supabase/releases/fixture-release-0001/fake.env'
        with self.assertRaisesRegex(ValueError,'ORIGINAL_ENV'):self.compile()
    def test_paths_reject_shell_systemd_and_traversal_expansion(self):
        for path in ['/x/%n','/x/$ENV','/x/../etc','/x/./test','/x//test','/x/test\nExecStart=/bin/true','/x/test;bad','/x/test name','relative','/x/']:
            with self.subTest(path=path),self.assertRaises(ValueError):life.path_checked(path)
    def test_missing_live_project_identity_refused(self):
        for name in ('','NewProject','../supabase','supabase --force-recreate',None):
            bad=copy.deepcopy(self.spec);bad['observed_project_name']=name
            with self.subTest(name=name),self.assertRaises(ValueError):life.compile_bundle(bad,self.unit)
    def test_nonlocal_or_unobserved_daemon_refused(self):
        for value in ('tcp://remote:2376','/tmp/daemon.sock','',None):
            bad=copy.deepcopy(self.spec);bad['observed_daemon_socket']=value
            with self.subTest(value=value),self.assertRaises(ValueError):life.compile_bundle(bad,self.unit)
    def test_omitted_or_extra_service_would_orphan_refused(self):
        for removed in ('db','functions','project-admin','tenant-nissan-gtr-auth'):
            bad=copy.deepcopy(self.spec);bad['effective_services'].remove(removed)
            with self.subTest(removed=removed),self.assertRaisesRegex(ValueError,'EFFECTIVE_SERVICE'):life.compile_bundle(bad,self.unit)
        self.spec['effective_services'].append('unrelated-new-postgres')
        with self.assertRaisesRegex(ValueError,'EFFECTIVE_SERVICE'):self.compile()
    def test_duplicate_path_digest_and_unknown_fields_refused(self):
        for mutate in (lambda s:s['protected_files'].append(copy.deepcopy(s['protected_files'][0])),lambda s:s.update(authorizes_execution=True),lambda s:s['overlays']['edge'].update(sha256='bad')):
            bad=copy.deepcopy(self.spec);mutate(bad)
            with self.assertRaises(ValueError):life.compile_bundle(bad,self.unit)
    def test_private_material_cannot_be_read_from_data_or_other_roots(self):
        self.spec['protected_files'][0]['path']='/opt/van-trading/supabase/volumes/db/data/PG_VERSION'
        with self.assertRaisesRegex(ValueError,'OUTSIDE_SCOPE'):self.compile()
    def test_output_order_is_deterministic(self):
        a=self.compile();self.spec['overlays']=dict(reversed(list(self.spec['overlays'].items())))
        self.assertEqual(a,self.compile())
    def test_private_cli_generates_only_new_candidate_directory(self):
        with tempfile.TemporaryDirectory() as td:
            root=pathlib.Path(td);source=root/'unit';private=root/'input';out=root/'candidate'
            source.write_text(self.unit);private.write_text(json.dumps(self.spec));private.chmod(0o600)
            args=['--private-input',str(private),'--original-unit',str(source),'--out',str(out)]
            with redirect_stdout(io.StringIO()):self.assertEqual(life.main(args),0)
            self.assertEqual(out.stat().st_mode&0o777,0o700)
            self.assertTrue(all(f.stat().st_mode&0o777==0o600 for f in out.iterdir()))
            with redirect_stdout(io.StringIO()):self.assertEqual(life.main(args),2)
    def test_cli_refuses_nonprivate_descriptor(self):
        with tempfile.TemporaryDirectory() as td:
            root=pathlib.Path(td);source=root/'unit';private=root/'input'
            source.write_text(self.unit);private.write_text(json.dumps(self.spec));private.chmod(0o644)
            with redirect_stdout(io.StringIO()):self.assertEqual(life.main(['--private-input',str(private),'--original-unit',str(source),'--out',str(root/'candidate')]),2)
            self.assertFalse((root/'candidate').exists())

if __name__=='__main__':unittest.main()
