"""Actual signed native quote protocol over an explicit SDK simulation."""
from types import SimpleNamespace as N
import pytest
from test_mt5_symbol_contract_worker import TermsSdk
from test_mt5_worker_funding import connection
from vati.execution.base import VenueUnavailable


class QuoteSdk(TermsSdk):
    def __init__(self):
        super().__init__();self.on_tick=lambda tick:None;self.tick_available=True
    def symbol_info(self,symbol):
        row=super().symbol_info(symbol);row.select=True;row.subscription_delay=False
        return row
    def symbol_info_tick(self,symbol):
        if not self.tick_available:return None
        row=N(bid=1.10000,ask=1.10008,last=0.,volume_real=0.,volume=0,time=999,time_msc=999950,flags=6)
        self.on_tick(row);return row


def query(adapter,now,**changes):
    b={'alias':adapter.account_alias,'symbol':'EURUSD','deadline_ms':now['ms']+1000};b.update(changes)
    return adapter._call('quote_snapshot',b,now_ms=now['ms'])


@pytest.mark.parametrize('allowed',[True,False])
def test_original_native_prices_timestamp_and_subscription_are_not_a_trade_or_depth_grant(tmp_path,allowed):
    sdk,worker,adapter,now=connection(tmp_path,QuoteSdk());sdk.trade_allowed=allowed
    def forbidden(*args,**kwargs):raise AssertionError('native quote attempted an order operation')
    sdk.order_check=sdk.order_send=forbidden
    q=query(adapter,now)['observation']
    assert q['tick']['bid']=='1.1' and q['tick']['ask']=='1.10008'
    assert q['tick']['time_msc']=='999950' and q['tick']['volume']=='0'
    assert q['symbol_selected'] is True and q['subscription_delayed'] is False
    assert q['contract_before']['symbol']==q['contract_after']['symbol']=='EURUSD'
    assert q['account_before']['login']==q['account_after']['login']==12345678
    assert q['account_snapshot_atomic'] is q['risk_terms_qualified'] is q['execution_authority'] is False
    assert q['volume_basis']=='NATIVE_LAST_TRADE_VOLUME_NOT_LOTS_OR_GENUINE_DEPTH' and not sdk.sent


@pytest.mark.parametrize('field,value',[('bid',True),('ask',float('nan')),('last',-1),
    ('volume_real',float('inf')),('time_msc',False),('flags',-1),('volume',2**64)])
def test_invalid_native_quote_fields_are_unavailable_instead_of_zero_or_live(tmp_path,field,value):
    sdk,worker,adapter,now=connection(tmp_path,QuoteSdk());sdk.on_tick=lambda row:setattr(row,field,value)
    with pytest.raises(VenueUnavailable):query(adapter,now)
    assert not sdk.sent


def test_no_tick_and_missing_native_clock_remain_explicit_without_local_timestamp_fallback(tmp_path):
    sdk,worker,adapter,now=connection(tmp_path,QuoteSdk());sdk.tick_available=False
    assert query(adapter,now)['observation']['tick'] is None
    sdk.tick_available=True;sdk.on_tick=lambda row:setattr(row,'time_msc',None)
    q=query(adapter,now)['observation']
    assert q['tick']['time_msc'] is None and q['received_at_ms']==now['ms'] and not sdk.sent


def test_native_quote_expiry_after_sdk_tick_access_refuses_without_an_order(tmp_path):
    sdk,worker,adapter,now=connection(tmp_path,QuoteSdk())
    sdk.on_tick=lambda row:now.update(ms=now['ms']+1000)
    with pytest.raises(VenueUnavailable):query(adapter,now)
    assert not sdk.sent
