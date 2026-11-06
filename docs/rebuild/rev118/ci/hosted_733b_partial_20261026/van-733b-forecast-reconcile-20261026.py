from pathlib import Path
import json,hashlib,subprocess,xml.etree.ElementTree as E
repo=Path('/workspace/van-review-2026-10-18/publish');head='733b7ac93e403048f2807df80f56b7038a4f5d48';merge='96cd9f894123a5aab80b49ec6affac47ada89633'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def cases(p):
 cs=list(E.parse(p).getroot().iter('testcase'));return {'passed':sum(all(c.find(k) is None for k in ('failure','error','skipped')) for c in cs),'skips':sum(c.find('skipped') is not None for c in cs),'failures':sum(c.find('failure') is not None for c in cs),'errors':sum(c.find('error') is not None for c in cs)}
r=Path('/workspace/van-733b7ac9-hosted');a=r/'van-forecast-runtime-source-report';runtime=a/'runtime';native=r/'van-native-source-parquet-report';receipt=json.loads((runtime/'receipt.json').read_text());research=json.loads((runtime/'research/train-probe-receipt.json').read_text());inference=json.loads((runtime/'inference/inference-receipt.json').read_text());tree=json.loads((r/'run-and-jobs-metadata.json').read_text())['tree_comparison']
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
report={'source_head':head,'tested_merge':merge,'tree_comparison':'GitHub ahead1/behind0/files[]','run':40394743715,'workflow_status':'SUCCESS','native_parquet_passed':114,'native_parquet_skips':0,'native_parquet_audit':0,'six_actual_upstream_cases':True,'three_separate_cold_models_zero_difference':True,'232_versions_checked_each_process':True,'actual_kernel_limits_checked':True,'both_distinct_workers_removed':True,'source_controller_report_hashes_match':True,'image_id':receipt['image_id'],'not_unit_acceptance':True,'qualification':'Published733b source fixtures only;later arithmetic and depth candidates not qualified','file_sha256':{str(p.relative_to(r)):sha(p) for p in sorted(r.rglob('*')) if p.is_file()}}
(r/'independent-reconciliation.json').write_text(json.dumps(report,indent=2)+'\n')

print(json.dumps({k:v for k,v in report.items() if k!='file_sha256'}))
