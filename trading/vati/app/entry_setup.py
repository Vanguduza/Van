"""Original pre-dispatch thesis inputs; never financial execution authority."""
from copy import deepcopy
from dataclasses import replace
from decimal import Decimal

from vati.core.canonical import canonical_hash
from vati.lifecycle.thesis import TradeThesis,thesis_from_capsule


def prepare_setup(cycle,intent,decision,state,targets,*,now_ms):
    capsule=deepcopy(cycle.engine.registry.get(intent.strategy_id).data)
    if (capsule.get('capsule_hash')!=canonical_hash({k:v for k,v in capsule.items() if k!='capsule_hash'})
        or capsule.get('version')!=intent.strategy_version):
        raise ValueError('original strategy capsule identity is invalid')
    spread=getattr(state.features,'spread_percentile',None)
    thesis=thesis_from_capsule(trade_intent_id=intent.trade_intent_id,symbol=cycle.cfg.symbol,
        strategy_id=intent.strategy_id,direction=intent.direction,capsule_hash=capsule['capsule_hash'],
        market_state_hash=intent.market_snapshot_hash,entry=intent.entry,original_stop=intent.stop,
        original_approved_risk_pct=decision.approved_risk_pct,created_ms=now_ms,capsule_data=capsule,
        expected_gross_move_pct=intent.expected_gross_move_pct,targets=tuple(targets),
        regime_label=state.regime.trend.value,entry_volatility=getattr(state.features,'atr',None),
        entry_liquidity=None if spread is None else Decimal(1)-Decimal(str(spread)),
        event_sensitivity=(cycle.cfg.base,cycle.cfg.quote))
    return {'schema':'vati.prepared-entry-setup/1','capsule':capsule,'thesis':thesis.to_dict()}


def prepared_thesis(setup):
    if not isinstance(setup,dict):raise ValueError('prepared setup must be an object')
    if setup.get('schema')!='vati.prepared-entry-setup/1':raise ValueError('unknown prepared setup schema')
    if not isinstance(setup.get('capsule'),dict) or not isinstance(setup.get('thesis'),dict):
        raise ValueError('prepared capsule and thesis must be objects')
    capsule=setup['capsule'];thesis=TradeThesis.from_payload(setup['thesis'])
    if (not thesis.seal_ok() or capsule.get('strategy_id')!=thesis.strategy_id
        or capsule.get('capsule_hash')!=thesis.capsule_hash
        or capsule['capsule_hash']!=canonical_hash({k:v for k,v in capsule.items() if k!='capsule_hash'})):
        raise ValueError('prepared strategy/thesis identity is invalid')
    return thesis


def filled_thesis(setup,entry):
    # Retain the original plan; derive its R against the observed fill basis.
    # No current capsule, market terms or hindsight enters this conversion.
    prepared=prepared_thesis(setup)
    if not isinstance(entry,Decimal) or not entry.is_finite() or entry<=0 or entry==prepared.original_stop:
        raise ValueError('actual fill thesis basis is invalid')
    path=dict(prepared.expected_path)
    if 'target_r' in path and 'first_target' in prepared.confirmation:
        target=Decimal(str(prepared.confirmation['first_target']))
        path['target_r']=str(prepared.sign*(target-entry)/abs(entry-prepared.original_stop))
    return replace(prepared,entry=entry,expected_path=path,seal='').sealed()


def publish_prepared_thesis(cycle,setup,entry,*,now_ms):
    """A lost write acknowledgement cannot create another original claim."""
    from vati.core import EventKind
    from vati.execution.recovery_scope import NativePositionHistory
    thesis=filled_thesis(setup,entry)
    def original():
        history=NativePositionHistory(cycle.ledger,account_alias=cycle.cfg.account_alias,venue=cycle.cfg.venue)
        claims={}
        for event in history.events(EventKind.TRADE_THESIS):
            if event.correlation_id!=thesis.trade_intent_id:continue
            saved=TradeThesis.from_payload(event.payload)
            if not saved.seal_ok():raise ValueError('original persisted thesis is invalid')
            claims[saved.seal]=saved
        if not claims:return None
        if set(claims)!={thesis.seal}:raise ValueError('original prepared thesis conflicts with persisted claim')
        return claims[thesis.seal]
    saved=original()
    if saved is not None:return cycle.thesis.adopt(saved)
    try:
        return cycle.thesis.seal(thesis,now_ms=now_ms)
    except Exception:
        saved=original()
        if saved is None:raise
        return cycle.thesis.adopt(saved)
