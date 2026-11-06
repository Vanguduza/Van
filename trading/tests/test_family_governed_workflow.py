"""Synthetic SOURCE admission through real owner/risk/ledger/Paper owners."""
from dataclasses import replace
from decimal import Decimal as D

import pytest

from conftest import mandate_dict, owner_authority
from conftest_owner_authority import OWNER_KEY_ID, owner_keypair
from test_active_trade_e2e import World, _intent, _market_state, SYMBOL, STRATEGY
from vati.authority import OwnerAuthorityVerifier, OwnerAuthorityError, sign_token
from vati.core import EventKind, make_event
from vati.core.canonical import canonical_hash
from vati.execution.paper import PaperCloseContract
from vati.execution.recovery_scope import NativePositionHistory
from vati.lifecycle.family_actions import FamilyPolicy, FamilyActionError, number, plan_reduction
from vati.lifecycle.family_membership import original_native_snapshot
from vati.risk import TradingMandate, RiskAuthority
from vati.risk.mandate_source import capture_mandate_source
from vati.risk.operational_grant import OperationalOptimizationGrants, REQUIRED_GATES, subject, PolicyAdmissionError
from vati.risk.serde import intent_to_dict, snapshot_to_dict, mandate_binding_hash

NOW=1_800_000_000_000


def admitted_source_world(tmp_path, *, actual_runtime_lease=False, add_child=False, max_quantity=".04", policy_version="PROPORTIONAL_FLOOR_V1"):
    w=World(tmp_path)
    raw=mandate_dict(venue='paper',allowed_strategies=[STRATEGY],max_positions_per_instrument=2)
    w.mandate=TradingMandate.from_mapping(raw);w.authority=RiskAuthority(w.mandate)
    w.lifecycle.mandate=w.mandate;w.lifecycle.authority=w.authority;w.lifecycle.mandate_input=raw
    w.adapter.bind_close_contracts({SYMBOL:PaperCloseContract(D('.01'))})
    w.state=_market_state(NOW);intent=_intent(NOW);snapshot=w._snapshot_for(SYMBOL)
    from types import SimpleNamespace
    from vati.app.account_service import AccountCoordinatorService
    runtime=AccountCoordinatorService(SimpleNamespace(mandate=raw),clock=lambda:NOW,adapter=w.adapter)
    runtime._ledger=w.ledger;runtime.authority=w.authority;runtime.mandate=w.mandate
    decision=runtime._risk(intent,snapshot)
    original=next(e for e in w.ledger.iter(EventKind.RISK_DECISION,correlation_id=intent.trade_intent_id))
    assert original.producer=='vati-account-coordinator'
    assert original.payload['inputs']['original_mandate_source']['state']=='ORIGINAL_BOUND'
    receipt=w.router.execute(intent,decision,w.mandate,now_ms=NOW)
    w.lifecycle.record_entry(intent=intent,receipt=receipt,state=w.state,
        modelled_cost_pct=D('.0002'),software_stop=False,decision=decision)
    family=w.lifecycle.families.for_intent(intent.trade_intent_id)
    if add_child:
        from vati.lifecycle.scale_policy import Adjustment, PositionAdjustmentProposal
        from vati.lifecycle.thesis import ThesisState
        w.router.apply_preservation('paper',position_id=receipt.broker_position_id,
            trade_intent_id=intent.trade_intent_id,action='TIGHTEN_STOP',new_stop=receipt.average_fill,now_ms=NOW+1000)
        w.lifecycle.families.tighten_stop(family.family_id,receipt.average_fill,now_ms=NOW+1000)
        row=w.lifecycle.entries[intent.trade_intent_id];row['stop']=receipt.average_fill
        thesis=w.lifecycle.thesis.thesis_for(intent.trade_intent_id)
        half=(decision.approved_risk_pct/2).quantize(D('.00001'))
        proposal=PositionAdjustmentProposal(trade_intent_id=intent.trade_intent_id,symbol=SYMBOL,
            strategy_id=STRATEGY,action=Adjustment.ADD,reasons=('THESIS_STRONGER',),
            rationale='synthetic SOURCE same-family workflow',thesis_state=ThesisState.STRONGER.value,
            thesis_seal=thesis.seal,delta_risk_pct=half,original_approved_risk_pct=decision.approved_risk_pct,
            risk_after_action_pct=half,proposed_ms=NOW+60000)
        w.lifecycle.execute_add_fn=lambda i,d:w.router.execute(i,d,w.mandate,now_ms=NOW+60000)
        w.lifecycle._execute_adjustment(proposal=proposal,row=row,intent_id=intent.trade_intent_id,
            thesis=thesis,family=family,mark=D('1.10600'),now_ms=NOW+60000)
        assert len(w.adapter.positions())==2 and family.scale_ins==1
    history=NativePositionHistory(w.ledger,account_alias=w.adapter.account_alias,venue='paper')
    native=original_native_snapshot(history,family,w.adapter)
    issuer,issuer_pem=owner_keypair();owner=owner_authority();time=[NOW+60000 if add_child else NOW]
    epoch=7;fence='synthetic-current-account-fence'
    if actual_runtime_lease:
        from vati.app.account_lease import AccountRuntimeLease, InMemoryLeaseStore
        from vati.lifecycle.family_runtime import runtime_fence_ref
        lease=AccountRuntimeLease(InMemoryLeaseStore(),account_alias=w.adapter.account_alias,
            instance_id='synthetic-source-runtime',ttl_ms=180000)
        assert lease.acquire(now_ms=NOW).permits_orders
        w.lifecycle.runtime_lease=lease;epoch=lease.epoch;fence=runtime_fence_ref(lease)
    store=OperationalOptimizationGrants(w.ledger,owner_authority=owner.verifier,
        qualification_authority=OwnerAuthorityVerifier({'synthetic-source-issuer':issuer_pem}),clock=lambda:time[0])
    policy=FamilyPolicy(version=policy_version)
    scope=dict(environment='PAPER',account_alias=w.adapter.account_alias,venue='paper',
        native_cohort='paper-native-close-capture/1',strategy_id=STRATEGY,strategy_version='1.0.0',
        native_contract_refs=sorted({leg.close_rules.contract_ref for leg in native.legs}),
        native_capability_refs=sorted({leg.close_rules.evidence_ref for leg in native.legs}))
    qual=dict(policy_id=policy.policy_id,policy_version=policy.version,policy_hash=policy.artifact_hash,
        scope=scope,source_hash=policy.implementation_hash,evidence_refs=['SYNTHETIC_SOURCE_NOT_NATIVE'],
        gates={g:True for g in REQUIRED_GATES},issued_ms=time[0],expires_ms=time[0]+60000,
        issuer_key_id='synthetic-source-issuer',evidence_domain='SOURCE',operations=['PARTIAL_CLOSE','FULL_CLOSE'],
        max_requested_quantity=number(D(max_quantity)),max_family_risk_pct=number(D('.005')))
    grant=dict(grant_id='synthetic-source-only-grant',policy_id=policy.policy_id,policy_version=policy.version,
        policy_hash=policy.artifact_hash,scope=scope,operations=['PARTIAL_CLOSE','FULL_CLOSE'],
        max_requested_quantity=number(D(max_quantity)),max_family_risk_pct=number(D('.005')),
        qualification_hash=canonical_hash(qual),source_hash=policy.implementation_hash,
        evidence_refs=qual['evidence_refs'],activated_ms=time[0],expires_ms=time[0]+60000,
        parent_migration={'mode':'EXPLICIT_ORIGINAL_PARENTS','original_family_revisions':[native.family_revision]},
        lease_epoch=epoch,fence_ref=fence,issuer_key_id=qual['issuer_key_id'],owner_key_id=OWNER_KEY_ID)
    admitted=store.admit(grant,qual,owner_signature=owner.token(act='lifecycle-policy-grant',
        subject=subject(grant),issued_at_unix=time[0]//1000,lifetime_seconds=120),
        qualification_signature=sign_token(issuer,act='lifecycle-policy-qualify',subject=subject(qual),
            key_id=qual['issuer_key_id'],issued_at_unix=time[0]//1000,lifetime_seconds=120))
    policy=replace(policy,mode='ADMITTED',qualification_ref=canonical_hash(qual))
    bindings=dict(original_mandate_ref=original.hash,current_mandate_ref=mandate_binding_hash(w.mandate),
        grant_ref=admitted.hash,lease_ref=str(epoch),fence_ref=grant['fence_ref'])
    plan=plan_reduction(native,policy=policy,action='PARTIAL_CLOSE',requested_quantity=D('.04'),
        explicit_targets=({native.legs[0].position_id:D('.04')} if policy_version=='EXPLICIT_LEGS_V1' else None),authority_refs=bindings)
    w.lifecycle.operational_grants=store;w.lifecycle.family_policy_grant_id=grant['grant_id']
    return w,store,time,admitted,plan,history


def authorize(w,store,admitted,plan,history):
    return store.authorize_plan(admitted,plan,history=history,mandate=w.mandate,authority=w.authority,
        adapter=w.adapter,lease_epoch=7,fence_ref='synthetic-current-account-fence')


def test_real_current_mandate_original_source_and_independent_issuer_join(tmp_path):
    w,store,time,admitted,plan,history=admitted_source_world(tmp_path)
    try:
        assert authorize(w,store,admitted,plan,history) is None
        assert len(w.adapter.positions())==1  # Qualification is not a sender.
    finally:w.ledger.close()


@pytest.mark.parametrize('damage',['environment','account','venue','cohort','contract','policy','grant','mandate','lease','migration'])
def test_current_effect_context_cannot_borrow_an_admitted_grants_scope(tmp_path,damage,monkeypatch):
    w,store,time,admitted,plan,history=admitted_source_world(tmp_path)
    try:
        if damage in {'environment','cohort','contract'}:
            capture=w.adapter.close_capability_capture
            def changed(pid):
                body=capture(pid)
                if damage=='environment':body['environment']='LIVE'
                elif damage=='cohort':body['schema']='unqualified-other-cohort'
                else:body['contract_ref']='other-contract'
                return body
            monkeypatch.setattr(w.adapter,'close_capability_capture',changed)
        elif damage=='account':w.adapter.account_alias='foreign-account'
        elif damage=='venue':w.adapter.venue='mt5'
        elif damage=='policy':plan=replace(plan,policy=replace(plan.policy,mode='SHADOW'))
        elif damage=='grant':plan=replace(plan,authority_refs=tuple((k,'foreign-grant' if k=='grant_ref' else v) for k,v in plan.authority_refs))
        elif damage=='lease':plan=replace(plan,authority_refs=tuple((k,'8' if k=='lease_ref' else v) for k,v in plan.authority_refs))
        elif damage=='migration':plan=replace(plan,snapshot=replace(plan.snapshot,family_revision='another-original-family'))
        else:w.mandate=replace(w.mandate,max_risk_per_trade=D('.01'))
        with pytest.raises(PolicyAdmissionError):authorize(w,store,admitted,plan,history)
    finally:w.ledger.close()


def test_admitted_partial_effect_is_exact_durable_and_original_receipt_replays_after_revoke(tmp_path):
    from vati.lifecycle.family_action_journal import FamilyActionJournal
    from vati.lifecycle.family_execution import execute_original_action, reduce_original_receipts
    w,store,time,admitted,plan,history=admitted_source_world(tmp_path)
    try:
        action=FamilyActionJournal(w.ledger).prepare(plan,action_key='source-original-partial',now_ms=NOW)
        before=w.adapter.positions()[0].quantity
        progress=execute_original_action(w.lifecycle,action,grants=store,mandate=w.mandate,
            authority=w.authority,lease_epoch=7,fence_ref='synthetic-current-account-fence',
            lease_fence=lambda epoch:epoch==7,now_ms=NOW+1000)
        assert progress['state']=='COMPLETE' and D(progress['confirmed_quantity'])==D('.04')
        assert w.adapter.positions()[0].quantity==before-D('.04')
        family=w.lifecycle.families.for_intent('ti-e2e-1')
        net=family.net_quantity;members=len(family.members);closed=len(w.adapter.closed)
        revoke_body={'grant_id':admitted.payload['grant_id'],'expected_ref':admitted.hash}
        store.revoke(admitted.payload['grant_id'],expected_ref=admitted.hash,
            owner_signature=owner_authority().token(act='lifecycle-policy-revoke',subject=subject(revoke_body),issued_at_unix=NOW//1000))
        time[0]=NOW+120000
        reduce_original_receipts(w.lifecycle,action,now_ms=time[0])
        recovered=execute_original_action(w.lifecycle,action,grants=store,mandate=w.mandate,
            authority=w.authority,lease_epoch=7,fence_ref='synthetic-current-account-fence',
            lease_fence=lambda epoch:False,now_ms=time[0])
        assert recovered['state']=='COMPLETE'
        assert family.net_quantity==net and len(family.members)==members and len(w.adapter.closed)==closed
    finally:w.ledger.close()


def test_real_lifecycle_caller_uses_its_actual_runtime_owner_and_retains_exact_request(tmp_path):
    w,store,time,admitted,plan,history=admitted_source_world(tmp_path,actual_runtime_lease=True)
    try:
        family_id=plan.snapshot.family_id
        preview=w.lifecycle.request_family_reduction(family_id,action_key='real-owner-caller',
            action='PARTIAL_CLOSE',requested_quantity=D('.04'),now_ms=NOW,preview=True)
        assert preview['execution_authority'] is False and not w.adapter.closed
        result=w.lifecycle.request_family_reduction(family_id,action_key='real-owner-caller',
            action='PARTIAL_CLOSE',requested_quantity=D('.04'),now_ms=NOW+1000)
        assert result['state']=='COMPLETE' and D(result['confirmed_quantity'])==D('.04')
        with pytest.raises(FamilyActionError,match='original family request payload differs'):
            w.lifecycle.request_family_reduction(family_id,action_key='real-owner-caller',
                action='PARTIAL_CLOSE',requested_quantity=D('.03'),now_ms=NOW+2000)
        before=len(w.adapter.closed)
        time[0]=NOW+120000
        replay=w.lifecycle.request_family_reduction(family_id,action_key='real-owner-caller',
            action='PARTIAL_CLOSE',requested_quantity=D('.04'),now_ms=time[0])
        assert replay==result and len(w.adapter.closed)==before
    finally:w.ledger.close()


def test_real_add_then_proportional_residual_then_all_native_legs_close_once(tmp_path):
    from vati.lifecycle.family_outcome import publish_family_outcome
    from vati.lifecycle.family_action_journal import FamilyActionJournal
    w,store,time,admitted,plan,history=admitted_source_world(tmp_path,
        actual_runtime_lease=True,add_child=True,max_quantity='.20')
    try:
        family=w.lifecycle.families.get(plan.snapshot.family_id)
        before={p.position_id:p.quantity for p in w.adapter.positions()}
        partial=w.lifecycle.request_family_reduction(family.family_id,action_key='two-leg-partial',
            action='PARTIAL_CLOSE',requested_quantity=D('.04'),now_ms=time[0])
        assert partial['state']=='INCOMPLETE' and D(partial['residual_quantity'])==D('.01')
        assert D(partial['confirmed_quantity'])==D('.03')
        assert sorted(before[p.position_id]-p.quantity for p in w.adapter.positions())==[D('.01'),D('.02')]
        assert publish_family_outcome(w.lifecycle,family.family_id,reason='PARTIAL',now_ms=time[0]) is None
        assert not w.lifecycle.reviews
        time[0]+=1000
        full=w.lifecycle.request_family_reduction(family.family_id,action_key='two-leg-full',
            action='FULL_CLOSE',now_ms=time[0])
        assert full['state']=='COMPLETE' and D(full['residual_quantity'])==0
        assert not w.adapter.positions() and family.net_quantity==0
        event=publish_family_outcome(w.lifecycle,family.family_id,reason='FULL_FAMILY',now_ms=time[0])
        assert event.kind is EventKind.TRADE_REVIEW
        assert event.correlation_id=='ti-e2e-1' and len(w.lifecycle.reviews)==1
        episodes=list(w.ledger.iter(EventKind.TRADE_EXPERIENCE_ARTIFACT,correlation_id='ti-e2e-1'))
        assert len(episodes)==1
        assert episodes[0].payload['review']['learning_unit']=='POSITION_FAMILY'
        assert len(episodes[0].payload['execution']['family_native_legs'])==2
        child_ids={leg['trade_intent_id'] for leg in event.payload['family_outcome']['legs']}-{'ti-e2e-1'}
        assert not any(list(w.ledger.iter(EventKind.TRADE_EXPERIENCE_ARTIFACT,correlation_id=iid)) for iid in child_ids)
        assert event.payload['artifact_hash']==canonical_hash({k:v for k,v in event.payload.items() if k!='artifact_hash'})
        assert event.payload['family_outcome']['child_learning_trials']==0
        assert len(event.payload['family_outcome']['legs'])==2
        assert D(str(event.payload['initial_money_risk']))==D('40')
        assert D(str(event.payload['pnl']))==sum((row['pnl'] for row in w.adapter.closed),D(0))
        original=event.hash;closed=len(w.adapter.closed)
        assert publish_family_outcome(w.lifecycle,family.family_id,reason='REPLAY',now_ms=time[0]+1).hash==original
        assert len(w.lifecycle.reviews)==1 and len(w.adapter.closed)==closed
        assert len(list(w.ledger.iter(EventKind.TRADE_EXPERIENCE_ARTIFACT,correlation_id='ti-e2e-1')))==1
        assert FamilyActionJournal(w.ledger).progress(FamilyActionJournal(w.ledger).find(family.family_id,'two-leg-partial'))['state']=='INCOMPLETE'
    finally:w.ledger.close()


def test_explicit_original_targets_need_distinct_exact_signed_authority_and_replay_once(tmp_path):
    w,store,time,admitted,plan,history=admitted_source_world(tmp_path,
        actual_runtime_lease=True,policy_version='EXPLICIT_LEGS_V1')
    try:
        fid=plan.snapshot.family_id;pid=w.adapter.positions()[0].position_id
        request=dict(action='PARTIAL_CLOSE',requested_quantity=D('.04'),explicit_targets={pid:D('.04')})
        preview=w.lifecycle.request_family_reduction(fid,action_key='explicit-original',preview=True,
            now_ms=time[0],**request)
        assert preview['execution_authority'] is False and len(w.adapter.positions())==1
        with pytest.raises((PolicyAdmissionError,OwnerAuthorityError,ValueError)):
            w.lifecycle.request_family_reduction(fid,action_key='explicit-original',now_ms=time[0],**request)
        signed=owner_authority().token(act='lifecycle-explicit-targets',
            subject=subject({'grant_ref':admitted.hash,'plan_hash':preview['plan_hash']}),
            issued_at_unix=time[0]//1000)
        before=w.adapter.positions()[0].quantity
        wrong=dict(request,requested_quantity=D('.03'),explicit_targets={pid:D('.03')})
        with pytest.raises((PolicyAdmissionError,OwnerAuthorityError,ValueError)):
            w.lifecycle.request_family_reduction(fid,action_key='wrong-exact-payload',
                explicit_signature=signed,now_ms=time[0],**wrong)
        result=w.lifecycle.request_family_reduction(fid,action_key='explicit-original',
            explicit_signature=signed,now_ms=time[0],**request)
        assert result['state']=='COMPLETE' and w.adapter.positions()[0].quantity==before-D('.04')
        closed=len(w.adapter.closed);time[0]+=300000
        assert w.lifecycle.request_family_reduction(fid,action_key='explicit-original',
            explicit_signature=signed,now_ms=time[0],**request)==result
        assert len(w.adapter.closed)==closed
    finally:w.ledger.close()
