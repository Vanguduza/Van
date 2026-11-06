"""One original family outcome; child fills do not create new learning trials."""
from decimal import Decimal, localcontext, ROUND_HALF_EVEN
from fractions import Fraction
from dataclasses import dataclass, field, asdict, replace

from vati.core.canonical import canonical_hash
from vati.core.events import EventKind, make_event
from vati.execution.recovery_scope import NativePositionHistory
from vati.execution.paper import PaperAdapter
from vati.execution.review import (closed_trade_pnl, native_economic_maturity, economic_outcome_final,
                                   PnlMeasurement, TradeReview, review_trade, initial_risk_from_ledger)
from vati.execution.recorded_close_costs import recorded_close_cost_entry
from vati.lifecycle.family_actions import FamilyActionError, exact_decimal
from vati.lifecycle.family_execution import reduce_original_family_receipts
from vati.risk.contracts import Direction

VERSION='family-outcome/1'


@dataclass(frozen=True)
class FamilyTradeReview(TradeReview):
    # Base TradeReview fields and legacy seals remain byte-for-byte unchanged.
    family_outcome: dict = field(default_factory=dict)


def publish_family_outcome(lifecycle, family_id, *, reason, now_ms):
    with localcontext() as context:
        context.prec=50;context.rounding=ROUND_HALF_EVEN
        return _publish_family_outcome(lifecycle,family_id,reason=reason,now_ms=now_ms)


def _publish_family_outcome(lifecycle, family_id, *, reason, now_ms):
    """Observe original effects even after admission changes; never send/retry."""
    family=lifecycle.families.get(family_id)
    root=family.members[0].trade_intent_id
    previous=[e for e in lifecycle.ledger.iter(correlation_id=root)
        if e.kind in {EventKind.TRADE_REVIEW,EventKind.TRADE_REVIEW_REVISION}
        and e.producer=='vati-account-lifecycle' and e.payload.get('family_outcome',{}).get('family_id')==family_id]
    head=None
    for event in previous:
        p=event.payload
        if (event.hash!=canonical_hash(event.body()) or p.get('artifact_hash')!=canonical_hash({k:v for k,v in p.items() if k!='artifact_hash'})
                or p.get('record_revision',0)!=(head.payload['record_revision']+1 if head else 0)
                or p.get('supersedes_review_ref')!=(head.payload['artifact_hash'] if head else None)):
            raise FamilyActionError('original governed family outcome chain is conflicting')
        head=event
    source_reader=getattr(lifecycle,'native_economic_observations',None)
    if source_reader is not None:
        from vati.execution.family_economics import SourceFamilyEconomicObservations
        if (not isinstance(source_reader,SourceFamilyEconomicObservations)
                or source_reader.ledger is not lifecycle.ledger or source_reader.adapter is not lifecycle.adapter):
            raise FamilyActionError('native economic owner is not qualified for this runtime/source ledger')
    observation=source_reader.latest(family_id) if source_reader is not None else None
    if head is not None and (observation is None or
            head.payload['family_outcome'].get('native_economic_observation_ref')==observation.hash):
        consume_family_review(lifecycle,head,now_ms=now_ms)
        return head
    if not previous and any(e.producer=='vati-account-lifecycle' for e in lifecycle.ledger.iter(EventKind.TRADE_REVIEW,correlation_id=root)):
        raise FamilyActionError('legacy individual review requires original family trial reconciliation')
    snapshot=reduce_original_family_receipts(lifecycle,family_id,now_ms=now_ms)
    if not snapshot.known or any(leg.remaining!=0 for leg in snapshot.legs):
        return None
    history=NativePositionHistory(lifecycle.ledger,
        account_alias=lifecycle.adapter.account_alias,venue=lifecycle.adapter.venue)
    events={e.hash:e for e in history.events(EventKind.EXECUTION_RECEIPT)}
    leg_results=[];total=Fraction(0);known=True;all_final=True;refs=[]
    contract=lifecycle.contracts[family.symbol.upper()]
    for leg in snapshot.legs:
        openings=[events[ref] for ref in leg.source_refs if ref in events and not events[ref].payload.get('exit_action')]
        if len(openings)!=1:
            raise FamilyActionError('family outcome lacks one exact original native entry per leg')
        opening=openings[0];r=opening.payload
        closes=[events[ref] for ref in leg.source_refs if ref in events and events[ref].payload.get('exit_action')=='CLOSE'
            and Decimal(str(events[ref].payload.get('filled_qty','0')))>0]
        closes={e.payload['receipt_hash']:e for e in closes}
        q=sum((Fraction(Decimal(str(e.payload['filled_qty']))) for e in closes.values()),Fraction(0))
        if q!=Fraction(Decimal(str(r['filled_qty']))):
            raise FamilyActionError('family native exit quantities do not settle the original entry')
        # Every original fill, rather than a weighted presentation price,
        # remains the economic input to the existing recorded-cost owner.
        last=max(closes.values(),key=lambda e:(e.received_time_ms,e.hash))
        exit_price=Decimal(str(last.payload['average_fill']))
        entry=dict(lifecycle.entries.get(leg.trade_intent_id,{}) or lifecycle.entries.get(root,{}))
        entry.update(trade_intent_id=leg.trade_intent_id,symbol=family.symbol,direction=family.direction,
            entry=Decimal(str(r['average_fill'])),quantity=Decimal(str(r['filled_qty'])),
            broker_position_id=leg.position_id,fees=r.get('fees'),carry=entry.get('carry',Decimal(0) if type(lifecycle.adapter) is PaperAdapter else None),
            recorded_exit_fills=[{'quantity':e.payload['filled_qty'],'price':e.payload['average_fill']} for e in closes.values()])
        if entry['fees'] is not None:entry['fees']=Decimal(str(entry['fees']))
        entry=recorded_close_cost_entry(lifecycle.ledger,entry,trade_intent_id=leg.trade_intent_id,
            venue=lifecycle.adapter.venue,account_alias=lifecycle.adapter.account_alias,available_at_ms=now_ms)
        measurement=closed_trade_pnl(entry,exit_price,contract,getattr(lifecycle.adapter,'closed',None))
        maturity=native_economic_maturity(lifecycle.adapter,leg.trade_intent_id,measurement)
        final=economic_outcome_final(maturity,measurement.basis,account_currency=contract.account_currency)
        known=known and measurement.amount is not None;all_final=all_final and final
        if measurement.amount is not None:total+=Fraction(measurement.amount)
        leg_refs=[opening.hash,*[e.hash for e in closes.values()]];refs.extend(leg_refs)
        leg_results.append({'position_id':leg.position_id,'trade_intent_id':leg.trade_intent_id,
            'original_quantity':r['filled_qty'],'pnl':None if measurement.amount is None else str(measurement.amount),
            'pnl_basis':measurement.basis,'native_maturity':maturity,'economic_final':final,'source_refs':leg_refs})
    if observation is not None:
        body=observation.payload['observation']
        if body['currency']!=contract.account_currency:
            raise FamilyActionError('native owner economic currency differs from original family contract')
        total=sum((Fraction(Decimal(d['net_cash_delta'])) for d in body['deals']),Fraction(0))
        known=True;all_final=True;refs.append(observation.hash)
        for leg in leg_results:
            cash=sum((Fraction(Decimal(d['net_cash_delta'])) for d in body['deals']
                if d['trade_intent_id']==leg['trade_intent_id']),Fraction(0))
            leg.update(pnl=str(exact_decimal(cash)),pnl_basis='REPORTED_NET_CONFIRMED',
                native_maturity={'source':'SYNTHETIC_NATIVE_OWNER_SOURCE_ONLY','source_environment':'DEMO',
                    'account_currency':contract.account_currency,'observation_ref':observation.hash},economic_final=True)
    root_row=lifecycle.entries.get(root,{})
    root_entry=family.members[0]
    initial_risk=initial_risk_from_ledger(lifecycle.ledger,root)
    pnl=exact_decimal(total) if known else Decimal(0)
    if initial_risk is None:
        # Confirmed native closes do not invent a price-based R for a multi-entry
        # family. Preserve the economic observation while its original unit is unknown.
        payload=dict(version=VERSION,state='CLOSED_ORIGINAL_RISK_UNIT_UNKNOWN',family_id=family_id,
            membership_ref=snapshot.digest,legs=leg_results,pnl=str(pnl) if known else None,
            economic_final=all_final,source_refs=refs,child_learning_trials=0,execution_authority=False)
        with lifecycle.ledger.atomic():
            existing=next((e for e in lifecycle.ledger.iter(EventKind.SESSION,correlation_id=family_id)
                if e.producer=='vati-account-lifecycle' and e.payload==payload),None)
            if existing:return existing
            event=make_event(EventKind.SESSION,'vati-account-lifecycle',payload,
                event_time_ms=now_ms,received_time_ms=now_ms,correlation_id=family_id)
            lifecycle.ledger.append(event)
        return event
    if not known or not all_final:
        payload=dict(version=VERSION,state='CLOSED_NATIVE_ECONOMICS_PENDING',family_id=family_id,
            membership_ref=snapshot.digest,legs=leg_results,pnl=str(pnl) if known else None,
            original_money_risk=str(initial_risk.amount),initial_risk_ref=initial_risk.evidence_ref,
            economic_final=False,source_refs=refs,child_learning_trials=0,execution_authority=False)
        with lifecycle.ledger.atomic():
            existing=next((e for e in lifecycle.ledger.iter(EventKind.SESSION,correlation_id=family_id)
                if e.producer=='vati-account-lifecycle' and e.payload==payload),None)
            if existing:return existing
            event=make_event(EventKind.SESSION,'vati-account-lifecycle',payload,
                event_time_ms=now_ms,received_time_ms=now_ms,correlation_id=family_id)
            lifecycle.ledger.append(event)
        return event
    maturity={'parent_final':all_final,'fees_final':all_final,'cash_reconciled':all_final,
        'source_environment':'DEMO' if all_final else None,'account_currency':contract.account_currency,
        'source':('SYNTHETIC_NATIVE_OWNER_SOURCE_ONLY' if observation is not None else 'DETERMINISTIC_PAPER_SETTLEMENT') if all_final else 'PROVIDER_FINALITY_UNAVAILABLE'}
    basis=('REPORTED_NET_CONFIRMED' if observation is not None else 'REPORTED_GROSS_NET_RECORDED_CHARGES') if all_final else 'FAMILY_ORIGINAL_LEG_RESULTS_NOT_NATIVE_FINAL'
    review=review_trade(trade_intent_id=root,strategy_id=str(root_row.get('strategy_id') or
        history.commands[root][0].get('strategy_id','')),entry=root_entry.price,
        exit_price=exit_price,stop=root_entry.stop or root_entry.price,
        direction_long=family.direction is Direction.LONG,pnl=pnl,
        account_alias=lifecycle.adapter.account_alias,maturity=maturity,
        thesis_correct=known and pnl>0,process_ok=True,broker_ok=known,exit_reason=(previous[0].payload['family_outcome'].get('close_reason',reason) if previous else reason),
        initial_money_risk=initial_risk.amount if initial_risk else None,
        initial_risk_evidence_ref=initial_risk.evidence_ref if initial_risk else None,
        pnl_basis=basis,thesis_evidence_basis='PNL_SIGN_PROXY_NOT_SETUP_VALIDATION')
    family_metadata={'version':VERSION,'family_id':family_id,'family_revision':snapshot.family_revision,
        'membership_ref':snapshot.digest,'original_root_intent_id':root,'legs':leg_results,
        'pnl_known':known,'economic_final':all_final,'source_refs':refs,
        'learning_unit':'POSITION_FAMILY','trial_identity':family_id,'child_learning_trials':0,
        'close_reason':previous[0].payload['family_outcome'].get('close_reason',reason) if previous else reason,
        'native_economic_observation_ref':observation.hash if observation else None,
        'correction_domain':'SOURCE_ONLY' if observation else None,
        'production_native_correction_owner':'NOT_QUALIFIED',
        'weighted_average_economics_separate_from_native_leg_selection':True}
    review=FamilyTradeReview(**asdict(review),family_outcome=family_metadata)
    review=replace(review,record_revision=head.payload['record_revision']+1 if head else 0,
        supersedes_review_ref=head.payload['artifact_hash'] if head else None,artifact_hash='')
    review=replace(review,artifact_hash=canonical_hash({k:v for k,v in asdict(review).items() if k!='artifact_hash'}))
    payload=asdict(review)
    with lifecycle.ledger.atomic():
        existing=[e for e in lifecycle.ledger.iter(correlation_id=root)
            if e.kind in {EventKind.TRADE_REVIEW,EventKind.TRADE_REVIEW_REVISION}
            and e.producer=='vati-account-lifecycle' and e.payload.get('family_outcome',{}).get('family_id')==family_id]
        current=existing[-1] if existing else None
        if current is not None and current.payload.get('artifact_hash')==review.artifact_hash:return current
        if (current.hash if current else None)!=(head.hash if head else None):
            raise FamilyActionError('family outcome revision compare-and-swap requires fresh original readback')
        event=make_event(EventKind.TRADE_REVIEW_REVISION if head else EventKind.TRADE_REVIEW,'vati-account-lifecycle',payload,
            event_time_ms=now_ms,received_time_ms=now_ms,correlation_id=root);lifecycle.ledger.append(event)
    lifecycle.reviews.append(review)
    consume_family_review(lifecycle,event,now_ms=now_ms,review=review,root_entry=root_row)
    for member in family.members:
        if member.adds:lifecycle.entries.pop(member.trade_intent_id,None)
    lifecycle._family_halts.pop(family_id,None)
    return event


def consume_family_review(lifecycle, event, *, now_ms, review=None, root_entry=None):
    # Serialize the existing-artifact check with the actual learner invocation,
    # not merely with the later artifact append. A competing consumer cannot
    # create a duplicate in-memory health/episode contribution before losing CAS.
    with lifecycle.ledger.atomic():
        return _consume_family_review(lifecycle,event,now_ms=now_ms,review=review,root_entry=root_entry)


def _consume_family_review(lifecycle, event, *, now_ms, review=None, root_entry=None):
    """Recover one existing root learning consumer, never a child trade trial."""
    from dataclasses import fields
    from vati.execution.review import TradeReview, Outcome, STRATEGY_LEARNING_OUTCOMES
    p=event.payload;family=p.get('family_outcome',{});root=event.correlation_id
    if (family.get('original_root_intent_id')!=root or event.hash!=canonical_hash(event.body())
            or event.producer!='vati-account-lifecycle'):
        raise FamilyActionError('family learning lacks its original governed outcome')
    if event.kind is EventKind.TRADE_REVIEW and lifecycle.streaks is not None:
        # Existing ledger fold includes original reviews and owner resets, in
        # knowledge order. Replays do not increment again; later restatements
        # do not rewrite the decisions or reset boundaries already observed.
        from vati.risk.lockouts import LossStreakGovernor
        lifecycle.streaks=LossStreakGovernor.rebuild(lifecycle.streaks.policy,
            lifecycle.ledger.iter(),account_alias=lifecycle.adapter.account_alias)
        lifecycle.consecutive_losses=lifecycle.streaks.verdict(p['strategy_id'],now_ms).losses
    if lifecycle.learning is not None and event.kind is EventKind.TRADE_REVIEW_REVISION:
        # Replace the existing parent contribution in the rightful restated
        # analysis owner; never emit another child/root experience trial.
        lifecycle.learning.update_projection(lifecycle.ledger)
        return
    if (not family.get('pnl_known') or not family.get('economic_final')
            or lifecycle.learning is None):
        return
    existing=[e for e in lifecycle.ledger.iter(EventKind.TRADE_EXPERIENCE_ARTIFACT,correlation_id=root)
        if e.producer=='vati-account-lifecycle'
        and e.payload.get('review',{}).get('source_review_ref')==event.hash]
    if existing:
        if len(existing)!=1 or existing[0].hash!=canonical_hash(existing[0].body()):
            raise FamilyActionError('family learning original trial is conflicting')
        return
    if review is None:
        values={f.name:p[f.name] for f in fields(FamilyTradeReview) if f.name in p}
        for key in ('r_multiple','pnl','initial_money_risk'):
            if values.get(key) is not None:values[key]=Decimal(str(values[key]))
        values['outcome']=Outcome(values['outcome']);values['lessons']=tuple(values['lessons'])
        review=FamilyTradeReview(**values)
    if review.outcome not in STRATEGY_LEARNING_OUTCOMES:
        return
    lifecycle.admission.propose(review.artifact_hash,knowledge_class='TRADE_EXPERIENCE',
        proposed_by=review.proposed_by,trust_tier='T0_VAN_TRADING_POLICY')
    entry=root_entry or lifecycle.entries.get(root)
    process_ok=False
    if entry:
        verdict=lifecycle._classify_decision(intent_id=root,entry=entry,review=review,
            now_ms=now_ms,outcome_known=True)
        process_ok=verdict is not None and not verdict.faults
    lifecycle._learn(root,review,Decimal(str((entry or {}).get('cost_ratio','1'))),now_ms,
        process_ok=process_ok,deduplicate_episode=True)
    lifecycle.thesis.forget(root)
