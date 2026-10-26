from pathlib import Path
import subprocess,json,hashlib,xml.etree.ElementTree as ET,os

root=Path('/workspace/van-review-2026-10-18/publish')
out=Path('/workspace/van-parquet-faults-r2-20261026');out.mkdir()
worker='trading/vati_forecast_worker/source_partitions.py'
service='trading/vati/research/bar_partitions.py'
cases={
 'ignore-original-source':(service,'self.reader.verify(', '_unverified(', 'trading/worker_tests/test_native_source_parquet.py::test_claimed_window_cannot_replace_actual_archive_resolution'),
 'ignore-parquet-row-content':(worker,'if table.to_pylist() != rows:', 'if False:', 'trading/worker_tests/test_native_source_parquet.py::test_actual_parquet_tampering_refuses_even_when_file_hash_is_recomputed[rows]'),
 'allow-compressed-partition':(worker,"column.compression != 'UNCOMPRESSED'", "column.compression == 'NOT_A_CODEC'", 'trading/worker_tests/test_native_source_parquet.py::test_actual_parquet_tampering_refuses_even_when_file_hash_is_recomputed[compression]'),
 'self-qualify-derived-data':(worker,"'media_type': 'application/vnd.apache.parquet', 'qualified_for_research': False", "'media_type': 'application/vnd.apache.parquet', 'qualified_for_research': True", 'trading/worker_tests/test_native_source_parquet.py::test_actual_parquet_readback_is_typed_exact_and_deterministic'),
 'ignore-global-storage-capacity':(service,'if len(publications) > self.budget.publications or sum(existing.values()) > self.budget.stored_bytes:', 'if False:', 'trading/worker_tests/test_native_source_parquet.py::test_storage_capacity_refuses_before_new_publication_and_preserves_original'),
 'overwrite-conflicting-orphan':(service,'if path.stat().st_size != len(data) or self._read(path) != data:', 'if False:', 'trading/worker_tests/test_native_source_parquet.py::test_missing_manifest_recovers_only_exact_original_orphan'),
 'allow-arrow-inside-T0':('trading/vati/core/model_boundary.py',"'safetensors','pyarrow'", "'safetensors'", 'trading/tests/test_ml_runtime_boundary.py::test_actual_serve_entrypoint_refuses_model_import_before_model_code_executes[pyarrow]'),
 'leak-research-ledger':('trading/vati/__main__.py','            ledger.close()','            pass', 'trading/tests/test_forecast_source_partitions.py::test_research_cli_closes_real_sqlite_connection_on_success_and_failure'),
}
originals={path:(root/path).read_bytes() for path,_,_,_ in cases.values()}
results=[]
def run(label,targets):
 with (out/(label+'.log')).open('wb') as log:
  r=subprocess.run(['/workspace/van-parquet-source-venv-20261026/bin/python','tools/rebuild/source_storage_audit.py',
   '--report',str(out/(label+'-audit.json')),*targets,'--junitxml='+str(out/(label+'.xml')),'-q'],cwd=root,
   env=dict(os.environ,PYTHONDONTWRITEBYTECODE='1'),stdout=log,stderr=subprocess.STDOUT,timeout=90)
 tests=list(ET.parse(out/(label+'.xml')).iter('testcase'))
 fail=[f for t in tests for f in t.findall('failure')]
 assertions=sum('AssertionError' in f.get('message','') or f.get('message','').startswith(('Failed: DID NOT RAISE','assert ')) or 'AssertionError' in (f.text or '') for f in fail)
 return dict(exit=r.returncode,cases=len(tests),failures=len(fail),assertions=assertions,
   errors=sum(t.find('error') is not None for t in tests),skips=sum(t.find('skipped') is not None for t in tests),
   storage_audit_violations=len(json.loads((out/(label+'-audit.json')).read_text())['forbidden_events']))
try:
 targets=['trading/worker_tests','trading/tests/test_forecast_source_partitions.py','trading/tests/test_ml_runtime_boundary.py']
 control=run('positive-control',targets);assert control['exit']==control['errors']==control['skips']==control['storage_audit_violations']==0,control
 for label,(path,old,new,target) in cases.items():
  text=originals[path].decode();assert text.count(old)==(3 if label=='ignore-original-source' else 1),(label,text.count(old))
  changed=text.replace(old,new)
  if label=='ignore-original-source':changed+='\n\ndef _unverified(window, **kwargs):\n    return window\n'
  (root/path).write_text(changed)
  try:
   result=run(label,[target]);results.append(dict(case=label,path=path,mutant_sha256=hashlib.sha256(changed.encode()).hexdigest(),**result))
   assert result['exit']==1 and result['assertions']>0 and result['errors']==result['skips']==result['storage_audit_violations']==0,results[-1]
  finally:(root/path).write_bytes(originals[path])
 restored=run('restored-control',targets);assert restored['exit']==restored['errors']==restored['skips']==restored['storage_audit_violations']==0,restored
finally:
 for path,body in originals.items():(root/path).write_bytes(body)
 (out/'receipt.json').write_text(json.dumps(dict(schema='van.supplemental-source-faults/1',not_canonical_374=True,
  positive_control=locals().get('control'),restored_control=locals().get('restored'),cases=results,
  restored=all((root/p).read_bytes()==b for p,b in originals.items()),
  source_sha256={p:hashlib.sha256(b).hexdigest() for p,b in originals.items()}),indent=2)+'\n')
print(json.dumps(dict(caught=len(results),restored=True)))
