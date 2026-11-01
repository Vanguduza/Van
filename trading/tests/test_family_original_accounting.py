"""Original family quantities/costs survive partial exits, later adds and restart."""
from dataclasses import asdict
from decimal import Decimal as D,localcontext,Inexact,Rounded
from types import SimpleNamespace

import pytest

from vati.core import EventKind,Ledger,make_event
from vati.lifecycle.family import FamilyRegistry,FamilyMember,MemberRole
from vati.lifecycle.envelope import EnvelopeCalculator
from vati.risk.contracts import Direction,TradeIntent,StrategyState


def after_partial(*,direction=Direction.LONG):
    short=direction is Direction.SHORT
    registry=FamilyRegistry()
    family=registry.open_family(family_id='original-family',account_alias='source-fixture',
        symbol='EURUSD',direction=direction,
        root=FamilyMember('root',MemberRole.ROOT,D(10),D(100),1000,trade_intent_id='root-intent',
            stop=D(120 if short else 80)),now_ms=1000)
    registry.apply(family.family_id,FamilyMember('first-exit',MemberRole.PARTIAL_EXIT,D(5),
        D(90 if short else 110),2000),now_ms=2000)
    registry.apply(family.family_id,FamilyMember('add',MemberRole.SCALE_IN,D(5),
        D(80 if short else 120),3000,trade_intent_id='add-intent'),now_ms=3000)
    return family


@pytest.mark.parametrize('direction,expected_average,mark',[
    (Direction.LONG,D(110),D(130)),(Direction.SHORT,D(90),D(70))])
def test_actual_remaining_family_basis_after_reduction_and_new_add(direction,expected_average,mark):
    family=after_partial(direction=direction)
    assert family.net_quantity==D(10) and family.gross_added==D(15) and family.scale_ins==1
    assert family.realised_money==D(50)
    assert family.average_entry==expected_average
    assert family.unrealised_money(mark)==D(200)
    envelope=EnvelopeCalculator().compute(family,mark=mark,value_per_price_unit=D(1),equity=D(10000),now_ms=4000)
    assert envelope.average_entry==expected_average and envelope.unrealised_money==D(200)
    assert envelope.protected_profit_credit==D(0)


def test_family_fold_does_not_take_precision_or_mutate_flags_from_ambient_decimal_context():
    family=after_partial()
    with localcontext() as ctx:
        ctx.prec=2;ctx.traps[Inexact]=ctx.traps[Rounded]=True;flags=dict(ctx.flags)
        assert family.net_quantity==D(10) and family.gross_added==D(15)
        assert family.average_entry==D(110) and family.realised_money==D(50)
        assert family.unrealised_money(D(130))==D(200)
        assert dict(ctx.flags)==flags


def recorded_paper_partial(ledger):
    from test_account_lifecycle import _lifecycle,_command,_append_command
    from vati.execution.paper import PaperAdapter
    adapter=PaperAdapter(venue='paper',account_alias='acct',spread=D(0),slippage=D(0))
    command=_command('original-family-restart');_append_command(ledger,command,now=1000)
    entry=adapter.submit(command,now_ms=1000)
    assert entry.status=='FILLED' and entry.filled_qty==D('.10')
    ledger.append(make_event(EventKind.EXECUTION_RECEIPT,'vati-execution-router',asdict(entry),
        event_time_ms=1000,received_time_ms=1000,correlation_id=command.trade_intent_id))
    life=_lifecycle(ledger,adapter)
    intent=TradeIntent(trade_intent_id=command.trade_intent_id,idempotency_key=command.idempotency_key,
        account_alias=command.account_alias,venue=command.venue,symbol=command.symbol,direction=command.direction,
        strategy_id=command.strategy_id,strategy_version='1.0.0',strategy_state=StrategyState.DEMO,
        entry=command.entry_price,stop=command.protective_stop,requested_risk_pct=D('.005'),
        decision_hash=command.decision_hash,market_snapshot_hash='m'*64)
    life.record_entry(intent=intent,receipt=entry,
        state=SimpleNamespace(session=SimpleNamespace(value='LONDON'),event_window=SimpleNamespace(value='NONE')),
        modelled_cost_pct=D('.0003'),software_stop=False)
    closed=life.router.apply_preservation('paper',position_id=entry.broker_position_id,
        trade_intent_id=command.trade_intent_id,action='PARTIAL_CLOSE',quantity=D('.04'),now_ms=2000,
        reason='SOURCE_PARTIAL')
    assert closed.status=='FILLED' and closed.filled_qty==D('.04')
    family=life.families.for_intent(command.trade_intent_id)
    life.families.apply(family.family_id,FamilyMember('original-confirmed-partial',MemberRole.PARTIAL_EXIT,
        closed.filled_qty,closed.average_fill,2000,trade_intent_id=command.trade_intent_id),now_ms=2000)
    life.entries[command.trade_intent_id]['quantity']=family.net_quantity
    assert family.gross_added==D('.10') and family.net_quantity==D('.06')
    return life,adapter,command,entry


def test_actual_cold_lifecycle_retains_original_gross_added_instead_of_reopening_exit_budget(tmp_path):
    from test_account_lifecycle import _lifecycle
    ledger=Ledger(tmp_path/'family-restart.sqlite');cold=None
    try:
        life,adapter,command,entry=recorded_paper_partial(ledger)
        cold=Ledger(ledger.path);count=ledger.count()
        restarted=_lifecycle(cold,adapter)
        restored,unresolved=restarted.recover_from_venue()
        assert restored==(command.trade_intent_id,) and unresolved==()
        original=life.families.for_intent(command.trade_intent_id)
        recovered=restarted.families.for_intent(command.trade_intent_id)
        assert recovered.net_quantity==D('.06') and recovered.gross_added==D('.10')
        assert [m.body() for m in recovered.members]==[m.body() for m in original.members]
        assert restarted.protection.stop_of(entry.broker_position_id)==command.protective_stop
        assert ledger.count()==count and ledger.verify_chain()[0]
    finally:
        if cold is not None:cold.close()
        ledger.close()
