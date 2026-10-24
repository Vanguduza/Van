"""Native query facts, not a settlement or timezone qualification."""
from copy import deepcopy
from dataclasses import replace
from decimal import Decimal as D
import pytest
from vati.core import Ledger
from vati.funding.mt5 import frame_from_poll,Mt5FundingFrame
from vati.funding.mt5_journal import Mt5FundingBook


def account(**changes):
    scope={'login':12345678,'server':'Broker-Demo','currency':'USD','demo':True}
    a={**scope,'balance':'10000','equity':'10200','credit':'200','currency_digits':2}
    a['funding']={'schema':'van.mt5.cash-telemetry/1','complete':True,'native_from_ms':0,'native_to_ms':9000,'native_clock_ms':8000,
        'binding_before':dict(scope),'balance_before':'10000','credit_before':'200','movements':[]}
    a.update(changes);return a


def frame(**changes):
    a=account();a.update(changes)
    return frame_from_poll('native',a,received_ms=10000,nonce='original-native-poll')


def cash(**changes):
    return {'native_id':9007199254740993,'operation':'DEAL_TYPE_BALANCE','native_time_ms':7500,
        'profit':'10000','commission':'0','swap':'0','fee':'-0.00000013',**changes}


def test_native_credit_is_excluded_without_treating_display_digits_as_a_settlement_quantum():
    a=account();a['funding']['movements']=[cash()]
    f=frame_from_poll('native',a,received_ms=10000,nonce='original-native-poll')
    assert f.net_equity==10000 and f.movements[0].native_id==9007199254740993
    assert f.movements[0].fee==D('-0.00000013')
    assert Mt5FundingFrame.from_body(f.body())==f
    assert f.body()['money_basis']=='NATIVE_DOUBLE_TEXT_NOT_SETTLED_MINOR_UNITS'
    assert f.body()['native_time_basis']=='MT5_TERMINAL_NATIVE_NOT_UTC_QUALIFIED'


@pytest.mark.parametrize('case',['missing','partial','unknown_currency','wrong_before','changed_balance','changed_credit','duplicate',
    'trade_row','nonfinite','bool_id','bool_start','bool_before','too_many','unknown_credit','negative_credit'])
def test_partial_foreign_changed_or_unrepresentable_native_cash_is_not_an_empty_window(case):
    a=account();raw=a['funding']
    if case=='missing':a.pop('funding')
    elif case=='partial':raw['complete']=False
    elif case=='unknown_currency':a['currency']=''
    elif case=='wrong_before':raw['binding_before']['server']='other'
    elif case=='changed_balance':a['balance']='11000'
    elif case=='changed_credit':a['credit']='300'
    elif case=='duplicate':raw['movements']=[cash(),cash()]
    elif case=='trade_row':raw['movements']=[cash(operation='DEAL_TYPE_BUY')]
    elif case=='nonfinite':raw['movements']=[cash(fee='NaN')]
    elif case=='bool_id':raw['movements']=[cash(native_id=True)]
    elif case=='bool_start':raw['native_from_ms']=False
    elif case=='bool_before':raw['binding_before']['login']=True;a['login']=1
    elif case=='too_many':raw['movements']=[cash()]*4097
    elif case=='unknown_credit':a.pop('credit')
    else:a['credit']=raw['credit_before']='-200'
    with pytest.raises((ValueError,KeyError,ArithmeticError)):
        frame_from_poll('native',a,received_ms=10000,nonce='original-native-poll')


def test_unchanged_native_cash_deduplicates_the_large_statement_but_preserves_each_current_query(tmp_path):
    ledger=Ledger(tmp_path/'native.sqlite');book=Mt5FundingBook(ledger,clock=lambda:20000)
    a=account();a['funding']['movements']=[cash()];f=frame_from_poll('native',a,received_ms=10000,nonce='original')
    first,statement=book.capture(f)
    again,old=book.capture(f)
    assert again==first and old==statement
    new=replace(f,observed_at_ms=11000,source_nonce='next',reported_equity=D('10300'))
    second,same=book.capture(new)
    assert second!=first and same==statement
    assert ledger.count(book.kind)==1 and len(book._queries(f.scope_hash))==2
    assert book.observations(f.scope_hash)['movements'][0]['received_at_ms']==20000


def test_native_cash_correction_is_retained_as_a_conflict_and_scope_never_borrows_another_server(tmp_path):
    ledger=Ledger(tmp_path/'native.sqlite');book=Mt5FundingBook(ledger,clock=lambda:20000)
    a=account();a['funding']['movements']=[cash()];f=frame_from_poll('native',a,received_ms=10000,nonce='original')
    original,_=book.capture(f)
    changed=replace(f,source_nonce='corrected',movements=(replace(f.movements[0],profit=D('11000')),))
    _,receipt=book.capture(changed)
    assert receipt['state']=='CONFLICT' and book.observations(f.scope_hash)['state']=='CONFLICT'
    assert book.observations(replace(f,server='another').scope_hash)['state']=='NO_DATA'
