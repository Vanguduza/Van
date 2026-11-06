"""Original SQL-backed native observations bound capacity without grants."""
from dataclasses import replace
from decimal import Decimal as D

import pytest

from conftest import NOW
from test_native_risk_history_inputs import native_facts,record
from test_native_risk_history_index import other_context
from vati.core import Ledger,EventKind
from vati.core.units import Money
from vati.risk.native_collateral import original_native_collateral


def observed(ledger,facts,**changes):
    event=record(ledger,replace(facts,**changes))
    return event,original_native_collateral(ledger,event.hash,available_at_ms=NOW*1000)


def test_original_reported_free_margin_never_exceeds_cash_equity_after_native_commitments(tmp_path,eurusd):
    ledger,_,_,_,facts=native_facts(tmp_path,eurusd)
    event,value=observed(ledger,facts,used_margin=D('1000.00'),free_margin=D('11000.00'),margin_level_pct=D('1200'))
    before=ledger.count();body=value.body()
    assert body['state']=='MEASURED'
    assert Money.from_body(body['net_equity']).decimal==D('10000')
    assert Money.from_body(body['reported_free_margin']).decimal==D('11000.00')
    assert Money.from_body(body['available_capacity']).decimal==D('9000.00')
    assert body['execution_authority'] is body['risk_capital_qualified'] is False
    assert body['source_event_ref']==event.hash
    assert ledger.count()==before and ledger.count(EventKind.ORDER_COMMAND)==0
    copy=value.body();copy['state']='INVENTED';assert value.body()['state']=='MEASURED'


@pytest.mark.parametrize('used,free,level',[('0','10000',None),('1000','8000','1000'),('1000','-20','1000')])
def test_native_zero_usage_and_actual_negative_free_margin_are_distinct_from_unknown(tmp_path,eurusd,used,free,level):
    ledger,_,_,_,facts=native_facts(tmp_path,eurusd)
    _,value=observed(ledger,facts,used_margin=D(used),free_margin=D(free),
        margin_level_pct=None if level is None else D(level))
    p=value.body();assert p['state']=='MEASURED'
    assert Money.from_body(p['reported_free_margin']).decimal==D(free)
    assert Money.from_body(p['available_capacity']).decimal==max(D(0),min(D(free),facts.equity-D(used)))


@pytest.mark.parametrize('changes',[{'used_margin':None},{'free_margin':None},
    {'used_margin':D('10'),'margin_level_pct':None}])
def test_missing_original_margin_is_unmeasured_not_zero_capacity(tmp_path,eurusd,changes):
    ledger,_,_,_,facts=native_facts(tmp_path,eurusd)
    _,value=observed(ledger,facts,**changes)
    assert value.body()['state']=='UNMEASURED' and value.body()['available_capacity'] is None


@pytest.mark.parametrize('changes',[{'used_margin':D('-1')},
    {'used_margin':D('0'),'margin_level_pct':D('0')}, {'free_margin':D('NaN')}])
def test_invalid_margin_never_supplies_a_capacity_fallback(tmp_path,eurusd,changes):
    ledger,_,_,_,facts=native_facts(tmp_path,eurusd)
    _,value=observed(ledger,facts,**changes)
    assert value.body()['state']=='UNAVAILABLE' and value.body()['available_capacity'] is None


def test_readback_remains_original_after_expiry_reopen_and_alias_change(tmp_path,eurusd):
    ledger,adapter,account,_,a=native_facts(tmp_path,eurusd)
    event,first=observed(ledger,a,used_margin=D(0),free_margin=a.equity,margin_level_pct=None)
    b=other_context(ledger,adapter,account,a,alias='another_alias')
    record(ledger,b)
    reopened=Ledger(ledger.path)
    original=original_native_collateral(reopened,event.hash,available_at_ms=(NOW+90*86400)*1000)
    assert original==first and original.body()['origin_alias']==a.account_alias
    assert original.body()['monetary_scope_hash']==a.native_account_context.monetary_scope_hash
    assert original.body()['execution_authority'] is False


def test_bad_reference_or_missing_original_context_never_borrows_current_configuration(tmp_path,eurusd):
    ledger,_,_,_,facts=native_facts(tmp_path,eurusd)
    event=record(ledger,replace(facts,native_account_context=None))
    for ref in (event.hash,'0'*64):
        p=original_native_collateral(ledger,ref,available_at_ms=NOW*1000).body()
        assert p['state']=='UNAVAILABLE' and p['available_capacity'] is None
        assert 'monetary_scope_hash' not in p


def test_original_ctrader_cash_bound_keeps_its_actual_native_monetary_scope(tmp_path,eurusd):
    from conftest import snapshot
    from test_funding_risk_fence import book,native,mark
    from vati.risk.account_context import context_for_account
    ledger,_,_=book(tmp_path)
    adapter,account=native(mark(3500,equity='98'))
    context=context_for_account(ledger,adapter,account,now_ms=10000)
    facts=snapshot(replace(eurusd,venue=adapter.venue,account_currency=account.currency),account_alias=account.account_alias,
        equity=account.equity,balance=account.balance,native_account_context=context)
    _,value=observed(ledger,facts,used_margin=D('40'),free_margin=D('99'),margin_level_pct=D('300'))
    body=value.body();assert body['state']=='MEASURED', body
    amount=Money.from_body(body['available_capacity'])
    assert amount.decimal==D('58') and amount.asset_ref==context.monetary_scope_hash
    assert body['source_query_ref'] is None and body['execution_authority'] is False


def test_uncommitted_native_input_never_supplies_durable_collateral(tmp_path,eurusd):
    ledger,_,_,_,facts=native_facts(tmp_path,eurusd)
    with pytest.raises(RuntimeError,match='deliberate rollback'):
        with ledger.atomic():
            event=record(ledger,replace(facts,used_margin=D(0),free_margin=facts.equity,margin_level_pct=None))
            p=original_native_collateral(ledger,event.hash,available_at_ms=NOW*1000).body()
            assert p['state']=='UNAVAILABLE' and p['available_capacity'] is None
            raise RuntimeError('deliberate rollback')
    assert original_native_collateral(ledger,event.hash,available_at_ms=NOW*1000).body()['state']=='UNAVAILABLE'


def test_original_collateral_retains_first_source_availability(tmp_path,eurusd):
    ledger,_,_,_,facts=native_facts(tmp_path,eurusd)
    event=record(ledger,replace(facts,used_margin=D(0),free_margin=facts.equity,
        margin_level_pct=None),now_ms=NOW*1000+1)
    assert original_native_collateral(ledger,event.hash,available_at_ms=NOW*1000).body()['state']=='UNAVAILABLE'
    assert original_native_collateral(ledger,event.hash,available_at_ms=NOW*1000+1).body()['state']=='MEASURED'


def test_equal_currency_labels_cannot_merge_other_native_accounts_budget_units(tmp_path,eurusd):
    from vati.core.units import UnitError
    ledger,adapter,account,_,a=native_facts(tmp_path,eurusd)
    _,first=observed(ledger,a,used_margin=D(0),free_margin=a.equity,margin_level_pct=None)
    b=other_context(ledger,adapter,account,a,alias='same_currency_other_account',server='Another-Broker-Demo')
    _,second=observed(ledger,b,used_margin=D(0),free_margin=b.equity,margin_level_pct=None)
    one,two=(Money.from_body(v.body()['available_capacity']) for v in (first,second))
    assert one.currency==two.currency and one.asset_ref!=two.asset_ref
    with pytest.raises(UnitError,match='ASSET_MISMATCH'):one+two
