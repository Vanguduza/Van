"""Native symbol terms over the actual signed protocol and explicit SDK fixture."""
import pytest
from test_mt5_worker_funding import CashMt5,connection
from vati.execution.base import VenueUnavailable


class TermsSdk(CashMt5):
    def __init__(self):
        super().__init__();self.on_symbol=lambda value:None
    def symbol_info(self,symbol):
        value=super().symbol_info(symbol)
        value.name=symbol;value.trade_tick_value=1.1
        value.trade_tick_value_profit=1.1;value.trade_tick_value_loss=.9
        value.trade_freeze_level=0;value.trade_calc_mode=0
        value.currency_base='EUR';value.currency_profit='USD';value.currency_margin='EUR'
        self.on_symbol(value)
        return value


def query(adapter,now,**changes):
    body={'alias':adapter.account_alias,'symbol':'EURUSD','deadline_ms':now['ms']+1000}
    body.update(changes)
    return adapter._call('symbol_contract',body,now_ms=now['ms'])


@pytest.mark.parametrize('allowed',[True,False])
def test_actual_signed_read_retains_original_loss_profit_currency_and_scope_without_permission(tmp_path,allowed):
    sdk,worker,adapter,now=connection(tmp_path,TermsSdk());sdk.trade_allowed=allowed
    def forbidden(*args,**kwargs):raise AssertionError('symbol read attempted a native order operation')
    sdk.order_check=sdk.order_send=forbidden
    body=query(adapter,now)['observation'];c=body['contract']
    assert body['request']=={'symbol':'EURUSD'}
    assert c['trade_tick_value_loss']=='0.9' and c['trade_tick_value_profit']=='1.1' and c['trade_tick_value']=='1.1'
    assert c['currency_base']=='EUR' and c['currency_profit']=='USD' and c['currency_margin']=='EUR'
    assert body['account_before']['login']==body['account_after']['login']==12345678
    assert body['received_at_ms']<body['deadline_ms'] and body['native_numeric_format']=='PYTHON_BINARY64_SHORTEST'
    assert body['account_snapshot_atomic'] is body['risk_terms_qualified'] is body['execution_authority'] is False
    assert not sdk.sent


@pytest.mark.parametrize('field,value',[
    ('volume_min',None),('volume_step',0),('volume_max',True),('trade_contract_size',float('inf')),
    ('trade_tick_size',-1),('trade_tick_value_loss',True),('trade_tick_value_profit',float('nan')),
    ('currency_base',None),('currency_profit',12),('trade_freeze_level',False),
    ('trade_calc_mode',-1),('digits',True),('name','OTHER'),
])
def test_missing_malformed_or_other_symbol_terms_do_not_become_valid_native_data(tmp_path,field,value):
    sdk,worker,adapter,now=connection(tmp_path,TermsSdk());sdk.on_symbol=lambda row:setattr(row,field,value)
    with pytest.raises(VenueUnavailable):query(adapter,now)
    assert not sdk.sent


@pytest.mark.parametrize('changes',[{'symbol':'EUR|USD'},{'symbol':''},{'symbol':True},
    {'deadline_ms':1000000},{'deadline_ms':True}])
def test_invalid_original_symbol_request_refuses_without_native_effect(tmp_path,changes):
    sdk,worker,adapter,now=connection(tmp_path,TermsSdk())
    with pytest.raises(VenueUnavailable):query(adapter,now,**changes)
    assert not sdk.sent


def test_deadline_is_rechecked_after_sdk_read_and_explicit_zero_remains_unpriced_data(tmp_path):
    sdk,worker,adapter,now=connection(tmp_path,TermsSdk())
    sdk.on_symbol=lambda row:now.update(ms=now['ms']+1000)
    with pytest.raises(VenueUnavailable):query(adapter,now)
    sdk.on_symbol=lambda row:setattr(row,'trade_tick_value_loss',0)
    body=query(adapter,now)['observation']
    assert body['contract']['trade_tick_value_loss']=='0' and body['risk_terms_qualified'] is False
    assert not sdk.sent
