from pathlib import Path
import subprocess,json,hashlib,xml.etree.ElementTree as ET,os
root=Path('/workspace/van-review-2026-10-18/publish')
out=Path('/workspace/van-dataset-publication-faults-20261026');out.mkdir()
path='trading/vati/research/dataset_archive.py'
test='trading/worker_tests/test_dataset_candidate_archive.py'
cases={
'self-grant-research':("'qualified_for_research':False","'qualified_for_research':True",'test_real_publication_readback_replay_and_current_inspection_stay_unadmitted'),
'lookup-uncommitted':("self._outside_transaction()\n        rows,_=self._history();event=next((e for e in rows if e.payload['request_id']==request_id),None)\n        return None","rows,_=self._history();event=next((e for e in rows if e.payload['request_id']==request_id),None)\n        return None",'test_lookup_cannot_report_an_uncommitted_candidate_as_published'),
'mix-financial-ledger':("if self.ledger.count()!=count:raise DatasetContractError('DATASET_DEDICATED_SOURCE_LEDGER_REQUIRED')","if False:raise DatasetContractError('DATASET_DEDICATED_SOURCE_LEDGER_REQUIRED')",'test_financial_or_other_event_kinds_are_not_a_candidate_metadata_store'),
'ignore-record-identity':(" or any(e.payload['manifest']['record_id']==requested['record_id'] for e in rows)","",'test_original_request_and_record_identity_cannot_be_rebound'),
'ignore-request-fingerprint':("            if original.payload['request_sha256']!=fingerprint:raise DatasetContractError('DATASET_ORIGINAL_REQUEST_CONFLICT')\n            return self._receipt(original)","            return self._receipt(original)",'test_original_request_and_record_identity_cannot_be_rebound'),
'skip-original-bytes':("inspection=self.inspector.inspect(candidate,expected_scope=scope)","inspection={'resolved_source_facts':{}}",'test_new_publication_requires_current_original_bytes_before_any_sql_append'),
'hide-readback-success':("if confirmed is None or confirmed['record_ref']!=original.hash:","if False:",'test_hidden_original_readback_is_not_a_success_receipt'),
'accept-decision-envelope':("or event.decision_time_ms is not None","or False",'test_even_sealed_incompatible_original_records_refuse_recovery'),
}
original=(root/path).read_bytes();results=[]
def run(label,target):
 with (out/(label+'.log')).open('wb') as log:
  r=subprocess.run(['/workspace/van-backend-venv-20261025/bin/python','tools/rebuild/source_storage_audit.py','--report',str(out/(label+'-audit.json')),target,'-k','not postgres','--junitxml='+str(out/(label+'.xml')),'-q'],cwd=root,env=dict(os.environ,PYTHONDONTWRITEBYTECODE='1'),stdout=log,stderr=subprocess.STDOUT,timeout=90)
 tests=list(ET.parse(out/(label+'.xml')).iter('testcase'));fail=[f for t in tests for f in t.findall('failure')]
 assertions=sum('AssertionError' in f.get('message','') or f.get('message','').startswith(('Failed: DID NOT RAISE','assert ')) or 'AssertionError' in (f.text or '') for f in fail)
 return dict(exit=r.returncode,cases=len(tests),failures=len(fail),assertions=assertions,errors=sum(t.find('error') is not None for t in tests),skips=sum(t.find('skipped') is not None for t in tests),storage_audit_violations=len(json.loads((out/(label+'-audit.json')).read_text())['forbidden_events']))
try:
 control=run('positive-control',test);assert control['exit']==control['errors']==control['skips']==control['storage_audit_violations']==0,control
 for label,(old,new,target) in cases.items():
  text=original.decode();assert text.count(old)==1,(label,text.count(old));changed=text.replace(old,new);(root/path).write_text(changed)
  try:
   result=run(label,test+'::'+target);results.append(dict(case=label,mutant_sha256=hashlib.sha256(changed.encode()).hexdigest(),**result))
   assert result['exit']==1 and result['assertions']>0 and result['errors']==result['skips']==result['storage_audit_violations']==0,results[-1]
  finally:(root/path).write_bytes(original)
 restored=run('restored-control',test);assert restored['exit']==restored['errors']==restored['skips']==restored['storage_audit_violations']==0,restored
finally:
 (root/path).write_bytes(original)
 (out/'receipt.json').write_text(json.dumps(dict(schema='van.supplemental-source-faults/1',not_canonical_374=True,selection='SQLite only; PostgreSQL parameterizations deselected, separately executed in broad actual PostgreSQL fixture',positive_control=locals().get('control'),restored_control=locals().get('restored'),cases=results,restored=(root/path).read_bytes()==original,source_sha256={path:hashlib.sha256(original).hexdigest()}),indent=2)+'\n')
print(json.dumps(dict(caught=len(results),restored=True)))

