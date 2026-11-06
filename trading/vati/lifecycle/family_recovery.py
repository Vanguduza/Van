"""Recover original native families and their one outcome without new effects."""
from decimal import Decimal

from vati.core.canonical import canonical_hash
from vati.core.events import EventKind
from vati.execution.recovery_scope import NativePositionHistory
from vati.lifecycle.family import FamilyError
from vati.lifecycle.family_actions import FamilyActionError, FamilyPolicy, plan_reduction, exact_decimal
from vati.lifecycle.family_action_journal import FamilyActionJournal
from vati.lifecycle.family_execution import reduce_original_family_receipts
from vati.lifecycle.family_membership import original_native_snapshot
from vati.lifecycle.family_runtime import runtime_fence_ref
from vati.lifecycle.thesis import TradeThesis
from vati.risk.contracts import Direction
from vati.risk.serde import mandate_binding_hash


def current_native_family_eligible(lifecycle, family, history, snapshot):
    """A source runtime selection still needs authentic current admission."""
    if (lifecycle.operational_grants is None or not lifecycle.family_policy_grant_id
            or lifecycle.runtime_lease is None or lifecycle.mandate is None or not snapshot.known):
        return False
    try:
        store=lifecycle.operational_grants
        original=store.latest(lifecycle.family_policy_grant_id)
        if original is None:return False
        admitted=store.current(lifecycle.family_policy_grant_id,expected_ref=original.hash)
        grant=admitted.payload['grant'];root=family.members[0].trade_intent_id
        risk=next(e for e in history.rows if e.kind is EventKind.RISK_DECISION
            and e.correlation_id==root and e.payload.get('decision',{}).get('decision_hash')==history.commands[root][0]['decision_hash'])
        plan=plan_reduction(snapshot,policy=FamilyPolicy(policy_id=grant['policy_id'],version=grant['policy_version'],
            mode='ADMITTED',qualification_ref=grant['qualification_hash']),action='PARTIAL_CLOSE',
            requested_quantity=min(exact_decimal(snapshot.remaining_exact),Decimal('0.00000001')),
            authority_refs=dict(original_mandate_ref=risk.hash,current_mandate_ref=mandate_binding_hash(lifecycle.mandate),
                grant_ref=admitted.hash,lease_ref=str(lifecycle.runtime_lease.epoch),
                fence_ref=runtime_fence_ref(lifecycle.runtime_lease)))
        store.authorize_plan(admitted,plan,history=history,mandate=lifecycle.mandate,
            authority=lifecycle.authority,adapter=lifecycle.adapter,lease_epoch=lifecycle.runtime_lease.epoch,
            fence_ref=runtime_fence_ref(lifecycle.runtime_lease))
        return True
    except (PermissionError,ValueError,KeyError,StopIteration,ArithmeticError):
        return False


def recover_original_native_families(lifecycle, *, now_ms):
    """Include flat families omitted by native open-position enumeration.

    This function only observes and reduces original receipts. A changed lease,
    grant or key does not make an original unknown effect eligible for resend.
    """
    history=NativePositionHistory(lifecycle.ledger,account_alias=lifecycle.adapter.account_alias,
        venue=lifecycle.adapter.venue)
    candidates={e.correlation_id:e for e in history.rows if e.kind is EventKind.POSITION_FAMILY
        and e.producer=='vati-position-family' and e.hash==canonical_hash(e.body())}
    recovered=[];unresolved=[]
    for family_id,event in candidates.items():
        members=event.payload.get('members',[])
        if len({m.get('trade_intent_id') for m in members if m.get('role') in {'ROOT','SCALE_IN','REENTRY'}})<2:
            continue
        try:
            root=members[0]['trade_intent_id'];command,opened=history.commands[root]
            entries=[e for e in history.events(EventKind.EXECUTION_RECEIPT)
                if not e.payload.get('exit_action') and e.correlation_id==root
                and e.payload.get('status') in {'FILLED','PARTIAL'}]
            if len(entries)!=1:raise FamilyActionError('original root native fill is ambiguous')
            family=lifecycle.families.restore(history,family_id=family_id,trade_intent_id=root,
                symbol=command['symbol'],direction=Direction(command['direction']),
                position_id=entries[0].payload['broker_position_id'])
            if family is None:raise FamilyActionError('original native family is unavailable')
            snapshot=original_native_snapshot(history,family,lifecycle.adapter)
            for leg in snapshot.legs:
                payload,opened=history.commands[leg.trade_intent_id]
                receipt=next(e for e in history.events(EventKind.EXECUTION_RECEIPT)
                    if e.hash in leg.source_refs and not e.payload.get('exit_action'))
                risk=next((e for e in history.rows if e.kind is EventKind.RISK_DECISION
                    and e.correlation_id==leg.trade_intent_id and e.payload.get('decision',{}).get('decision_hash')==payload['decision_hash']),None)
                inputs=risk.payload.get('inputs',{}).get('intent',{}) if risk else {}
                row=lifecycle.entries.setdefault(leg.trade_intent_id,{})
                # Scope/identity come from original authenticated owners; current
                # observation only supplies residual quantity and native stop.
                row.update(symbol=payload['symbol'],direction=family.direction,
                    entry=Decimal(str(receipt.payload['average_fill'])),
                    stop=leg.stop,strategy_id=payload['strategy_id'],strategy_version=payload.get('strategy_version',''),
                    strategy_state=inputs.get('strategy_state'),decision_price=Decimal(str(payload['entry_price'])),
                    broker_position_id=leg.position_id,quantity=leg.remaining,quantity_known=leg.remaining is not None,
                    open=leg.remaining is None or leg.remaining>0,pending=False,recovered=True,
                    opened_ms=opened,family_id=family_id,family_root_intent_id=root,
                    family_history_known=True,scale_ins_used=family.scale_ins,
                    cost_pct=lifecycle.modelled_costs.get(family.symbol,lifecycle.contracts[family.symbol].round_trip_cost_pct),
                    original_approved_risk_pct=(risk.payload['decision'].get('approved_risk_pct') if risk else None),
                    protective_stop_confirmed=leg.protection_confirmed,software_stop=payload.get('stop_mode')=='SOFTWARE',
                    fees=receipt.payload.get('fees'))
                row.setdefault('best_price',row['entry']);row.setdefault('worst_price',row['entry'])
            for e in history.rows:
                if e.kind is EventKind.TRADE_THESIS and e.producer=='vati-trade-thesis' and e.correlation_id==root:
                    thesis=TradeThesis.from_payload(e.payload)
                    if not thesis.seal_ok():raise FamilyActionError('original family thesis seal differs')
                    lifecycle.thesis.adopt(thesis)
            snapshot=reduce_original_family_receipts(lifecycle,family_id,now_ms=now_ms)
            if snapshot.known and snapshot.remaining_exact==0:
                from vati.lifecycle.family_outcome import publish_family_outcome
                publish_family_outcome(lifecycle,family_id,reason='ORIGINAL_NATIVE_RECOVERY',now_ms=now_ms)
            else:
                eligible=current_native_family_eligible(lifecycle,family,history,snapshot)
                # Original managed ownership and current native membership can
                # still support mandatory protection when optional allocation
                # admission expires. This grants no partial or ADD authority.
                from vati.risk.mandate_source import validate_mandate_source
                original_risk=next((e for e in history.rows if e.kind is EventKind.RISK_DECISION
                    and e.correlation_id==root and e.payload.get('decision',{}).get('decision_hash')==command['decision_hash']),None)
                protective=False
                if (original_risk is not None and lifecycle.runtime_lease is not None and lifecycle.mandate is not None
                        and lifecycle.mandate.authority_matches_policy() and lifecycle.mandate.owner_keys_current()
                        and lifecycle.mandate.account_alias==lifecycle.adapter.account_alias
                        and lifecycle.mandate.venue==lifecycle.adapter.venue):
                    validate_mandate_source(original_risk.payload['inputs'].get('original_mandate_source'),
                        decision_time_ms=original_risk.event_time_ms,expected_hash=original_risk.payload['decision']['mandate_hash'])
                    protective=True
                for leg in snapshot.legs:
                    lifecycle.entries[leg.trade_intent_id]['family_execution_available']=eligible
                    lifecycle.entries[leg.trade_intent_id]['family_native_protection_available']=protective
                if eligible:lifecycle._family_halts.pop(family_id,None)
                else:lifecycle._family_halts[family_id]=('HEDGED_FAMILY_EXECUTION_UNAVAILABLE',)
                journal=FamilyActionJournal(lifecycle.ledger)
                if any(e.correlation_id==family_id and journal.progress(e)['state']!='COMPLETE' for e in journal.plans()):
                    lifecycle._family_halts[family_id]=('FAMILY_ACTION_RESIDUAL_OR_UNKNOWN',)
                if not snapshot.known:unresolved.append(family_id)
            recovered.append(family_id)
        except (FamilyError,ValueError,KeyError,TypeError,StopIteration,ArithmeticError) as exc:
            lifecycle._family_halts[family_id]=('ORIGINAL_NATIVE_FAMILY_RECOVERY_UNRESOLVED',)
            lifecycle._log(EventKind.SESSION,{'event':'ORIGINAL_NATIVE_FAMILY_RECOVERY_UNRESOLVED',
                'error_type':type(exc).__name__,'detail':str(exc)[:240]},now_ms=now_ms,corr=family_id)
            unresolved.append(family_id)
    return tuple(recovered),tuple(unresolved)
