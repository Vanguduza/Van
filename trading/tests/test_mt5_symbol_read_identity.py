"""Signed symbol reads cannot label another account's terms as the original."""
import pytest

from test_mt5_worker_funding import connection,CashMt5
from vati.execution.base import VenueUnavailable


@pytest.mark.parametrize('change',['login','currency','server','demo'])
def test_actual_signed_symbol_read_rechecks_native_identity_after_sdk_access(tmp_path,change):
    sdk,worker,adapter,now=connection(tmp_path,CashMt5())
    symbol=sdk.symbol_info;account=sdk.account_info;changed={'yes':False}
    def switched_symbol(name):
        changed['yes']=True
        if change=='login':sdk._login=87654321
        return symbol(name)
    def current_account():
        value=account()
        if changed['yes'] and change=='currency':value.currency='EUR'
        if changed['yes'] and change=='server':value.server='Different-Broker-Demo'
        if changed['yes'] and change=='demo':value.trade_mode=2
        return value
    sdk.symbol_info=switched_symbol;sdk.account_info=current_account
    with pytest.raises(VenueUnavailable,match='identity|account'):
        adapter._call('sync_symbols',{'alias':adapter.account_alias,'symbols':['EURUSD']},now_ms=now['ms'])
    assert changed['yes'] and not sdk.sent


@pytest.mark.parametrize('allowed',[True,False])
def test_unchanged_signed_symbol_read_retains_legacy_shape_without_an_order_effect(tmp_path,allowed):
    sdk,worker,adapter,now=connection(tmp_path,CashMt5());sdk.trade_allowed=allowed
    result=adapter._call('sync_symbols',{'alias':adapter.account_alias,'symbols':['EURUSD']},now_ms=now['ms'])
    assert result['symbols']==[worker.t.symbol('EURUSD')]
    assert result['identity_binding']==adapter.identity.as_dict()
    assert result['nonce'] and result['worker_time_ms']==now['ms'] and not sdk.sent
