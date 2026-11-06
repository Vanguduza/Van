from pathlib import Path
import json,shutil,hashlib,datetime,xml.etree.ElementTree as ET
r=Path('/workspace/van-review-2026-10-18/publish');base=r/'docs/rebuild/rev118';out=base/'ci/forecast_runtime_20261026'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
pg=Path('/workspace/van-ml004-pg-final-20261026');pgr=json.loads((pg/'receipt.json').read_text())
assert pgr['exit']==0 and pgr['cleaned'] and json.loads((pg/'storage-audit.json').read_text())['forbidden_events']==[]
xml=ET.parse(pg/'full-trading.xml');cases=list(xml.iter('testcase'))
assert len(cases)==116 and all(not any(c.findall(t)) for c in cases for t in ('failure','error','skipped'))
diffs=[p for p,digest in pgr['source_sha256'].items() if sha(r/p)!=digest]
assert diffs==['trading/tests/test_forecast_worker_policy.py'],diffs
fault=Path('/workspace/van-ml004-supplemental-faults-20261026');f=json.loads((fault/'receipt.json').read_text())
assert f['source_restored'] and len(f['cases'])==8 and all(sha(r/p)==digest for p,digest in f['control_sha256'].items())
for src,name in [(pg,'postgres-final'),(fault,'supplemental-faults')]:shutil.copytree(src,out/name)
for p in Path('/workspace').glob('van-ml004*20261026*'):
 if p.is_file() and p.suffix in {'.py','.log','.xml','.json'}:shutil.copyfile(p,out/p.name)
# Reconstruct the exact earlier executed controller from the recorded bounded changes,
# and require its original execution digest before saving it as such.
p=r/'tools/rebuild/run_forecast_runtime_smoke.py';s=p.read_text()
start=s.index('        finally:\n            try:\n                if self.created:');end=s.index('\n\ndef run(',start)
old="""        finally:
            if self.created:
                current=self.inspect()
                if current is not None:self.call(['rm','--force',self.name],timeout=180)
                self.receipt['removed']=self.inspect() is None
            (self.output.parent/(self.role.lower()+'-supervisor.json')).write_text(json.dumps(self.receipt,indent=2)+'\\n')
"""
s=s[:start]+old+s[end:]
s=s.replace('        require_completed_worker(research.receipt)\n','').replace('        require_completed_worker(inference.receipt)\n','').replace('        require_unchanged_snapshot(snapshot,hashes)\n','',1)
start=s.index('        try:\n            require_unchanged_snapshot(snapshot,hashes)');end=s.index('        adopted=[]',start)
s=s[:start]+"        receipt['source_snapshot_unchanged']=all(hashlib.sha256((snapshot/path).read_bytes()).hexdigest()==digest for path,digest in hashes.items())\n"+s[end:]
assert hashlib.sha256(s.encode()).hexdigest()=='76a66fe42df34c3c1d68c89e99ee256dacb62cff212324c0381ff1cd264a987d'
(out/'executed-r2-controller.reconstructed.py').write_text(s)
r2=json.loads((out/'curated-r2/receipt.json').read_text())
assert r2['status']=='SOURCE_FIXTURE_RESEARCH_AND_COLD_INFERENCE_PASS_NOT_ADMISSION'
for p,digest in r2['source_sha256'].items():assert sha(r/'trading/vati_forecast_worker'/p)==digest
source_paths=[r/'trading/vati/__main__.py',r/'trading/vati/core/model_boundary.py',r/'tools/rebuild/run_forecast_runtime_smoke.py',r/'.github/workflows/van-forecast-runtime-source.yml']
source_paths+=list((r/'trading/vati_forecast_worker').rglob('*'))
source_paths+=[r/'trading/tests'/n for n in ['test_forecast_fixture_artifacts.py','test_forecast_runtime_supervisor.py','test_forecast_worker_policy.py','test_ml_runtime_boundary.py']]
source={str(p.relative_to(r)):sha(p) for p in source_paths if p.is_file() and '__pycache__' not in p.parts}
receipt={'schema':'van.rebuild.forecast-runtime-source/1','status':'SOURCE_TESTED_COMPONENT_NOT_UNIT_ACCEPTANCE','base_head':pgr['base_head'],'updated_at_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'unit':'VAN-ML-PKT-004','unit_status':'IN_PROGRESS','acceptance':'NOT_ISSUED','source_sha256':source,'evidence':'ci/forecast_runtime_20261026','actual_research':{'cases':6,'unexecuted':0,'data_environment':'FIXTURE','economic_evidence':False,'execution_authority':False,'locked_distributions':232,'image_id':r2['image_id'],'controller_sha256':r2['controller_sha256'],'model_runtime_sources_match_current':True,'controller_copy_provenance':'Reconstructed by reversing recorded later cleanup/tamper changes;exact original SHA-256 verified'},'cold_inference':{'model_rows':{'qlib_lightgbm':10,'xgboost':10,'neuralforecast':2},'max_abs_error':0,'training_executed':False,'distinct_containers':True,'independently_absent':True},'tests':{'pre_change_t0':'9 actual serve import-boundary failures;fake model packages reveal import side effects,not upstream model qualification','postgres':'116 passes/0skips/audit0;pytestexit0;owned pinned isolated PostgreSQL removed;exact then-current source+test digests recorded','subsequent_test_only_change':{'path':diffs[0],'description':'4 architecture/interpreter refusals now first pin all other platform fields;runtime sources unchanged;latest49control cases pass after restoration'},'latest_controls':f['restored_control'],'supplemental_faults':{'caught':8,'setup_errors':0,'skips':0,'audit_violations':0,'exact_source_restoration':True,'not_canonical_374':True},'earlier_selection':'107pass/2PGskip/3PGdeselected retained;subsequent full116PG result executes those cases'},'attempts_retained':['Initial30s container-creation client timeout;original stopped identity reconciled once','Actual LightGBM missing-libgomp import failure;fixed by pinned Torch bundled OpenMP initialization','Prototype all6 actual upstream fixture cases pass','Curated R1 aggregateFAILED_OR_INCOMPLETE on inference creation;later original container inferencePASS separately;original failure preserved','Curated R2 complete6research+3coldmodel parityPASS;later controller cleanup/tamper guards separately tested'],'source_build':'Active Docker recipe not locally built;fresh hosted exact-commit build pending,including Gym wheel hash reproducibility;build-only env removed from runtime rather than weakening minimal environment','remaining':['Canonical prerequisites BE001/002/003/PRE003 and independent unit acceptance unchanged','Native authorized host/bootstrap/architecture/capacity/T0 noninterference and complete parser qualification','Granted real research jobs,dataset entitlements and production artifact lifecycle','All subsequent forecast/research units,whole backend,Android and native owner/device acceptance'],'published_previous_head':'receipts/HOSTED_SOURCE_1f4ecbf7.json;17publicjobsPASS/two unwaived mandatoryfailures;does not qualify this later ML source'}
(base/'receipts/FORECAST_RUNTIME_SOURCE_20261026.json').write_text(json.dumps(receipt,indent=2)+'\n')
print('native116PG/49currentcontrols/8faults;runtime source hashes and original controller reconstruction verified')
