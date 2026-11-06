"""Signed worker cash telemetry; the terminal is an explicit SDK simulation."""
from decimal import Decimal as D
from types import SimpleNamespace as NS
import pytest
from test_mt5_worker import FakeMt5, KEY, worker_mod
from vati.execution.mt5_bridge import Mt5BridgeAdapter, Mt5BridgeClient
from vati.execution.mt5_identity import Mt5Identity


class CashMt5(FakeMt5):
    DEAL_TYPE_BUY, DEAL_TYPE_SELL, DEAL_TYPE_BALANCE, DEAL_TYPE_CREDIT = 0, 1, 2, 3
    def __init__(self):
        super().__init__()
        self.credit = 250.5
        self.cash = [NS(ticket=9007199254740993, type=2, time_msc=999000,
                        profit=10000.0, commission=0.0, swap=0.0, fee=-0.00000013,
                        comment='private-native-description-never-exported')]
    def account_info(self):
        a = super().account_info(); a.credit = self.credit; a.currency_digits = 2
        return a
    def history_deals_get(self, *args, **kwargs):
        return super().history_deals_get(*args, **kwargs) if 'ticket' in kwargs else self.cash


def connection(tmp_path, sdk=None):
    sdk = sdk or CashMt5(); now={'ms':1000000}
    pw=tmp_path/'pw'; pw.write_text('s3cret\n')
    worker=worker_mod.Worker({'nonce_store':str(tmp_path/'nonce.sqlite'),'accounts':{
        'native':{'login':12345678,'server':'Broker-Demo','currency':'USD','demo':True,'password_file':str(pw)}}},
        worker_mod.Terminal(sdk),KEY,clock=lambda:now['ms'])
    client=Mt5BridgeClient(signing_key=KEY,transport=worker.handle)
    adapter=Mt5BridgeAdapter(client,account_alias='native',clock=lambda:now['ms'],identity=Mt5Identity('12345678','Broker-Demo','USD',True))
    return sdk,worker,adapter,now


def test_worker_keeps_original_cash_money_and_nonce_and_excludes_native_credit(tmp_path):
    sdk,worker,adapter,now=connection(tmp_path)
    account=adapter.sync_account(); frame=account.funding_mark
    assert frame is not None and account.equity==D('10000.0') and account.balance==D('10000.0')
    assert frame.credit==D('250.5') and frame.source_nonce==str(adapter.client.sent[-1].nonce)
    assert frame.source_kind=='MT5_SIGNED_MTLS_READ'
    assert frame.body()['native_time_basis']=='MT5_PYTHON_QUERY_UTC_HOST_NOT_BROKER_CLOCK'
    assert frame.movements[0].native_id==9007199254740993
    assert frame.movements[0].fee==D('-0.00000013')
    assert 'private-native-description' not in str(frame.body())
    assert not sdk.sent


@pytest.mark.parametrize('damage',['none','throws','badfee','missingfee','boolticket','duplicate',
    'overbound','missingcredit','missingdigits','identitychange','balancechange','creditchange','expiredquery'])
def test_unavailable_or_changed_cash_fails_closed_without_breaking_account_protection_reads(tmp_path,damage):
    sdk,worker,adapter,now=connection(tmp_path)
    if damage=='none':sdk.cash=None
    elif damage=='throws':
        def unavailable(*a,**k):raise RuntimeError('private broker details')
        sdk.history_deals_get=unavailable
    elif damage=='badfee':sdk.cash[0].fee=float('nan')
    elif damage=='missingfee':del sdk.cash[0].fee
    elif damage=='boolticket':sdk.cash[0].ticket=True
    elif damage=='duplicate':sdk.cash*=2
    elif damage=='overbound':sdk.cash*=4097
    elif damage in {'missingcredit','missingdigits'}:
        original=sdk.account_info
        def missing():
            a=original();delattr(a,'credit' if damage=='missingcredit' else 'currency_digits');return a
        sdk.account_info=missing
    else:
        original=sdk.history_deals_get
        def changed(*a,**k):
            rows=original(*a,**k)
            if damage=='identitychange':sdk._login+=1
            elif damage=='creditchange':sdk.credit+=1
            elif damage=='balancechange':
                before=sdk.account_info
                def next_account():
                    result=before();result.balance+=1;return result
                sdk.account_info=next_account
            else:now['ms']+=2000
            return rows
        sdk.history_deals_get=changed
    account=adapter.sync_account()
    assert account.verified is True and account.funding_mark is None
    assert adapter._funding_issue=='MT5_NATIVE_CASH_HISTORY_UNAVAILABLE'
    assert not sdk.sent


def test_unknown_native_operation_is_preserved_instead_of_disappearing(tmp_path):
    sdk,worker,adapter,now=connection(tmp_path);sdk.cash[0].type=700
    frame=adapter.sync_account().funding_mark
    assert frame is not None and frame.movements[0].operation=='DEAL_TYPE_UNKNOWN_700'
