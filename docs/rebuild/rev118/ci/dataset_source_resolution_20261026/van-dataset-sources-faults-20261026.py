from pathlib import Path
import subprocess,json,hashlib,xml.etree.ElementTree as ET,os

root=Path('/workspace/van-review-2026-10-18/publish')
out=Path('/workspace/van-dataset-sources-faults-20261026');out.mkdir()
assert json.loads(Path('/workspace/van-dataset-sources-pg-final-20261026/receipt.json').read_text())['owned_fixture_independently_absent']
manifest='trading/vati/research/dataset_manifest.py';source='trading/vati/research/dataset_sources.py'
cases={
 'round-away-nanosecond-leakage':(manifest,"Fraction(int(digits or '0'), 10**len(digits))",'Fraction(0)', 'trading/tests/test_dataset_manifest_candidates.py::test_temporal_order_compares_exact_nanoseconds'),
 'self-qualify-candidate':(manifest,"'manifest_sha256': self.digest, 'authority_effect': 'NONE', 'qualified_for_research': False", "'manifest_sha256': self.digest, 'authority_effect': 'NONE', 'qualified_for_research': True", 'trading/tests/test_dataset_manifest_candidates.py::test_well_formed_manifest_stays_unresolved_and_mutation_cannot_rewrite_candidate'),
 'ignore-extra-manifest-fields':(manifest,"set(record) != set(schema['required'])",'False', 'trading/tests/test_dataset_manifest_candidates.py::test_malformed_or_ambiguous_manifest_is_refused[field]'),
 'ignore-actual-artifact-hash':(source,"reference['sha256'] != hashlib.sha256(original.parquet).hexdigest()",'False', 'trading/worker_tests/test_dataset_source_inspection.py::test_plausible_metadata_cannot_replace_actual_bytes_clocks_or_native_scope[hash]'),
 'ignore-source-row-identity':(source,"record['row_count'] != len(rows) or record['row_identity_digest'] != canonical_hash(rows)",'False', 'trading/worker_tests/test_dataset_source_inspection.py::test_plausible_metadata_cannot_replace_actual_bytes_clocks_or_native_scope[row_identity]'),
 'ignore-original-source-manifest':(source,"if single_source and record['source_manifest_digest'] != windows[0]['window_sha256']:",'if False:', 'trading/worker_tests/test_dataset_source_inspection.py::test_plausible_metadata_cannot_replace_actual_bytes_clocks_or_native_scope[source_digest]'),
 'ignore-actual-availability':(source,"if _timestamp(record['max_input_available_at']) != maximum:",'if False:', 'trading/worker_tests/test_dataset_source_inspection.py::test_plausible_metadata_cannot_replace_actual_bytes_clocks_or_native_scope[availability]'),
 'accept-cli-duplicate-keys':('trading/vati/__main__.py','if key in result:','if False:', 'trading/tests/test_dataset_manifest_candidates.py::test_actual_research_cli_refuses_nested_duplicate_keys_before_any_reference_resolution'),
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
 targets=['trading/worker_tests','trading/tests/test_dataset_manifest_candidates.py','trading/tests/test_contract_schemas.py',
          'trading/tests/test_forecast_source_partitions.py','trading/tests/test_research_and_drift.py','trading/tests/test_ml_runtime_boundary.py']
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
