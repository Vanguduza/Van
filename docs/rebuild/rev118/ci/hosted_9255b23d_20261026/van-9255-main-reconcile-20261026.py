from pathlib import Path
from collections import Counter
import json,hashlib,re,sys,subprocess,xml.etree.ElementTree as E
repo=Path('/workspace/van-review-2026-10-18/publish');head='9255b23d07ce976fa48c2f2e452b70113e6e6458';merge='cb9c7f2f9ade8e50bc8b21843cae2189b298dd21'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def cases(p):
 cs=list(E.parse(p).getroot().iter('testcase'));return {'passed':sum(all(c.find(k) is None for k in ('failure','error','skipped')) for c in cs),'skips':sum(c.find('skipped') is not None for c in cs),'failures':sum(c.find('failure') is not None for c in cs),'errors':sum(c.find('error') is not None for c in cs)}
r=Path('/workspace/van-9255b23d-hosted');meta=json.loads((r/'run-and-jobs-metadata.json').read_text())
assert next(x for x in meta['runs'] if x['id']==40411152887)['conclusion']=='failure'
junit={str(p.relative_to(r)):cases(p) for p in r.rglob('*.xml')};assert all(v['failures']==v['errors']==0 for v in junit.values())
assert junit['van-postgres-ledger-report/trading-source-report.xml']==dict(passed=4125,skips=1,failures=0,errors=0)
assert junit['van-postgres-ledger-report/voice-source-report.xml']==dict(passed=117,skips=0,failures=0,errors=0)
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
assert sum(j['conclusion']=='success' for j in meta['jobs'])==17
report={'source_head':head,'tested_merge':merge,'tree_comparison':'GitHub ahead1/behind0/files[]','run_id':40411152887,'status':'TERMINAL_FAILURE_MANDATORY_PREREQUISITES_UNWAIVED','public_jobs_success':sum(j['conclusion']=='success' for j in meta['jobs']),'mandatory_unwaived_failures':['missing private DDS deploy key','absent trusted-main checker'],'postgres_job':'SUCCESS;actual4125trading/1privateDDSskip,26Postgres,117voice;allreportcasesreconciled','junit':junit,'android_emulator':android,'canonical_mutations':{'actual_reports':len(list(r.rglob('mutation-report.txt'))),'caught_exactly_once':sum(actual.values()),'edits':383,'survivors':0,'unexecuted':0},'actual_verified_archives':len(json.loads((r/'download-receipts.json').read_text())),'native_or_unit_acceptance':False,'qualification':'Published9255 source only;not later HTTP or aggregation source'}
(r/'reconciliation.json').write_text(json.dumps(report,indent=2)+'\n')

print(json.dumps({k:v for k,v in report.items() if k not in ('junit',)}))
