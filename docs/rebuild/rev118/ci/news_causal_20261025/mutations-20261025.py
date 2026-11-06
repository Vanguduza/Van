from pathlib import Path
import os,subprocess,json,hashlib
root=Path('/workspace/van-review-2026-10-18/publish');path=root/'trading/vati/events/news_ingress.py';original=path.read_text();out=Path('/workspace/van-news-causal-mutations-20261025');out.mkdir(exist_ok=True)
variants={
 'ignore-future-availability':('if not self._available_at(headline,now_ms):','if False:',2),
 'ignore-original-capture-clock':('return not captures or min(captures)<=now_ms','return True',1),
 'include-future-relays':('if as_of_ms is None or self._relay_times[headline_id][source]<=as_of_ms','if True',1),
 'feed-self-promotes-trust':('trust=min((requested,registered),key=lambda state:state.weight)','trust=requested',1),
 'unbounded-risk-floor':('if not ZERO<=floor<=ONE:','if False:',1),
 'nonfinite-materiality':('if not result.is_finite():','if False:',1),
 'collide-subject-kinds':('                "subject_kind":subject_kind,','',1),
 'backdate-replayed-observation':('original_capture=next((at for h,at in claims if h==headline),None)','original_capture=None',1),
 'count-unavailable-report':('available=self.headlines(since_ms=-(2**63),as_of_ms=now_ms)','available=self.headlines(since_ms=-(2**63))',1),
}
receipts=[];env=dict(os.environ,PYTHONPATH='backend:backend/tests:trading:trading/tests:.')
try:
 for name,(old,new,count) in variants.items():
  assert original.count(old)==count,(name,original.count(old));mutated=original.replace(old,new);path.write_text(mutated)
  with (out/(name+'.log')).open('wb') as log:
   r=subprocess.run(['/workspace/van-backend-venv-20261025/bin/python','tools/rebuild/source_storage_audit.py','--report',str(out/(name+'-audit.json')),'trading/tests/test_news_causal_boundaries.py','--junitxml='+str(out/(name+'.xml')),'-q'],cwd=root,env=env,stdout=log,stderr=subprocess.STDOUT,timeout=30)
  receipts.append({'case':name,'exit':r.returncode,'mutated_sha256':hashlib.sha256(mutated.encode()).hexdigest()});path.write_text(original)
finally:
 path.write_text(original)
 (out/'receipt.json').write_text(json.dumps({'schema':'van.supplemental-source-faults/1','original_sha256':hashlib.sha256(original.encode()).hexdigest(),'source_restored':path.read_text()==original,'cases':receipts,'not_canonical_corpus':True},indent=2)+'\n')
assert len(receipts)==len(variants) and all(r['exit']==1 for r in receipts)
print('all9 fault subprocesses exit1; inspect JUnit assertions/errors independently')
