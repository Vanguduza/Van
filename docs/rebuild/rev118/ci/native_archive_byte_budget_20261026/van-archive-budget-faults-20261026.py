from pathlib import Path
import os,json,subprocess,hashlib,xml.etree.ElementTree as E
root=Path('/workspace/van-review-2026-10-18/publish');out=Path('/workspace/van-archive-budget-supplemental-20261026');out.mkdir(exist_ok=False)
python='/workspace/van-backend-venv-20261025/bin/python';env=dict(os.environ,PYTHONPATH='backend:trading:trading/tests:.')
path=root/'trading/vati/market_data/native_archive.py';original=path.read_bytes()
def run(name):
    with (out/(name+'.log')).open('wb') as log:
        result=subprocess.run([python,'tools/rebuild/source_storage_audit.py','--report',str(out/(name+'-audit.json')),
            'trading/tests/test_native_archive_read_budget.py','--junitxml='+str(out/(name+'.xml')),'--maxfail=1','-q'],cwd=root,env=env,stdout=log,stderr=subprocess.STDOUT,timeout=120)
    cs=list(E.parse(out/(name+'.xml')).getroot().iter('testcase'))
    values={'exit':result.returncode,'cases':len(cs),'failures':sum(c.find('failure') is not None for c in cs),
            'errors':sum(c.find('error') is not None for c in cs),'skips':sum(c.find('skipped') is not None for c in cs),
            'failure_messages':[c.find('failure').get('message','') for c in cs if c.find('failure') is not None]}
    assert not json.loads((out/(name+'-audit.json')).read_text())['forbidden_events']
    return values
faults=[('unbounded-actual-read',"with path.open('rb') as source:blob=source.read(bound+1)",'blob=path.read_bytes()',1),
        ('reset-cumulative-budget','remaining=None if self.max_history_bytes is None else self.max_history_bytes-used','remaining=None',2),
        ('postcommit-only-capacity','self._require_history_capacity(prospective,self._head_blob(scope,timeframe,prospective))','pass',1),
        ('unbounded-index-repair','self._require_history_capacity(rows,blob)','pass',1)]
receipt={'qualification':'Supplemental source assertions; not canonical374 or host resource qualification','positive':None,'faults':[],'all_restored':False}
try:
    receipt['positive']=run('positive');assert receipt['positive']=={'exit':0,'cases':11,'failures':0,'errors':0,'skips':0,'failure_messages':[]}
    for name,before,after,count in faults:
        text=original.decode();assert text.count(before)==count
        try:
            path.write_text(text.replace(before,after));result=run(name)
            assert result['exit']==1 and result['failures'] and result['errors']==result['skips']==0
            assert any('assert' in m.lower() or 'DID NOT RAISE' in m for m in result['failure_messages'])
            receipt['faults'].append({'name':name,**result})
        finally:path.write_bytes(original)
    receipt['restored']=run('restored');assert receipt['restored']==receipt['positive']
finally:
    path.write_bytes(original);receipt['all_restored']=path.read_bytes()==original
    receipt['source_sha256']=hashlib.sha256(original).hexdigest();(out/'receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
assert receipt['all_restored'] and len(receipt['faults'])==4
print(json.dumps({'positive':11,'faults_caught':4,'restored':11,'all_restored':True}))
