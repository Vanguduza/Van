"""Pure offline metadata comparator refuses hidden/partial scopes and release claims."""
import copy
import pathlib
import sys
import unittest
ROOT=pathlib.Path(__file__).parent
sys.path.insert(0,str(ROOT))
import gtr_final_schema_gate as gate

def source():
 return {
    'tables':[['public','a',True,'p']],
    'views':[['public','v','a'*64,['security_invoker=true']]],
    'functions':[['public','f','p_id uuid','b'*32,True,True,True]],
    'policies':[['public','a','a_select','PERMISSIVE',['authenticated'],'SELECT','c'*64,None]],
    'relation_grants':[['public','a','anon',False,False,False,False,False,False,False,False]],
    'private_usage':[False,False,True]
 }

class SchemaReviewTests(unittest.TestCase):
 def test_exact(self):
  x=gate.compare(source(),source())
  self.assertTrue(x['metadata_identity_and_fingerprint_equal'])
  self.assertEqual(x['blockers'],[])
  self.assertFalse(x['production_deployment_authorized'])
  self.assertFalse(x['canary_activation_authorized'])
  self.assertFalse(x['nissan_gtr_cutover_authorized'])
 def test_new_function(self):
  a=source();b=source()
  b['functions'].append(['public','g','','d'*32,True,False,False])
  x=gate.compare(a,b)['groups']['functions']
  self.assertEqual(x['new_in_postforward'],1)
  self.assertEqual(x['changed_shared'],0)
 def test_missing_function(self):
  a=source();b=source()
  a['functions'].append(['public','g','','d'*32,False,False,False])
  self.assertEqual(gate.compare(a,b)['groups']['functions']['missing_from_postforward'],1)
 def test_function_body_drift(self):
  a=source();b=source();b['functions'][0][3]='c'*32
  x=gate.compare(a,b)['groups']['functions']
  self.assertEqual(x['definition_hash_changes'],1)
  self.assertEqual(x['execute_grant_changes'],0)
 def test_function_access_drift(self):
  a=source();b=source();b['functions'][0][4]=False
  x=gate.compare(a,b)['groups']['functions']
  self.assertEqual(x['execute_grant_changes'],1)
  self.assertEqual(x['execute_grant_direction']['anon']['lost'],1)
 def test_policy_predicate_addition(self):
  a=source();b=source()
  b['policies'].append(['public','a','z_add','PERMISSIVE',['authenticated'],'INSERT',None,'e'*64])
  x=gate.compare(a,b)['groups']['policies']
  self.assertEqual(x['new_in_postforward'],1)
  self.assertEqual(x['predicate_changes'],0)
 def test_changed_existing_policy_blocks(self):
  a=source();b=source();b['policies'][0][6]='e'*64
  x=gate.compare(a,b)
  self.assertEqual(x['groups']['policies']['predicate_changes'],1)
  self.assertFalse(x['metadata_identity_and_fingerprint_equal'])
 def test_role_changed_policy(self):
  a=source();b=source();b['policies'][0][4]=['anon']
  self.assertEqual(gate.compare(a,b)['groups']['policies']['role_or_command_changes'],1)
 def test_table_boolean_drift(self):
  a=source();b=source();b['tables'][0][2]=False
  self.assertEqual(gate.compare(a,b)['groups']['tables']['changed_shared'],1)
 def test_view_fingerprint_drift(self):
  a=source();b=source();b['views'][0][2]='f'*64
  self.assertEqual(gate.compare(a,b)['groups']['views']['changed_shared'],1)
 def test_private_schema_change(self):
  a=source();b=source();b['private_usage'][-1]=False
  self.assertFalse(gate.compare(a,b)['private_usage_equal'])
 def test_lost_effective_grants(self):
  a=source();b=source();a['relation_grants'][0][3]=True
  x=gate.compare(a,b)['groups']['relation_grants']
  self.assertEqual(x['lost_effective_privileges'],1)
  self.assertEqual(x['gained_effective_privileges'],0)
 def test_granted_effective_grants(self):
  a=source();b=source();b['relation_grants'][0][3]=True
  x=gate.compare(a,b)['groups']['relation_grants']
  self.assertEqual(x['gained_effective_privileges'],1)
 def test_duplicated_keys_refused(self):
  d=source();d['functions'].append(d['functions'][0][:])
  with self.assertRaisesRegex(gate.SchemaReviewError,'DUPLICATE'):gate.compare(d,source())
 def test_unsorted_refused(self):
  d=source();d['functions'].insert(0,['public','z','','b'*32,True,False,False])
  with self.assertRaisesRegex(gate.SchemaReviewError,'UNSORTED'):gate.compare(d,source())
 def test_wrong_scope_refused(self):
  d=source();d['raw_sql']='SELECT secrets'
  with self.assertRaisesRegex(gate.SchemaReviewError,'EXACT_METADATA'):gate.compare(d,source())
 def test_missing_scope_refused(self):
  d=source();del d['policies']
  with self.assertRaises(gate.SchemaReviewError):gate.compare(d,source())
 def test_empty_group_refused(self):
  d=source();d['functions']=[]
  with self.assertRaises(gate.SchemaReviewError):gate.compare(d,source())
 def test_private_boolean_int_refused(self):
  d=source();d['private_usage'][0]=0
  with self.assertRaises(gate.SchemaReviewError):gate.compare(d,source())
 def test_grant_bool_int_refused(self):
  d=source();d['relation_grants'][0][3]=1
  with self.assertRaises(gate.SchemaReviewError):gate.compare(d,source())
 def test_function_code_or_raw_sql_refused(self):
  d=source();d['functions'][0][3]="CREATE FUNCTION ..."
  with self.assertRaises(gate.SchemaReviewError):gate.compare(d,source())
 def test_policy_raw_expression_refused(self):
  d=source();d['policies'][0][6]='auth.uid()=user_id'
  with self.assertRaises(gate.SchemaReviewError):gate.compare(d,source())
 def test_view_raw_definition_refused(self):
  d=source();d['views'][0][2]='SELECT private.secret'
  with self.assertRaises(gate.SchemaReviewError):gate.compare(d,source())
 def test_boolean_not_truthy(self):
  d=source();d['tables'][0][2]='true'
  with self.assertRaises(gate.SchemaReviewError):gate.compare(d,source())
 def test_all_non_release_claims(self):
  r=gate.compare(source(),source())
  for k in ('production_deployment_authorized','migration_history_repair_authorized','canary_activation_authorized','nissan_gtr_cutover_authorized','hosted_database_modified','sql_or_customer_rows_returned'):
   self.assertFalse(r[k],k)
 def test_no_sql_or_network_executor_imports(self):
  s=(ROOT/'gtr_final_schema_gate.py').read_text()
  for part in ('subprocess','socket','psycopg','requests','supabase.','os.system','eval('):
   self.assertNotIn(part,s)

if __name__=='__main__':unittest.main()
