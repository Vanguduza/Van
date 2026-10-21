"""Preserve full-run truth and requalify its sole changed static Android input."""
from pathlib import Path
import hashlib,json,shutil,xml.etree.ElementTree as ET
ROOT=Path('/workspace/Van');WORK=Path('/workspace/van-audit');OUT=ROOT/'docs/audit/validation'
STEM='backend-expansion-frozen-final-2026-10-08-r2'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def load(p):return json.loads(p.read_text())
def passing_counts(path):
    suites=list(ET.parse(path).iter('testsuite'))
    c={k:sum(int(s.attrib.get(k,0)) for s in suites) for k in ('tests','failures','errors','skipped')}
    assert c['failures']==c['errors']==0,c
    c['passed']=c['tests']-c['skipped'];return c
inputs=load(WORK/(STEM+'-inputs.json'))
result=load(WORK/(STEM+'-result.json'))
assert result['exit_code']==0
changed=sorted(p for p,h in inputs['files'].items() if not(ROOT/p).is_file() or sha(ROOT/p)!=h)
assert changed==['android/app/src/main/java/com/dial/van/browser/BrowserPhoneActions.kt'],changed
assert result['changed_inputs']==changed
archived=OUT/'van-production-source-freeze-before-android-recovery-encryption-2026-10-08.json'
assert inputs['production_manifest_sha256']==sha(archived)
current=OUT/'van-production-source-freeze-2026-10-08.json'
f=load(current)
assert all(sha(ROOT/p)==h for p,h in f['files'].items())
# The full test input already hashed both test modules. The new production
# manifest was captured before the rerun and includes every Android source.
selection=['backend/tests/test_account_approval_contract.py','backend/tests/test_owner_status_kotlin_contract.py']
assert all(sha(ROOT/p)==inputs['files'][p] for p in selection)
static_xml=WORK/'backend-android-static-requalified-2026-10-08.xml'
static_log=WORK/'backend-android-static-requalified-2026-10-08.log'
static=passing_counts(static_xml);assert static['passed']==16 and static['skipped']==0
for p in (static_xml,static_log):shutil.copy2(p,OUT/p.name)
doc={'schema_version':1,'status':'CURRENT_BACKEND_COMPONENT_AND_ANDROID_SOURCE_CONTRACT_PASS',
    'full_suite_counts':passing_counts(WORK/(STEM+'.xml')),
    'full_junit_sha256':sha(WORK/(STEM+'.xml')),
    'original_full_runner_receipt':STEM+'-result.json',
    'original_whole_input_stability':result['source_unchanged_during_test'],
    'original_production_manifest_sha256':inputs['production_manifest_sha256'],
    'final_production_manifest_sha256':sha(current),'changed_global_inputs':changed,
    'backend_runtime_and_remaining_full_test_inputs_changed':[],
    'unchanged_full_inputs_verified':len(inputs['files'])-len(changed),
    'affected_static_source_contract_selection':selection,'static_contract_rerun_counts':static,
    'static_contract_junit':str((OUT/static_xml.name).relative_to(ROOT)),
    'static_contract_junit_sha256':sha(static_xml),
    'static_contract_log':str((OUT/static_log.name).relative_to(ROOT)),
    'static_contract_log_sha256':sha(static_log),
    'scope':'Full backend runtime/tests retained exact bytes. The sole concurrent change was Android browser recovery encryption. Both backend test modules that read Android source were rerun against the final frozen Android source (16 passing overlapping cases); these are not added to the full-suite total. The original broad runner correctly retains whole-input stability false.',
    'physical_tests_executed':0,'production_deployed':False}
p=OUT/'backend-component-requalification-2026-10-08.json';p.write_text(json.dumps(doc,indent=2)+'\n')
print(json.dumps({'receipt':str(p),'sha256':sha(p),'full_counts':doc['full_suite_counts'],'overlapping_static_cases':16}))
