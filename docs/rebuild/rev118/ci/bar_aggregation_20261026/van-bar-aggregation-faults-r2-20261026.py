from pathlib import Path
import os,json,subprocess,hashlib,xml.etree.ElementTree as E
root=Path('/workspace/van-review-2026-10-18/publish');out=Path('/workspace/van-bar-aggregation-supplemental-r2-20261026');out.mkdir(exist_ok=False)
python='/workspace/van-backend-venv-20261025/bin/python';env=dict(os.environ,PYTHONPATH='backend:backend/tests:trading:trading/tests:.')
path=root/'trading/vati/market_data/bars.py';original=path.read_bytes()
(out/'source-original.py').write_bytes(original)
prefix='trading/tests/test_bar_aggregation_boundaries.py::'
positive=['trading/tests/test_bar_aggregation_boundaries.py']
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
faults=[
 ('accept-regressed-clock','t.ts_ms < self._last_ts','False',[prefix+'test_out_of_order_tick_refuses_before_publishing_or_changing_a_bar']),
 ('ambient-arithmetic','localcontext(native_decimal_context())','localcontext()',[prefix+'test_original_tick_aggregation_is_independent_of_caller_context']),
 ('mutate-current-before-arithmetic','dict(previous)','previous',[prefix+'test_failed_arithmetic_neither_flushes_nor_partially_updates_original_state']),
 ('flush-before-validating','        if not isinstance(t, Tick)', '        if self._cur is not None and t.ts_ms != self._last_ts:self._flush()\n        if not isinstance(t, Tick)',[prefix+'test_invalid_new_interval_cannot_flush_the_current_original'])]
receipt={'qualification':'Supplemental aggregation assertion faults;not canonical374 or native/unit acceptance','positive':None,'faults':[],'all_restored':False}
try:
 receipt['positive']=run('positive',positive);assert receipt['positive']['exit']==0 and receipt['positive']['cases']==26 and receipt['positive']['skips']==0
 for name,before,after,selection in faults:
  try:
   source=original.decode();assert before in source
   path.write_text(source.replace(before,after));result=run(name,selection)
   assert result['exit']==1 and result['failures'] and result['errors']==result['skips']==0
   assert any('AssertionError' in t or 'DID NOT RAISE' in t for t in result['failure_text'])
   receipt['faults'].append({'name':name,**result})
  finally:path.write_bytes(original)
 receipt['restored']=run('restored',positive);assert receipt['restored']==receipt['positive']
finally:
 path.write_bytes(original);receipt['all_restored']=path.read_bytes()==original
 receipt['source_sha256']=hashlib.sha256(original).hexdigest();(out/'receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
assert len(receipt['faults'])==4 and receipt['all_restored']
print(json.dumps({'faults':4,'positive':26,'restored':26,'all_restored':True}))
