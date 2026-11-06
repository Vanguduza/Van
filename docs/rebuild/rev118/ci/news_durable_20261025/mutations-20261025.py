from pathlib import Path
import os,subprocess,json,hashlib
root=Path('/workspace/van-review-2026-10-18/publish');path=root/'trading/vati/events/news_ingress.py';original=path.read_text();out=Path('/workspace/van-news-durable-mutations-20261025');out.mkdir(exist_ok=True)
variants={
 'duplicate-cold-headline':('            original=read()','            original=None'),
 'recreate-missing-headline':('                if hid in self._headlines:','                if False:'),
 'recreate-missing-observation':('                if oid in self._published_observations:','                if False:'),
 'replace-original-observation-clock':('return original,created,observation[1]','return original,created,available_ms'),
 'ignore-recovery-chain':("if not ledger.verify_chain()[0]:raise NewsIngressError('news recovery ledger integrity unavailable')",'if False:raise NewsIngressError(\'news recovery ledger integrity unavailable\')'),
 'ignore-recovery-capacity':('if sum(ledger.count(kind) for kind in kinds)>max_events:','if False:'),
 'duplicate-original-impact':('            if read() is None:','            if True:'),
 'collapse-changed-evidence':('"basis":basis,"evidence_refs":evidence_refs,','"basis":basis,'),
}
receipts=[];env=dict(os.environ,PYTHONPATH='backend:backend/tests:trading:trading/tests:.')
try:
 for name,(old,new) in variants.items():
  assert original.count(old)==1,(name,original.count(old));mutated=original.replace(old,new);path.write_text(mutated)
  with (out/(name+'.log')).open('wb') as log:
   r=subprocess.run(['/workspace/van-backend-venv-20261025/bin/python','tools/rebuild/source_storage_audit.py','--report',str(out/(name+'-audit.json')),'trading/tests/test_news_durable_publication.py','-k','not postgres','--junitxml='+str(out/(name+'.xml')),'-q'],cwd=root,env=env,stdout=log,stderr=subprocess.STDOUT,timeout=45)
  receipts.append({'case':name,'exit':r.returncode,'mutated_sha256':hashlib.sha256(mutated.encode()).hexdigest()});path.write_text(original)
finally:
 path.write_text(original)
 (out/'receipt.json').write_text(json.dumps({'schema':'van.supplemental-source-faults/1','original_sha256':hashlib.sha256(original.encode()).hexdigest(),'source_restored':path.read_text()==original,'cases':receipts,'not_canonical_corpus':True},indent=2)+'\n')
assert len(receipts)==len(variants) and all(r['exit']==1 for r in receipts)
print('8 fault subprocesses exit1; inspect JUnit assertion and setup evidence')
