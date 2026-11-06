"""Replay original failed and exact recovery JUnit identities without relabelling runs."""
from pathlib import Path
import json,hashlib,xml.etree.ElementTree as ET,subprocess
W=Path('/workspace')
def read(p):return json.loads(Path(p).read_text())
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def key(n):
 head,marker,param=n.partition('[');p=head.split('::');return(p[0][:-3].replace('/','.')+('.'+'.'.join(p[1:-1]) if len(p)>2 else ''),p[-1]+(marker+param if marker else ''))
def outcomes(xml,lookup):
 results={}
 for c in ET.parse(xml).findall('.//testcase'):
  k=(c.get('classname'),c.get('name'));assert k in lookup,('Unknown actual JUnit identity',xml,k);nid=lookup[k]
  row=results.setdefault(nid,{'bad':False,'skipped':False,'reasons':[]})
  row['bad'] |= c.find('failure') is not None or c.find('error') is not None
  if c.find('skipped') is not None:row['skipped']=True;row['reasons'].append(c.find('skipped').get('message',''))
 return results
def replay(label,expected,original_lookup,recovery_lookup,original_xml,original_terminal,recovery_dir,recovery_xml,further_recovery=None):
 plan_path=W/'van-storage-recovery-sets-20261101'/(label+'.json');plan=read(plan_path);assert sha(original_xml)==plan['original_xml_sha256'];original=outcomes(original_xml,original_lookup)
 bad={n for n,r in original.items() if r['bad']};missing=expected-set(original);passed={n for n,r in original.items() if not r['bad'] and not r['skipped']};skipped={n for n,r in original.items() if not r['bad'] and r['skipped']};need=bad|missing
 assert bad==set(plan['failed_or_error_cases']) and missing==set(plan['unexecuted_cases']) and passed==set(plan['fully_passed_original_cases']) and skipped==set(plan['declared_skip_cases']) and need==set(plan['recovery_cases'])
 oldterm=read(original_terminal);assert oldterm.get('exit')!=0 and (oldterm.get('state')=='COMPLETED' or oldterm.get('completed') is True)
 recovery_dir=Path(recovery_dir);terminal=read(recovery_dir/'receipt.json');assert terminal['completed'] is True and terminal['owned_temp_cleanup']['independently_absent'] is True
 assert terminal['recovery_plan_sha256']==sha(plan_path)
 audit=read(recovery_dir/'storage-audit.json');assert audit['forbidden_events']==[]
 targets=(recovery_dir/'targets.txt').read_text().splitlines();assert len(targets)==len(set(targets)) and set(targets)==need
 recovered=outcomes(recovery_dir/recovery_xml,recovery_lookup);assert set(recovered)==need
 remaining_bad={n for n,r in recovered.items() if r['bad']};extra_proof=None
 if remaining_bad:
  assert further_recovery is not None and terminal['exit']!=0, 'Actual recovery failure remains unresolved'
  directory=Path(further_recovery);extra=read(directory/'receipt.json');assert extra['completed'] and extra['exit']==0 and extra['owned_temp_cleanup']['independently_absent']
  assert extra['source_sha256']==terminal['source_sha256'] and extra['environment_pin_sha256']==terminal['environment_pin_sha256']
  plan2_path=W/'van-auth-erasure-isolated-plan-20261101.json';plan2=read(plan2_path);assert extra['recovery_plan_sha256']==sha(plan2_path) and set(plan2['recovery_cases'])==remaining_bad and plan2['original_xml_sha256']==sha(recovery_dir/recovery_xml)
  assert read(directory/'storage-audit.json')['forbidden_events']==[]
  assert set((directory/'targets.txt').read_text().splitlines())==remaining_bad
  extra_results=outcomes(directory/'recovery.xml',recovery_lookup);assert set(extra_results)==remaining_bad and all(not r['bad'] for r in extra_results.values())
  extra_proof={'original_recovery_exit':terminal['exit'],'original_recovery_remains_failed':True,'failed_recovery_nodeids':sorted(remaining_bad),'exact_unchanged_isolated_replay':sorted(extra_results),'terminal_sha256':sha(directory/'receipt.json'),'xml_sha256':sha(directory/'recovery.xml'),'plan_sha256':sha(plan2_path)}
  recovered.update(extra_results)
 else:assert terminal['exit']==0
 assert all(not r['bad'] for r in recovered.values())
 assert not passed&need and not skipped&need and expected==passed|skipped|set(recovered)
 skips=[{'name':n,'reasons':r['reasons'],'origin':'original_failed_run_declared_skip'} for n,r in original.items() if n in skipped]+[{'name':n,'reasons':r['reasons'],'origin':'actual_recovery_run_declared_skip'} for n,r in recovered.items() if r['skipped']]
 return {'label':label,'tests':len(expected),'passed':len(passed)+sum(not r['skipped'] for r in recovered.values()),'failures':0,'errors':0,'skipped':len(skips),'skip_cases':skips,'original_terminal_exit':oldterm['exit'],'original_run_remains_failed':True,'retained_fully_passed_original_cases':len(passed),'actual_recovery_cases':len(recovered),'original_bad_cases':len(bad),'original_unexecuted_cases':len(missing),'unresolved_bad_or_unexecuted_cases':0,'exact_expected_identity_union_verified':True,'original_terminal_sha256':sha(original_terminal),'original_xml_sha256':sha(original_xml),'recovery_terminal_sha256':sha(recovery_dir/'receipt.json'),'recovery_xml_sha256':sha(recovery_dir/recovery_xml),'plan_sha256':sha(plan_path),'additional_exact_case_recovery':extra_proof,'recovery_nodeids':sorted(recovered),'retained_passed_nodeids':sorted(passed),'expected_nodeids_sha256':hashlib.sha256(json.dumps(sorted(expected),separators=(',',':')).encode()).hexdigest()}
def auth(selected_recovery,remainder_recovery,source_pins,collection_dir,selected_isolated=None):
 source_pins=Path(source_pins);pins=read(source_pins)['files'];C=Path(collection_dir);collection=read(C/'receipt.json');assert collection['full_equals_disjoint_union'] and collection['source_pins_sha256']==sha(source_pins)
 for name,h in collection['manifests'].items():assert sha(C/name)==h
 env=read(W/'van-auth-shared-shard-environment-20261101.json');R=Path(env['same_worktree'])
 for f,h in {**pins,**env['source_config_fixture_files']}.items():assert sha(R/f)==h,('Source/config/fixture drift',f)
 freeze=subprocess.check_output([env['same_python'],'-m','pip','freeze'],text=True);assert hashlib.sha256(freeze.encode()).hexdigest()==env['package_freeze_sha256']
 all_expected=set();rows=[]
 for label,directory,stem in [('selected',Path(selected_recovery),'van-auth-corrected-affected-20261101'),('remainder',Path(remainder_recovery),'van-auth-corrected-remainder-20261101')]:
  manifest=read(C/(label+'.json'));expected=set(manifest['nodeids']);lookup={key(raw):nid for raw,nid in zip(manifest['raw_nodeids'],manifest['nodeids'],strict=True)};assert len(lookup)==len(expected);assert not all_expected&expected;all_expected|=expected
  terminal=read(directory/'receipt.json');assert terminal['source_sha256']==pins and terminal['environment_pin_sha256']==sha(W/'van-auth-shared-shard-environment-20261101.json')
  assert read(W/(stem.replace('-20261101','-audit-20261101')+'.json'))['forbidden_events']==[]
  rows.append(replay(label,expected,lookup,lookup,W/(stem+'.xml'),W/(stem+'.json'),directory,'recovery.xml',selected_isolated if label=='selected' else None))
 assert all_expected==set(read(C/'full.json')['nodeids']) and len(all_expected)==5943
 return {'schema':'van.auth-exact-composite-source-coverage/1','tests':len(all_expected),'passed':sum(x['passed'] for x in rows),'failures':0,'errors':0,'skipped':sum(x['skipped'] for x in rows),'skip_cases':[s for x in rows for s in x['skip_cases']],'shards':rows,'exact_full_corrected_collection_covered':True,'single_successful_full_run_claimed':False,'original_runs_remain_failed':True,'unresolved_bad_or_unexecuted_cases':0}
def successor(original_dir,recovery_dir):
 O=Path(original_dir);R=Path(recovery_dir);old=read(O/'receipt.json');new=read(R/'receipt.json');assert old['source_sha256']==new['source_sha256'] and old['reference_fixtures_sha256']==new['reference_fixtures_sha256'];assert old['owned_fixture_independently_absent'] and new['owned_fixture_independently_absent']
 events=[json.loads(x) for x in (O/'test-events.jsonl').read_text().splitlines()];expected={x['nodeid'] for x in events};assert len(expected)==5775
 original_lookup={key(n):n for n in expected};plan=read(W/'van-storage-recovery-sets-20261101/successor.json');recovery_lookup={key(n.removeprefix('backend/')):n for n in plan['recovery_cases']};assert len(recovery_lookup)==50 and all(n.startswith('backend/') for n in plan['recovery_cases'])
 assert read(O/'storage-audit.json')['forbidden_events']==[]
 result=replay('successor',expected,original_lookup,recovery_lookup,O/'full-trading.xml',O/'receipt.json',R,'full-trading.xml');result['junit_classname_normalization']='Recovery has backend pytest root; canonical exact source file paths retained while tests.* XML classnames map to backend/tests/* identities.';return result
