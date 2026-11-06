"""Family-native orchestration inside the existing lifecycle/router owners.

No second sender, mandate, budget or promotion authority. Plans bind original
legs; current eligibility is checked for new effects and original receipts are
reduced once independently of later eligibility.
"""
from contextlib import contextmanager
from decimal import Decimal

from vati.core.events import EventKind
from vati.execution.recovery_scope import NativePositionHistory
from vati.lifecycle.family import FamilyMember, MemberRole
from vati.lifecycle.family_actions import FamilyActionError, plan_from_body
from vati.lifecycle.family_action_journal import FamilyActionJournal, target_ref
from vati.lifecycle.family_membership import original_native_snapshot


def reduce_original_receipts(lifecycle, action, *, now_ms):
    """Original effects remain facts after policy expiry/revocation/restart."""
    journal=FamilyActionJournal(lifecycle.ledger)
    family=lifecycle.families.get(action.correlation_id)
    for target in action.payload['plan']['targets']:
        attempt,outcome=journal.target_outcome(action,target)
        if outcome is None or not outcome.payload.get('receipt_event_ref'):
            continue
        receipt=next((e for e in lifecycle.ledger.iter(EventKind.EXECUTION_RECEIPT)
            if e.hash==outcome.payload['receipt_event_ref']),None)
        # progress validates the original request/receipt seals and scope first.
        journal.progress(action)
        qty=Decimal(str(receipt.payload['filled_qty']))
        if qty<=0:
            continue
        price=receipt.payload.get('average_fill')
        if price is None:
            continue
        member_id='family-native-receipt:'+receipt.payload['receipt_hash']
        if any(m.member_id==member_id for m in family.members):
            continue
        lifecycle.families.apply(family.family_id,FamilyMember(member_id,
            MemberRole.FULL_EXIT if qty==family.net_quantity else MemberRole.PARTIAL_EXIT,
            qty,Decimal(str(price)),receipt.received_time_ms,
            trade_intent_id=target['trade_intent_id']),now_ms=now_ms)
        row=lifecycle.entries.get(target['trade_intent_id'])
        if row is not None:
            # Recovery may already have loaded the residual native quantity.
            # Never subtract the same original receipt from that observation.
            native=next((p for p in lifecycle.adapter.positions()
                if p.position_id==target['position_id'] and p.trade_intent_id==target['trade_intent_id']),None)
            if native is not None:
                row['quantity']=native.quantity
                row['open']=True
            elif outcome.payload['state'] in {'CONFIRMED','PARTIAL_CONFIRMED'} and target['action']=='FULL_CLOSE':
                row['quantity']=Decimal(0);row['open']=False
            else:
                row['quantity_known']=False
            row['pending']=False


def execute_original_action(lifecycle, action, *, grants, mandate, authority,
                            lease_epoch, fence_ref, lease_fence,
                            explicit_signature=None, lease_submission_guard=None, mandatory_guard=None, now_ms):
    """Dispatch remaining original targets; never derive a new target on replay."""
    journal=FamilyActionJournal(lifecycle.ledger)
    observed=next((e for e in journal.plans() if e.hash==action.hash),None)
    if observed is None:
        raise FamilyActionError('family action has no original committed identity')
    action=observed;plan=plan_from_body(action.payload['plan'])
    # Reduce observed facts even when no current grant exists anymore.
    reduce_original_receipts(lifecycle,action,now_ms=now_ms)
    remaining=[target for target in plan.targets
        if target.quantity>0 and journal.target_attempt(action,target.body()) is None]
    if not remaining:
        # Original result recovery is independent of today's admission state.
        return journal.progress(action)
    binding=dict(plan.authority_refs)
    grant=None
    if mandatory_guard is None:
        original_grant=next((e for e in grants.events() if e.hash==binding['grant_ref']),None)
        if original_grant is None:
            raise FamilyActionError('original family grant identity is unavailable')
        grant=grants.current(original_grant.payload['grant_id'],expected_ref=binding['grant_ref'])
    elif plan.action!='FULL_CLOSE':
        raise FamilyActionError('existing mandatory protection cannot authorize a partial allocation')
    for target in remaining:
        body=target.body()
        history=NativePositionHistory(lifecycle.ledger,
            account_alias=lifecycle.adapter.account_alias,venue=lifecycle.adapter.venue)
        family=lifecycle.families.get(plan.snapshot.family_id)
        current=original_native_snapshot(history,family,lifecycle.adapter)
        original_ids={(leg.position_id,leg.trade_intent_id) for leg in plan.snapshot.legs}
        current_ids={(leg.position_id,leg.trade_intent_id) for leg in current.legs}
        current_leg=next((leg for leg in current.legs if leg.position_id==target.position_id),None)
        if (original_ids!=current_ids or (not current.known and (plan.action!='FULL_CLOSE'
                or current_leg is None or current_leg.remaining is None))):
            if plan.action=='FULL_CLOSE':
                continue
            raise FamilyActionError('current original family quantity/membership is unresolved')
        @contextmanager
        def guard():
            if mandatory_guard is not None:
                with mandatory_guard(plan,target,history,action):
                    yield
                return
            from contextlib import nullcontext
            lease_guard = lease_submission_guard(lease_epoch) if lease_submission_guard is not None else nullcontext(True)
            with lease_guard as held:
                if held is not True:
                    raise FamilyActionError('current runtime submission guard refused family effect')
                with grants.effect_guard(grant.payload['grant_id'],expected_ref=grant.hash,
                        lease_epoch=lease_epoch,fence_ref=fence_ref,lease_fence=lease_fence):
                    # The original request has committed; this writer guard serializes
                    # fresh authority with revocation through transport/receipt commit.
                    fresh_history=NativePositionHistory(lifecycle.ledger,
                        account_alias=lifecycle.adapter.account_alias,venue=lifecycle.adapter.venue)
                    fresh=original_native_snapshot(fresh_history,lifecycle.families.get(plan.snapshot.family_id),
                        lifecycle.adapter,prepared_action=action,prepared_target=target)
                    active=next((leg for leg in fresh.legs if leg.position_id==target.position_id
                        and leg.trade_intent_id==target.trade_intent_id),None)
                    if (active is None or active.remaining is None or target.quantity>active.remaining
                            or (plan.action=='FULL_CLOSE' and target.quantity!=active.remaining)
                            or (plan.action=='PARTIAL_CLOSE' and not fresh.known)):
                        raise FamilyActionError('current original native request/quantity changed before dispatch')
                    explicit_ref=grants.authorize_plan(grant,plan,history=fresh_history,mandate=mandate,authority=authority,
                        adapter=lifecycle.adapter,
                        lease_epoch=lease_epoch,fence_ref=fence_ref,explicit_signature=explicit_signature,
                        family_action=action,active_target=target)
                    if explicit_ref != action.payload.get('explicit_authority_ref'):
                        raise FamilyActionError('exact explicit target authority differs from original durable action')
                    yield
        try:
            lifecycle.router.apply_preservation(lifecycle.adapter.venue,
                position_id=target.position_id,trade_intent_id=target.trade_intent_id,
                action=target.action,quantity=target.quantity,now_ms=now_ms,
                family_action_ref=action.hash,family_target_ref=target_ref(action.hash,body),
                family_effect_guard=guard,reason='GOVERNED_FAMILY_NATIVE_REDUCTION')
        except Exception as exc:
            if plan.action!='FULL_CLOSE':
                raise
            lifecycle._log(EventKind.SESSION,{"event":"FAMILY_ORIGINAL_FULL_TARGET_UNRESOLVED",
                "family_action_ref":action.hash,"family_target_ref":target_ref(action.hash,body),
                "position_id":target.position_id,"error_type":type(exc).__name__},
                now_ms=now_ms,corr=plan.snapshot.family_id)
        reduce_original_receipts(lifecycle,action,now_ms=now_ms)
    return journal.progress(action)


def reduce_original_family_receipts(lifecycle, family_id, *, now_ms):
    """Fold each proven close once, including independently observed venue stops."""
    family=lifecycle.families.get(family_id)
    history=NativePositionHistory(lifecycle.ledger,
        account_alias=lifecycle.adapter.account_alias,venue=lifecycle.adapter.venue)
    snapshot=original_native_snapshot(history,family,lifecycle.adapter)
    events={e.hash:e for e in history.events(EventKind.EXECUTION_RECEIPT)}
    receipts=[]
    for leg in snapshot.legs:
        for ref in leg.source_refs:
            event=events.get(ref)
            if event is not None and event.payload.get('exit_action')=='CLOSE':
                receipts.append(event)
    unique={e.payload['receipt_hash']:e for e in receipts}
    consumed=set()
    for member in family.members:
        if member.adds:
            continue
        matches={key for key,e in unique.items() if e.correlation_id==member.trade_intent_id
            and Decimal(str(e.payload['filled_qty']))==member.quantity
            and e.payload.get('average_fill') is not None
            and Decimal(str(e.payload['average_fill']))==member.price
            and e.received_time_ms<=member.occurred_ms
            and (not member.member_id.startswith('family-native-receipt:')
                 or member.member_id=='family-native-receipt:'+key)}
        if len(matches)!=1 or matches&consumed:
            raise FamilyActionError('original family close membership is ambiguous or duplicated')
        consumed.update(matches)
    for key,event in sorted(unique.items(),key=lambda item:(item[1].received_time_ms,item[1].event_time_ms,item[0])):
        if key in consumed:
            continue
        r=event.payload;qty=Decimal(str(r['filled_qty']))
        if qty<=0 or r.get('average_fill') is None:
            continue
        lifecycle.families.apply(family_id,FamilyMember('family-native-receipt:'+key,
            MemberRole.FULL_EXIT if qty==family.net_quantity else MemberRole.PARTIAL_EXIT,
            qty,Decimal(str(r['average_fill'])),event.received_time_ms,
            trade_intent_id=event.correlation_id),now_ms=now_ms)
        consumed.add(key)
    # Bind the committed post-fold family revision, not a stale pre-fold body.
    history=NativePositionHistory(lifecycle.ledger,
        account_alias=lifecycle.adapter.account_alias,venue=lifecycle.adapter.venue)
    snapshot=original_native_snapshot(history,family,lifecycle.adapter)
    # The native snapshot, not arithmetic on an already residual recovery row,
    # supplies current leg quantities. Unknown remains open/unresolved.
    for leg in snapshot.legs:
        row=lifecycle.entries.get(leg.trade_intent_id)
        if row is not None:
            row['quantity_known']=leg.remaining is not None
            if leg.remaining is not None:
                row['quantity']=leg.remaining;row['open']=leg.remaining>0
    return snapshot
