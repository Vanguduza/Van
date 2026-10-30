from pathlib import Path
import os,subprocess,json,hashlib,xml.etree.ElementTree as E
root=Path('/workspace/van-review-2026-10-18/publish');out=Path('/workspace/van-native-dataset-faults-20261026');out.mkdir()
variants={
 'include-later-same-clock-vintages':('trading/vati/market_data/native_windows.py','for body,digest in originals[:through_revision]:','for body,digest in originals:','test_native_bar_windows.py'),
 'ignore-pinned-source-reference':('trading/vati/market_data/native_windows.py',"if digest!=boundary_ref:raise ValueError('NATIVE_WINDOW_BOUNDARY_CONFLICT')",'if False:raise ValueError()','test_native_bar_windows.py'),
 'allow-self-declared-research-permission':('trading/vati/execution/ctrader/catalog.py',"or body['qualified_for_research'] is not False or body['authority_effect']!='NONE'","or False or body['authority_effect']!='NONE'",'test_native_symbol_catalog.py'),
 'ignore-cross-account-byte-usage':('trading/vati/market_data/catalog_store.py','size=total+len(canonical_json(original.body()).encode())','size=sum(len(canonical_json(e.body()).encode()) for e in rows)+len(canonical_json(original.body()).encode())','test_native_catalog_store.py'),
 'backdate-durable-availability-to-network-receive':('trading/vati/market_data/catalog_store.py','now=native_integer(self.clock(),minimum=captured.received_at_ms','now=native_integer(captured.received_at_ms,minimum=captured.received_at_ms','test_native_catalog_store.py'),
 'ignore-hidden-original-readback':('trading/vati/market_data/catalog_store.py',"if seen!=count:raise CatalogArchiveError('native catalog original readback missing')",'if False:raise ValueError()','test_native_catalog_store.py'),
 'ignore-native-response-payload-type':('trading/vati/execution/ctrader/catalog.py',"if 'payloadType' in response and not",'if False and not','test_native_symbol_catalog.py'),
 'omit-required-archived-catalog-request':('trading/vati/execution/ctrader/adapter.py',"'includeArchivedSymbols':True","'includeArchivedSymbols':False",'test_native_symbol_catalog.py'),
}
originals={p:(root/p).read_bytes() for p,_,_,_ in variants.values()};results=[]
env=dict(os.environ,PYTHONPATH='backend:backend/tests:trading:trading/tests:.')
def run(label,files):
 with (out/(label+'.log')).open('wb') as log:
  process=subprocess.run(['/workspace/van-backend-venv-20261025/bin/python','tools/rebuild/source_storage_audit.py','--report',str(out/(label+'-audit.json')),*['trading/tests/'+name for name in files],'-k','not postgres','--junitxml='+str(out/(label+'.xml')),'-q'],cwd=root,env=env,stdout=log,stderr=subprocess.STDOUT,timeout=75)
 cases=list(E.parse(out/(label+'.xml')).iter('testcase'));fail=[f for c in cases for f in c.findall('failure')]
 assertions=sum('AssertionError' in f.attrib.get('type','') or f.attrib.get('message','').startswith('AssertionError:') or (f.text or '').rstrip().splitlines()[-1].endswith(': AssertionError') for f in fail)
 return {'exit':process.returncode,'cases':len(cases),'assertion_failures':assertions,'failures':len(fail),'errors':sum(bool(c.findall('error')) for c in cases),'skips':sum(bool(c.findall('skipped')) for c in cases),'audit_violations':len(json.loads((out/(label+'-audit.json')).read_text())['forbidden_events'])}
try:
 files=sorted({row[3] for row in variants.values()});control=run('positive-control',files)
 assert control['exit']==0 and control['errors']==control['skips']==control['audit_violations']==0,control
 for label,(path,old,new,target) in variants.items():
  text=originals[path].decode();assert text.count(old)==1,(label,text.count(old));changed=text.replace(old,new).encode();(root/path).write_bytes(changed)
  try:
   result=run(label,[target]);result.update(case=label,path=path,mutated_sha256=hashlib.sha256(changed).hexdigest());results.append(result)
   assert result['exit']==1 and result['assertion_failures']>0 and result['errors']==result['skips']==result['audit_violations']==0,result
  finally:(root/path).write_bytes(originals[path])
 restored=run('restored-control',files);assert restored['exit']==0 and restored['errors']==restored['skips']==restored['audit_violations']==0,restored
finally:
 for path,body in originals.items():(root/path).write_bytes(body)
 (out/'receipt.json').write_text(json.dumps({'schema':'van.supplemental-source-faults/1','not_canonical_374':True,'positive_control':locals().get('control'),'restored_control':locals().get('restored'),'cases':results,'source_restored':all((root/p).read_bytes()==b for p,b in originals.items()),'source_sha256':{p:hashlib.sha256(b).hexdigest() for p,b in originals.items()}},indent=2)+'\n')
print(json.dumps({'caught':len(results),'source_restored':True}))
