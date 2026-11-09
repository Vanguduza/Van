"""Source and owner-context safety; full SQL executes only in the native fixture."""
import copy
import hashlib
import json
import pathlib
import sys
import tempfile
import unittest
BASE=pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0,str(BASE/'tools'))
import gtr_migration_plan as p
import gtr_schema_contract as c

class MigrationContext(unittest.TestCase):
 def test_exact_thirteen_locked_migrations(self):
  lock=p.load_lock();self.assertEqual(len(lock['files']),13)
  self.assertEqual(lock['commit'],p.shared_scheduler.GTR_COMMIT)
  self.assertEqual(lock['files'][0]['sha256'],p.shared_scheduler.BASELINE_SHA256)
 def test_locked_source_digest(self):
  self.assertEqual(hashlib.sha256(p.LOCK.read_bytes()).hexdigest(),p.LOCK_SHA256)
 def test_tampered_lock_rejected(self):
  with tempfile.TemporaryDirectory() as td:
   f=pathlib.Path(td)/'lock';f.write_bytes(p.LOCK.read_bytes()+b' ')
   with self.assertRaisesRegex(ValueError,'LOCK_DIGEST'):p.load_lock(f)
 def test_unknown_migration_rejected(self):
  with self.assertRaisesRegex(ValueError,'UNKNOWN_MIGRATION'):p.prepare('arbitrary.sql',b'SELECT 1',p.load_lock(),target_database='gtr_stage')
 def test_changed_baseline_bytes_rejected(self):
  with self.assertRaisesRegex(ValueError,'BYTES_CHANGED'):p.prepare(p.BASELINE,b'SELECT 1',p.load_lock(),target_database='gtr_stage')
 def test_nonbyte_source_rejected(self):
  with self.assertRaisesRegex(ValueError,'BYTES_CHANGED'):p.prepare(p.BASELINE,'SELECT 1',p.load_lock(),target_database='gtr_stage')
 def test_forged_source_binding_rejected(self):
  lock=copy.deepcopy(p.load_lock());lock['files'][0]['sha256']=p.digest(b'SELECT 1');lock['files'][0]['bytes']=8
  with self.assertRaisesRegex(ValueError,'UNTRUSTED'):p.prepare(p.BASELINE,b'SELECT 1',lock,target_database='gtr_stage')
 def test_partial_migration_set_rejected(self):
  with self.assertRaisesRegex(ValueError,'EXACT_MIGRATION_SET'):p.prepare_all({},p.load_lock(),target_database='gtr_stage')
 def test_extra_migration_set_rejected(self):
  source={pathlib.PurePosixPath(x['path']).name:b'' for x in p.load_lock()['files']};source['extra.sql']=b''
  with self.assertRaisesRegex(ValueError,'EXACT_MIGRATION_SET'):p.prepare_all(source,p.load_lock(),target_database='gtr_stage')
 def test_protected_database_targets_rejected(self):
  for db in ('postgres','_supabase','template0','template1','a;DROP DATABASE postgres','',None):
   with self.subTest(db=db),self.assertRaisesRegex(ValueError,'EXACT_FRESH'):p.prepare(p.BASELINE,b'',p.load_lock(),target_database=db)
 def test_exact_section_adds_only_context_wrappers(self):
  text='before\nBEGIN_NATIVE\nCREATE POLICY x ON storage.objects USING (true);\nEND_NATIVE\nafter'
  result,receipt=p.scoped_section(text,'BEGIN_NATIVE','END_NATIVE')
  self.assertEqual(result.replace(p.RESET,'',1).replace(p.RESUME,'',1),text)
  self.assertTrue(receipt['byte_exact_reverse_verified'])
  self.assertEqual(result.count('RESET ROLE;'),1)
  self.assertEqual(result.count('SET LOCAL ROLE postgres;'),1)
 def test_missing_section_marker_rejected(self):
  with self.assertRaisesRegex(ValueError,'BOUNDARY'):p.scoped_section('start only','start','end')
 def test_duplicate_section_marker_rejected(self):
  with self.assertRaisesRegex(ValueError,'BOUNDARY'):p.scoped_section('start start end','start','end')
 def test_reversed_section_marker_rejected(self):
  with self.assertRaisesRegex(ValueError,'BOUNDARY'):p.scoped_section('end start','start','end')
 def test_already_scoped_source_rejected(self):
  with self.assertRaisesRegex(ValueError,'ALREADY_SCOPED'):p.scoped_section('start'+p.RESET+'end','start','end')
 def test_application_function_cannot_enter_platform_owner_section(self):
  with self.assertRaisesRegex(ValueError,'APPLICATION_FUNCTION'):p.scoped_section('start\nCREATE OR REPLACE FUNCTION public.bad() RETURNS void AS $$ BEGIN END $$ LANGUAGE plpgsql;\nend','start','end')
 def test_scope_receipt_binds_original_region(self):
  text='aSTART native DDL ENDz';_,report=p.scoped_section(text,'START','END')
  self.assertEqual(report['protected_section_sha256'],p.digest(b'START native DDL '))
 def test_guard_binds_role_database_and_privilege(self):
  for term in ('current_database()','__DIAL_GTR_TARGET_DB__','current_user','supabase_admin','rolsuper','SET LOCAL ROLE postgres'):
   self.assertIn(term,p.GUARD)
 def test_context_compiler_has_no_external_operations(self):
  src=(BASE/'tools/gtr_migration_plan.py').read_text()
  for token in ('subprocess','os.system','urllib','socket','psycopg'):self.assertNotIn(token,src)

class SchemaContractComparison(unittest.TestCase):
 def test_exact_match(self):
  data={'tables':[['public','a',True,'p']]}
  self.assertTrue(c.differences(data,data)['tables']['match'])
 def test_missing_relation_fails(self):
  diff=c.differences({'tables':[]},{'tables':[['public','a',True,'p']]})
  self.assertFalse(diff['tables']['match'])
 def test_extra_relation_fails(self):
  diff=c.differences({'tables':[['public','a',True,'p']]},{'tables':[]})
  self.assertFalse(diff['tables']['match'])
 def test_rls_change_fails(self):
  diff=c.differences({'tables':[['public','a',False,'p']]},{'tables':[['public','a',True,'p']]})
  self.assertFalse(diff['tables']['match'])
 def test_function_capability_change_fails(self):
  old={'functions':[['public','f','','hash',False,False,True]]};new=copy.deepcopy(old);new['functions'][0][4]=True
  self.assertFalse(c.differences(new,old)['functions']['match'])
 def test_duplicate_contract_identity_rejected(self):
  rows={'tables':[['public','a',True,'p']]*2}
  with self.assertRaisesRegex(ValueError,'DUPLICATE'):c.differences(rows,rows)
 def test_permission_rows_order_irrelevant_but_values_exact(self):
  rows={'relation_grants':[['public','a','anon','SELECT',False],['public','a','authenticated','SELECT',True]]}
  reordered={'relation_grants':list(reversed(rows['relation_grants']))}
  self.assertTrue(c.differences(reordered,rows)['relation_grants']['match'])
 def test_private_usage_change_fails(self):
  self.assertFalse(c.differences({'private_usage':[True,False,False]},{'private_usage':[False,False,False]})['private_usage']['match'])

if __name__=='__main__':unittest.main()
