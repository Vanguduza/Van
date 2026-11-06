import json,os,tempfile
from pathlib import Path
from conftest import owner_authority
from conftest_owner_authority import OWNER_KEY_ID
from test_family_governed_workflow import admitted_source_world
from vati.lifecycle.family_protection import mandatory_family_close
from vati.lifecycle.preservation import ActionKind,Urgency
OUT=Path('/workspace/van-family-frozen-independent-review-20261101')
with tempfile.TemporaryDirectory(prefix='van-family-preexisting-unknown-',dir='/tmp') as temp:
 path=Path(temp);registry=path/'synthetic-owner-registry.json';registry.write_text(json.dumps({'keys':{OWNER_KEY_ID:owner_authority().pem}}));os.environ['VAN_OWNER_AUTHORITY_KEYS']=str(registry)
 w,store,time,grant,plan,history=admitted_source_world(path,actual_runtime_lease=True,add_child=True,max_quantity='.20')
 try:
  family=w.lifecycle.families.get(plan.snapshot.family_id);first=w.adapter.positions()[0];real=w.adapter.close
  def lost(*a,**kw):real(*a,**kw);raise OSError('original native first-leg close happened but reply lost')
  w.adapter.close=lost
  try:w.router.apply_preservation('paper',position_id=first.position_id,trade_intent_id=first.trade_intent_id,action='FULL_CLOSE',reason='ORIGINAL_INDEPENDENT_PROTECTION',now_ms=time[0])
  except OSError:pass
  w.adapter.close=real;before=[p.position_id for p in w.adapter.positions()]
  decision=w.lifecycle.preservation._act(family,ActionKind.FULL_CLOSE,Urgency.IMMEDIATE,('THESIS_INVALIDATED',),time[0],detail='existing mandatory exit after independent UNKNOWN')
  try:result=mandatory_family_close(w.lifecycle,decision,now_ms=time[0])
  except Exception as exc:result={'error':type(exc).__name__+': '+str(exc)}
  after=[p.position_id for p in w.adapter.positions()]
  record={'before_remaining_leg_ids':before,'after_remaining_leg_ids':after,'result':result,'finding':'MANDATORY_OTHER_LEG_CLOSE_BLOCKED_BY_PREEXISTING_UNKNOWN' if before==after else 'OTHER_LEG_CLOSED'}
 finally:w.ledger.close()
(OUT/'probe-preexisting-unknown-results.json').write_text(json.dumps(record,indent=2));print(json.dumps(record))
