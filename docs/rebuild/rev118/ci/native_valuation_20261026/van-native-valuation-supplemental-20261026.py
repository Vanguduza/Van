from pathlib import Path
import os,subprocess,json,hashlib,xml.etree.ElementTree as ET
root=Path('/workspace/van-review-2026-10-18/publish');out=Path('/workspace/van-native-valuation-supplemental-20261026');out.mkdir(exist_ok=False)
mutants=[('equity-is-not-cash', 'trading/vati/funding/valuation.py', 'net=_money(mark.net_equity,mark)', 'net=_money(mark.balance,mark)', 'trading/tests/test_native_valuation.py::test_original_exact_native_value_and_optional_credit_keep_distinct_bases'), ('native-scope', 'trading/vati/funding/valuation.py', "if valuation.body()['scope_hash']!=scope_hash:", 'if False:', 'trading/tests/test_native_valuation.py::test_source_reference_and_native_scope_cannot_be_replaced_by_matching_alias'), ('caller-transaction', 'trading/vati/funding/valuation.py', 'FinancialMovementBook(ledger)._transaction()', 'pass', 'trading/tests/test_native_valuation.py::test_source_reference_and_native_scope_cannot_be_replaced_by_matching_alias'), ('source-clock', 'trading/vati/funding/valuation.py', 'or source.event_time_ms>source.received_time_ms', 'or False', 'trading/tests/test_native_valuation.py::test_sealed_foreign_or_ill_typed_snapshot_cannot_be_a_native_valuation'), ('verified-boolean', 'trading/vati/funding/valuation.py', "p.get('verified') is not True", "not p.get('verified')", 'trading/tests/test_native_valuation.py::test_sealed_foreign_or_ill_typed_snapshot_cannot_be_a_native_valuation'), ('complete-readback', 'trading/vati/funding/valuation.py', 'if count!=expected:', 'if False:', 'trading/tests/test_native_valuation.py::test_incomplete_independent_source_readback_cannot_claim_a_complete_original'), ('period-render-context', 'trading/vati/funding/reconciliation.py', "performance['worst_observed_drawdown']=_render(worst)", "performance['worst_observed_drawdown']=str(Decimal(worst.numerator)/Decimal(worst.denominator))", 'trading/tests/test_native_valuation.py::test_actual_period_drawdown_does_not_inherit_unrelated_decimal_rounding_or_traps')]
env=dict(os.environ,PYTHONDONTWRITEBYTECODE='1',PYTHONPATH='backend:backend/tests:trading:trading/tests:.');env.pop('VATI_TEST_PG_DSN',None);env.pop('VATI_TEST_PG_ISOLATED_FIXTURE',None)
controls=list(dict.fromkeys(m[4] for m in mutants))
def run(name,targets):
 with (out/(name+'.log')).open('wb') as log:
  p=subprocess.run(['/workspace/van-backend-venv-20261025/bin/python','tools/rebuild/source_storage_audit.py','--report',str(out/(name+'-audit.json')),*targets,'-k','not postgres','--junitxml='+str(out/(name+'.xml')),'-q'],cwd=root,env=env,stdout=log,stderr=subprocess.STDOUT,timeout=90)
 cases=list(ET.parse(out/(name+'.xml')).getroot().iter('testcase'));result={'exit':p.returncode,'tests':len(cases),'failures':sum(c.find('failure') is not None for c in cases),'errors':sum(c.find('error') is not None for c in cases),'skips':sum(c.find('skipped') is not None for c in cases),'audit':json.loads((out/(name+'-audit.json')).read_text())['forbidden_events']}
 return result
receipt={'scope':'SUPPLEMENTAL_SOURCE_ASSERTION_FAULTS_NOT_CANONICAL374','positive':run('positive',controls),'faults':[]}
assert receipt['positive']['exit']==0
for name,path,before,after,target in mutants:
 p=root/path;data=p.read_bytes();text=data.decode();assert text.count(before)==1,(name,text.count(before))
 try:
  p.write_text(text.replace(before,after));r=run(name,[target]);r.update(name=name,path=path,original_sha256=hashlib.sha256(data).hexdigest())
  assert r['exit']==1 and r['failures']>0 and r['errors']==r['skips']==0 and not r['audit'],r
  receipt['faults'].append(r)
 finally:
  p.write_bytes(data);assert p.read_bytes()==data
receipt['restored']=run('restored',controls);assert receipt['restored']['exit']==0
receipt['all_restored']=all(hashlib.sha256((root/r['path']).read_bytes()).hexdigest()==r['original_sha256'] for r in receipt['faults'])
assert receipt['all_restored'];(out/'receipt.json').write_text(json.dumps(receipt,indent=2)+'\n');print(json.dumps(receipt))
