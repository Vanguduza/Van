import hashlib,json,os,tempfile,zipfile
from pathlib import Path
import pytest
import vati.execution.router as router
import vati.lifecycle.family_execution as execution
import vati.lifecycle.family_membership as membership
from conftest import owner_authority
from conftest_owner_authority import OWNER_KEY_ID
from test_family_unknown_independence import test_optional_native_identity_read_unavailable_does_not_gate_actual_protective_close,test_preexisting_independent_unknown_cannot_block_new_mandatory_other_leg_close,test_partial_dispatch_rereads_new_other_leg_unknown_under_current_writer
from test_family_governed_workflow import admitted_source_world
from vati.execution.base import VenueUnavailable
from vati.core import EventKind
from vati.lifecycle.family_protection import mandatory_family_close
from vati.lifecycle.family_action_journal import FamilyActionJournal
from vati.lifecycle.preservation import ActionKind,Urgency
ROOT=Path('/workspace/van-lanes-20261101/family-multiposition');OUT=Path('/workspace/van-family-frozen-independent-recheck-r2-20261101');FREEZE=Path('/workspace/van-family-workflow-freeze-r2-20261101')
frozen=json.loads((FREEZE/'FROZEN_SOURCE_INPUTS.json').read_text())
def pins():return {p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in frozen['source_pins']}
before=pins();assert before==frozen['source_pins'];(OUT/'before.json').write_text(json.dumps(before,indent=2))
with zipfile.ZipFile(FREEZE/'FROZEN_SOURCE.zip') as z:
 for p,h in before.items():
  names=[n for n in z.namelist() if n==p or n.endswith('/'+p)];assert len(names)==1
  assert hashlib.sha256(z.read(names[0])).hexdigest()==h
results=[]
def fixture(path):
 registry=path/'synthetic-owner-registry.json';registry.write_text(json.dumps({'keys':{OWNER_KEY_ID:owner_authority().pem}}));os.environ['VAN_OWNER_AUTHORITY_KEYS']=str(registry)
for name,fn,args in [('FAM01 actual ProtectionManager unavailable portfolio preserves urgent close original journal and no resend',test_optional_native_identity_read_unavailable_does_not_gate_actual_protective_close,()),('FAM02 preexisting UNKNOWN native effect happened',test_preexisting_independent_unknown_cannot_block_new_mandatory_other_leg_close,(True,)),('FAM02 preexisting UNKNOWN native effect not observed',test_preexisting_independent_unknown_cannot_block_new_mandatory_other_leg_close,(False,)),('FAM03 new otherleg UNKNOWN between planning and writer refuses any automatic partial',test_partial_dispatch_rereads_new_other_leg_unknown_under_current_writer,())]:
 with tempfile.TemporaryDirectory(prefix='van-family-r2-recheck-',dir='/tmp') as temp:
  path=Path(temp);fixture(path)
  with pytest.MonkeyPatch.context() as mp:fn(path,mp,*args)
 results.append({'case':name,'result':'PASS'})
# Re-execute original independent FAM01 direct counterexample with stronger readback.
with tempfile.TemporaryDirectory(prefix='van-family-r2-original01-',dir='/tmp') as temp:
 path=Path(temp);fixture(path);w,store,time,grant,plan,history=admitted_source_world(path,actual_runtime_lease=True)
 try:
  pid=w.adapter.positions()[0].position_id;calls=[];real=w.adapter.close
  def close(*a,**kw):calls.append(a[0]);return real(*a,**kw)
  def unavailable():raise VenueUnavailable('original independent counterexample native reader unavailable')
  w.adapter.close=close;w.adapter.positions=unavailable
  receipt=w.router.apply_preservation('paper',position_id=pid,trade_intent_id='',action='FULL_CLOSE',reason='EXISTING_URGENT_PROTECTION',now_ms=time[0])
  requests=[e for e in w.ledger.iter(EventKind.EXIT_ATTEMPT) if e.payload.get('state')=='REQUESTED']
  assert len(calls)==1 and receipt.status=='FILLED' and len(requests)==1 and requests[0].payload['trade_intent_id']==''
  assert w.router.exit_journal.latest('paper',pid).payload['state']=='CONFIRMED'
  results.append({'case':'original independent FAM01 counterexample','result':'PASS','request_ref':requests[0].hash,'attribution':'EMPTY_ORIGINAL_REQUEST_NOT_GUESSED'})
 finally:w.ledger.close()
# Re-execute original independent FAM02 after an actual close with lost reply.
with tempfile.TemporaryDirectory(prefix='van-family-r2-original02-',dir='/tmp') as temp:
 path=Path(temp);fixture(path);w,store,time,grant,plan,history=admitted_source_world(path,actual_runtime_lease=True,add_child=True,max_quantity='.20')
 try:
  family=w.lifecycle.families.get(plan.snapshot.family_id);first=w.adapter.positions()[0];real=w.adapter.close
  def lost(*a,**kw):real(*a,**kw);raise OSError('original independent close happened reply lost')
  w.adapter.close=lost
  try:w.router.apply_preservation('paper',position_id=first.position_id,trade_intent_id=first.trade_intent_id,action='FULL_CLOSE',reason='ORIGINAL_INDEPENDENT_PROTECTION',now_ms=time[0])
  except OSError:pass
  original=w.router.exit_journal.pending('paper',first.position_id);w.adapter.close=real
  decision=w.lifecycle.preservation._act(family,ActionKind.FULL_CLOSE,Urgency.IMMEDIATE,('THESIS_INVALIDATED',),time[0],detail='original independent mandatory exit after UNKNOWN')
  result=mandatory_family_close(w.lifecycle,decision,now_ms=time[0])
  assert not w.adapter.positions() and w.router.exit_journal.pending('paper',first.position_id).hash==original.hash
  assert result['state']=='INCOMPLETE' and result['unresolved_native_effect'] and result['requested_quantity'] is None and result['residual_quantity'] is None
  assert not w.lifecycle.reviews and not w.learning.episodes
  results.append({'case':'original independent FAM02 counterexample','result':'PASS','original_unknown_ref':original.hash,'progress':result})
 finally:w.ledger.close()
after=pins();assert after==before;(OUT/'after.json').write_text(json.dumps(after,indent=2))
record={'imports':{'router':router.__file__,'execution':execution.__file__,'membership':membership.__file__},'all37_source_pins_and_archive_verified_unchanged':True,'results':results,'owned_tmp_cleanup':True}
(OUT/'probe-results.json').write_text(json.dumps(record,indent=2));print(json.dumps({'results':[{'case':p['case'],'result':p['result']} for p in results],'all37_source_pins_and_archive_verified_unchanged':True}))
