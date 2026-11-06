import hashlib,json,os,pathlib,subprocess
root=pathlib.Path('/workspace/van-review-2026-10-18/publish');source=root/'trading/vati/calendar/recorder.py';original=source.read_text()
out=pathlib.Path('/workspace/van-calendar-causal-mutations-20261025');out.mkdir(exist_ok=True)
variants={
 'ignore-declared-cutoff':('if now_ms is None or o.observed_ms<=now_ms','if True'),
 'compare-decimal-text':('by_value.setdefault(o.actual, []).append(source)','by_value.setdefault(str(o.actual), []).append(source)'),
 'admit-clock-defect-values':('eligible=tuple(o for o in obs if o.observed_ms>=o.released_ms>=sched.scheduled_ms)','eligible=obs'),
 'lose-observation-availability':('received_time_ms=event_ms if received_ms is None else received_ms','received_time_ms=event_ms'),
 'repeat-original-publication':('            if original() is None:\n                if must_exist:','            if True:\n                if must_exist:'),
}
receipts=[];env=dict(os.environ,PYTHONPATH='backend:backend/tests:trading:trading/tests:.')
try:
 for name,(old,new) in variants.items():
  assert original.count(old)==1,(name,original.count(old))
  mutated=original.replace(old,new);source.write_text(mutated)
  with (out/(name+'.log')).open('wb') as log:
   r=subprocess.run(['/workspace/van-backend-venv-20261025/bin/python','tools/rebuild/source_storage_audit.py','--report',str(out/(name+'-audit.json')),'trading/tests/test_calendar_causal_boundaries.py','-k','not postgres','--junitxml='+str(out/(name+'.xml')),'-q'],cwd=root,env=env,stdout=log,stderr=subprocess.STDOUT,timeout=40)
  receipts.append({'case':name,'exit':r.returncode,'mutated_sha256':hashlib.sha256(mutated.encode()).hexdigest()});source.write_text(original)
finally:
 source.write_text(original)
 (out/'receipt.json').write_text(json.dumps({'schema':'van.supplemental-source-faults/1','control_sha256':hashlib.sha256(original.encode()).hexdigest(),'source_restored':source.read_text()==original,'cases':receipts,'not_canonical_corpus':True},indent=2)+'\n')
print(json.dumps(receipts));assert len(receipts)==len(variants) and all(r['exit']==1 for r in receipts)
