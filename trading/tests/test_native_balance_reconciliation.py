"""Independent capital, fee, native-order and historical-credit counterexamples."""
from dataclasses import replace
from decimal import Decimal as D
import pytest
from vati.core import EventKind,Ledger
from vati.core.events import make_event
from vati.core.ledger import LedgerError
from vati.funding.native import NativeAccountMark,NativeCashStatement,NativeCashMovement
from vati.funding.deals import NativeDealStatement,NativeDeal,NativeCloseBalance
from vati.funding.journal import FundingBook
from vati.funding.deal_journal import DealBook
from vati.funding.reconciliation import period_report

def mark(at,balance='100',equity='100',version=1):
    return NativeAccountMark('CTRADER','DEMO','ctrader_primary',12345,2,'EUR',at,D(balance),D(equity),version,None,None,None)

def snapshot(ledger,point,*,received=None):
    event=make_event(EventKind.ACCOUNT_SNAPSHOT,'vati-service',{'account_alias':point.account_alias,'equity':str(point.net_equity),
        'balance':str(point.balance),'currency':point.currency,'verified':True,'native_account_mark':point.body()},
        event_time_ms=point.observed_at_ms,received_time_ms=received if received is not None else point.observed_at_ms+10,correlation_id=point.account_alias)
    ledger.append(event);return event

def observe(ledger,*,cash=(),deals=(),from_ms=1000,to_ms=3000):
    raw=NativeCashStatement('CTRADER','DEMO','ctrader_primary',12345,2,'EUR',from_ms,to_ms,5000,tuple(cash))
    FundingBook(ledger,clock=lambda:6000).record_statement(raw)
    raw_deals=NativeDealStatement('CTRADER','DEMO','ctrader_primary',12345,2,'EUR',from_ms,to_ms,5000,tuple(deals),1)
    DealBook(ledger,clock=lambda:6000).record_statement(raw_deals)
    return raw.scope_hash

def cash(delta='100',balance='200',version=2,at=2000,operation='BALANCE_DEPOSIT'):
    return NativeCashMovement(7,operation,D(delta),D(balance),D(balance),version,at,2)

def closed(balance='110',version=2,at=2000):
    detail=NativeCloseBalance(D('1.1'),D('12'),D('-1'),D('-1'),D(balance),2,None,version,100)
    return NativeDeal(1,2,3,4,at,'FILLED',100,100,D('1.2'),D('-1'),2,detail)

def test_no_capital_flow_uses_native_net_marks_without_guessing_missing_bonus_or_trade_finality(tmp_path):
    ledger=Ledger(tmp_path/'facts.sqlite');snapshot(ledger,mark(1000));snapshot(ledger,mark(3000,equity='110'))
    scope=observe(ledger);r=period_report(ledger,scope)
    assert r['state']=='MEASURED' and r['balance_state']=='RECONCILED' and D(r['performance']['flow_neutral_return'])==D('.1')
    assert r['return_qualification']=='NOT_ISSUED' and r['trade_alpha_claimed'] is False and r['execution_authority'] is False

def test_all_observed_native_marks_contribute_to_drawdown_even_after_a_recovery(tmp_path):
    ledger=Ledger(tmp_path/'facts.sqlite');snapshot(ledger,mark(1000));dip=snapshot(ledger,mark(2000,equity='80'));snapshot(ledger,mark(3000,equity='110'))
    r=period_report(ledger,observe(ledger))
    assert r['state']=='MEASURED' and D(r['performance']['worst_observed_drawdown'])==D('.2')
    assert dip.hash in r['performance']['evidence_refs']

def test_native_closed_balance_versions_reconcile_without_inventing_final_fee_or_trade_alpha(tmp_path):
    ledger=Ledger(tmp_path/'facts.sqlite');snapshot(ledger,mark(1000));snapshot(ledger,mark(3000,balance='110',equity='112',version=2))
    r=period_report(ledger,observe(ledger,deals=[closed()]))
    assert r['state']=='MEASURED' and r['balance_state']=='RECONCILED' and D(r['performance']['net_account_pnl'])==12
    assert r['trade_alpha_claimed'] is False

def test_external_deposit_reconciles_capital_without_guessing_historical_net_equity(tmp_path):
    ledger=Ledger(tmp_path/'facts.sqlite');snapshot(ledger,mark(1000));snapshot(ledger,mark(3000,balance='200',equity='200',version=2))
    r=period_report(ledger,observe(ledger,cash=[cash()]))
    assert r['state']=='UNMEASURED' and r['balance_state']=='RECONCILED' and r['performance'] is None
    assert r['reason']=='NORMALIZED_HISTORICAL_FLOW_EQUITY_UNAVAILABLE' and r['external_flows'][0]['delta']=='100'
    assert r['cash_neutral_net_account_pnl']=='0' and r['net_account_pnl_excluding_capital_and_separate_business']=='0'

def test_bank_capital_and_ib_business_income_cannot_be_counted_as_trading_profit(tmp_path):
    ledger=Ledger(tmp_path/'facts.sqlite');snapshot(ledger,mark(1000));snapshot(ledger,mark(3000,balance='210',equity='210',version=3))
    deposit=cash();income=replace(cash(delta='10',balance='210',version=3,at=2500,operation='BALANCE_DEPOSIT_IB_COMMISSIONS'),native_id=8)
    r=period_report(ledger,observe(ledger,cash=[deposit,income]))
    assert r['balance_state']=='RECONCILED' and r['cash_neutral_net_account_pnl']=='10'
    assert r['separate_business_income_or_expense']=='10' and r['net_account_pnl_excluding_capital_and_separate_business']=='0'
    assert r['performance'] is None and r['trade_alpha_claimed'] is False

@pytest.mark.parametrize('change,reason',[('version_gap','NATIVE_BALANCE_VERSION_GAP'),('wrong_closing_balance','NATIVE_CLOSING_BALANCE_MISMATCH'),
    ('wrong_cash_delta','NATIVE_CASH_BALANCE_MISMATCH'),('missing_cash_version','NATIVE_CASH_ORDER_UNAVAILABLE'),
    ('unknown_operation','NATIVE_CASH_CLASSIFICATION_UNRESOLVED'),('version_collision','NATIVE_BALANCE_VERSION_COLLISION')])
def test_unreconciled_history_never_looks_like_zero_profit_or_a_qualified_return(tmp_path,change,reason):
    ledger=Ledger(tmp_path/'facts.sqlite');snapshot(ledger,mark(1000));snapshot(ledger,mark(3000,balance='200',equity='200',version=2))
    row=cash();deals=[]
    if change=='version_gap':row=replace(row,balance_version=3)
    elif change=='wrong_closing_balance':row=replace(row,balance_after=D('199'),delta=D('99'))
    elif change=='wrong_cash_delta':row=replace(row,delta=D('99'))
    elif change=='missing_cash_version':row=replace(row,balance_version=None)
    elif change=='unknown_operation':row=replace(row,operation='NATIVE_UNKNOWN:999')
    else:deals=[closed(balance='200')]
    r=period_report(ledger,observe(ledger,cash=[row],deals=deals))
    assert r['state']=='UNMEASURED' and r['reason']==reason and r['performance'] is None

def test_source_coverage_and_original_marks_are_required_instead_of_empty_history_assumptions(tmp_path):
    ledger=Ledger(tmp_path/'facts.sqlite');a=snapshot(ledger,mark(1000));b=snapshot(ledger,mark(3000,equity='105'))
    scope=observe(ledger,to_ms=2000)
    r=period_report(ledger,scope,baseline_ref=a.hash,closing_ref=b.hash)
    assert r['state']=='UNMEASURED' and r['reason']=='NATIVE_PERIOD_COVERAGE_INCOMPLETE'

def test_backdated_native_availability_is_never_used_as_known_at_the_original_time(tmp_path):
    ledger=Ledger(tmp_path/'facts.sqlite');point=mark(1000);snapshot(ledger,point,received=999)
    scope=observe(ledger)
    with pytest.raises(LedgerError,match='native_account_mark_source_invalid'):period_report(ledger,scope)

def test_intermediate_native_balance_cannot_conflict_with_the_reconciled_version(tmp_path):
    ledger=Ledger(tmp_path/'facts.sqlite');snapshot(ledger,mark(1000));snapshot(ledger,mark(2000,balance='99',equity='100'));snapshot(ledger,mark(3000,equity='110'))
    r=period_report(ledger,observe(ledger))
    assert r['reason']=='NATIVE_INTERMEDIATE_MARK_BALANCE_MISMATCH' and r['performance'] is None

def test_native_mark_amount_resource_bounds_apply_before_any_rational_calculation(tmp_path):
    ledger=Ledger(tmp_path/'facts.sqlite');point=mark(1000,equity='1E+4097');snapshot(ledger,point)
    with pytest.raises(LedgerError,match='native_account_mark_source_invalid'):period_report(ledger,observe(ledger))

def test_an_advisor_cannot_supply_native_mark_evidence_by_copying_an_account_body(tmp_path):
    ledger=Ledger(tmp_path/'facts.sqlite');point=mark(1000)
    event=make_event(EventKind.ACCOUNT_SNAPSHOT,'unqualified-advisor',{'account_alias':point.account_alias,'equity':'100',
        'balance':'100','currency':'EUR','verified':True,'native_account_mark':point.body()},event_time_ms=1000,received_time_ms=1010,correlation_id=point.account_alias)
    ledger.append(event)
    with pytest.raises(LedgerError,match='native_account_mark_source_invalid'):period_report(ledger,observe(ledger))
