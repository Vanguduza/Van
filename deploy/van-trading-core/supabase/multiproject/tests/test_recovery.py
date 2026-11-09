"""Offline recovery-boundary tests; synthetic PGDMP headers are NOT real dumps.

Actual pg_dump/pg_restore, Auth and data preservation are in rehearse_recovery.py.
"""
from __future__ import annotations
import copy
import hashlib
import io
import json
import os
import pathlib
import sys
import tempfile
import unittest
from contextlib import redirect_stdout,redirect_stderr
from unittest.mock import patch
from datetime import datetime,timezone

BASE=pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0,str(BASE/'tools'))
import bootstrap as b
import render
import recovery as r


class RecoveryContracts(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=pathlib.Path(self.tmp.name);self.root.chmod(0o700)
        self.projects=render.validate(json.loads((BASE/'projects.rehearsal.json').read_text()))
        self.p=self.projects[0]
        self.bytes=b'PGDMP\x00fixture-not-a-real-postgres-archive'
        self.manifest={'schema_version':1,'kind':'DIAL_PROJECT_LOGICAL_BACKUP_V1',
            'backup_id':'3a4ce774-1f60-4e87-b9ca-0ff204e0444c',
            'created_at':datetime.now(timezone.utc).isoformat(),
            'source_revision':'58e7040342bfd7137fb9227d9709fd4287172574',
            'project':r.project_identity(self.p),
            'observation':{'database':self.p['database'],'project_uuid':self.p['project_uuid'],
                'issuer':'https://'+self.p['hostname']+'/auth/v1','server_version_num':170011,
                'system_identifier':'123456789','snapshot':'00000003-0000001A-1'},
            'archive':{'file':'project.dump','sha256':hashlib.sha256(self.bytes).hexdigest(),'bytes':len(self.bytes)},
            'format':'postgresql-custom',
            'external_prerequisites':['cluster_roles','project_secrets','server_configuration','storage_objects','independent_owner_admission'],
            'production_restore_authorized':False}
        self.bundle=self.root/'backup';self.bundle.mkdir(mode=0o700)
        self.write_private('project.dump',self.bytes)
        self.write_private('manifest.json',r.canonical(self.manifest))
        self.digest=hashlib.sha256(r.canonical(self.manifest)).hexdigest()

    def write_private(self,name,data):
        p=self.bundle/name;p.write_bytes(data);p.chmod(0o600)

    def verify(self,p=None,digest=None):
        with r.verified_archive(self.bundle,digest or self.digest,p or self.p) as (m,fd):
            return m,os.read(fd,1024)

    def test_valid_archive_integrity_binds_exact_project(self):
        m,data=self.verify();self.assertEqual(m,self.manifest);self.assertEqual(data,self.bytes)
        self.assertFalse(m['production_restore_authorized'])

    def test_wrong_project_refused(self):
        with self.assertRaisesRegex(r.RecoveryError,'BACKUP_PROJECT_MISMATCH'):
            self.verify(p=self.projects[1])

    def test_external_digest_required_and_mismatch_refused(self):
        for value in ('','not-sha','0'*64):
            with self.subTest(value=value),self.assertRaises((r.RecoveryError,ValueError)):
                with r.verified_archive(self.bundle,value,self.p):pass

    def test_corrupted_archive_refused(self):
        self.write_private('project.dump',self.bytes[:-1]+b'!')
        with self.assertRaisesRegex(r.RecoveryError,'BACKUP_ARCHIVE_DIGEST_MISMATCH'):self.verify()

    def test_truncated_archive_refused(self):
        self.write_private('project.dump',b'PGDMP')
        with self.assertRaisesRegex(r.RecoveryError,'BACKUP_ARCHIVE_DIGEST_MISMATCH'):self.verify()

    def test_manifest_replacement_refused(self):
        self.write_private('manifest.json',r.canonical({**self.manifest,'production_restore_authorized':True}))
        with self.assertRaisesRegex(r.RecoveryError,'BACKUP_MANIFEST_DIGEST_MISMATCH'):self.verify()

    def test_signed_scope_cannot_omit_external_dependencies(self):
        bad=copy.deepcopy(self.manifest);bad['external_prerequisites']=[]
        with self.assertRaisesRegex(r.RecoveryError,'BACKUP_PREREQUISITES_MISSING'):r.validate_manifest(bad,self.p)

    def test_archive_name_cannot_traverse(self):
        for name in ('../project.dump','/tmp/project.dump','other.dump'):
            bad=copy.deepcopy(self.manifest);bad['archive']['file']=name
            with self.subTest(name=name),self.assertRaises(r.RecoveryError):r.validate_manifest(bad,self.p)

    def test_manifests_cannot_claim_production_authority(self):
        for key,value in [('schema_version',True),('production_restore_authorized',True),('format','sql')]:
            bad=copy.deepcopy(self.manifest);bad[key]=value
            with self.subTest(key=key),self.assertRaises(r.RecoveryError):r.validate_manifest(bad,self.p)
        bad=copy.deepcopy(self.manifest);bad['password']='unexpected'
        with self.assertRaises(r.RecoveryError):r.validate_manifest(bad,self.p)

    def test_source_observation_must_match_scope_and_version(self):
        for key,value in [('database','postgres'),('project_uuid',self.projects[1]['project_uuid']),
                          ('issuer','https://other.invalid/auth/v1'),('server_version_num',160011),
                          ('server_version_num',True),('snapshot','anything;'),('system_identifier','not-observed')]:
            bad=copy.deepcopy(self.manifest);bad['observation'][key]=value
            with self.subTest(key=key),self.assertRaises(r.RecoveryError):r.validate_manifest(bad,self.p)

    def test_private_file_permissions_required(self):
        for name in ('manifest.json','project.dump'):
            p=self.bundle/name;p.chmod(0o644)
            try:
                with self.assertRaisesRegex(r.RecoveryError,'PRIVATE_REGULAR'):self.verify()
            finally:p.chmod(0o600)

    def test_private_directory_permissions_required(self):
        self.bundle.chmod(0o755)
        with self.assertRaisesRegex(r.RecoveryError,'PRIVATE_DIRECTORY'):self.verify()

    def test_archive_symlink_refused(self):
        p=self.bundle/'project.dump';target=self.root/'elsewhere';p.rename(target);p.symlink_to(target)
        with self.assertRaises(OSError):self.verify()

    def test_archive_hardlink_refused(self):
        os.link(self.bundle/'project.dump',self.root/'hardlink')
        with self.assertRaisesRegex(r.RecoveryError,'SINGLE_LINK'):self.verify()

    def test_parent_symlink_refused(self):
        (self.root/'link').symlink_to(self.bundle,target_is_directory=True)
        with self.assertRaises(OSError):
            with r.verified_archive(self.root/'link',self.digest,self.p):pass

    def test_duplicate_json_key_rejected_even_with_matching_digest(self):
        raw=r.canonical(self.manifest).rstrip()[:-1]+b',"schema_version":1}\n'
        self.write_private('manifest.json',raw)
        with self.assertRaisesRegex(render.CandidateError,'DUPLICATE_JSON_KEY'):
            self.verify(digest=hashlib.sha256(raw).hexdigest())

    def test_verified_snapshot_is_immutable(self):
        with r.verified_archive(self.bundle,self.digest,self.p) as (_,fd):
            with self.assertRaises(OSError):os.write(fd,b'changed')
            with self.assertRaises(OSError):os.ftruncate(fd,1)
            self.write_private('project.dump',b'PGDMPchanged-after-verification')
            self.assertEqual(os.read(fd,1024),self.bytes)

    def test_archive_readback_has_resource_limit(self):
        with patch.object(r,'MAX_VERIFIED_ARCHIVE_BYTES',4):
            with self.assertRaisesRegex(r.RecoveryError,'SNAPSHOT_LIMIT'):self.verify()

    def test_restore_plan_only_allows_fresh_named_target(self):
        for target in ('postgres',self.p['database'],self.projects[1]['database'],'legacy_van','new_db','dial_restore_bad','x;drop database postgres'):
            with self.subTest(target=target),self.assertRaises(ValueError):
                r.restore_plan(self.p,self.manifest,target,self.projects,self.digest)

    def test_restore_plan_preserves_privileges_and_has_no_overwrite(self):
        plan=r.restore_plan(self.p,self.manifest,'dial_restore_1234567890abcdef',self.projects,self.digest)
        self.assertFalse(plan['production_restore_authorized'])
        self.assertFalse(plan['changes_source_database'])
        self.assertFalse(plan['switches_live_routing'])
        self.assertIn('--single-transaction',plan['restore_args'])
        self.assertIn('--exit-on-error',plan['restore_args'])
        for forbidden in ('--clean','--create','--no-owner','--no-acl'):
            self.assertNotIn(forbidden,plan['restore_args'])
        self.assertIn('ALLOW_CONNECTIONS false',plan['create_sql'])
        self.assertIn('RESTORE_TARGET_ALREADY_EXISTS',plan['create_sql'])
        for gate in ('RESTORE_TARGET_IDENTITY_MISMATCH','RESTORE_TARGET_OWNER_MISMATCH','RESTORE_TARGET_NOT_EMPTY','RESTORE_TARGET_NOT_QUARANTINED'):
            self.assertIn(gate,plan['pre_restore_sql'])
        self.assertNotIn('DROP DATABASE',plan['create_sql'])

    def test_restore_plan_rejects_unbound_manifest(self):
        with self.assertRaisesRegex(r.RecoveryError,'RESTORE_PLAN_MANIFEST_MISMATCH'):
            r.restore_plan(self.p,self.manifest,'dial_restore_1234567890abcdef',self.projects,'0'*64)

    def endpoint(self):
        pw=self.root/'passfile';pw.write_text('# test only\n');pw.chmod(0o600)
        return {'host':'127.0.0.1','port':5432,'user':'fixture_admin','passfile':str(pw),'system_identifier':'123456789','sslmode':'disable'}

    def test_endpoint_excludes_password_and_requires_identity(self):
        config=self.endpoint();env=r.connection_env(config)
        self.assertNotIn('PGPASSWORD',env)
        self.assertEqual(env['PGCONNECT_TIMEOUT'],'5')
        for key,value in [('port',True),('port',0),('host','a;sh'),('system_identifier',''),('user','a;drop')]:
            with self.subTest(key=key),self.assertRaises(ValueError):r.connection_env({**config,key:value})
        with self.assertRaises(r.RecoveryError):r.connection_env({**config,'password':'forbidden'})

    def test_remote_endpoint_requires_tls(self):
        config=self.endpoint()
        with self.assertRaisesRegex(r.RecoveryError,'REMOTE_TLS_REQUIRED'):r.connection_env({**config,'host':'db.example.invalid'})
        self.assertEqual(r.connection_env({**config,'host':'db.example.invalid','sslmode':'verify-full'})['PGSSLMODE'],'verify-full')

    def test_endpoint_credentials_file_must_be_private(self):
        config=self.endpoint();pathlib.Path(config['passfile']).chmod(0o644)
        with self.assertRaises(r.RecoveryError):r.connection_env(config)

    def test_verification_and_plan_cli_have_no_database_effects(self):
        manifest=BASE/'projects.rehearsal.json';out=self.root/'plan'
        common=['--manifest',str(manifest),'--project',self.p['slug'],'--bundle',str(self.bundle),'--manifest-sha256',self.digest]
        with patch.object(r.subprocess,'run',side_effect=AssertionError('NO_PROCESS_ALLOWED')),patch.object(r.subprocess,'Popen',side_effect=AssertionError('NO_PROCESS_ALLOWED')),redirect_stdout(io.StringIO()):
            self.assertEqual(r.main(['verify',*common]),0)
            self.assertEqual(r.main(['plan',*common,'--out',str(out),'--target','dial_restore_1234567890abcdef']),0)
        self.assertTrue((out/'restore-plan.json').is_file())
        self.assertEqual((out/'restore-plan.json').stat().st_mode&0o777,0o600)

    def test_bounded_dump_streams_exact_bytes(self):
        with tempfile.TemporaryFile() as out,tempfile.TemporaryFile() as err:
            size=r.bounded_dump([sys.executable,'-c',"import sys;sys.stdout.buffer.write(b'PGDMPfixture')"],{'PATH':'/usr/bin:/bin'},out.fileno(),err.fileno(),5)
            out.seek(0);self.assertEqual(out.read(),b'PGDMPfixture');self.assertEqual(size,12)

    def test_bounded_dump_stops_on_limit(self):
        with tempfile.TemporaryFile() as out,tempfile.TemporaryFile() as err,patch.object(r,'MAX_VERIFIED_ARCHIVE_BYTES',5):
            with self.assertRaisesRegex(r.RecoveryError,'SNAPSHOT_LIMIT'):
                r.bounded_dump([sys.executable,'-c',"import sys;sys.stdout.buffer.write(b'x'*100)"],{'PATH':'/usr/bin:/bin'},out.fileno(),err.fileno(),5)

    def test_bounded_dump_nonzero_exit_is_not_success(self):
        with tempfile.TemporaryFile() as out,tempfile.TemporaryFile() as err:
            with self.assertRaisesRegex(r.RecoveryError,'PG_DUMP_FAILED'):
                r.bounded_dump([sys.executable,'-c','raise SystemExit(2)'],{'PATH':'/usr/bin:/bin'},out.fileno(),err.fileno(),5)

    def test_bounded_dump_timeout_terminates_owned_child(self):
        with tempfile.TemporaryFile() as out,tempfile.TemporaryFile() as err:
            with self.assertRaisesRegex(r.RecoveryError,'PG_DUMP_TIMEOUT'):
                r.bounded_dump([sys.executable,'-c','import time;time.sleep(10)'],{'PATH':'/usr/bin:/bin'},out.fileno(),err.fileno(),.1)

    def test_cli_cannot_apply_or_restore(self):
        with self.assertRaises(SystemExit),redirect_stdout(io.StringIO()),redirect_stderr(io.StringIO()):
            r.main(['restore','--manifest',str(BASE/'projects.rehearsal.json'),'--project',self.p['slug']])


if __name__=='__main__':unittest.main()
