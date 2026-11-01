"""One existing preservation/expansion decision over original native legs.

Each leg supplies its own health and protection evidence. Family economics
never stand in for confirmation that every native stop still exists.
"""
from decimal import Decimal

from vati.core.canonical import canonical_hash
from vati.core.events import EventKind
from vati.execution.recovery_scope import NativePositionHistory
from vati.lifecycle.family_actions import FamilyActionError
from vati.lifecycle.family_execution import reduce_original_family_receipts
from vati.lifecycle.family_membership import original_native_snapshot
from vati.lifecycle.family_protection import mandatory_family_close
from vati.lifecycle.preservation import ActionKind, Urgency
from vati.lifecycle.trade_health import PositionHealthInputs
from vati.risk.contracts import Direction, LossModel

ZERO=Decimal(0)


def tighten_native_legs(lifecycle, family, snapshot, new_stop, *, now_ms):
    """Tighten independently under the existing owner and current runtime fence."""
    if lifecycle.runtime_lease is None or lifecycle.mandate is None:
        raise FamilyActionError('native family protection runtime owner is unavailable')
    epoch=lifecycle.runtime_lease.epoch
    clock=(lifecycle.operational_grants.clock if lifecycle.operational_grants is not None else lifecycle.router.clock)
    if not callable(clock):raise FamilyActionError('current native protection clock is unavailable')
    for original_leg in snapshot.legs:
        if original_leg.remaining is None or original_leg.remaining<=ZERO:
            continue
        try:
            with lifecycle.mandate.owner_authority_submission_guard() as owner_current:
                if not owner_current:raise FamilyActionError('current native protection owner is unavailable')
                with lifecycle.runtime_lease.submission_guard(epoch,now_ms=clock()) as held:
                    if held is not True:raise FamilyActionError('native family protection runtime lease is unavailable')
                    history=NativePositionHistory(lifecycle.ledger,account_alias=lifecycle.adapter.account_alias,
                        venue=lifecycle.adapter.venue)
                    current=original_native_snapshot(history,lifecycle.families.get(family.family_id),lifecycle.adapter)
                    leg=next((x for x in current.legs if x.position_id==original_leg.position_id
                        and x.trade_intent_id==original_leg.trade_intent_id),None)
                    if leg is None or leg.remaining is None or leg.remaining<=ZERO or leg.stop is None:
                        continue
                    tighter=(new_stop>leg.stop if family.direction is Direction.LONG else new_stop<leg.stop)
                    if not tighter:continue
                    if not lifecycle.runtime_lease.fence(epoch,now_ms=clock()):
                        raise FamilyActionError('current native stop dispatch fence refused effect')
                    receipt=lifecycle.router.apply_preservation(lifecycle.adapter.venue,
                        position_id=leg.position_id,trade_intent_id=leg.trade_intent_id,
                        action='TIGHTEN_STOP',new_stop=new_stop,now_ms=now_ms,
                        reason='ORIGINAL_NATIVE_FAMILY_PROTECTION')
                    if receipt is None or receipt.status not in {'REJECTED','CANCELLED','EXPIRED','UNKNOWN'}:
                        row=lifecycle.entries.get(leg.trade_intent_id)
                        if row is not None:row['stop']=new_stop
        except Exception as exc:
            lifecycle._family_halts[family.family_id]=('NATIVE_LEG_STOP_UNRESOLVED',)
            lifecycle._log(EventKind.SESSION,{'event':'NATIVE_LEG_STOP_UNRESOLVED',
                'position_id':original_leg.position_id,'error_type':type(exc).__name__},
                now_ms=now_ms,corr=family.family_id)


def supervise_native_family(lifecycle, family, *, bid, ask, equity, now_ms):
    root=family.members[0].trade_intent_id
    row=lifecycle.entries.get(root)
    # Retain the explicit legacy recovery hold; no rollout/admission inferred.
    if row is None or (row.get('family_execution_available') is False and not row.get('family_native_protection_available')) or lifecycle.runtime_lease is None:
        lifecycle._family_halts[family.family_id]=('HEDGED_FAMILY_EXECUTION_UNAVAILABLE',)
        return
    try:
        snapshot=reduce_original_family_receipts(lifecycle,family.family_id,now_ms=now_ms)
        if not family.is_open:
            from vati.lifecycle.family_outcome import publish_family_outcome
            publish_family_outcome(lifecycle,family.family_id,reason='ORIGINAL_NATIVE_CLOSE',now_ms=now_ms)
            return
        history=NativePositionHistory(lifecycle.ledger,account_alias=lifecycle.adapter.account_alias,
            venue=lifecycle.adapter.venue)
        mark=bid if family.direction is Direction.LONG else ask
        healths=[]
        for leg in snapshot.legs:
            if leg.remaining==ZERO:
                continue
            member=lifecycle.entries.get(leg.trade_intent_id)
            command=history.commands.get(leg.trade_intent_id)
            if member is None or command is None or command[0].get('protective_stop') is None:
                raise FamilyActionError('original native health input is unavailable')
            member['best_price']=(max(Decimal(str(member.get('best_price',mark))),mark)
                if family.direction is Direction.LONG else min(Decimal(str(member.get('best_price',mark))),mark))
            member['worst_price']=(min(Decimal(str(member.get('worst_price',mark))),mark)
                if family.direction is Direction.LONG else max(Decimal(str(member.get('worst_price',mark))),mark))
            healths.append(lifecycle.trade_health.assess(PositionHealthInputs(
                trade_intent_id=leg.trade_intent_id,symbol=family.symbol,direction=family.direction,
                entry_price=Decimal(str(member['entry'])),current_price=mark,
                original_stop=Decimal(str(command[0]['protective_stop'])),current_stop=leg.stop,
                has_confirmed_stop=leg.protection_confirmed,opened_ms=int(member.get('opened_ms') or now_ms),
                now_ms=now_ms,expected_horizon_ms=int(member.get('expected_horizon_ms') or 0),
                worst_price=member['worst_price'],best_price=member['best_price'],spread=max(ZERO,ask-bid))))
        if not healths:
            raise FamilyActionError('no original native family health inputs')
        health=max(healths,key=lambda h:(h.state.rank,'GIVE_BACK' in h.reasons,h.mfe_r))
        contract=lifecycle.contracts[family.symbol.upper()]
        vpu=contract.value_per_price_unit_per_lot if contract.loss_model is LossModel.STOP_DISTANCE else Decimal(1)
        envelope=lifecycle.envelope_calculator.compute_native(family,snapshot,mark=mark,
            value_per_price_unit=vpu,equity=equity,now_ms=now_ms)
        action=lifecycle.preservation.evaluate(family=family,health=health,envelope=envelope,mark=mark,now_ms=now_ms)
        if action.blocks_new_risk:lifecycle._family_halts[family.family_id]=action.reasons or (action.kind.value,)
        elif snapshot.known and row.get('family_execution_available') is not False:
            from vati.lifecycle.family_action_journal import FamilyActionJournal
            journal=FamilyActionJournal(lifecycle.ledger)
            if any(e.correlation_id==family.family_id and journal.progress(e)['state']!='COMPLETE'
                    for e in journal.plans()):
                lifecycle._family_halts[family.family_id]=('FAMILY_ACTION_RESIDUAL_OR_UNKNOWN',)
            else:lifecycle._family_halts.pop(family.family_id,None)
        if action.kind is ActionKind.FULL_CLOSE:
            result=mandatory_family_close(lifecycle,action,now_ms=now_ms)
            if result['state']!='COMPLETE':
                lifecycle._family_halts[family.family_id]=('FAMILY_ACTION_RESIDUAL_OR_UNKNOWN',)
            if family.net_quantity==ZERO:
                from vati.lifecycle.family_outcome import publish_family_outcome
                publish_family_outcome(lifecycle,family.family_id,reason=action.kind.value,now_ms=now_ms)
            return
        if action.kind is ActionKind.PARTIAL_CLOSE:
            lifecycle.request_family_reduction(family.family_id,action_key='preservation:'+action.digest,
                action=action.kind.value,requested_quantity=family.net_quantity*action.close_fraction,now_ms=now_ms)
        elif action.kind is ActionKind.TIGHTEN_STOP:
            tighten_native_legs(lifecycle,family,snapshot,action.new_stop,now_ms=now_ms)
        # A scalar at the root's entry is used only to tell the existing
        # proposal owner that every independently confirmed native leg is at
        # break-even. It never certifies native protection or feeds the envelope.
        all_break_even=snapshot.known and all(leg.remaining==ZERO or (
            leg.protection_confirmed and leg.stop is not None and
            (leg.stop>=Decimal(str(lifecycle.entries[leg.trade_intent_id]['entry']))
             if family.direction is Direction.LONG else
             leg.stop<=Decimal(str(lifecycle.entries[leg.trade_intent_id]['entry'])))) for leg in snapshot.legs)
        proposal_stop=Decimal(str(row['entry'])) if all_break_even else None
        # Thesis is assessed once for the original family, before expansion.
        assessment=lifecycle._assess_thesis(intent_id=root,row=row,health=health,mark=mark,
            current_stop=proposal_stop,now_ms=now_ms)
        if assessment is not None:
            lifecycle._adjust(assessment=assessment,health=health,row=row,intent_id=root,
                family=family,mark=mark,current_stop=proposal_stop,now_ms=now_ms)
        lifecycle.expansion.evaluate(family=family,strategy_id=str(row.get('strategy_id') or ''),
            policy=lifecycle.scale_policies.policy_for(str(row.get('strategy_id') or '')),
            health=health,envelope=envelope,preservation=action,root_quantity=family.members[0].quantity,
            last_scale_ms=None,in_event_window=False,now_ms=now_ms)
    except (PermissionError,FamilyActionError,ValueError,KeyError,ArithmeticError) as exc:
        lifecycle._family_halts[family.family_id]=('ORIGINAL_NATIVE_FAMILY_SUPERVISION_UNRESOLVED',)
        lifecycle._log(EventKind.SESSION,{'event':'ORIGINAL_NATIVE_FAMILY_SUPERVISION_UNRESOLVED',
            'error_type':type(exc).__name__,'detail':str(exc)[:240]},now_ms=now_ms,corr=family.family_id)


def execute_native_family_adjustment(lifecycle, family, proposal, *, now_ms):
    """Retain the existing proposal owner, dispatch only original native targets."""
    from vati.lifecycle.scale_policy import Adjustment
    if proposal.action is Adjustment.MOVE_PROTECTION:
        if proposal.new_stop is None:return
        history=NativePositionHistory(lifecycle.ledger,account_alias=lifecycle.adapter.account_alias,
            venue=lifecycle.adapter.venue)
        snapshot=original_native_snapshot(history,family,lifecycle.adapter)
        tighten_native_legs(lifecycle,family,snapshot,proposal.new_stop,now_ms=now_ms)
    elif proposal.action is Adjustment.EXIT:
        # This is the existing deterministic thesis/preservation owner, not a
        # partial-policy admission or a request that can expand exposure.
        action=lifecycle.preservation._act(family,ActionKind.FULL_CLOSE,Urgency.IMMEDIATE,
            ('THESIS_INVALIDATED',),now_ms,detail='original family thesis exit: '+proposal.thesis_state)
        result=mandatory_family_close(lifecycle,action,now_ms=now_ms)
        if result['state']!='COMPLETE':lifecycle._family_halts[family.family_id]=('FAMILY_ACTION_RESIDUAL_OR_UNKNOWN',)
        if family.net_quantity==ZERO:
            from vati.lifecycle.family_outcome import publish_family_outcome
            publish_family_outcome(lifecycle,family.family_id,reason='THESIS_EXIT',now_ms=now_ms)
    else:
        quantity=family.net_quantity*Decimal(str(proposal.size_fraction or ZERO))
        if quantity>ZERO:
            lifecycle.request_family_reduction(family.family_id,action_key='thesis:'+canonical_hash(proposal.body()),
                action='PARTIAL_CLOSE',requested_quantity=quantity,now_ms=now_ms)
