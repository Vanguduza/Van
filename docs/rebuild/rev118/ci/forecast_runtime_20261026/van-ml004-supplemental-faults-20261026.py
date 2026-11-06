from pathlib import Path
import os,subprocess,json,hashlib,xml.etree.ElementTree as ET
root=Path('/workspace/van-review-2026-10-18/publish');out=Path('/workspace/van-ml004-supplemental-faults-20261026');out.mkdir()
variants={
 'allow-t0-model-import':('trading/vati/core/model_boundary.py',"if fullname.partition('.')[0] in MODEL_FRAMEWORK_ROOTS:",'if False:','test_ml_runtime_boundary.py'),
 'allow-preloaded-t0-model':('trading/vati/core/model_boundary.py','if loaded:','if False:','test_ml_runtime_boundary.py'),
 'forward-host-environment':('trading/vati_forecast_worker/policy.py',"return {**{name:'' for name in _PROXIES}","return {**dict(os.environ),**{name:'' for name in _PROXIES}",'test_forecast_worker_policy.py'),
 'ignore-kernel-memory-pids':('trading/vati_forecast_worker/policy.py',"if observed[name]=='max' or not 0<int(observed[name])<=maximum:raise ValueError()",'if False:raise ValueError()','test_forecast_worker_policy.py'),
 'ignore-artifact-hash':('trading/vati_forecast_worker/artifacts.py',"if hashlib.sha256(data).hexdigest()!=expected:raise WorkerBoundaryError('MODEL_ARTIFACT_HASH_MISMATCH')",'if False:raise ValueError()','test_forecast_fixture_artifacts.py'),
 'allow-extra-artifact-files':('trading/vati_forecast_worker/artifacts.py',"if present!=MODEL_FILES|{'fixture-models.json'} or any(path.is_symlink() for path in root.rglob('*')):",'if False:','test_forecast_fixture_artifacts.py'),
 'ignore-unconfirmed-cleanup':('tools/rebuild/run_forecast_runtime_smoke.py',"if receipt.get('removed') is not True or 'cleanup_error_type' in receipt:",'if False:','test_forecast_runtime_supervisor.py'),
 'ignore-snapshot-tampering':('tools/rebuild/run_forecast_runtime_smoke.py','if not all((snapshot/path).is_file()','if False and not all((snapshot/path).is_file()','test_forecast_runtime_supervisor.py'),
}
originals={p:(root/p).read_bytes() for p,_,_,_ in variants.values()};receipts=[]
env=dict(os.environ,PYTHONPATH='backend:backend/tests:trading:trading/tests:.')
def execute(label,files):
 with (out/(label+'.log')).open('wb') as log:
  p=subprocess.run(['/workspace/van-backend-venv-20261025/bin/python','tools/rebuild/source_storage_audit.py','--report',str(out/(label+'-audit.json')),*['trading/tests/'+x for x in files],'--junitxml='+str(out/(label+'.xml')),'-q'],cwd=root,env=env,stdout=log,stderr=subprocess.STDOUT,timeout=60)
 xml=ET.parse(out/(label+'.xml'));cases=list(xml.iter('testcase'))
 return {'exit':p.returncode,'cases':len(cases),'failed_assertions':sum(bool(c.findall('failure')) for c in cases),'errors':sum(bool(c.findall('error')) for c in cases),'skipped':sum(bool(c.findall('skipped')) for c in cases),'storage_audit_violations':len(json.loads((out/(label+'-audit.json')).read_text())['forbidden_events'])}
try:
 before=execute('positive-control',sorted({row[3] for row in variants.values()}));assert before['exit']==0 and before['cases']==49 and before['skipped']==0,before
 for name,(path,old,new,test) in variants.items():
  original=originals[path].decode();assert original.count(old)==1,(name,original.count(old))
  mutated=original.replace(old,new).encode();(root/path).write_bytes(mutated)
  try:
   result=execute(name,[test]);result.update(case=name,path=path,mutated_sha256=hashlib.sha256(mutated).hexdigest());receipts.append(result)
   assert result['exit']==1 and result['failed_assertions']>0 and result['errors']==result['skipped']==result['storage_audit_violations']==0,result
  finally:(root/path).write_bytes(originals[path])
 after=execute('restored-control',sorted({row[3] for row in variants.values()}));assert after['exit']==0 and after['cases']==49 and after['skipped']==0,after
finally:
 for path,body in originals.items():(root/path).write_bytes(body)
 receipt={'schema':'van.supplemental-source-faults/1','not_canonical_corpus':True,'control_sha256':{p:hashlib.sha256(s).hexdigest() for p,s in originals.items()},'source_restored':all((root/p).read_bytes()==s for p,s in originals.items()),'positive_control':locals().get('before'),'restored_control':locals().get('after'),'cases':receipts}
 (out/'receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
print(json.dumps(receipt),flush=True)
