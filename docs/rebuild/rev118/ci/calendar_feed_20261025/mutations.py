import hashlib,json,os,pathlib,subprocess
root=pathlib.Path('/workspace/van-review-2026-10-18/publish')
variants={
 'assume-worker-timezone':('trading/vati/core/calendar_time.py','        if parsed.tzinfo is None or parsed.utcoffset() is None:','        if False:'),
 'silently-floor-submillisecond':('trading/vati/core/calendar_time.py','        if parsed.microsecond%1000:','        if False:'),
 'discard-original-event-key':('trading/vati/calendar/recorder.py','    return explicit.strip()','    return event_key(name,scheduled_ms)'),
 'ignore-key-scope-conflicts':('trading/vati/intelligence/calendar_feed.py',"        if (e['name'],e['release'],e['currencies'])!=(name,release,currencies):",'        if False:'),
 'promote-file-labels-to-live':('trading/vati/intelligence/calendar_feed.py','"live_eligible": 0,','"live_eligible": sum(1 for e in upcoming if e.verified_sources>=2),'),
 'drop-bare-array-rows':('trading/vati/calendar/recorder.py','        if isinstance(data,list):rows=data','        if isinstance(data,list):rows=[]'),
}
originals={name:(root/name).read_text() for name,_,_ in variants.values()};out=pathlib.Path('/workspace/van-calendar-feed-mutations-20261025');out.mkdir(exist_ok=True)
receipts=[];env=dict(os.environ,PYTHONPATH='backend:backend/tests:trading:trading/tests:.')
try:
 for name,(path,old,new) in variants.items():
  original=originals[path];assert original.count(old)==1,(name,original.count(old))
  mutated=original.replace(old,new);(root/path).write_text(mutated)
  with (out/(name+'.log')).open('wb') as log:
   r=subprocess.run(['/workspace/van-backend-venv-20261025/bin/python','tools/rebuild/source_storage_audit.py','--report',str(out/(name+'-audit.json')),'trading/tests/test_calendar_feed_boundaries.py','--junitxml='+str(out/(name+'.xml')),'-q'],cwd=root,env=env,stdout=log,stderr=subprocess.STDOUT,timeout=30)
  receipts.append({'case':name,'path':path,'exit':r.returncode,'mutated_sha256':hashlib.sha256(mutated.encode()).hexdigest()});(root/path).write_text(original)
finally:
 for path,text in originals.items():(root/path).write_text(text)
 (out/'receipt.json').write_text(json.dumps({'schema':'van.supplemental-source-faults/1','control_sha256':{p:hashlib.sha256(t.encode()).hexdigest() for p,t in originals.items()},'source_restored':all((root/p).read_text()==t for p,t in originals.items()),'cases':receipts,'not_canonical_corpus':True},indent=2)+'\n')
print(json.dumps(receipts));assert len(receipts)==len(variants) and all(r['exit']==1 for r in receipts)
