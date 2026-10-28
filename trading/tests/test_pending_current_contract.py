"""Original pending terms cannot hide a higher current account-currency loss."""
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
from test_physical_pending_risk import pending
from vati.risk.pending import pending_risk_losses,PendingValuationUnavailable
from vati.risk.physical_pending import PhysicalPendingRisk,project_pending_risk
from vati.risk.serde import snapshot_to_dict,snapshot_from_dict
from vati.risk.authority import _canonical_hash,RiskDecision,Decision
from vati.execution.router import recompute_decision_hash


def test_actual_parent_pending_bodies_keep_original_hashes_but_do_not_supply_current_valuation():
    from pathlib import Path
    import json
    raw=json.loads((Path(__file__).parent/'fixtures/pending_risk_snapshots_eac4761f.json').read_text())
    assert raw['source_commit']=='eac4761f34c2c966ccc57578d7a8865695b40cf7'
    assert len(raw['fixtures'])==4 and raw['execution_authority'] is False
    for row in raw['fixtures']:
        facts=snapshot_from_dict(row['snapshot'])
        assert snapshot_to_dict(facts)==row['snapshot']
        assert _canonical_hash(facts)==row['decision']['risk_snapshot_hash']
        assert all(p.valuation_contract is None for p in facts.pending_risk_commitments)
        decision=dict(row['decision']);decision['decision']=Decision(decision['decision'])
        for field in ('approved_size','approved_risk_pct','requested_risk_pct','portfolio_heat_before','portfolio_heat_after'):
            decision[field]=D(decision[field])
        decision['constraints']=tuple(decision['constraints']);decision=RiskDecision(**decision)
        assert recompute_decision_hash(decision)==decision.decision_hash
        grant=TradingMandate.from_mapping(mandate_dict(account_alias=facts.account_alias))
        result=RiskAuthority(grant).evaluate_safe(intent(account_alias=facts.account_alias),facts)
        assert result.reason_code=='PENDING_VALUATION_UNAVAILABLE' and result.decision is Decision.REJECTED


@pytest.mark.parametrize('tick_value',['0.5','2'])
def test_lower_terms_cannot_release_original_floor_and_higher_terms_increase_risk(tmp_path,eurusd,tick_value):
    from fractions import Fraction
    ledger,_,_,_,facts=native_facts(tmp_path,eurusd);command(ledger,facts,'loss-floor')
    p=pending(ledger,facts)[0];original_loss=pending_risk_losses(replace(facts,pending_risk_commitments=(p,)))[0][1]
    current=replace(eurusd,tick_value=eurusd.tick_value*D(tick_value))
    p=replace(p,valuation_contract=current)
    actual=pending_risk_losses(replace(facts,pending_risk_commitments=(p,)))[0][1]
    assert actual==original_loss*max(Fraction(1),Fraction(D(tick_value)))
    assert p.contract==eurusd and p.valuation_contract==current


@pytest.mark.parametrize('field,value',[
    ('symbol','GBPUSD'),('venue','ctrader'),('account_currency','EUR'),
    ('base_currency','GBP'),('quote_currency','JPY'),('contract_size',D('1000')),
])
def test_instrument_or_monetary_unit_changes_require_reconciliation(tmp_path,eurusd,field,value):
    ledger,_,_,_,facts=native_facts(tmp_path,eurusd);command(ledger,facts,'unit-change')
    p=pending(ledger,facts)[0];p=replace(p,valuation_contract=replace(eurusd,**{field:value}))
    with pytest.raises(PendingValuationUnavailable,match='identity, unit or loss model changed'):
        pending_risk_losses(replace(facts,pending_risk_commitments=(p,)))


def test_current_terms_refresh_without_another_financial_event_or_full_scan(tmp_path,eurusd,monkeypatch):
    ledger,_,_,_,facts=native_facts(tmp_path,eurusd);command(ledger,facts,'changing-tick')
    runtime=PhysicalPendingRisk(ledger,facts.native_account_context,now_ms=NOW*1000+100)
    def forbidden(*args,**kwargs):raise AssertionError('current contract update performed a full history scan')
    monkeypatch.setattr(ledger,'iter',forbidden)
    first=runtime.refresh((),now_ms=NOW*1000+100,contracts={'EURUSD':eurusd})[0]
    higher=replace(eurusd,tick_value=eurusd.tick_value*2)
    second=runtime.refresh((),now_ms=NOW*1000+101,contracts={'EURUSD':higher})[0]
    assert first.contract==second.contract==eurusd and second.valuation_contract==higher
    assert second.command_ref==first.command_ref and second.original_input_ref==first.original_input_ref
    assert second.protection_confirmed is second.execution_authority is False


def test_missing_current_symbol_is_a_hold_and_current_boolean_is_not_coerced(tmp_path,eurusd):
    ledger,_,_,_,facts=native_facts(tmp_path,eurusd);command(ledger,facts,'missing-current')
    out,issue=project_pending_risk(N(),ledger,facts.native_account_context,(),now_ms=NOW*1000+100,contracts={})
    assert out==() and issue=='NATIVE_PENDING_RISK_UNAVAILABLE:PendingValuationUnavailable'
    p=pending(ledger,facts)[0];p=replace(p,valuation_contract=replace(eurusd,is_synthetic='false'))
    grant=TradingMandate.from_mapping(mandate_dict(account_alias=facts.account_alias))
    result=RiskAuthority(grant).evaluate_safe(intent(account_alias=facts.account_alias),
        replace(facts,pending_risk_commitments=(p,)))
    assert result.reason_code=='INVALID_BOOLEAN_FACT'


@pytest.mark.parametrize('kind',['single','account'])
@pytest.mark.parametrize('limits,expected',[
    ({'max_open_stop_risk':'0.012'},'CURRENCY_LEG_EXPOSURE'),
    ({'max_open_stop_risk':'0.010','max_currency_leg_exposure':'0.0400'},'PORTFOLIO_HEAT'),
])
def test_actual_native_owner_revalues_pending_loss_with_higher_current_contract(tmp_path,eurusd,kind,limits,expected):
    ledger,adapter,account,_,original=native_facts(tmp_path,eurusd)
    _,first=command(ledger,original,'before-contract-change');receipt(ledger,first,status='ACCEPTED')
    b=other_context(ledger,adapter,account,original,alias='second_alias')
    current=replace(account,account_alias=b.account_alias,
        funding_mark=replace(account.funding_mark,account_alias=b.account_alias),
        used_margin=D(0),free_margin=account.equity,margin_level_pct=None)
    # Existing risk owner receives a changed current contract for this symbol;
    # no broker, native conversion or external account qualification is claimed.
    terms=replace(eurusd,tick_value=eurusd.tick_value*2)
    b=replace(b,symbol_contract=terms)
    owner=producer(kind,ledger,adapter,current,b);now=NOW*1000+100
    if kind=='single':facts=owner.snapshot(now_ms=now,quote_age_ms=0,strategy_id=intent().strategy_id)
    else:
        owner.clock=lambda:now
        facts=owner._snapshot_for(N(symbol='EURUSD',strategy_id=intent().strategy_id))
    assert facts.symbol_contract.tick_value==terms.tick_value
    assert facts.reconciliation_ok and not facts.preservation_blocks_new_risk and not facts.open_positions
    grant=TradingMandate.from_mapping(mandate_dict(account_alias=b.account_alias,
        max_positions_per_instrument=10,max_total_positions=20,**limits))
    result=RiskAuthority(grant).evaluate_safe(intent(account_alias=b.account_alias),facts)
    assert result.reason_code==expected and result.decision.value=='REJECTED',result
