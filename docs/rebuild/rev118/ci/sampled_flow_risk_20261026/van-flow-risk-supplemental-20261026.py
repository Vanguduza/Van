from pathlib import Path
import os,subprocess,json,hashlib,xml.etree.ElementTree as ET
root=Path('/workspace/van-review-2026-10-18/publish');out=Path('/workspace/van-flow-risk-supplemental-20261026');out.mkdir(exist_ok=False)
mutants=[('intermediate-loss', 'trading/vati/funding/flow_risk.py', 'result=unitize(baseline,closing,[*flows,*observations])', 'result=unitize(baseline,closing,flows)', 'trading/tests/test_flow_adjusted_risk.py::test_intermediate_loss_between_external_flows_cannot_disappear_from_drawdown'), ('external-units', 'trading/vati/funding/flow_risk.py', 'result=unitize(baseline,closing,[*flows,*observations])', 'result=unitize(baseline,closing,observations)', 'trading/tests/test_flow_adjusted_risk.py::test_intermediate_loss_between_external_flows_cannot_disappear_from_drawdown'), ('source-identity', 'trading/vati/funding/flow_risk.py', 'if len(set(refs))!=len(refs):', 'if False:', 'trading/tests/test_flow_adjusted_risk.py::test_wrong_scope_identity_dimensions_and_capacity_cannot_be_computed'), ('point-capacity', 'trading/vati/funding/flow_risk.py', 'or len(flows)+len(samples)>MAX_POINTS', 'or False', 'trading/tests/test_flow_adjusted_risk.py::test_wrong_scope_identity_dimensions_and_capacity_cannot_be_computed'), ('float-normalization', 'trading/vati/funding/flow_risk.py', '_number(point.equity)', '_number(Decimal(str(point.equity)))', 'trading/tests/test_flow_adjusted_risk.py::test_a_float_cannot_hide_in_an_equal_redundant_sample'), ('native-qualification', 'trading/vati/funding/flow_risk.py', "'native_source_qualification':'NOT_ISSUED'", "'native_source_qualification':'QUALIFIED'", 'trading/tests/test_flow_adjusted_risk.py::test_intermediate_loss_between_external_flows_cannot_disappear_from_drawdown'), ('runtime-samples', 'trading/vati/funding/reconciliation.py', 'samples=[ValuationSnapshot(source).equity_point() for source in unique.values()]', 'samples=[]', 'trading/tests/test_native_valuation.py::test_actual_period_keeps_intermediate_drawdown_in_the_immutable_calculation')]
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
