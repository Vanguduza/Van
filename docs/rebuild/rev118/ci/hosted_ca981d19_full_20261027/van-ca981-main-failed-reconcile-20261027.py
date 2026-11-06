from pathlib import Path
from collections import Counter
import hashlib,json,subprocess,sys,tempfile,xml.etree.ElementTree as E
repo=Path('/workspace/van-review-2026-10-18/publish');root=Path('/workspace/van-ca981d19-full-hosted')
head='ca981d19615f614a1c41f78618e04ea1582d620e';merge='49debf86b517d1fef56e21d299a45ecfc0e76f74'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def cases(p):
 rows=list(E.parse(p).getroot().iter('testcase'))
 return {'passed':sum(all(c.find(k) is None for k in ('failure','error','skipped')) for c in rows),'failures':sum(c.find('failure') is not None for c in rows),'errors':sum(c.find('error') is not None for c in rows),'skips':sum(c.find('skipped') is not None for c in rows)}
meta=json.loads((root/'run-and-jobs-metadata.json').read_text());jobs=meta['jobs']
assert next(x for x in meta['runs'] if x['id']==40432745614)['conclusion']=='failure'
assert sum(x['conclusion']=='success' for x in jobs)==15
assert {x['id'] for x in jobs if x['conclusion']=='failure'}=={121954111965,121954111985,121954112010,121954112205}
junit={str(p.relative_to(root)):cases(p) for p in root.rglob('*.xml')}
assert junit['van-backend-public-source/gateway-report.xml']==dict(passed=5788,failures=62,errors=0,skips=7)
assert junit['van-backend-public-source/media-report.xml']==dict(passed=198,failures=0,errors=0,skips=0)
assert junit['van-postgres-ledger-report/trading-source-report.xml']==dict(passed=4271,failures=0,errors=0,skips=1)
assert all(v['errors']==0 and (name=='van-backend-public-source/gateway-report.xml' or v['failures']==0) for name,v in junit.items())
for p in root.rglob('*audit.json'):assert not json.loads(p.read_text())['forbidden_events']
for p in list(root.rglob('tested-commit.txt'))+list(root.rglob('tested-head.txt')):assert p.read_text().strip() in {head,merge}
sys.path.insert(0,str(repo/'tools/rebuild'));from mutation_registry import suite_groups,inspect
expected=Counter(m[-1] for _,ms,_,_ in suite_groups() for m in ms)
lines=[line for p in root.rglob('mutation-report.txt') for line in p.read_text().splitlines()]
caught=Counter(line.split(None,1)[1].strip() for line in lines if line.startswith('CAUGHT '))
survived=Counter(line.partition('*** SURVIVED ***')[2].strip() for line in lines if line.startswith('*** SURVIVED ***'))
assert sum(caught.values())==373 and survived==Counter({'C11 an expired approval challenge can still be signed':1})
assert caught+survived==expected and inspect(suite_groups())['edit_count']==383
assert not any(line.startswith('UNEXECUTED ') for line in lines)
manifest=json.loads((root/'van-backend-public-source/selection.json').read_text())
controller=repo/'tools/rebuild/backend_public_source.py'
assert subprocess.check_output(['git','show',head+':tools/rebuild/backend_public_source.py'],cwd=repo)==controller.read_bytes()
from backend_public_source import verify
with tempfile.TemporaryDirectory(prefix='van-ca981-failed-source-verification-') as temp:
 target=Path(temp)
 with subprocess.Popen(['git','cat-file','--batch'],cwd=repo,stdin=subprocess.PIPE,stdout=subprocess.PIPE) as process:
  for row in manifest['selected']+manifest['separate']:
   process.stdin.write((head+':'+row['path']+'\n').encode());process.stdin.flush();header=process.stdout.readline().decode().split();assert header[1]=='blob'
   original=process.stdout.read(int(header[2]));assert process.stdout.read(1)==b'\n';assert hashlib.sha256(original).hexdigest()==row['sha256']
   dest=target/row['path'];dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(original)
  process.stdin.close();assert process.wait()==0
 try:verify(manifest,root/'van-backend-public-source/report.xml',root/'van-backend-public-source/storage-audit.json',root=target)
 except ValueError as error:assert 'source cases missing, failed or errored' in str(error)
 else:raise AssertionError('canonical verifier must refuse the actual failed source cases')
assert len(json.loads((root/'download-receipts.json').read_text()))==19
assert 'runtime owner signature is invalid' in (root/'public-job.log').read_text()
assert 'DDS_CONTRACT_READ_DEPLOY_KEY is not provisioned' in (root/'private-job.log').read_text()
assert "trusted/tools/ci/project_truth_ledger.py': [Errno 2]" in (root/'truth-job.log').read_text()
report={'source_head':head,'tested_merge':merge,'run_id':40432745614,'status':'FAILED_FOUR_JOBS_RETAINED','public_jobs_success':15,'public_failed_jobs':['backend-public-source:62 failed/5788passed/7declaredskips','mutation-python2:expired-approval case survived'],'mandatory_unwaived_failures':['missing private DDS deploy key','absent trusted-main checker'],'canonical_public_verifier':'REFUSED_FAILED_CASES_AS_REQUIRED','selection_hashes_match_exact_committed_head':True,'junit':junit,'canonical_mutations':{'reports':len(list(root.rglob('mutation-report.txt'))),'caught':373,'survivors':dict(survived),'unexecuted':0,'total_cases':374,'edits':383},'verified_archives':19,'qualification':'Failed exactca981 source run; not later guard/digest repairs or native/unit/production/economic/S24 acceptance','file_sha256':{str(p.relative_to(root)):sha(p) for p in root.rglob('*') if p.is_file() and p.name!='failed-reconciliation.json'}}
(root/'failed-reconciliation.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps({k:v for k,v in report.items() if k not in ('junit','file_sha256')}))
