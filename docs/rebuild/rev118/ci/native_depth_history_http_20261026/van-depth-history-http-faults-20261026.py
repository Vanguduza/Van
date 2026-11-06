from pathlib import Path
import os,json,subprocess,hashlib,xml.etree.ElementTree as E
root=Path('/workspace/van-review-2026-10-18/publish');out=Path('/workspace/van-depth-history-http-supplemental-20261026');out.mkdir(exist_ok=False)
python='/workspace/van-backend-venv-20261025/bin/python';env=dict(os.environ,PYTHONPATH='backend:backend/tests:trading:trading/tests:.')
path=root/'backend/van_gateway/trading/native_depth_history.py';original=path.read_bytes()
(out/'source-original.py').write_bytes(original)
prefix='backend/tests/test_native_depth_history.py::'
scope=prefix+'test_another_native_scope_cannot_reuse_a_saved_ladder'
budget=prefix+'test_storage_integrity_and_read_capacity_refuse_without_changing_history[budget]'
cancel=prefix+'test_cancelled_call_keeps_its_original_worker_slot_until_the_read_finishes'
positive=[prefix+'test_registered_owner_route_reads_original_scope_and_preserves_capture_policy',scope,budget,cancel]
def run(name,selection):
    with (out/(name+'.log')).open('wb') as log:
        result=subprocess.run([python,'tools/rebuild/source_storage_audit.py','--report',str(out/(name+'-audit.json')),
            *selection,'--junitxml='+str(out/(name+'.xml')),'--maxfail=1','-q'],cwd=root,env=env,stdout=log,stderr=subprocess.STDOUT,timeout=180)
    cs=list(E.parse(out/(name+'.xml')).getroot().iter('testcase'))
    values={'exit':result.returncode,'cases':len(cs),'failures':sum(c.find('failure') is not None for c in cs),
            'errors':sum(c.find('error') is not None for c in cs),'skips':sum(c.find('skipped') is not None for c in cs),
            'failure_text':[c.find('failure').text or '' for c in cs if c.find('failure') is not None]}
    assert not json.loads((out/(name+'-audit.json')).read_text())['forbidden_events']
    return values
faults=[('foreign-account-scope','native_account_id=native_account_id,native_symbol_id=native_symbol_id)',
         'native_account_id=123,native_symbol_id=native_symbol_id)',[scope]),
        ('discard-provisioned-byte-budget','NativeDepthArchive(root,max_history_bytes=max_history_bytes)',
         'NativeDepthArchive(root,max_history_bytes=None)',[budget]),
        ('cancel-reopens-native-read-slot','return await asyncio.shield(task)','return await task',[cancel])]
receipt={'qualification':'Supplemental HTTP/source control assertions;not canonical374 or native/unitacceptance','positive':None,'faults':[],'all_restored':False}
try:
    receipt['positive']=run('positive',positive);assert receipt['positive']=={'exit':0,'cases':6,'failures':0,'errors':0,'skips':0,'failure_text':[]}
    for name,before,after,selection in faults:
        text=original.decode();assert text.count(before)==1
        try:
            path.write_text(text.replace(before,after,1));result=run(name,selection)
            assert result['exit']==1 and result['failures'] and result['errors']==result['skips']==0
            assert any('assert' in t.lower() for t in result['failure_text'])
            receipt['faults'].append({'name':name,**result})
        finally:path.write_bytes(original)
    receipt['restored']=run('restored',positive);assert receipt['restored']==receipt['positive']
finally:
    path.write_bytes(original);receipt['all_restored']=path.read_bytes()==original
    receipt['source_sha256']=hashlib.sha256(original).hexdigest();(out/'receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
assert receipt['all_restored'] and len(receipt['faults'])==3
print(json.dumps({'positive':6,'faults_caught':3,'restored':6,'all_restored':True}))
