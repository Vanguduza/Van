from pathlib import Path
import os,subprocess,json,hashlib,xml.etree.ElementTree as ET
root=Path('/workspace/van-review-2026-10-18/publish');out=Path('/workspace/van-news-cli-faults-r2-20261026');out.mkdir()
variants={
 'bypass-required-durable-rss':('trading/vati/__main__.py',"if input_format=='rss2' and not a.ledger:",'if False:'),
 'acknowledge-source-error-as-success':('trading/vati/__main__.py',"exit_code=0 if state in {'READY_DECLARED','EMPTY_DECLARED'} else 1 if state=='PARTIAL' else 2",'exit_code=0'),
 'discard-cold-original-history':('trading/vati/events/news_runtime.py',"news=NewsIngress.from_ledger(ledger,registry=registry,sources=options['sources'],\n            relevance_window_ms=options['relevance_window_ms'],max_events=options['max_recovery_events'])","news=NewsIngress(ledger=ledger,registry=registry,sources=options['sources'],\n            relevance_window_ms=options['relevance_window_ms'])"),
 'consume-first-batch-twice':('trading/vati/__main__.py',"counts={name:result[name] for name in ('accepted','duplicates','skipped')}","from vati.events.news_runtime import refresh_news_file\n            result=refresh_news_file(ingress,config|{'path':path},ledger=ledger,scope='news-ingest-cli',now_ms=now_ms)\n            counts={name:result[name] for name in ('accepted','duplicates','skipped')}"),
 'leak-cli-ledger-connection':('trading/vati/__main__.py','if ledger is not None:ledger.close()','if False:ledger.close()'),
}
originals={p:(root/p).read_bytes() for p,_,_ in variants.values()};receipts=[]
env=dict(os.environ,PYTHONPATH='backend:backend/tests:trading:trading/tests:.')
def run(label):
 with (out/(label+'.log')).open('wb') as log:
  p=subprocess.run(['/workspace/van-backend-venv-20261025/bin/python','tools/rebuild/source_storage_audit.py','--report',str(out/(label+'-audit.json')),'trading/tests/test_news_cli_source.py','--junitxml='+str(out/(label+'.xml')),'-q'],cwd=root,env=env,stdout=log,stderr=subprocess.STDOUT,timeout=40)
 cases=list(ET.parse(out/(label+'.xml')).iter('testcase'));failures=[f for c in cases for f in c.findall('failure')]
 return {'exit':p.returncode,'cases':len(cases),'assertion_failures':sum(('AssertionError' in f.attrib.get('type','') or f.attrib.get('message','').startswith('AssertionError:')) for f in failures),'failures':len(failures),'errors':sum(bool(c.findall('error')) for c in cases),'skipped':sum(bool(c.findall('skipped')) for c in cases),'audit_violations':len(json.loads((out/(label+'-audit.json')).read_text())['forbidden_events'])}
try:
 control=run('positive-control');assert control['exit']==0 and control['cases']==15,control
 for label,(path,old,new) in variants.items():
  text=originals[path].decode();assert text.count(old)==1,(label,text.count(old));mutated=text.replace(old,new).encode();(root/path).write_bytes(mutated)
  try:
   result=run(label);result.update(case=label,path=path,mutated_sha256=hashlib.sha256(mutated).hexdigest());receipts.append(result)
   assert result['exit']==1 and result['assertion_failures']>0 and result['errors']==result['skipped']==result['audit_violations']==0,result
  finally:(root/path).write_bytes(originals[path])
 restored=run('restored-control');assert restored['exit']==0 and restored['cases']==15,restored
finally:
 for path,body in originals.items():(root/path).write_bytes(body)
 (out/'receipt.json').write_text(json.dumps({'schema':'van.supplemental-source-faults/1','not_canonical_374':True,'positive_control':locals().get('control'),'restored_control':locals().get('restored'),'cases':receipts,'source_restored':all((root/p).read_bytes()==s for p,s in originals.items()),'source_sha256':{p:hashlib.sha256(s).hexdigest() for p,s in originals.items()}},indent=2)+'\n')
print(json.dumps({'caught':len(receipts),'source_restored':True}))
