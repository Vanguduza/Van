"""Fresh-process source fault/control checks. No network, authority or acceptance claims."""
import base64, contextlib, hashlib, io, json, os, sys
from pathlib import Path
import xml.etree.ElementTree as E

root=Path('/workspace/van-review-2026-10-18/publish')
out=Path('/tmp/van-market-monitor-faults-20261025')
out.mkdir(exist_ok=True)
os.chdir(root)
service='backend/van_gateway/trading/monitor_service.py'
calc='backend/van_gateway/trading/monitor_calculations.py'
bus='backend/van_gateway/events/bus.py'
pure='backend/tests/test_market_monitor_measurements.py::'
runtime='backend/tests/test_market_monitor_runtime.py::'
cases=[
 ('native-scope',[(service,'if snapshot.instrument != instrument or snapshot.timeframe != timeframe:','if snapshot.timeframe != timeframe:')],[pure+'test_full_scope_and_actual_availability_refusals']),
 ('stale-source',[(service,'if now-snapshot.bars[-1].end_ms > max_age:','if False:')],[pure+'test_stale_data_missing_binding_and_short_indicator_history_are_not_zeroes']),
 ('news-trust',[(service,'if (row.trust not in allowed or row.published_ms < view.armed_at_ms','if (row.published_ms < view.armed_at_ms')],[pure+'test_literal_news_keyword_matching_preserves_trust_freshness_time_and_declared_relevance']),
 ('corrected-price',[(service,'if current.event_time_ms == previous.event_time_ms:','if False:')],[pure+'test_same_time_price_correction_cannot_become_a_new_level_trigger']),
 ('unobserved-cross',[
  (service,"        if condition.comparator.startswith('CROSS_') and prior_value is None:\n            return current, False\n",''),
  (calc,'    if previous is None:\n        return False\n','    previous = threshold if previous is None else previous\n')
 ],[pure+'test_a_first_sample_already_above_the_line_is_not_an_observed_crossing']),
 ('clock-rollback',[(service,'\n            if now < high_water:\n','\n            if False:\n')],[runtime+'test_clock_rollback_cannot_publish_before_rule_arm_or_clear_its_durable_high_water']),
 ('evaluation-cas',[(service,'\n            if current.evaluation != view.evaluation:\n                return False\n','\n')],[runtime+'test_competing_evaluators_cannot_overwrite_a_newer_baseline_or_emit_from_a_stale_view']),
 ('atomic-event',[(bus,'        return int(cur.lastrowid)\n','        await db.commit()\n        return int(cur.lastrowid)\n')],[runtime+'test_event_alert_state_and_projection_witness_have_one_sqlite_rollback_boundary']),
 ('scan-budget',[(service,"            used = old['used'] if old is not None and old['window_ms'] == window else 0","            used = 0")],[runtime+'test_scan_quota_is_atomic_and_survives_service_restart_and_clock_rollback']),
]
backup=json.loads((out/'baseline.json').read_text())
original={p:base64.b64decode(b)for p,b in backup.items()}
sha=lambda b:hashlib.sha256(b).hexdigest()
step=int(sys.argv[1]) if len(sys.argv)>1 else 0
if step>=len(cases)*2:
 rows=[json.loads((out/(name+'-pair.json')).read_text())for name,_,_ in cases]
 result={'schema':'van.rebuild.market-monitor-source-fault-controls/1',
  'expected':len(cases),'caught':sum(x['status']=='CAUGHT'for x in rows),'pairs':rows,
  'source_sha256':{p:sha(b)for p,b in original.items()},
  'source_restored':all((root/p).read_bytes()==b for p,b in original.items()),
  'scope':'Fresh actual source tests, not canonical unit/native/provider acceptance.'}
 (out/'summary.json').write_text(json.dumps(result,indent=2)+'\n')
 print(json.dumps({k:v for k,v in result.items()if k!='pairs'}),flush=True)
 raise SystemExit(0 if result['caught']==len(cases) and result['source_restored'] else 1)
name,edits,nodes=cases[step//2]
phase='mutant' if step%2==0 else 'control'
for p,b in original.items():
 assert (root/p).read_bytes()==b, 'source changed outside this fault runner: '+p
changed={}
if phase=='mutant':
 for path,old,new in edits:
  b=changed.get(path,original[path])
  assert b.count(old.encode())==1,(name,path,b.count(old.encode()))
  changed[path]=b.replace(old.encode(),new.encode())
 for path,b in changed.items():
  (root/path).write_bytes(b)
for path in original:
 cache=(root/path).parent/'__pycache__'
 if cache.exists():
  for p in cache.glob(Path(path).stem+'.*.pyc'):
   p.unlink()
(out/'active.json').write_text(json.dumps({'case':name,'phase':phase,
 'mutated_sha256':{p:sha(b)for p,b in changed.items()}},indent=2)+'\n')
report=out/(name+'-'+phase+'.xml')
log=io.StringIO()
try:
 import pytest
 with contextlib.redirect_stdout(log),contextlib.redirect_stderr(log):
  code=int(pytest.main([*nodes,'-q','--tb=short','--junitxml='+str(report)]))
finally:
 for path,b in changed.items():
  assert (root/path).read_bytes()==b,'refuse to overwrite outside edit: '+path
  (root/path).write_bytes(original[path])
(output:=out/(name+'-'+phase+'.log')).write_text(log.getvalue())
cs=list(E.parse(report).getroot().iter('testcase'))
counts={'tests':len(cs),'failures':sum(c.find('failure')is not None for c in cs),
 'errors':sum(c.find('error')is not None for c in cs),'skipped':sum(c.find('skipped')is not None for c in cs)}
failtext='\n'.join((c.find('failure').text or '')for c in cs if c.find('failure')is not None)
invalid=any(s in failtext for s in ["can't start new thread",'Resource temporarily unavailable',
 'ModuleNotFoundError','ImportError','SyntaxError','NameError','TypeError'])
observed={'case':name,'phase':phase,'exit_code':code,'counts':counts,
 'report_sha256':sha(report.read_bytes()),'log_sha256':sha(output.read_bytes()),
 'restored_sha256':{p:sha((root/p).read_bytes())for p in original},
 'semantic_failure':code==1 and counts['failures']>0 and counts['errors']==0 and counts['skipped']==0
  and not invalid and ('assert' in failtext or 'DID NOT RAISE' in failtext)}
(out/(name+'-'+phase+'.json')).write_text(json.dumps(observed,indent=2)+'\n')
if phase=='control':
 mutant=json.loads((out/(name+'-mutant.json')).read_text())
 passed=code==0 and counts['tests']>0 and all(counts[k]==0 for k in ['failures','errors','skipped'])
 pair={'case':name,'status':'CAUGHT'if mutant['semantic_failure']and passed else 'NOT_QUALIFIED',
       'mutant':mutant,'control':observed}
 (out/(name+'-pair.json')).write_text(json.dumps(pair,indent=2)+'\n')
print(name,phase,'exit',code,counts,flush=True)
os.execve(sys.executable,[sys.executable,__file__,str(step+1)],os.environ.copy())
