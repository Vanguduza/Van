"""The owner-read-only Supabase canary gate never effects or grants a release."""
from __future__ import annotations

import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
import io

BASE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE / 'tools'))
import target_admission as a


def sample():
    return {
        'schema_version': 1,
        'observation_class': 'UNTRUSTED_NONSECRET_READ_ONLY_FACTS',
        'target': {
            'hostname': 'van-trading-core', 'architecture': 'aarch64',
            'free_root_bytes': 4_239_806_464, 'available_memory_kib': 4_894_720,
            'compose_project': 'supabase', 'compose_containers': 11,
            'healthy_containers': 11, 'canary_container_count': 0, 'systemd_active': True,
            'base_git_blob': a.EXPECTED_DONOR['base_git_blob'],
            'override_git_blob': a.EXPECTED_DONOR['override_git_blob'],
            'unit_sha256': a.EXPECTED_DONOR['unit_sha256'],
            'original_images_arm64': True,
        },
        'postgres': {
            'server_version_num': 170006,
            'database_names': ['_supabase','postgres'],
            'max_connections':100,'connections_observed':25,
            'wal_level':'logical','max_replication_slots':5,
            'used_replication_slots':0,
            'role_collision_count':0,'database_collision_count':0,
            'api_roles': copy.deepcopy(a.EXPECTED_API_ROLES),
            'execution_role':'postgres',
            'privileges': {k: False for k in a.EXECUTION_PRIV_KEYS},
        },
        'backup': {
            'target_cipher_sha256': 'e6f4147d9c994d220e12664cacf311935f54f9de0a8b2f87ea1c23c0eb42f0ff',
            'offhost_cipher_sha256': 'e6f4147d9c994d220e12664cacf311935f54f9de0a8b2f87ea1c23c0eb42f0ff',
            'verified_restore': True, 'verified_table_count': 57,
            'captured_cluster_backup': True,
        },
        'governance': {
            'source_sha':'e62c0f0948b1d0c8778deee3a4460bc378a003eb',
            'proposed_project_count':2,'original_canary_execution_refused':True,
            'refusal_reconciled_with_authority':False,
            'production_release_receipt_present':False,
            'required_slot_reserve':2,
            'candidate_arm64_images_qualified':False,
            'canonical_lifecycle_installed':False,
            'full_target_service_coexistence_tested':False,
        },
    }


class TargetAdmissionTests(unittest.TestCase):
    def setUp(self):self.data=sample()
    def eval(self):return a.evaluate(self.data)

    def test_exact_live_snapshot_blocks_actuation(self):
        r=self.eval()
        self.assertFalse(r['canary_activation_authorized'])
        self.assertFalse(r['release_authorized'])
        self.assertFalse(r['production_effects'])
        self.assertFalse(r['full_service_technically_ready'])
        self.assertEqual(r['required_realtime_slots_with_reserve'],6)
        self.assertEqual(r['actual_replication_slots_max'],5)
        self.assertIn('bootstrap_privilege_and_hba_visibility',r['auth_rest_canary_blockers'])
        self.assertIn('no_live_canary_refusal_remaining',r['auth_rest_canary_blockers'])
        self.assertIn('operator_release_receipt',r['auth_rest_canary_blockers'])
        self.assertIn('realtime_slot_reserve',r['full_service_blockers'])
    def test_original_donor_and_backup_checks_pass_independently(self):
        r=self.eval()
        for name in ('exact_original_compose_and_unit','existing_compose_healthy','original_database_set_preserved',
                     'no_namespace_collisions','standard_api_roles_match','backup_verified_and_available_offhost'):
            self.assertTrue(r['checks'][name],name)
    def test_source_report_is_not_authority(self):
        self.assertIn('not signed admission',self.eval()['interpretation'].lower())
    def test_release_cannot_be_authorized_even_if_all_assertions_green(self):
        self.data['postgres']['privileges']={k:True for k in a.EXECUTION_PRIV_KEYS}
        self.data['postgres']['max_replication_slots']=16
        self.data['governance']['original_canary_execution_refused']=False
        self.data['governance']['production_release_receipt_present']=True
        self.data['governance']['candidate_arm64_images_qualified']=True
        self.data['governance']['canonical_lifecycle_installed']=True
        self.data['governance']['full_target_service_coexistence_tested']=True
        r=self.eval()
        self.assertTrue(r['full_service_technically_ready'])
        self.assertFalse(r['release_authorized'])
        self.assertFalse(r['canary_activation_authorized'])
    def test_missing_or_extra_snapshot_field_refused(self):
        self.data.pop('backup')
        with self.assertRaises(a.SnapshotError):self.eval()
        self.data=sample();self.data['unreviewed_authority']='true'
        with self.assertRaises(a.SnapshotError):self.eval()
    def test_unknown_product_source_blocks(self):
        self.data['governance']['source_sha']='0'*40
        self.assertFalse(self.eval()['checks']['exact_tested_product_source'])

    def test_identically_spoofed_backup_hashes_cannot_replace_verified_backup(self):
        self.data['backup']['target_cipher_sha256']='f'*64
        self.data['backup']['offhost_cipher_sha256']='f'*64
        self.assertFalse(self.eval()['checks']['backup_verified_and_available_offhost'])

    def test_unqualified_arm64_lifecycle_and_live_coexistence_are_independent_blocks(self):
        actual=self.eval()['full_service_blockers']
        for gate in ('candidate_arm64_images_admitted','canonical_lifecycle_installed','real_target_full_service_coexistence'):
            self.assertIn(gate,actual)
        self.assertNotIn('candidate_arm64_images_admitted',self.eval()['auth_rest_canary_blockers'])

    def test_wrong_kind_refused(self):
        self.data['observation_class']='SIGNED_OWNER_RELEASE'
        with self.assertRaises(a.SnapshotError):self.eval()
    def test_negative_memory_or_disk_refused(self):
        for val in (-1,'123',None,True):
            with self.subTest(value=val):
                self.data['target']['free_root_bytes']=val
                with self.assertRaises(a.SnapshotError):self.eval()
    def test_nan_boolean_or_wrong_source_refused(self):
        for val in ('true',1,None):
            with self.subTest(value=val):
                self.data['backup']['verified_restore']=val
                with self.assertRaises(a.SnapshotError):self.eval()
        self.data=sample()
        self.data['governance']['source_sha']='unreviewed'
        with self.assertRaises(a.SnapshotError):self.eval()
    def test_tampered_donor_detected(self):
        self.data['target']['unit_sha256']='0'*64
        r=self.eval()
        self.assertIn('exact_original_compose_and_unit',r['auth_rest_canary_blockers'])
    def test_wrong_architecture_blocks(self):
        self.data['target']['architecture']='amd64'
        self.assertFalse(self.eval()['checks']['target_name_and_cpu'])
    def test_resource_floor_blocks_without_mutation(self):
        self.data['target']['free_root_bytes']=2*1024**3-1
        self.assertIn('auth_rest_candidate_disk_floor',self.eval()['auth_rest_canary_blockers'])
        self.data=sample();self.data['target']['available_memory_kib']=2*1024**2-1
        self.assertIn('auth_rest_candidate_memory_floor',self.eval()['auth_rest_canary_blockers'])
    def test_original_canary_presence_detected(self):
        self.data['target']['canary_container_count']=1
        self.assertIn('original_database_set_preserved',self.eval()['auth_rest_canary_blockers'])
    def test_other_database_detected(self):
        self.data['postgres']['database_names'].append('another-project')
        self.assertFalse(self.eval()['checks']['original_database_set_preserved'])
    def test_replication_slot_envelope_for_more_projects(self):
        self.data['governance']['proposed_project_count']=3
        self.data['postgres']['max_replication_slots']=7
        r=self.eval()
        self.assertEqual(r['required_realtime_slots_with_reserve'],8)
        self.assertFalse(r['checks']['realtime_slot_reserve'])
    def test_pg17_version_not_silently_mapped(self):
        self.data['postgres']['server_version_num']=160011
        self.assertFalse(self.eval()['checks']['pg17_supported'])
    def test_shared_api_roles_must_match(self):
        self.data['postgres']['api_roles']['service_role']['bypassrls']=False
        self.assertFalse(self.eval()['checks']['standard_api_roles_match'])
    def test_privileged_bootstrap_operator_gate(self):
        self.data['postgres']['privileges']['can_read_hba_rules']=True
        r=self.eval()
        self.assertFalse(r['checks']['bootstrap_privilege_and_hba_visibility'])
    def test_backup_digests_must_match(self):
        self.data['backup']['offhost_cipher_sha256']='0'*64
        self.assertFalse(self.eval()['checks']['backup_verified_and_available_offhost'])
    def test_cli_writes_only_new_mode_0600_report(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);snap=root/'facts.json';out=root/'read-only.json'
            snap.write_text(json.dumps(self.data))
            with redirect_stdout(io.StringIO()) as stream:
                self.assertEqual(a.main(['--snapshot',str(snap),'--out',str(out)]),0)
            self.assertIn('BLOCKED=true',stream.getvalue())
            self.assertEqual(out.stat().st_mode & 0o777,0o600)
            self.assertFalse(json.loads(out.read_text())['release_authorized'])
            with redirect_stdout(io.StringIO()):
                self.assertEqual(a.main(['--snapshot',str(snap),'--out',str(out)]),2)
    def test_cli_rejects_symlinked_input(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);actual=root/'actual.json';actual.write_text(json.dumps(self.data))
            alias=root/'alias.json';alias.symlink_to(actual)
            with redirect_stdout(io.StringIO()):
                self.assertEqual(a.main(['--snapshot',str(alias),'--out',str(root/'out.json')]),2)
            self.assertFalse((root/'out.json').exists())
    def test_duplicate_or_nonlist_databases_refused(self):
        self.data['postgres']['database_names']=['postgres','postgres']
        with self.assertRaises(a.SnapshotError):self.eval()
    def test_registry_does_not_accept_unknown_privilege_flags(self):
        self.data['postgres']['privileges']['override_safety_guard']=True
        with self.assertRaises(a.SnapshotError):self.eval()

if __name__ == '__main__':unittest.main()
