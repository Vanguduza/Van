import hashlib,json,os,pathlib,subprocess
root=pathlib.Path('/workspace/van-review-2026-10-18/publish')
source=root/'trading/vati/execution/ctrader/transport.py';original=source.read_text()
out=pathlib.Path('/workspace/van-event-selection-mutations-20261025');out.mkdir(exist_ok=True)
variants={
 'remove-before-predicate':('                matches=predicate(name,deepcopy(body))','                claim(original)\n                matches=predicate(name,deepcopy(body))'),
 'omit-original-claim':('                if matches and claim(original):','                if matches:'),
 'give-callback-original':('matches=predicate(name,deepcopy(body))','matches=predicate(name,body)'),
 'omit-post-callback-expiry':('                if time.monotonic()>=deadline:return None\n                if matches and claim(original):','                if matches and claim(original):'),
 'rotate-unmatched-originals':('                        del self.events.queue[index]','                        self.events.queue.rotate(-index)\n                        self.events.queue.popleft()'),
 'omit-retired-source-recheck':('                    current=self._event_value(original)','                    current=item'),
}
receipts=[]
env=dict(os.environ,PYTHONPATH='backend:backend/tests:trading:trading/tests:.')
try:
 for name,(old,new) in variants.items():
  assert original.count(old)==1,(name,original.count(old))
  mutated=original.replace(old,new);source.write_text(mutated)
  with (out/(name+'.log')).open('wb') as log:
   result=subprocess.run(['/workspace/van-backend-venv-20261025/bin/python','tools/rebuild/source_storage_audit.py','--report',str(out/(name+'-audit.json')),'trading/tests/test_ctrader_event_selection.py','--junitxml='+str(out/(name+'.xml')),'-q'],cwd=root,env=env,stdout=log,stderr=subprocess.STDOUT,timeout=30)
  receipts.append({'case':name,'exit':result.returncode,'mutated_sha256':hashlib.sha256(mutated.encode()).hexdigest()})
  source.write_text(original)
finally:
 source.write_text(original)
 (out/'receipt.json').write_text(json.dumps({'schema':'van.supplemental-source-faults/1','control_sha256':hashlib.sha256(original.encode()).hexdigest(),'source_restored':source.read_text()==original,'cases':receipts,'not_canonical_corpus':True},indent=2)+'\n')
print(json.dumps(receipts))
assert len(receipts)==len(variants) and all(r['exit']==1 for r in receipts)
