from pathlib import Path
import os,subprocess,json,hashlib,xml.etree.ElementTree as ET

root=Path('/workspace/van-review-2026-10-18/publish')
out=Path(os.environ['VAN_READ_BOUNDARY_FAULT_OUTPUT']);out.mkdir(exist_ok=False)
assert os.environ.get('VATI_TEST_PG_ISOLATED_FIXTURE')=='1' and os.environ.get('VATI_TEST_PG_DSN')
base='trading/tests/test_funding_committed_reads.py::'
faults=[
 ('period-writer','trading/vati/funding/reconciliation.py','with committed_source_snapshot(ledger):','with ledger.read_snapshot():',base+'test_period_cannot_consume_a_closing_source_from_its_callers_writer','sqlite'),
 ('owner-mt5-writer','trading/vati/funding/runtime.py','with committed_source_snapshot(ledger):return _reported_funding(ledger,event,account_record)','with ledger.read_snapshot():return _reported_funding(ledger,event,account_record)',base+'test_mt5_query_and_owner_snapshot_cannot_escape_the_callers_writer','sqlite'),
 ('risk-mt5-writer','trading/vati/funding/risk_fence.py','with committed_source_snapshot(ledger):','with ledger.read_snapshot():',base+'test_mt5_query_and_owner_snapshot_cannot_escape_the_callers_writer','sqlite'),
 ('sqlite-rollback-cache','trading/vati/core/ledger.py','self._incremental=None','pass',base+'test_incremental_verification_does_not_misreport_corruption_after_owned_writer_rollback','sqlite'),
 ('postgres-rollback-cache','trading/vati/core/ledger_pg.py','self._incremental=None','pass',base+'test_incremental_verification_does_not_misreport_corruption_after_owned_writer_rollback','postgres'),
 ('committed-source-guard','trading/vati/core/ledger.py','if active and not (type(depth) is int and depth>0):','if False:',base+'test_period_cannot_consume_a_closing_source_from_its_callers_writer','postgres'),
]
env=dict(os.environ,PYTHONDONTWRITEBYTECODE='1')
def run(name,target,selection=None):
 command=['/workspace/van-backend-venv-20261025/bin/python','tools/rebuild/source_storage_audit.py','--report',str(out/(name+'-audit.json')),target,'--junitxml='+str(out/(name+'.xml')),'-q']
 if selection:command+=['-k',selection]
 with (out/(name+'.log')).open('wb') as log:
  process=subprocess.run(command,cwd=root,env=env,stdout=log,stderr=subprocess.STDOUT,timeout=90)
 cases=list(ET.parse(out/(name+'.xml')).getroot().iter('testcase'))
 return {'exit':process.returncode,'tests':len(cases),'failures':sum(c.find('failure') is not None for c in cases),'errors':sum(c.find('error') is not None for c in cases),'skips':sum(c.find('skipped') is not None for c in cases),'audit':json.loads((out/(name+'-audit.json')).read_text())['forbidden_events']}
receipt={'scope':'SUPPLEMENTAL_ACTUAL_SQLITE_AND_POSTGRES_SOURCE_FAULTS_NOT_CANONICAL374','positive':run('positive','trading/tests/test_funding_committed_reads.py'),'faults':[]}
assert receipt['positive']['exit']==0 and receipt['positive']['tests']==14 and receipt['positive']['skips']==0
for name,path,old,new,target,selection in faults:
 p=root/path;original=p.read_bytes();source=original.decode();assert source.count(old)==1,(name,source.count(old))
 mutated=source.replace(old,new).encode()
 try:
  p.write_bytes(mutated);result=run(name,target,selection)
  result.update(name=name,path=path,selection=selection,original_sha256=hashlib.sha256(original).hexdigest())
  assert result['exit']==1 and result['tests']>0 and result['failures']>0 and result['errors']==result['skips']==0 and not result['audit'],result
  receipt['faults'].append(result)
 finally:
  assert p.read_bytes() in (original,mutated),'concurrent source change; preserve and reconcile'
  p.write_bytes(original);assert p.read_bytes()==original
receipt['restored']=run('restored','trading/tests/test_funding_committed_reads.py')
assert receipt['restored']['exit']==0 and receipt['restored']['tests']==14 and receipt['restored']['skips']==0
receipt['all_restored']=all(hashlib.sha256((root/f['path']).read_bytes()).hexdigest()==f['original_sha256'] for f in receipt['faults'])
assert receipt['all_restored'];(out/'receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
print(json.dumps({'faults':len(receipt['faults']),'positive':receipt['positive'],'restored':receipt['restored'],'all_restored':receipt['all_restored']}))
