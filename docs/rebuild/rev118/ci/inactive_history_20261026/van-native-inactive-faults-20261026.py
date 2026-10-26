from pathlib import Path
import subprocess,json,hashlib,xml.etree.ElementTree as ET,os

root=Path('/workspace/van-review-2026-10-18/publish')
out=Path('/workspace/van-native-inactive-faults-20261026');out.mkdir()
assert json.loads(Path('/workspace/van-native-inactive-pg-final-20261026/receipt.json').read_text())['owned_fixture_independently_absent']
manifest='trading/vati/research/dataset_manifest.py';source='trading/vati/research/dataset_sources.py'
cases={
 'self-grant-read-execution':('trading/vati/execution/ctrader/read_identity.py',"'qualified_for_execution':False", "'qualified_for_execution':True", 'trading/tests/test_native_read_identity.py::test_visible_hidden_nameless_and_archived_entries_have_read_only_identity'),
 'renew-identity-on-capture-clock':('trading/vati/execution/ctrader/read_identity.py','return canonical_hash(self.metadata)',"return canonical_hash({'metadata':self.metadata,'clock':self.received_at_ms})", 'trading/tests/test_native_read_identity.py::test_identity_revision_ignores_receipt_clock_but_retains_original_metadata_and_private_copies'),
 'accept-corrupt-qualification-zero':('trading/vati/execution/ctrader/read_identity.py',"if any(body.get(key) is not False for key in ('qualified_for_execution','qualified_for_research','provider_qualified')):",'if False:', 'trading/tests/test_native_read_identity.py::test_read_identity_cannot_self_grant_or_corrupt_qualification_types'),
 'truncate-native-name-as-identity':('trading/vati/execution/ctrader/read_identity.py',"return 'CTRADER_NATIVE_' + str(self.native_scope['native_symbol_id'])", "return (self.display_name or 'UNKNOWN')[:256]", 'trading/tests/test_native_read_identity.py::test_unknown_or_unusable_display_label_retains_native_identity_without_truncating_data'),
 'ignore-original-catalog-revision':('trading/vati/execution/ctrader/adapter.py','if original.revision!=expected_identity.revision:', 'if False:', 'trading/tests/test_native_read_identity.py::test_changed_catalog_refuses_before_historical_request'),
 'ignore-retired-read-session':('trading/vati/execution/ctrader/adapter.py','current();transport.check_budget()', 'transport.check_budget()', 'trading/tests/test_native_read_identity.py::test_retired_history_connection_cannot_publish_success'),
 'ignore-final-history-parse-budget':('trading/vati/execution/ctrader/adapter.py','current();transport.check_budget()', 'current()', 'trading/tests/test_native_read_identity.py::test_deadline_expiring_during_history_parse_prevents_archive_publication'),
 'allow-disabled-execution-contract':('trading/vati/execution/ctrader/contracts.py'," or light.get('enabled') is not True", '', 'trading/tests/test_native_read_identity.py::test_enabled_execution_contract_remains_independently_required'),
}
originals={path:(root/path).read_bytes() for path,_,_,_ in cases.values()};results=[]
def run(label,targets):
 with (out/(label+'.log')).open('wb') as log:
  r=subprocess.run(['/workspace/van-backend-venv-20261025/bin/python','tools/rebuild/source_storage_audit.py',
    '--report',str(out/(label+'-audit.json')),*targets,'--junitxml='+str(out/(label+'.xml')),'-q'],cwd=root,
    env=dict(os.environ,PYTHONDONTWRITEBYTECODE='1'),stdout=log,stderr=subprocess.STDOUT,timeout=90)
 tests=list(ET.parse(out/(label+'.xml')).iter('testcase'));fail=[f for t in tests for f in t.findall('failure')]
 assertions=sum('AssertionError' in f.get('message','') or f.get('message','').startswith(('Failed: DID NOT RAISE','assert ')) or 'AssertionError' in (f.text or '') for f in fail)
 return dict(exit=r.returncode,cases=len(tests),failures=len(fail),assertions=assertions,
   errors=sum(t.find('error') is not None for t in tests),skips=sum(t.find('skipped') is not None for t in tests),
   storage_audit_violations=len(json.loads((out/(label+'-audit.json')).read_text())['forbidden_events']))
try:
 targets=['trading/tests/test_native_read_identity.py','trading/worker_tests/test_inactive_source_parquet.py']
 control=run('positive-control',targets);assert control['exit']==control['errors']==control['skips']==control['storage_audit_violations']==0,control
 for label,(path,old,new,target) in cases.items():
  text=originals[path].decode();assert text.count(old)==1,(label,text.count(old));changed=text.replace(old,new);(root/path).write_text(changed)
  try:
   result=run(label,[target]);results.append(dict(case=label,path=path,mutant_sha256=hashlib.sha256(changed.encode()).hexdigest(),**result))
   assert result['exit']==1 and result['assertions']>0 and result['errors']==result['skips']==result['storage_audit_violations']==0,results[-1]
  finally:(root/path).write_bytes(originals[path])
 restored=run('restored-control',targets);assert restored['exit']==restored['errors']==restored['skips']==restored['storage_audit_violations']==0,restored
finally:
 for path,body in originals.items():(root/path).write_bytes(body)
 (out/'receipt.json').write_text(json.dumps(dict(schema='van.supplemental-source-faults/1',not_canonical_374=True,
  positive_control=locals().get('control'),restored_control=locals().get('restored'),cases=results,
  restored=all((root/p).read_bytes()==b for p,b in originals.items()),source_sha256={p:hashlib.sha256(b).hexdigest() for p,b in originals.items()}),indent=2)+'\n')
print(json.dumps(dict(caught=len(results),restored=True)))
