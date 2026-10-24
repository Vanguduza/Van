"""Cash changes must never be sold to the owner as trading performance."""
from decimal import Decimal as D
from vati.core.events import EventKind,make_event
from vati.core.ledger import Ledger
from vati.app.portfolio import account_states,portfolio

def profile(**changes):
    return {'alias':'ctrader_primary','label':'Native','broker':'CTRADER','mode':'DEMO_TRADER',
        'currency':'EUR','demo':True,'enabled':True,'login':'12345',**changes}

def snapshot(ledger,**changes):
    event=make_event(EventKind.ACCOUNT_SNAPSHOT,'vati-service',{'account_alias':'ctrader_primary',
        'equity':'200','balance':'200','currency':'EUR','verified':True,'connected':True,
        'peak_equity':'200','day_start_equity':'100','week_start_equity':'100',**changes},
        event_time_ms=3000,received_time_ms=3000,correlation_id='original-session')
    ledger.append(event);return event

def test_native_deposit_without_qualified_cash_coverage_is_not_reported_as_profit(tmp_path):
    ledger=Ledger(tmp_path/'facts.sqlite');snapshot(ledger)
    account=account_states(ledger,[profile()])[0]
    assert account['day_pnl'] is None and account['week_pnl'] is None and account['drawdown_pct'] is None
    assert account['raw_equity_change']['day']=='100'
    assert account['performance_state']=='UNMEASURED'
    assert portfolio(ledger,[profile()],reporting_currency='EUR')['totals']['day_pnl'] is None

def test_nonfinite_native_equity_is_unknown_instead_of_a_nonfinite_owner_total(tmp_path):
    ledger=Ledger(tmp_path/'facts.sqlite');snapshot(ledger,equity='NaN',balance='Infinity')
    row=account_states(ledger,[profile()])[0]
    assert row['equity'] is None and row['balance'] is None and row['floating_pnl'] is None

def test_native_funding_facts_survive_runtime_snapshot_and_only_current_profile_can_read_them(tmp_path):
    from test_native_cash_history import NativeCash
    from test_retirement_venue_observations import ctrader
    from vati.funding.runtime import capture_funding
    ledger=Ledger(tmp_path/'facts.sqlite');adapter=ctrader(NativeCash());adapter.clock=lambda:3000
    acct=adapter.sync_account();funding=capture_funding(ledger,adapter,acct,now_ms=3000)
    event=snapshot(ledger,funding_observation=funding)
    row=account_states(ledger,[profile()])[0]
    assert row['funding']['state']=='OBSERVED' and row['funding']['snapshot_ref']==event.hash
    assert row['funding']['movement_count']==1 and row['funding']['return_qualification']=='NOT_ISSUED'
    assert row['funding']['movements'][0]['classification']['category']=='EXTERNAL_CAPITAL'
    for changed in (profile(login='99999'),profile(demo=False),profile(currency='USD'),profile(broker='MT5')):
        hidden=account_states(ledger,[changed])[0]
        assert hidden['funding']['reason']=='CURRENT_PROFILE_NATIVE_SCOPE_MISMATCH'
        assert hidden['funding']['movements']==[] and hidden['equity'] is None and hidden['connection_state']=='STALE'
