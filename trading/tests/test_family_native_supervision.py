"""Actual mark caller over synthetic SOURCE-admitted native Paper legs."""
from decimal import Decimal as D
from test_family_governed_workflow import admitted_source_world
from vati.core import EventKind


def test_mark_supervises_once_and_records_independent_native_stop_evidence(tmp_path):
    w,store,time,grant,plan,history=admitted_source_world(tmp_path,actual_runtime_lease=True,add_child=True,max_quantity='.20')
    try:
        family=w.lifecycle.families.get(plan.snapshot.family_id)
        before=len(list(w.ledger.iter(EventKind.PRESERVATION_ACTION)))
        w.lifecycle.mark('EURUSD',D('1.106'),D('1.1062'),now_ms=time[0])
        actions=list(w.ledger.iter(EventKind.PRESERVATION_ACTION))
        envelopes=list(w.ledger.iter(EventKind.POSITION_RISK_ENVELOPE))
        assert len(actions)==before+1
        env=envelopes[-1].payload
        assert len(env['leg_protections'])==2 and all(p['confirmed'] for p in env['leg_protections'])
        assert env['current_stop'] is None and env['protected_profit_credit']=='0'
        assert family.scale_ins==1 and len(w.adapter.positions())==2
    finally:w.ledger.close()


def test_missing_native_stop_forces_full_family_close_without_partial_policy_admission(tmp_path):
    w,store,time,grant,plan,history=admitted_source_world(tmp_path,actual_runtime_lease=True,add_child=True,max_quantity='.20')
    try:
        positions=w.adapter.positions();pid=positions[-1].position_id
        # The actual simulator native owner loses a stop; a remembered manager
        # rule must not replace this observed absence.
        w.adapter._positions[pid]["stop"]=None
        w.lifecycle.family_policy_grant_id=''
        w.lifecycle.mark('EURUSD',D('1.106'),D('1.1062'),now_ms=time[0])
        assert not w.adapter.positions()
        assert len(w.lifecycle.reviews)==1 and len(w.learning.episodes)==1
        actions=list(w.ledger.iter(EventKind.PRESERVATION_ACTION))
        assert actions[-1].payload['kind']=='FULL_CLOSE' and 'UNPROTECTED' in actions[-1].payload['reasons']
        w.lifecycle.mark('EURUSD',D('1.106'),D('1.1062'),now_ms=time[0]+1000)
        assert len(w.lifecycle.reviews)==1 and len(w.learning.episodes)==1
    finally:w.ledger.close()


def test_cold_recovery_restores_original_membership_and_full_native_targets(tmp_path):
    from vati.lifecycle.family import FamilyRegistry
    w,store,time,grant,plan,history=admitted_source_world(tmp_path,actual_runtime_lease=True,add_child=True,max_quantity='.20')
    try:
        fid=plan.snapshot.family_id
        w.lifecycle.entries.clear();w.lifecycle.families=FamilyRegistry(ledger=w.ledger)
        restored,unresolved=w.lifecycle.recover_from_venue()
        assert len(restored)==2 and not unresolved
        family=w.lifecycle.families.get(fid)
        assert family.scale_ins==1 and family.net_quantity==sum(p.quantity for p in w.adapter.positions())
        assert all(row['family_execution_available'] for row in w.lifecycle.entries.values())
        result=w.lifecycle.request_family_reduction(fid,action_key='cold-original-full',action='FULL_CLOSE',now_ms=time[0])
        assert result['state']=='COMPLETE' and not w.adapter.positions()
        assert len(w.lifecycle.reviews)==1 and len(w.learning.episodes)==1
    finally:w.ledger.close()


def test_cold_flat_recovery_reduces_original_receipts_and_consumes_once_after_policy_expiry(tmp_path,monkeypatch):
    from vati.lifecycle.family import FamilyRegistry
    from vati.lifecycle.family_action_journal import FamilyActionJournal
    import vati.lifecycle.family_outcome as outcomes
    w,store,time,grant,plan,history=admitted_source_world(tmp_path,actual_runtime_lease=True,add_child=True,max_quantity='.20')
    try:
        publish=outcomes.publish_family_outcome
        monkeypatch.setattr(outcomes,'publish_family_outcome',lambda *a,**k:None)
        result=w.lifecycle.request_family_reduction(plan.snapshot.family_id,action_key='closed-before-consumer-crash',action='FULL_CLOSE',now_ms=time[0])
        assert result['state']=='COMPLETE' and not w.lifecycle.reviews
        monkeypatch.setattr(outcomes,'publish_family_outcome',publish)
        w.lifecycle.entries.clear();w.lifecycle.families=FamilyRegistry(ledger=w.ledger)
        time[0]+=300000
        restored,unresolved=w.lifecycle.recover_from_venue()
        assert not restored and not unresolved
        assert len(w.lifecycle.reviews)==1 and len(w.learning.episodes)==1
        assert not w.adapter.positions()
        w.lifecycle.entries.clear();w.lifecycle.families=FamilyRegistry(ledger=w.ledger)
        w.lifecycle.recover_from_venue()
        assert len(w.lifecycle.reviews)==1 and len(w.learning.episodes)==1
        assert len(list(w.ledger.iter(EventKind.TRADE_REVIEW)))==1
    finally:w.ledger.close()


def test_independent_tighten_rechecks_current_lease_before_each_native_effect(tmp_path,monkeypatch):
    from vati.execution.recovery_scope import NativePositionHistory
    from vati.lifecycle.family_membership import original_native_snapshot
    from vati.lifecycle.family_supervision import tighten_native_legs
    w,store,time,grant,plan,history=admitted_source_world(tmp_path,actual_runtime_lease=True,add_child=True,max_quantity='.20')
    try:
        family=w.lifecycle.families.get(plan.snapshot.family_id)
        snapshot=original_native_snapshot(NativePositionHistory(w.ledger,
            account_alias=w.adapter.account_alias,venue='paper'),family,w.adapter)
        modify=w.adapter.modify_stop;calls=[]
        def advance_after_effect(pid,*args,**kwargs):
            calls.append(pid);result=modify(pid,*args,**kwargs);time[0]+=300000;return result
        monkeypatch.setattr(w.adapter,'modify_stop',advance_after_effect)
        tighten_native_legs(w.lifecycle,family,snapshot,D('1.105'),now_ms=time[0])
        assert len(calls)==1
        stops={p.position_id:p.stop_price for p in w.adapter.positions()}
        assert stops[calls[0]]==D('1.105')
        untouched=next(leg for leg in snapshot.legs if leg.position_id!=calls[0])
        assert stops[untouched.position_id]==untouched.stop
        assert w.lifecycle._family_halts[family.family_id]==('NATIVE_LEG_STOP_UNRESOLVED',)
    finally:w.ledger.close()


def test_cold_optional_policy_expiry_does_not_disable_existing_mandatory_family_protection(tmp_path):
    from vati.lifecycle.family import FamilyRegistry
    w,store,time,grant,plan,history=admitted_source_world(tmp_path,actual_runtime_lease=True,add_child=True,max_quantity='.20')
    try:
        time[0]+=61000  # Grant expired; current runtime lease still valid.
        w.lifecycle.entries.clear();w.lifecycle.families=FamilyRegistry(ledger=w.ledger)
        restored,unresolved=w.lifecycle.recover_from_venue()
        assert len(restored)==2 and not unresolved
        assert all(not row['family_execution_available'] and row['family_native_protection_available']
            for row in w.lifecycle.entries.values())
        pid=w.adapter.positions()[-1].position_id;w.adapter._positions[pid]['stop']=None
        w.lifecycle.mark('EURUSD',D('1.106'),D('1.1062'),now_ms=time[0])
        assert not w.adapter.positions() and len(w.lifecycle.reviews)==1
        assert len(w.learning.episodes)==1
    finally:w.ledger.close()


def test_cold_expired_optional_policy_keeps_independent_native_stops_in_one_original_trial(tmp_path):
    from vati.lifecycle.family import FamilyRegistry
    w,store,time,grant,plan,history=admitted_source_world(tmp_path,actual_runtime_lease=True,add_child=True,max_quantity='.20')
    try:
        time[0]+=61000
        w.lifecycle.entries.clear();w.lifecycle.families=FamilyRegistry(ledger=w.ledger)
        w.lifecycle.recover_from_venue()
        root=w.lifecycle.entries['ti-e2e-1']['broker_position_id']
        w.adapter._positions[root]['stop']=D('1.105')
        w.lifecycle.mark('EURUSD',D('1.104'),D('1.1042'),now_ms=time[0])
        assert len(w.adapter.positions())==1 and not w.lifecycle.reviews and not w.learning.episodes
        remaining=w.adapter.positions()[0]
        w.lifecycle.mark('EURUSD',remaining.stop_price-D('.001'),remaining.stop_price,now_ms=time[0]+1000)
        assert not w.adapter.positions() and len(w.lifecycle.reviews)==1, {'states':[(e.payload.get('event'),e.payload.get('state'),e.payload.get('detail')) for e in w.ledger.iter(EventKind.SESSION)],'rows':[(k,v.get('open'),v.get('quantity'),v.get('family_native_protection_available')) for k,v in w.lifecycle.entries.items()],'quantity':w.lifecycle.families.get(plan.snapshot.family_id).net_quantity}
        assert len(w.learning.episodes)==1 and len(list(w.ledger.iter(EventKind.TRADE_REVIEW)))==1
    finally:w.ledger.close()
