from pathlib import Path
import os,subprocess,json,hashlib
root=Path('/workspace/van-review-2026-10-18/publish');out=Path('/workspace/van-news-runtime-mutations-20261026');out.mkdir(exist_ok=True)
runtime='trading/vati/events/news_runtime.py';ingress='trading/vati/events/news_ingress.py';account='trading/vati/app/account_service.py'
variants={
 'discard-cold-history':(runtime,"news=NewsIngress.from_ledger(ledger,registry=registry,sources=options['sources'],\n            relevance_window_ms=options['relevance_window_ms'],max_events=options['max_recovery_events'])","news=NewsIngress(ledger=ledger,registry=registry,sources=options['sources'],\n            relevance_window_ms=options['relevance_window_ms'])"),
 'abort-jsonl-neighbors':(ingress,"out.append(NewsRowFailure(f'line {number}',line[:200],\n                    'invalid JSON' if isinstance(exc,json.JSONDecodeError) else 'row must be an object'))",'raise'),
 'claim-missing-ready':(runtime,"_health(news,ledger,scope,'MISSING',now_ms,source_ref=source_ref)","_health(news,ledger,scope,'READY_DECLARED',now_ms,source_ref=source_ref)"),
 'qualify-file-labels':(runtime,"'provider_qualified':False,'live_eligible':False","'provider_qualified':True,'live_eligible':True"),
 'skip-health-readback':(runtime,"if not confirmed:raise OSError('news health original durable publication not confirmed')","if False:raise OSError('news health original durable publication not confirmed')"),
 'duplicate-health-replay':(runtime,"if previous is not None and previous.payload['material']==material:",'if False:'),
 'ignore-row-capacity':(runtime,"if len(rows)>options['max_rows']:",'if False:'),
 'discard-profile-identity':(runtime,"source_ref=canonical_hash(news._file_profile)","source_ref=canonical_hash({'path':str(path)})"),
 'count-future-headlines':(runtime,"last_known_headlines=None if now_ms is None else len(news.headlines(since_ms=-(2**63),as_of_ms=now_ms)),","last_known_headlines=len(news._headlines),"),
 'hide-account-assessment-failure':(account,"                applied[symbol.upper()]={'state':'UNAVAILABLE','error_code':type(exc).__name__}",'                pass'),
}
originals={path:(root/path).read_text() for path,_,_ in variants.values()};receipts=[];env=dict(os.environ,PYTHONPATH='backend:backend/tests:trading:trading/tests:.')
try:
 for name,(path,old,new) in variants.items():
  original=originals[path];assert original.count(old)==1,(name,original.count(old));mutated=original.replace(old,new);(root/path).write_text(mutated)
  with (out/(name+'.log')).open('wb') as log:
   r=subprocess.run(['/workspace/van-backend-venv-20261025/bin/python','tools/rebuild/source_storage_audit.py','--report',str(out/(name+'-audit.json')),'trading/tests/test_news_runtime_health.py','-k','not postgres','--junitxml='+str(out/(name+'.xml')),'-q'],cwd=root,env=env,stdout=log,stderr=subprocess.STDOUT,timeout=45)
  receipts.append({'case':name,'path':path,'exit':r.returncode,'mutated_sha256':hashlib.sha256(mutated.encode()).hexdigest()});(root/path).write_text(original)
finally:
 for path,text in originals.items():(root/path).write_text(text)
 (out/'receipt.json').write_text(json.dumps({'schema':'van.supplemental-source-faults/1','control_sha256':{p:hashlib.sha256(s.encode()).hexdigest() for p,s in originals.items()},'source_restored':all((root/p).read_text()==s for p,s in originals.items()),'cases':receipts,'not_canonical_corpus':True},indent=2)+'\n')
assert len(receipts)==len(variants) and all(r['exit']==1 for r in receipts)
print('10 fault subprocesses exit1; inspect JUnit assertions/errors independently')
