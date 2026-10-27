from pathlib import Path
from collections import Counter
import json,hashlib,sys,subprocess,tempfile,xml.etree.ElementTree as E
repo=Path('/workspace/van-review-2026-10-18/publish');r=Path('/workspace/van-2a1186ee-main-hosted')
head='2a1186ee1199f56c0ae9fce06d13b27f9098d3c3';merge='76184cd978eee3dc558a2778ecb5501f2685546d'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def cases(p):
 cs=list(E.parse(p).getroot().iter('testcase'));return {'passed':sum(all(c.find(k) is None for k in ('failure','error','skipped')) for c in cs),'skips':sum(c.find('skipped') is not None for c in cs),'failures':sum(c.find('failure') is not None for c in cs),'errors':sum(c.find('error') is not None for c in cs)}
meta=json.loads((r/'run-and-jobs-metadata.json').read_text())
assert next(x for x in meta['runs'] if x['id']==40421043580)['conclusion']=='failure'
public=next(x for x in meta['jobs'] if x['id']==121915259747)
assert public['conclusion']=='cancelled'
assert all(x['conclusion']=='success' for x in public['steps'] if x['number']<=12)
assert sum(x['conclusion']=='success' for x in meta['jobs'])==16
assert sum(x['conclusion']=='failure' for x in meta['jobs'])==2
junit={str(p.relative_to(r)):cases(p) for p in r.rglob('*.xml')}
assert all(v['failures']==v['errors']==0 for v in junit.values())
for filename,passed,skips in [('van-postgres-ledger-report/trading-source-report.xml',4157,1),('van-postgres-ledger-report/voice-source-report.xml',117,0),('van-backend-public-source/gateway-report.xml',5807,7),('van-backend-public-source/media-report.xml',198,0)]:
 assert junit[filename]==dict(passed=passed,skips=skips,failures=0,errors=0)
for p in r.rglob('*audit.json'):assert not json.loads(p.read_text())['forbidden_events']
for p in r.rglob('tested-commit.txt'):assert p.read_text().strip() in {head,merge}
sys.path.insert(0,str(repo/'tools/rebuild'));from mutation_registry import suite_groups,inspect
expected=Counter(m[-1] for _,ms,_,_ in suite_groups() for m in ms)
actual=Counter(line.split(None,1)[1].strip() for p in r.rglob('mutation-report.txt') for line in p.read_text().splitlines() if line.startswith('CAUGHT '))
assert expected==actual and sum(actual.values())==374 and inspect(suite_groups())['edit_count']==383
summary=json.loads((r/'van-backend-public-source/summary.json').read_text())
assert summary['status']=='PUBLIC_SOURCE_SUBSET_PASS' and summary['passed']==6005
manifest=json.loads((r/'van-backend-public-source/selection.json').read_text())
controller=repo/'tools/rebuild/backend_public_source.py'
assert subprocess.check_output(['git','show',head+':tools/rebuild/backend_public_source.py'],cwd=repo)==controller.read_bytes()
from backend_public_source import verify
with tempfile.TemporaryDirectory(prefix='van-2a-public-source-verification-') as temp:
 root=Path(temp)
 with subprocess.Popen(['git','cat-file','--batch'],cwd=repo,stdin=subprocess.PIPE,stdout=subprocess.PIPE) as process:
  for row in manifest['selected']+manifest['separate']:
   process.stdin.write((head+':'+row['path']+'\n').encode());process.stdin.flush()
   header=process.stdout.readline().decode().split();assert header[1]=='blob'
   original=process.stdout.read(int(header[2]));assert process.stdout.read(1)==b'\n'
   assert hashlib.sha256(original).hexdigest()==row['sha256']
   dest=root/row['path'];dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(original)
  process.stdin.close();assert process.wait()==0
 assert verify(manifest,r/'van-backend-public-source/report.xml',r/'van-backend-public-source/storage-audit.json',root=root)==summary
assert len(json.loads((r/'download-receipts.json').read_text()))==17
assert "trusted/tools/ci/project_truth_ledger.py': [Errno 2]" in (r/'truth-job.log').read_text()
assert 'DDS_CONTRACT_READ_DEPLOY_KEY is not provisioned' in (r/'private-job.log').read_text()
report={'source_head':head,'tested_merge':merge,'run_id':40421043580,'status':'TERMINAL_FAILURE_MANDATORY_PREREQUISITES_AND_PUBLIC_JOB_CANCELLATION_UNWAIVED','public_jobs_success':16,'public_backend_job':'CANCELLED at configured45minute boundary; actual gateway5807/7 and media198, coverage verify and artifact upload succeeded; cancellation is not relabelled SUCCESS','public_source_selection_hashes_and_canonical_verify_match_exact_committed_head':True,'mandatory_unwaived_failures':['missing private DDS deploy key','absent trusted-main checker'],'junit':junit,'canonical_mutations':{'reports':len(list(r.rglob('mutation-report.txt'))),'caught_exactly_once':374,'edits':383,'survivors':0,'unexecuted':0},'actual_verified_main_archives':17,'native_or_unit_acceptance':False,'qualification':'Published2a source only; not later funding drafts or A4 expiry repair','file_sha256':{str(p.relative_to(r)):sha(p) for p in r.rglob('*') if p.is_file() and p.name!='reconciliation.json'}}
(r/'reconciliation.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps({k:v for k,v in report.items() if k not in ('junit','file_sha256')}))
