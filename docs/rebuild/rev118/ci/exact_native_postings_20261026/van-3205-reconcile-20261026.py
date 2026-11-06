from pathlib import Path
from collections import Counter
import json,hashlib,re,sys,subprocess,xml.etree.ElementTree as E
repo=Path('/workspace/van-review-2026-10-18/publish');head='3205594c907665732e69dcac26852ff28078c48a';merge='8d50404f49304c80e59dd93bcf95a33ad8cb8c3e'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def cases(p):
 cs=list(E.parse(p).getroot().iter('testcase'));return {'passed':sum(all(c.find(k) is None for k in ('failure','error','skipped')) for c in cs),'skips':sum(c.find('skipped') is not None for c in cs),'failures':sum(c.find('failure') is not None for c in cs),'errors':sum(c.find('error') is not None for c in cs)}
r=Path('/workspace/van-3205594c-hosted');meta=json.loads((r/'run-and-jobs-metadata.json').read_text())
assert next(x for x in meta['runs'] if x['id']==40367094242)['conclusion']=='failure'
junit={str(p.relative_to(r)):cases(p) for p in r.rglob('*.xml')};assert all(v['failures']==v['errors']==0 for v in junit.values())
assert junit['van-postgres-ledger-report/trading-source-report.xml']==dict(passed=3828,skips=1,failures=0,errors=0)
assert not list(r.rglob('voice-source-report.xml'))
for p in r.rglob('*audit.json'):assert not json.loads(p.read_text())['forbidden_events']
for p in r.rglob('tested-commit.txt'):assert p.read_text().strip() in {head,merge}
sys.path.insert(0,str(repo/'tools/rebuild'));from mutation_registry import suite_groups,inspect
expected=Counter(m[-1] for _,ms,_,_ in suite_groups() for m in ms)
actual=Counter(line.split(None,1)[1].strip() for p in r.rglob('mutation-report.txt') for line in p.read_text().splitlines() if line.startswith('CAUGHT '))
assert expected==actual and sum(actual.values())==374
assert inspect(suite_groups())['edit_count']==383
html=(r/'van-instrumentation-report/debug/index.html').read_text()
android={key:int(re.search(r'<div class="counter">(\d+)</div>\s*<p>'+label+'</p>',html).group(1)) for key,label in [('tests','tests'),('failures','failures'),('skipped','skipped')]}
assert android==dict(tests=22,failures=0,skipped=4);android['passed']=18
annotations=json.loads((r/'postgres-job-annotations.json').read_text());assert any('35m0s' in a['message'] for a in annotations)
report={'source_head':head,'tested_merge':merge,'tree_comparison':'GitHub ahead1/behind0/files[]','run_id':40367094242,'status':'TERMINAL_FAILURE_WITH_POSTGRES_JOB_CANCELLED35MIN','public_jobs_success':sum(j['conclusion']=='success' for j in meta['jobs']),'mandatory_unwaived_failures':['missing private DDS deploy key','absent trusted-main checker'],'cancelled_job':'postgres-ledger after35minute maximum;full trading JUnit positive3828/1, voice not executed;no jobPASS claim','junit':junit,'android_emulator':android,'canonical_mutations':{'actual_reports':len(list(r.rglob('mutation-report.txt'))),'caught_exactly_once':sum(actual.values()),'edits':383,'survivors':0,'unexecuted':0},'actual_verified_archives':len(json.loads((r/'download-receipts.json').read_text())),'native_or_unit_acceptance':False,'qualification':'Published3205 source only;not later financial movement candidate','logging_finding':'One hosted verbose test result line1048755characters;source collection independently reproduces1048712character nodeID. Short descriptive parameter IDs tested separately;causal sufficiency requires fresh hosted CI.'}
(r/'reconciliation.json').write_text(json.dumps(report,indent=2)+'\n')
r=Path('/workspace/van-forecast-3205594c-source');a=r/'van-forecast-runtime-source-report';runtime=a/'runtime';native=r/'van-native-source-parquet-report';receipt=json.loads((runtime/'receipt.json').read_text());research=json.loads((runtime/'research/train-probe-receipt.json').read_text());inference=json.loads((runtime/'inference/inference-receipt.json').read_text());tree=json.loads((r/'run-and-jobs-metadata.json').read_text())['tree_comparison']
assert tree['ahead_by']==1 and tree['behind_by']==0 and tree['files']==[]
for p in [a/'tested-head.txt',native/'tested-head.txt']:assert p.read_text().strip()==merge
assert cases(native/'report.xml')==dict(passed=114,skips=0,failures=0,errors=0)
assert not json.loads((native/'storage-audit.json').read_text())['forbidden_events']
assert sha(runtime/'research/train-probe-receipt.json')==receipt['research_report_sha256']
assert sha(runtime/'inference/inference-receipt.json')==receipt['inference_report_sha256']
assert receipt['source_snapshot_unchanged'] is True
controller=subprocess.check_output(['git','show',head+':tools/rebuild/run_forecast_runtime_smoke.py'],cwd=repo)
assert hashlib.sha256(controller).hexdigest()==receipt['controller_sha256']
for f,h in receipt['source_sha256'].items():
 assert sha(runtime/'source/vati_forecast_worker'/f)==h
 assert hashlib.sha256(subprocess.check_output(['git','show',head+':trading/vati_forecast_worker/'+f],cwd=repo)).hexdigest()==h
assert len(research['cases'])==6 and all(c['status']=='PASS' for c in research['cases']) and research['unexecuted']==[]
assert inference['model_rows']==dict(qlib_lightgbm=10,xgboost=10,neuralforecast=2)
assert set(inference['max_abs_reload_errors'].values())=={0.0} and inference['training_executed'] is False
for value in [research,inference]:
 assert value['data_environment']=='FIXTURE' and value['execution_authority'] is False and value['economic_evidence'] is False
 assert value['locked_environment']['locked_distribution_count']==232
 assert value['worker_boundary']['observed_cgroup']=={'cpu.max':'200000 100000','memory.max':'6442450944','pids.max':'256'}
 assert value['worker_boundary']['root_read_only'] is value['worker_boundary']['no_new_privileges'] is True
 assert value['worker_boundary']['effective_capabilities']==0
assert receipt['research']['container_id']!=receipt['inference']['container_id']
for role in ['research','inference']:
 d=receipt[role];assert d['removed'] is True and d['exit']==d['container_exit']==0 and d['oom_killed'] is False
 assert d['declared_kernel_configuration']=={'NanoCpus':2000000000,'Memory':6442450944,'PidsLimit':256,'ReadonlyRootfs':True,'NetworkMode':'none','Init':True}
report={'source_head':head,'tested_merge':merge,'tree_comparison':'GitHub ahead1/behind0/files[]','run':40367094028,'workflow_status':'SUCCESS','native_parquet_passed':114,'native_parquet_skips':0,'native_parquet_audit':0,'six_actual_upstream_cases':True,'three_separate_cold_models_zero_difference':True,'232_versions_checked_each_process':True,'actual_kernel_limits_checked':True,'both_distinct_workers_removed':True,'source_controller_report_hashes_match':True,'image_id':receipt['image_id'],'not_unit_acceptance':True,'qualification':'Published3205 source fixtures only;later financial movement candidate not qualified','file_sha256':{str(p.relative_to(r)):sha(p) for p in sorted(r.rglob('*')) if p.is_file()}}
(r/'independent-reconciliation.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps({'main_public_jobs_success':16,'main_overall':'FAILED','trading':3828,'pg':26,'voice':'NOT_EXECUTED','canonical_mutations':374,'forecast':'SUCCESS','native_parquet':114,'CPU_models':6,'cold_models':3}))
