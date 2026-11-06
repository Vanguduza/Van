"""UNKNOWN original full-close outcome cannot cancel another leg's protection."""
from contextlib import closing
from decimal import Decimal as D
import pytest

from conftest import owner_authority
from test_family_governed_workflow import admitted_source_world
from vati.core import Ledger, EventKind
from vati.lifecycle.family_action_journal import FamilyActionJournal
from vati.risk.operational_grant import OperationalOptimizationGrants, subject


def test_original_unknown_full_target_is_not_resent_and_other_full_leg_executes(tmp_path,monkeypatch):
    w,store,time,grant,plan,history=admitted_source_world(tmp_path,
        actual_runtime_lease=True,add_child=True,max_quantity='.20')
    try:
        family=w.lifecycle.families.get(plan.snapshot.family_id);close=w.adapter.close;calls=[]
        def lost_reply(pid,*args,**kwargs):
            calls.append(pid);receipt=close(pid,*args,**kwargs)
            if len(calls)==1:raise OSError('synthetic native effect happened but reply lost')
            return receipt
        monkeypatch.setattr(w.adapter,'close',lost_reply)
        result=w.lifecycle.request_family_reduction(family.family_id,action_key='unknown-full',
            action='FULL_CLOSE',now_ms=time[0])
        assert len(calls)==2 and not w.adapter.positions()
        assert result['state']=='INCOMPLETE' and result['unresolved_native_effect']
        assert D(result['confirmed_quantity'])>0 and D(result['residual_quantity'])>0
        assert sorted(t['state'] for t in result['targets'])==['CONFIRMED','UNKNOWN']
        assert not w.lifecycle.reviews and not w.learning.episodes
        time[0]+=300000
        replay=w.lifecycle.request_family_reduction(family.family_id,action_key='unknown-full',
            action='FULL_CLOSE',now_ms=time[0])
        assert replay==result and len(calls)==2
        assert w.lifecycle.preservation_blocks_new_risk
    finally:w.ledger.close()


def test_committed_other_writer_revocation_refuses_next_target_but_native_stop_survives(tmp_path,monkeypatch):
    w,store,time,grant,plan,history=admitted_source_world(tmp_path,
        actual_runtime_lease=True,add_child=True,max_quantity='.20')
    try:
        family=w.lifecycle.families.get(plan.snapshot.family_id);apply=w.lifecycle.families.apply;revoked=[]
        def apply_then_revoke(*args,**kwargs):
            result=apply(*args,**kwargs)
            if not revoked:
                with closing(Ledger(w.ledger.path)) as other:
                    peer=OperationalOptimizationGrants(other,owner_authority=store.owner,
                        qualification_authority=store.qualifier,clock=store.clock)
                    body=dict(grant_id=grant.payload['grant_id'],expected_ref=grant.hash)
                    signed=owner_authority().token(act='lifecycle-policy-revoke',subject=subject(body),
                        issued_at_unix=time[0]//1000)
                    revoked.append(peer.revoke(grant.payload['grant_id'],expected_ref=grant.hash,owner_signature=signed).hash)
            return result
        monkeypatch.setattr(w.lifecycle.families,'apply',apply_then_revoke)
        result=w.lifecycle.request_family_reduction(family.family_id,action_key='revoke-between-legs',
            action='FULL_CLOSE',now_ms=time[0])
        assert revoked and len(w.adapter.positions())==1
        assert sorted(t['state'] for t in result['targets'])==['CONFIRMED','NOT_EXECUTED']
        assert not result['unresolved_native_effect'] and result['state']=='INCOMPLETE'
        refused=next(t for t in result['targets'] if t['state']=='NOT_EXECUTED')
        outcome=next(e for e in w.ledger.iter(EventKind.EXIT_ATTEMPT) if e.hash==refused['outcome_ref'])
        assert outcome.payload['receipt_event_ref'] is None and outcome.payload['dispatch_refusal_ref']
        remaining=w.adapter.positions()[0]
        # Existing urgent protection does not require the revoked partial-policy grant.
        receipts=w.router.apply_exits('paper','EURUSD',remaining.stop_price-D('.001'),remaining.stop_price,now_ms=time[0]+1000)
        assert len(receipts)==1 and receipts[0].status=='FILLED' and not w.adapter.positions()
    finally:w.ledger.close()


def test_optional_native_identity_read_unavailable_does_not_gate_actual_protective_close(tmp_path,monkeypatch):
    from vati.execution.base import VenueUnavailable
    from vati.execution.recovery_scope import NativePositionHistory
    from vati.lifecycle.family_membership import original_native_snapshot
    w,store,time,grant,plan,history=admitted_source_world(tmp_path,
        actual_runtime_lease=True,add_child=True,max_quantity='.20')
    try:
        family=w.lifecycle.families.get(plan.snapshot.family_id)
        positions=w.adapter.positions;close=w.adapter.close;calls=[]
        def unavailable():raise VenueUnavailable('synthetic actual venue positions read unavailable')
        def recorded_close(pid,*args,**kwargs):calls.append(pid);return close(pid,*args,**kwargs)
        monkeypatch.setattr(w.adapter,'positions',unavailable)
        monkeypatch.setattr(w.adapter,'close',recorded_close)
        receipts=w.router.apply_exits('paper','EURUSD',D('1.09'),D('1.0902'),now_ms=time[0])
        assert len(calls)==2 and len(receipts)==2 and all(r.status=='FILLED' for r in receipts)
        requests=[e for e in w.ledger.iter(EventKind.EXIT_ATTEMPT) if e.payload.get('state')=='REQUESTED']
        assert len(requests)==2 and all(e.payload['trade_intent_id']=='' for e in requests)
        assert all(w.router.exit_journal.latest('paper',pid).payload['state']=='CONFIRMED' for pid in calls)
        monkeypatch.setattr(w.adapter,'positions',positions)
        assert not positions()
        snapshot=original_native_snapshot(NativePositionHistory(w.ledger,
            account_alias=w.adapter.account_alias,venue='paper'),family,w.adapter)
        assert not snapshot.known and all(leg.remaining is None for leg in snapshot.legs)
        assert not w.lifecycle.reviews and not w.learning.episodes
        assert w.router.apply_exits('paper','EURUSD',D('1.09'),D('1.0902'),now_ms=time[0]+1000)==[]
        assert len(calls)==2  # Attribution uncertainty never licenses a resend.
    finally:w.ledger.close()


@pytest.mark.parametrize('effect_applied',[True,False])
def test_preexisting_independent_unknown_cannot_block_new_mandatory_other_leg_close(tmp_path,monkeypatch,effect_applied):
    w,store,time,grant,plan,history=admitted_source_world(tmp_path,
        actual_runtime_lease=True,add_child=True,max_quantity='.20')
    try:
        family=w.lifecycle.families.get(plan.snapshot.family_id)
        root=w.lifecycle.entries['ti-e2e-1']['broker_position_id'];close=w.adapter.close;calls=[]
        def lost_original_reply(pid,*args,**kwargs):
            calls.append(pid)
            if pid==root and not effect_applied:raise OSError('synthetic original send outcome unknown before observation')
            receipt=close(pid,*args,**kwargs)
            if pid==root:raise OSError('synthetic earlier independent native close reply lost')
            return receipt
        monkeypatch.setattr(w.adapter,'close',lost_original_reply)
        with pytest.raises(OSError):
            w.router.apply_preservation('paper',position_id=root,trade_intent_id='ti-e2e-1',
                action='FULL_CLOSE',now_ms=time[0],reason='EARLIER_INDEPENDENT_FULL')
        original=w.router.exit_journal.latest('paper',root)
        assert original.payload['state']=='REQUESTED' and len(w.adapter.positions())==(1 if effect_applied else 2)
        assert w.router.exit_journal.pending('paper',root).hash==original.hash
        from vati.risk.contracts import KillSwitchTrigger
        assert KillSwitchTrigger.RECONCILIATION_FAILURE in w.router.kill.active
        sibling=next(p for p in w.adapter.positions() if p.position_id!=root)
        w.adapter._positions[sibling.position_id]['stop']=None
        w.lifecycle.family_policy_grant_id=''  # Mandatory protection is independent.
        w.lifecycle.mark('EURUSD',D('1.106'),D('1.1062'),now_ms=time[0]+1000)
        assert len(calls)==2 and calls.count(root)==1
        assert {p.position_id for p in w.adapter.positions()}==(set() if effect_applied else {root})
        assert w.router.exit_journal.latest('paper',root).hash==original.hash
        action=list(FamilyActionJournal(w.ledger).plans())[-1]
        result=FamilyActionJournal(w.ledger).progress(action)
        assert result['state']=='INCOMPLETE' and result['unresolved_native_effect']
        assert result['requested_quantity'] is None and result['residual_quantity'] is None
        bound_root=next(x for x in action.payload['plan']['snapshot']['legs'] if x['position_id']==root)
        assert bound_root['remaining'] is None and original.hash in bound_root['source_refs']
        assert sorted(t['state'] for t in result['targets'])==['CONFIRMED','ORIGINAL_NATIVE_QUANTITY_UNKNOWN']
        assert next(t for t in result['targets'] if t['position_id']==root)['request_ref'] is None
        assert family.net_quantity>D(0) and not w.lifecycle.reviews and not w.learning.episodes
    finally:w.ledger.close()


def test_partial_dispatch_rereads_new_other_leg_unknown_under_current_writer(tmp_path,monkeypatch):
    from vati.lifecycle.family_actions import FamilyActionError
    w,store,time,grant,plan,history=admitted_source_world(tmp_path,
        actual_runtime_lease=True,add_child=True,max_quantity='.20')
    try:
        before={p.position_id:p.quantity for p in w.adapter.positions()}
        sibling=next(p for p in w.adapter.positions() if p.trade_intent_id!='ti-e2e-1')
        apply=w.router.apply_preservation;close=w.adapter.close;injected=[]
        def uncertain(pid,*args,**kwargs):
            if pid==sibling.position_id:raise OSError('synthetic competing original close outcome unknown')
            return close(pid,*args,**kwargs)
        def interposed(*args,**kwargs):
            if not injected:
                injected.append(True)
                with pytest.raises(OSError):
                    apply('paper',position_id=sibling.position_id,trade_intent_id=sibling.trade_intent_id,
                        action='FULL_CLOSE',now_ms=time[0],reason='COMPETING_ORIGINAL_UNKNOWN')
            return apply(*args,**kwargs)
        monkeypatch.setattr(w.adapter,'close',uncertain)
        monkeypatch.setattr(w.router,'apply_preservation',interposed)
        with pytest.raises(FamilyActionError):
            w.lifecycle.request_family_reduction(plan.snapshot.family_id,action_key='partial-with-new-unknown',
                action='PARTIAL_CLOSE',requested_quantity=D('.04'),now_ms=time[0])
        assert not w.adapter.closed
        assert {p.position_id:p.quantity for p in w.adapter.positions()}==before
        assert w.router.exit_journal.pending('paper',sibling.position_id).payload['reason']=='COMPETING_ORIGINAL_UNKNOWN'
        assert not w.lifecycle.reviews and not w.learning.episodes
    finally:w.ledger.close()
