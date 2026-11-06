from pathlib import Path
import os,json,subprocess,hashlib,xml.etree.ElementTree as E
root=Path('/workspace/van-review-2026-10-18/publish');out=Path('/workspace/van-depth-supplemental-20261026');out.mkdir(exist_ok=False)
python='/workspace/van-backend-venv-20261025/bin/python'
env=dict(os.environ,PYTHONPATH='backend:trading:trading/tests:.')
depth='trading/vati/execution/ctrader/depth.py';adapter='trading/vati/execution/ctrader/adapter.py'
originals={p:(root/p).read_bytes() for p in (depth,adapter)}
def run(name):
    with (out/(name+'.log')).open('wb') as log:
        p=subprocess.run([python,'tools/rebuild/source_storage_audit.py','--report',str(out/(name+'-audit.json')),
            'trading/tests/test_ctrader_native_depth.py','--junitxml='+str(out/(name+'.xml')),'--maxfail=1','-q'],cwd=root,env=env,stdout=log,stderr=subprocess.STDOUT,timeout=120)
    cases=list(E.parse(out/(name+'.xml')).getroot().iter('testcase'))
    result={'exit':p.returncode,'cases':len(cases),'failures':sum(c.find('failure') is not None for c in cases),
            'errors':sum(c.find('error') is not None for c in cases),'skips':sum(c.find('skipped') is not None for c in cases)}
    assert not json.loads((out/(name+'-audit.json')).read_text())['forbidden_events']
    result['failure_messages']=[c.find('failure').get('message','') for c in cases if c.find('failure') is not None]
    return result
faults=[('foreign-account',depth,"!=scope['native_account_id']","!=scope['native_account_id'] and False"),
        ('book-capacity',depth,'if len(next_quotes)>self.max_quotes:','if False:'),
        ('rejuvenate-on-noop',depth,"age=evaluated-row['changed']","age=evaluated-row['processed']"),
        ('clear-error-on-next-delta',depth,"if row['error'] is not None:return  # Only a fresh native context recovers lost continuity.","row['error']=None"),
        ('retry-retired-control',adapter,'if key in self._depth_retired:','if False:')]
receipt={'qualification':'Supplemental source assertion controls; not canonical374 or native acceptance','positive':None,'faults':[],'all_restored':False}
try:
    receipt['positive']=run('positive');assert receipt['positive']=={'exit':0,'cases':31,'failures':0,'errors':0,'skips':0,'failure_messages':[]}
    for name,path,before,after in faults:
        text=originals[path].decode();assert text.count(before)==1
        try:
            (root/path).write_text(text.replace(before,after,1));result=run(name)
            assert result['exit']==1 and result['failures'] and result['errors']==result['skips']==0
            assert any('assert ' in m.lower() or 'AssertionError' in m or 'Regex' in m for m in result['failure_messages'])
            receipt['faults'].append({'name':name,**result})
        finally:(root/path).write_bytes(originals[path])
    receipt['restored']=run('restored');assert receipt['restored']==receipt['positive']
finally:
    for p,data in originals.items():(root/p).write_bytes(data)
    receipt['all_restored']=all((root/p).read_bytes()==data for p,data in originals.items())
    receipt['original_sha256']={p:hashlib.sha256(data).hexdigest() for p,data in originals.items()}
    (out/'receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
assert receipt['all_restored'] and len(receipt['faults'])==5
print(json.dumps({'positive':receipt['positive']['cases'],'faults_caught':len(receipt['faults']),'restored':receipt['restored']['cases'],'all_restored':True}))
