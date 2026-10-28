"""A second alias cannot ignore another alias's still-pending stop risk."""
from dataclasses import replace
from decimal import Decimal as D
from types import SimpleNamespace as N

import pytest

from conftest import NOW,intent,mandate_dict
from test_native_risk_history_inputs import native_facts
from test_native_risk_history_index import other_context
from test_physical_order_exposure import command,receipt
from test_physical_snapshot_producers import producer
from vati.risk import TradingMandate,RiskAuthority
from vati.risk.physical_pending import PhysicalPendingRisk,project_pending_risk
from vati.risk.positions import project_open_position
from vati.risk.serde import snapshot_to_dict,snapshot_from_dict
from vati.risk.heat import exact_currency_leg_exposure
from vati.risk.pending import pending_risk_losses
from vati.risk.contracts import Direction
from test_physical_financial_history import close


def pending(ledger,facts,positions=(),*,now=NOW*1000+100):
    return PhysicalPendingRisk(ledger,facts.native_account_context,now_ms=now).refresh(positions,now_ms=now)


def position(cmd,contract,*,quantity=None,position_id='source-position'):
    return project_open_position(symbol=cmd.symbol,direction=cmd.direction,
        quantity=cmd.quantity if quantity is None else quantity,entry=cmd.entry_price,
        stop=cmd.protective_stop,contract=contract,loss_model=cmd.loss_model,broker_position_id=position_id)


@pytest.mark.parametrize('status',['ACCEPTED','PARTIAL','FILLED','UNKNOWN'])
def test_receipt_without_current_native_position_never_silently_releases_possible_fill(tmp_path,eurusd,status):
    ledger,_,_,_,facts=native_facts(tmp_path,eurusd);_,cmd=command(ledger,facts,'possible')
    filled=cmd.quantity/2 if status=='PARTIAL' else cmd.quantity if status=='FILLED' else D(0)
    receipt(ledger,cmd,status=status,filled=str(filled))
    out=pending(ledger,facts)
    assert len(out)==1 and out[0].quantity==cmd.quantity and out[0].new_position_slots==1
    assert out[0].protection_confirmed is out[0].execution_authority is False


@pytest.mark.parametrize('partial',[False,True])
def test_only_receipt_bound_actual_native_position_covers_quantity_once(tmp_path,eurusd,partial):
    ledger,_,_,_,facts=native_facts(tmp_path,eurusd);_,cmd=command(ledger,facts,'native-cover')
    quantity=cmd.quantity/2 if partial else cmd.quantity
    receipt(ledger,cmd,status='PARTIAL' if partial else 'FILLED',filled=str(quantity))
    p=position(cmd,eurusd,quantity=quantity)
    out=pending(ledger,facts,(p,))
    if partial:
        assert len(out)==1 and out[0].quantity==cmd.quantity-quantity and out[0].new_position_slots==0
    else:assert out==()
    assert pending(ledger,facts,(replace(p,broker_position_id='manual-or-spoofed-comment'),))[0].quantity==cmd.quantity


def test_local_cancel_or_time_passage_does_not_release_but_original_native_no_effect_does(tmp_path,eurusd):
    ledger,_,_,_,facts=native_facts(tmp_path,eurusd);_,cmd=command(ledger,facts,'cancel')
    receipt(ledger,cmd,status='ACCEPTED');receipt(ledger,cmd,status='CANCELLED',when=3)
    assert pending(ledger,facts,now=(NOW+900)*1000)[0].quantity==cmd.quantity
    receipt(ledger,cmd,status='CANCELLED',when=4,native_entry_observation={
        'schema':'vati.native-entry-observation/1','command_hash':cmd.command_hash,'source':'ORIGINAL_NATIVE_RESULT'})
    assert pending(ledger,facts)==()


@pytest.mark.parametrize('status',['FILLED','PARTIAL'])
def test_original_close_releases_only_fully_filled_absent_position_stop_risk(tmp_path,eurusd,status):
    ledger,_,_,_,facts=native_facts(tmp_path,eurusd);event,cmd=command(ledger,facts,'close')
    receipt(ledger,cmd,status=status,filled=str(cmd.quantity if status=='FILLED' else cmd.quantity/2))
    original=next(e for e in ledger.iter() if e.hash==pending(ledger,facts)[0].original_input_ref)
    close(ledger,original)
    out=pending(ledger,facts)
    assert (out==()) is (status=='FILLED')
    assert pending(ledger,facts,(position(cmd,eurusd,quantity=cmd.quantity/2),))[0].quantity==cmd.quantity/2


def test_future_receipt_is_consumed_only_at_original_availability_and_reopen_retains_pending(tmp_path,eurusd):
    from vati.core import Ledger
    ledger,_,_,_,facts=native_facts(tmp_path,eurusd);_,cmd=command(ledger,facts,'future')
    runtime=PhysicalPendingRisk(ledger,facts.native_account_context,now_ms=NOW*1000+1)
    receipt(ledger,cmd,status='REJECTED',when=200)
    assert runtime.refresh((),now_ms=NOW*1000+100)[0].quantity==cmd.quantity
    # A separate SQL connection independently re-reads the original records.
    reopened=Ledger(ledger.path)
    try:assert pending(reopened,facts)[0].quantity==cmd.quantity
    finally:reopened.close()
    assert runtime.refresh((),now_ms=NOW*1000+200)==()


def test_ordinary_tick_uses_incremental_cursor_without_full_history_rescan(tmp_path,eurusd,monkeypatch):
    from vati.core import EventKind,make_event
    ledger,_,_,_,facts=native_facts(tmp_path,eurusd);_,cmd=command(ledger,facts,'cached')
    runtime=PhysicalPendingRisk(ledger,facts.native_account_context,now_ms=NOW*1000+100)
    def forbidden(*args,**kwargs):raise AssertionError('ordinary tick performed a full scan')
    monkeypatch.setattr(ledger,'iter',forbidden)
    ledger.append(make_event(EventKind.SESSION,'vati-cycle',{'event':'ORDINARY_TICK'},
        event_time_ms=NOW*1000+101,received_time_ms=NOW*1000+101,correlation_id='tick'))
    assert runtime.refresh((),now_ms=NOW*1000+101)[0].quantity==cmd.quantity


def test_pending_serialization_roundtrip_and_independent_currency_fill_bounds(tmp_path,eurusd):
    from fractions import Fraction
    ledger,_,_,_,facts=native_facts(tmp_path,eurusd);_,cmd=command(ledger,facts,'serialized')
    p=pending(ledger,facts)[0]
    body=snapshot_to_dict(replace(facts,pending_risk_commitments=(p,)))
    restored=snapshot_from_dict(body)
    assert restored.pending_risk_commitments==(p,) and snapshot_to_dict(restored)==body
    loss=pending_risk_losses(restored)[0][1]
    opposite=replace(p,direction=Direction.SHORT,command_ref='b'*64)
    values=exact_currency_leg_exposure((),facts.equity,additional_loss=loss,
        base_currency=eurusd.base_currency,quote_currency=eurusd.quote_currency,
        direction=Direction.LONG,pending_losses=((p,loss),(opposite,loss)))
    assert values['EUR']==2*loss/Fraction(facts.equity)


@pytest.mark.parametrize('damage',['scope','boolean','receipt'])
def test_uncertain_original_input_holds_entries_without_issuing_authority(tmp_path,eurusd,damage):
    ledger,_,_,_,facts=native_facts(tmp_path,eurusd);_,cmd=command(ledger,facts,'uncertain')
    if damage=='receipt':
        receipt(ledger,cmd,status='REJECTED',receipt_hash='0'*64)
        out,issue=project_pending_risk(N(),ledger,facts.native_account_context,(),now_ms=NOW*1000+100)
        assert out==() and issue.startswith('NATIVE_PENDING_RISK_UNAVAILABLE:')
    else:
        p=pending(ledger,facts)[0]
        p=replace(p,monetary_scope_hash='0'*64) if damage=='scope' else replace(p,execution_authority=0)
        with pytest.raises(ValueError):pending_risk_losses(replace(facts,pending_risk_commitments=(p,)))


@pytest.mark.parametrize('limit,expected',[
    ({'max_open_stop_risk':'0.02'},'OK'),
    ({'max_total_positions':1},'MAX_TOTAL_POSITIONS'),
    ({'max_positions_per_instrument':1},'MAX_POSITIONS_PER_INSTRUMENT'),
    ({'max_currency_leg_exposure':'0.005'},'CURRENCY_LEG_EXPOSURE'),
])
def test_existing_authority_applies_pending_limits_with_a_permitted_positive_case(tmp_path,eurusd,limit,expected):
    ledger,_,_,_,facts=native_facts(tmp_path,eurusd);command(ledger,facts,'limits')
    facts=replace(facts,pending_risk_commitments=pending(ledger,facts),
        used_margin=D(0),free_margin=facts.equity,margin_level_pct=None)
    policy={'max_open_stop_risk':'0.05','max_positions_per_instrument':10,'max_total_positions':20}
    policy.update(limit)
    grant=TradingMandate.from_mapping(mandate_dict(account_alias=facts.account_alias,**policy))
    result=RiskAuthority(grant).evaluate_safe(intent(account_alias=facts.account_alias),facts)
    assert result.reason_code==expected,result
    assert (result.decision.value=='APPROVED') is (expected=='OK')


def test_pending_contract_boolean_is_an_explicit_fact_and_legacy_bodies_keep_hashes(tmp_path,eurusd):
    from pathlib import Path
    import json
    from vati.risk.authority import _canonical_hash
    ledger,_,_,_,facts=native_facts(tmp_path,eurusd);command(ledger,facts,'booleans')
    p=pending(ledger,facts)[0]
    invalid=replace(p,contract=replace(p.contract,is_synthetic='false'))
    result=RiskAuthority(TradingMandate.from_mapping(mandate_dict(account_alias=facts.account_alias))).evaluate_safe(
        intent(account_alias=facts.account_alias),replace(facts,pending_risk_commitments=(invalid,)))
    assert result.reason_code=='INVALID_BOOLEAN_FACT'
    for name in ('legacy_risk_snapshot_b58bb578.json','legacy_risk_snapshot_no_margin_74b1749a.json'):
        raw=json.loads((Path(__file__).parent/'fixtures'/name).read_text())
        restored=snapshot_from_dict(raw['snapshot'])
        assert snapshot_to_dict(restored)==raw['snapshot']
        assert _canonical_hash(restored)==_canonical_hash(raw['snapshot'])


@pytest.mark.parametrize('kind',['single','account'])
def test_second_alias_cannot_reuse_pending_risk_capacity_at_the_actual_snapshot_owner(tmp_path,eurusd,kind):
    ledger,adapter,account,_,facts=native_facts(tmp_path,eurusd)
    _,first=command(ledger,facts,'first-pending-risk')
    receipt(ledger,first,status='ACCEPTED')
    b=other_context(ledger,adapter,account,facts,alias='second_alias')
    current=replace(account,account_alias=b.account_alias,
        funding_mark=replace(account.funding_mark,account_alias=b.account_alias),
        used_margin=D(0),free_margin=account.equity,margin_level_pct=None)
    service=producer(kind,ledger,adapter,current,b)
    now=NOW*1000+100
    if kind=='single':
        snapshot=service.snapshot(now_ms=now,quote_age_ms=0,strategy_id=intent().strategy_id)
    else:
        service.clock=lambda:now
        snapshot=service._snapshot_for(N(symbol='EURUSD',strategy_id=intent().strategy_id))
    assert snapshot.reconciliation_ok and not snapshot.preservation_blocks_new_risk, snapshot
    assert snapshot.open_positions==()
    grant=TradingMandate.from_mapping(mandate_dict(account_alias=b.account_alias,venue=adapter.venue,
        max_open_stop_risk='0.005',max_positions_per_instrument=10,max_total_positions=20))
    result=RiskAuthority(grant).evaluate_safe(intent(account_alias=b.account_alias,venue=adapter.venue),snapshot)
    assert result.decision.value=='REJECTED' and result.reason_code=='PORTFOLIO_HEAT',result
