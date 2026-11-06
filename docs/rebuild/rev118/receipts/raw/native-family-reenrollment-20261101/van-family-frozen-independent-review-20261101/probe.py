import hashlib,json,os,tempfile,zipfile
from pathlib import Path
import pytest
import vati.execution.router as router_module
from conftest import owner_authority
from conftest_owner_authority import OWNER_KEY_ID
from test_family_governed_workflow import admitted_source_world
from test_family_outcome_restatements import test_pending_actual_owner_read_then_first_qualified_outcome_one_trial,test_source_owner_late_cash_revision_replaces_same_parent_without_new_trial
from test_family_native_supervision import test_cold_optional_policy_expiry_does_not_disable_existing_mandatory_family_protection
from test_family_unknown_independence import test_original_unknown_full_target_is_not_resent_and_other_full_leg_executes
from vati.execution.base import VenueUnavailable
ROOT=Path('/workspace/van-lanes-20261101/family-multiposition');OUT=Path('/workspace/van-family-frozen-independent-review-20261101')
frozen=json.loads(Path('/workspace/van-family-workflow-freeze-20261101/FROZEN_SOURCE_INPUTS.json').read_text())
def pins():return {p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in frozen['source_pins']}
before=pins();assert before==frozen['source_pins'];(OUT/'before.json').write_text(json.dumps(before,indent=2))
results=[]
for name,fn,monkey in [('pending finality to one root review',test_pending_actual_owner_read_then_first_qualified_outcome_one_trial,False),('late source cash restates same trial',test_source_owner_late_cash_revision_replaces_same_parent_without_new_trial,False),('cold optional expiry retains mandatory full close',test_cold_optional_policy_expiry_does_not_disable_existing_mandatory_family_protection,False),('UNKNOWN original target no resend other leg full close',test_original_unknown_full_target_is_not_resent_and_other_full_leg_executes,True)]:
 with tempfile.TemporaryDirectory(prefix='van-family-frozen-review-',dir='/tmp') as temp:
  path=Path(temp);registry=path/'synthetic-owner-registry.json';registry.write_text(json.dumps({'keys':{OWNER_KEY_ID:owner_authority().pem}}));os.environ['VAN_OWNER_AUTHORITY_KEYS']=str(registry)
  if monkey:
   with pytest.MonkeyPatch.context() as mp:fn(path,mp)
  else:fn(path)
 results.append({'case':name,'result':'PASS'})
with tempfile.TemporaryDirectory(prefix='van-family-legacy-join-',dir='/tmp') as temp:
 path=Path(temp);registry=path/'synthetic-owner-registry.json';registry.write_text(json.dumps({'keys':{OWNER_KEY_ID:owner_authority().pem}}));os.environ['VAN_OWNER_AUTHORITY_KEYS']=str(registry)
 w,store,time,grant,plan,history=admitted_source_world(path,actual_runtime_lease=True)
 try:
  pid=w.adapter.positions()[0].position_id;calls=[];real=w.adapter.close
  def close(*args,**kw):calls.append(args[0]);return real(*args,**kw)
  def unavailable():raise VenueUnavailable('synthetic readonly native portfolio unavailable')
  w.adapter.close=close;w.adapter.positions=unavailable
  try:w.router.apply_preservation('paper',position_id=pid,trade_intent_id='',action='FULL_CLOSE',reason='EXISTING_URGENT_PROTECTION',now_ms=time[0])
  except Exception as exc:error=type(exc).__name__+': '+str(exc)
  else:error=None
  results.append({'case':'optional original-intent attribution positions reader unavailable','result':'REPRODUCED_CLOSE_SUPPRESSED' if not calls else 'PASS','close_calls':len(calls),'error':error})
 finally:w.ledger.close()
after=pins();assert after==before;(OUT/'after.json').write_text(json.dumps(after,indent=2))
record={'imports':{'router':router_module.__file__},'results':results,'all37_source_pins_match_and_unchanged':True,'owned_tmp_cleanup':True}
(OUT/'probe-results.json').write_text(json.dumps(record,indent=2));print(json.dumps(record))
