"""No database effects; source compiler and schedule custody contracts."""
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
BASE=pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0,str(BASE/'tools'))
import shared_scheduler as s
import render


def projects():
    return render.validate(json.loads((BASE/'projects.rehearsal.json').read_text()))

def source_fixture():
    return b'-- fixture: NOT upstream GTR acceptance\n'+s.CRON_INSTALL+b'\nCREATE TABLE app_fixtures(id int);\n'+b'\n'.join(s.original_schedule(j) for j in s.JOBS)+b'\n'

class SharedSchedulerContracts(unittest.TestCase):
    def setUp(self):self.ps=projects();self.p=self.ps[0]
    def fixture_bundle(self):
        raw=source_fixture()
        with patch.object(s,'BASELINE_SHA256',hashlib.sha256(raw).hexdigest()),patch.object(s,'BASELINE_SIZE',len(raw)):
            return s.compile_bundle(raw,self.p,'postgres','GMT')
    def test_cron_role_is_stable_project_scoped(self):
        self.assertNotEqual(s.role(self.ps[0]),s.role(self.ps[1]))
        self.assertLessEqual(len(s.role(self.p)),63)
        self.assertTrue(s.role(self.p).endswith('_cron'))
    def test_same_business_job_names_distinct_across_projects(self):
        for j in s.JOBS:self.assertNotEqual(s.job_name(self.ps[0],j[0]),s.job_name(self.ps[1],j[0]))
    def test_unknown_or_injected_job_name_refused(self):
        for x in ('new-job',"x');SELECT 1;--",'',None):
            with self.subTest(x=x),self.assertRaises(ValueError):s.job_name(self.p,x)
    def test_project_manifest_is_required(self):
        for change in ({'database':'postgres'},{'project_uuid':'fake'},{'slug':'van'},{'status':'LIVE'}):
            p={**self.p,**change}
            with self.subTest(change=change),self.assertRaises(ValueError):s.role(p)
    def test_original_timezone_and_schedules_preserved(self):
        x=s.registration_sql(self.p,'postgres','GMT')
        for _,schedule,command,_ in s.JOBS:
            self.assertIn(s.b.lit(schedule),x);self.assertIn(s.b.lit(command),x)
        self.assertIn("IS DISTINCT FROM 'GMT'",x)
        self.assertNotIn('ALTER SYSTEM',x)
    def test_registration_must_use_separate_existing_database(self):
        with self.assertRaises(ValueError):s.registration_sql(self.p,self.p['database'],'GMT')
        with self.assertRaises(ValueError):s.registration_sql(self.p,'postgres;bad','GMT')
    def test_timezone_injection_and_absence_refused(self):
        for value in ('','GMT\nALTER SYSTEM','../x;',None):
            with self.subTest(value=value),self.assertRaises(ValueError):s.registration_sql(self.p,'postgres',value)
    def test_never_installs_or_replaces_central_extension(self):
        text=s.registration_sql(self.p,'postgres','GMT')
        for bad in ('CREATE EXTENSION','DROP ','CREATE DATABASE','ALTER SYSTEM'):
            self.assertNotIn(bad,text)
    def test_all_four_jobs_registered_inactive(self):
        text=s.registration_sql(self.p,'postgres','GMT')
        self.assertEqual(text.count('SELECT cron.schedule_in_database('),4)
        self.assertEqual(text.count(',false);'),4)
        self.assertEqual(text.count('AND NOT active'),4)
        self.assertTrue(all(line.endswith(',false);') for line in text.splitlines() if line.startswith('SELECT cron.schedule_in_database(')))
    def test_existing_name_rejected_under_native_table_lock(self):
        text=s.registration_sql(self.p,'postgres','GMT')
        self.assertLess(text.index('LOCK TABLE cron.job IN SHARE ROW EXCLUSIVE MODE'),text.index('CRON_JOB_ALREADY_EXISTS_NO_UPSERT'))
        self.assertLess(text.index('CRON_JOB_ALREADY_EXISTS_NO_UPSERT'),text.index('SELECT cron.schedule_in_database('))
        self.assertIn('pg_advisory_xact_lock',text)
        self.assertTrue(text.endswith('COMMIT;\n'))
    def test_runtime_role_cannot_administer_jobs(self):
        text=s.registration_sql(self.p,'postgres','GMT')
        self.assertIn('CRON_RUNTIME_HAS_SCHEDULING_AUTHORITY',text)
        self.assertIn("'cron','USAGE'",text)
        self.assertIn('NOT rolsuper',text)
        self.assertIn('NOT rolbypassrls',text)
    def test_role_starts_nologin_without_password(self):
        text=s.role_sql(self.p)
        self.assertIn('NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS NOINHERIT',text)
        self.assertNotIn('PASSWORD',text)
        self.assertIn('CONNECTION LIMIT 2',text)
    def test_role_may_not_overwrite_existing_role(self):
        text=s.role_sql(self.p)
        self.assertIn('CRON_ROLE_EXISTS_RECONCILE',text)
        self.assertNotIn('DROP ROLE',text)
        self.assertIn('statement_timeout=60000',text)
    def test_morning_summary_grant_uses_actual_default_date_signature(self):
        text=s.grants_sql(self.p)
        self.assertIn('GRANT EXECUTE ON FUNCTION private.send_morning_summaries(date)',text)
        self.assertNotIn('GRANT EXECUTE ON FUNCTION private.send_morning_summaries()',text)
    def test_grants_check_project_identity_and_function_security(self):
        text=s.grants_sql(self.p)
        self.assertIn(self.p['project_uuid'],text)
        self.assertIn('CRON_PROJECT_IDENTITY_MISMATCH',text)
        self.assertIn('prosecdef',text)
        self.assertIn("('search_path='||chr(34)||chr(34))",text)
        self.assertIn('CRON_UNREVIEWED_PRIVATE_FUNCTION_ACCESS',text)
    def test_hba_rejects_all_client_transports(self):
        prefix,rules=s.deny_hba(self.ps)
        self.assertEqual(len(rules),6)
        self.assertTrue(all(r['auth_method']=='reject' and r['database']==['all'] for r in rules))
        self.assertNotIn('trust',prefix)
        self.assertNotIn('scram-sha-256',prefix)
        self.assertIn('::/0 reject',prefix)
    def test_hba_activation_requires_native_worker_and_exact_prefix(self):
        text=s.activation_sql(self.ps)
        for gate in ('CRON_NATIVE_BACKGROUND_WORKERS_REQUIRED','CRON_EXACT_DENY_PREFIX_REQUIRED','CRON_HBA_RELOAD_REQUIRED','CRON_ROLE_NOT_QUARANTINED'):
            self.assertIn(gate,text)
        self.assertIn('rolpassword IS NULL',text)
        self.assertEqual(text.count(' LOGIN;'),2)
    def test_duplicate_project_hba_refused(self):
        with self.assertRaises(ValueError):s.deny_hba([self.p,self.p])
    def test_unpinned_baseline_refused(self):
        with self.assertRaisesRegex(ValueError,'SOURCE_MISMATCH'):s.adapt_baseline(source_fixture())
    def test_mutation_of_baseline_refused(self):
        raw=source_fixture()
        with patch.object(s,'BASELINE_SHA256',hashlib.sha256(raw).hexdigest()),patch.object(s,'BASELINE_SIZE',len(raw)):
            with self.assertRaises(ValueError):s.adapt_baseline(raw[:-1]+b'x')
    def test_exact_five_statement_split_and_reversal(self):
        raw=source_fixture()
        with patch.object(s,'BASELINE_SHA256',hashlib.sha256(raw).hexdigest()),patch.object(s,'BASELINE_SIZE',len(raw)):
            candidate,proof=s.adapt_baseline(raw)
        self.assertEqual(proof['edit_count'],5)
        self.assertIn(b'CREATE TABLE app_fixtures(id int);',candidate)
        restored=candidate
        for edit in reversed(proof['edits']):
            restored=restored.replace(edit['replacement_utf8'].encode(),edit['original_utf8'].encode(),1)
        self.assertEqual(restored,raw)
        self.assertNotIn(s.CRON_INSTALL,candidate)
        self.assertFalse(proof['full_baseline_replayed'])
    def test_missing_or_duplicate_directive_refused_even_with_fixture_digest(self):
        for raw in (source_fixture().replace(s.CRON_INSTALL,b''),source_fixture()+s.CRON_INSTALL):
            with patch.object(s,'BASELINE_SHA256',hashlib.sha256(raw).hexdigest()),patch.object(s,'BASELINE_SIZE',len(raw)):
                with self.assertRaises(ValueError):s.adapt_baseline(raw)
    def test_bundle_is_staged_never_release_authority(self):
        bundle=self.fixture_bundle();r=json.loads(bundle['scheduler-candidate.json'])
        self.assertFalse(r['production_authorized']);self.assertFalse(r['canary_activation_authorized'])
        self.assertFalse(r['native_scheduler_changes_executed'])
        self.assertTrue(all(not j['active'] for j in r['jobs']))
        for name,digest in r['files'].items():self.assertEqual(hashlib.sha256(bundle[name].encode()).hexdigest(),digest)
    def test_private_bundle_creation_never_overwrites(self):
        with tempfile.TemporaryDirectory() as td:
            path=pathlib.Path(td)/'out';render.write_bundle(path,self.fixture_bundle())
            self.assertEqual(path.stat().st_mode&0o777,0o700)
            self.assertTrue(all(f.stat().st_mode&0o777==0o600 for f in path.iterdir()))
            with self.assertRaises(ValueError):render.write_bundle(path,self.fixture_bundle())
    def test_cli_unknown_baseline_or_multiple_projects_refused(self):
        with tempfile.TemporaryDirectory() as td:
            root=pathlib.Path(td);m=root/'manifest.json';raw=root/'bad.sql'
            m.write_text((BASE/'projects.rehearsal.json').read_text());raw.write_bytes(b'bad')
            with redirect_stdout(io.StringIO()):
                rc=s.main(['--manifest',str(m),'--baseline',str(raw),'--cron-database','postgres','--cron-timezone','GMT','--out',str(root/'out')])
            self.assertEqual(rc,2);self.assertFalse((root/'out').exists())

if __name__=='__main__':unittest.main()
