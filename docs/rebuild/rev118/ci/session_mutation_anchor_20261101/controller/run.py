from pathlib import Path
import os,json,hashlib,datetime,sys,importlib.util,subprocess,shutil,xml.etree.ElementTree as ET
from van_owned_basetemp_20261101 import preflight,cleanup
W=Path('/workspace');R=W/'van-lanes-20261101/mutation-ci-fix';O=W/'van-mutation-affected-20261101';O.mkdir(exist_ok=False)
parent=subprocess.check_output(['git','rev-parse','HEAD'],cwd=R,text=True).strip();assert parent=='f8758db746582439819c1c1129ca64a8cf9fca7d'
spec=importlib.util.spec_from_file_location('van_actual_mutation_suite',R/'tools/audit/mutation_suite.py');suite=importlib.util.module_from_spec(spec);spec.loader.exec_module(suite)
sourcepins={f:hashlib.sha256((R/f).read_bytes()).hexdigest() for f in ['backend/van_gateway/session/router.py','backend/van_gateway/session/service.py','backend/tests/test_van_hermes_session.py','backend/tests/test_session_transport_api.py','tools/audit/mutation.py','tools/audit/mutation_suite.py']}
for f,h in sourcepins.items():
 if f!='tools/audit/mutation_suite.py':assert hashlib.sha256(subprocess.check_output(['git','show',parent+':'+f],cwd=R)).hexdigest()==h,f
os.environ.update(PYTHONPATH='/workspace:'+':'.join(str(R/p) for p in ['.','backend','backend/tests','trading','trading/tests']),DIAL_REPO='/workspace/van-review-2026-10-18/dial-development-system',PYTEST_PLUGINS='van_mutation_storage_guard_20261101',VAN_MUTATION_SOURCE_ROOT=str(R))
reasons=[('c36','C36 an envelope nobody can carry out is written into the admission table first','test_a_kind_with_no_delegate_is_not_written_into_the_admission_table'),('c26','C26 an expired command executes late','test_an_expired_envelope_is_not_executed_late')];allresults=[]
for label,reason,expected in reasons:
 out=O/label;out.mkdir();temp='/tmp/van-recovery-mutation-'+label+'-20261101';prep=preflight(temp);currentxml=out/'current.xml';currentaudit=out/'current-audit.json';os.environ['PYTEST_ADDOPTS']='--basetemp='+temp+' --junitxml='+str(currentxml);os.environ['VAN_MUTATION_STORAGE_REPORT']=str(currentaudit);results=[]
 def observe(kind,why,result):
  assert why is None or why==reason
  path=out/(kind+'.xml');shutil.copy2(currentxml,path);shutil.copy2(currentaudit,out/(kind+'-storage-audit.json'));(out/(kind+'.log')).write_text(result.stdout+result.stderr);audit=json.load(open(currentaudit));assert audit['forbidden_events']==[]
  cases=ET.parse(path).findall('.//testcase');bad=[c for c in cases if c.find('failure') is not None];errors=[c for c in cases if c.find('error') is not None];skips=[c for c in cases if c.find('skipped') is not None];assert cases and not errors and not skips,(kind,'invalidcaseoutcome')
  if kind=='baseline':assert result.returncode==0 and not bad
  else:assert result.returncode==1 and any(c.get('name')==expected for c in bad),(reason,'not the original semantic oracle')
  for f,h in sourcepins.items():assert hashlib.sha256((R/f).read_bytes()).hexdigest()==h,('Source not restored',f)
  assert not (R/'tools/audit/.mutation-journal.json').exists()
  inventory=out/(kind+'-temp');inventory.mkdir();clean=cleanup(temp,inventory);results.append({'kind':kind,'reason':why,'exit':result.returncode,'tests':len(cases),'failed_assertions':[c.get('name') for c in bad],'errors':len(errors),'skipped':len(skips),'source_restored':True,'cleanup':clean,'actual_command':result.args})
  if kind=='baseline':preflight(temp)
 groups=list(suite.groups(reason,family='python'));assert len(groups)==1 and len(groups[0][1])==1
 tests,mutants,options=groups[0];survivors=suite.run(mutants,tests,root=R/'backend',cwd=R/'backend',observe=observe,**options);assert not survivors and len(results)==2;allresults.append({'identity':reason,'unmodified_control':results[0],'actual_semantic_mutant':results[1],'survivors':survivors});print(label,'CONTROL_PASS_SEMANTIC_MUTANT_CAUGHT',flush=True)
receipt={'schema':'van.current-session-mutation-reconciliation/1','completed_at_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'source_parent':parent,'source_worktree':str(R),'source_sha256':sourcepins,'registry_sha256':sourcepins['tools/audit/mutation_suite.py'],'diagnostic_plugin_sha256':hashlib.sha256((W/'van_mutation_storage_guard_20261101.py').read_bytes()).hexdigest(),'results':allresults,'production_and_test_assertions_changed':False,'scope':'Only2retargeted retainedmutationidentities executed; global374case consistency checked separately; no fullcorpus/nativeacceptance claim.'};(O/'receipt.json').write_text(json.dumps(receipt,indent=2)+'\n');print('MUTATION_AFFECTED_TERMINAL0',flush=True)
