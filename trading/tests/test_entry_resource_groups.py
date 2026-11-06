"""Physical-account holds consume slots and independent currency intervals."""
from dataclasses import replace
from decimal import Decimal as D
from fractions import Fraction

import pytest

from test_entry_resource_projection import projection
from test_provisional_resource_book import prepared
from test_native_risk_history_inputs import record
from test_entry_margin_binding import entry_command
from test_heat_governor import pos
from vati.core import EventKind,make_event
from vati.core.units import Money
from vati.risk import Direction,RiskAuthority
from vati.risk.heat import exact_currency_leg_intervals
from vati.risk.serde import intent_from_dict,snapshot_from_dict
from vati.risk.provisional_resource_book import ResourceHoldError,EVENT,PRODUCER,SCHEMA,V1_MISSING
from vati.risk.mandate_source import capture_mandate_source
from vati.risk.entry_resource_projection import project_entry_resources
from vati.risk.entry_margin import _body


def another_entry(ledger,command,authority,router,clock,*,direction=None,symbol=None,key='second-entry'):
    original=next(e for e in ledger.iter(EventKind.RISK_DECISION)
        if e.payload['decision']['decision_hash']==command.decision_hash)
    facts=snapshot_from_dict(original.payload['inputs']['snapshot'])
    trade=intent_from_dict(original.payload['inputs']['intent'])
    changes={'trade_intent_id':key,'idempotency_key':key}
    if direction is not None:
        changes.update(direction=direction,stop=D('1.10230'))
    if symbol is not None:
        assert symbol=='GBPUSD', 'this fixture only declares a second standard FX contract'
        facts=replace(facts,symbol_contract=replace(facts.symbol_contract,symbol=symbol,base_currency='GBP'))
        changes.update(symbol=symbol)
    trade=replace(trade,**changes)
    event=record(ledger,facts,request=trade,grant=original.payload['inputs']['mandate'])
    approved=RiskAuthority(authority.mandate).evaluate_safe(trade,facts)
    other=replace(entry_command(event),expires_at_ms=command.expires_at_ms,command_hash='').sealed()
    from vati.execution.risk_refresh import CurrentRiskFacts
    router.current_risk_facts_provider=lambda *a,**kw:CurrentRiskFacts(facts,clock['ms'])
    margin,_=router._native_entry_margin(other,router.adapters['mt5'],now_ms=clock['ms'])
    current=router._current_account_risk(trade,approved,authority.mandate,other,router.adapters['mt5'],
        now_ms=clock['ms'],market_reference=None)
    return other,margin,current


def test_real_entry_projection_keeps_slots_integer_and_money_in_native_scope(tmp_path,eurusd):
    sdk,clock,ledger,command,margin,current,authority,book,router=prepared(tmp_path,eurusd)
    try:
        body=projection(ledger,command,margin,current,clock)
        assert body['slot_burdens']=={'account':1,'instrument:EURUSD':1}
        assert body['slot_capacities']=={'account':4,'instrument:EURUSD':1}
        assert all(type(v)is int for v in body['slot_capacities'].values())
        assert Money.from_body(body['burdens']['currency_leg_up:EUR']).decimal==D('22')
        assert Money.from_body(body['burdens']['currency_leg_down:USD']).decimal==D('22')
        assert Money.from_body(body['capacities']['currency_leg_up:EUR']).decimal==D('100')
        assert body['obligations_complete'] is False and not sdk.sent
    finally:ledger.close()


@pytest.mark.parametrize('opposite',[False,True])
def test_two_unfilled_entries_cannot_share_one_signed_instrument_slot(tmp_path,eurusd,opposite):
    sdk,clock,ledger,command,margin,current,authority,book,router=prepared(tmp_path,eurusd)
    try:
        book.reserve_entry(command,margin,current,authority)
        other,m,c=another_entry(ledger,command,authority,router,clock,
            direction=Direction.SHORT if opposite else None)
        before=ledger.count()
        with pytest.raises(ResourceHoldError,match='RESOURCE_SLOT_CAPACITY_EXCEEDED:instrument:EURUSD'):
            book.reserve_entry(other,m,c,authority)
        assert ledger.count()==before and not sdk.sent
    finally:ledger.close()


def test_resealed_individually_valid_source_cannot_overdraw_original_resource_history(tmp_path,eurusd):
    sdk,clock,ledger,command,margin,current,authority,book,router=prepared(tmp_path,eurusd,
        native_margin=D('2500'),mandate_changes={'max_positions_per_instrument':2})
    try:
        book.reserve_entry(command,margin,current,authority)
        other,m,c=another_entry(ledger,command,authority,router,clock)
        original=next(e for e in ledger.iter(EventKind.RISK_DECISION)
            if e.payload['decision']['decision_hash']==other.decision_hash)
        proof=capture_mandate_source(authority.mandate,original.payload['inputs']['mandate'],now_ms=clock['ms'])
        p=project_entry_resources(ledger,other,m,c,proof,at_ms=clock['ms']).body()
        from vati.risk.provisional_resource_book import _key
        key=_key(p['physical_account_key'],p['monetary_scope_hash'],other.account_alias,other.idempotency_key)
        forged=make_event(EventKind.SESSION,PRODUCER,{'event':EVENT,'schema':SCHEMA,
            'command':_body(other),'projection':p,'mandate_source':proof,'missing_requirements':list(V1_MISSING)},
            event_time_ms=clock['ms'],received_time_ms=clock['ms'],correlation_id=key)
        ledger.append(forged)
        assert ledger.verify_chain()[0], 'test requires a valid hash chain with invalid combined financial semantics'
        with pytest.raises(ResourceHoldError,match='RESOURCE_CAPACITY_EXCEEDED:margin_floor_equity'):
            book.lookup(p['physical_account_key'],p['monetary_scope_hash'],other.account_alias,other.idempotency_key)
        assert not sdk.sent
    finally:ledger.close()


def test_interval_math_preserves_native_position_netting_and_independent_pending_fills(eurusd):
    positions=(pos('EURUSD','EUR','USD',Direction.LONG),)
    from types import SimpleNamespace
    pending=((SimpleNamespace(contract=eurusd,direction=Direction.SHORT),Fraction(7)),
             (SimpleNamespace(contract=eurusd,direction=Direction.LONG),Fraction(3)))
    intervals=exact_currency_leg_intervals(positions,pending_losses=pending)
    assert intervals=={'EUR':(Fraction(3),Fraction(13)),'USD':(Fraction(-13),Fraction(-3))}
    assert exact_currency_leg_intervals((pos('EURUSD','EUR','USD',Direction.LONG,protected=False),)) is None


def test_distinct_instruments_still_consume_the_same_physical_account_slot(tmp_path,eurusd):
    sdk,clock,ledger,command,margin,current,authority,book,router=prepared(tmp_path,eurusd,
        mandate_changes={'max_total_positions':1})
    try:
        book.reserve_entry(command,margin,current,authority)
        other,m,c=another_entry(ledger,command,authority,router,clock,symbol='GBPUSD')
        before=ledger.count()
        with pytest.raises(ResourceHoldError,match='RESOURCE_SLOT_CAPACITY_EXCEEDED:account'):
            book.reserve_entry(other,m,c,authority)
        assert ledger.count()==before and not sdk.sent
    finally:ledger.close()


def test_cross_instrument_shared_usd_leg_cannot_borrow_capacity_from_a_new_base_currency(tmp_path,eurusd):
    sdk,clock,ledger,command,margin,current,authority,book,router=prepared(tmp_path,eurusd,
        mandate_changes={'max_currency_leg_exposure':'0.003','max_risk_per_trade':'0.0025'})
    try:
        book.reserve_entry(command,margin,current,authority)
        other,m,c=another_entry(ledger,command,authority,router,clock,symbol='GBPUSD')
        before=ledger.count()
        with pytest.raises(ResourceHoldError,match='RESOURCE_CAPACITY_EXCEEDED:currency_leg_down:USD'):
            book.reserve_entry(other,m,c,authority)
        assert ledger.count()==before and not sdk.sent
    finally:ledger.close()


def test_opposing_unfilled_hold_cannot_cancel_the_next_same_direction_currency_burden(tmp_path,eurusd):
    sdk,clock,ledger,command,margin,current,authority,book,router=prepared(tmp_path,eurusd,
        mandate_changes={'max_positions_per_instrument':3,'max_currency_leg_exposure':'0.003',
            'max_risk_per_trade':'0.0025'})
    try:
        book.reserve_entry(command,margin,current,authority)
        short,m,c=another_entry(ledger,command,authority,router,clock,direction=Direction.SHORT)
        second=book.reserve_entry(short,m,c,authority)
        assert second['eligible_for_native_dispatch'] is False
        third,m,c=another_entry(ledger,command,authority,router,clock,key='third-entry')
        proposed=projection(ledger,third,m,c,clock)
        assert Money.from_body(proposed['burdens']['currency_leg_up:EUR']).decimal==D('22')
        assert Money.from_body(proposed['burdens']['currency_leg_down:USD']).decimal==D('22')
        before=ledger.count()
        with pytest.raises(ResourceHoldError,match='RESOURCE_CAPACITY_EXCEEDED:currency_leg_down:USD'):
            book.reserve_entry(third,m,c,authority)
        assert ledger.count()==before and ledger.count(EventKind.ORDER_COMMAND)==0 and not sdk.sent
    finally:ledger.close()
