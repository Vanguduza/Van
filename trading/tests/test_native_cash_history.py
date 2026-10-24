"""Read-only cTrader statement facts through the published protocol; no live account."""
from copy import deepcopy
from decimal import Decimal,localcontext
import pytest
from test_retirement_venue_observations import FundsTransport,ctrader
from vati.execution.base import VenueUnavailable

ROW={'operationType':'BALANCE_DEPOSIT','balanceHistoryId':7,'balance':100531234567,'delta':1234567,
    'changeBalanceTimestamp':1500,'balanceVersion':9,'equity':100531239567,'moneyDigits':8,
    'externalNote':'fixture-private-provider-note'}

class NativeCash(FundsTransport):
    host='demo.ctraderapi.com'
    def __init__(self):
        super().__init__();self.rows=[deepcopy(ROW)];self.requests=[];self.response_account=12345;self.response_name='ProtoOACashFlowHistoryListRes'
    def call(self,name,body):
        self.requests.append((name,deepcopy(body)))
        if name=='ProtoOACashFlowHistoryListReq':return self.response_name,{'ctidTraderAccountId':self.response_account,'depositWithdraw':deepcopy(self.rows)}
        if name=='ProtoOADealListReq':return 'ProtoOADealListRes',{'ctidTraderAccountId':12345,'deal':[],'hasMore':False}
        return deepcopy(super().call(name,body))


def test_native_statement_preserves_row_precision_scope_and_native_valuation_without_copying_notes():
    transport=NativeCash();adapter=ctrader(transport)
    result=adapter.cash_movements(from_ms=1000,to_ms=2000);row=result.movements[0]
    assert result.native_account_id==12345 and result.currency=='EUR' and result.deposit_asset_id==2 and result.environment=='DEMO'
    assert row.delta==Decimal('0.01234567') and row.balance_after==Decimal('1005.31234567')
    assert row.equity_after==Decimal('1005.31239567') and row.balance_version==9
    assert 'fixture-private-provider-note' not in str(result.body()) and len(result.digest)==64
    assert transport.requests[2]==('ProtoOACashFlowHistoryListReq',{'ctidTraderAccountId':12345,'fromTimestamp':1000,'toTimestamp':2000})
    assert set(name for name,_ in transport.requests)=={'ProtoOATraderReq','ProtoOAAssetListReq','ProtoOACashFlowHistoryListReq'}

@pytest.mark.parametrize('field,value',[('balanceHistoryId',True),('balanceHistoryId',0),('moneyDigits',None),('moneyDigits',True),
    ('moneyDigits',19),('delta',True),('delta','100'),('balance',None),('equity','100'),('balanceVersion',True),
    ('changeBalanceTimestamp',999),('changeBalanceTimestamp',2001),('operationType',True),('operationType','guessed-deposit')])
def test_incomplete_or_foreign_native_rows_are_refused_as_a_whole_statement(field,value):
    transport=NativeCash();transport.rows[0][field]=value
    with pytest.raises(VenueUnavailable):ctrader(transport).cash_movements(from_ms=1000,to_ms=2000)

@pytest.mark.parametrize('from_ms,to_ms',[(True,2000),(1000,True),(-1,2000),(2000,1000),(0,604800001),(0,2147483646001)])
def test_invalid_native_window_is_refused_before_any_provider_io(from_ms,to_ms):
    transport=NativeCash()
    with pytest.raises(VenueUnavailable):ctrader(transport).cash_movements(from_ms=from_ms,to_ms=to_ms)
    assert transport.requests==[]

@pytest.mark.parametrize('change',['foreign_account','bool_account','wrong_response','conflicting_duplicate','missing_precision','invalid_list'])
def test_unknown_history_never_becomes_a_silently_empty_or_partial_statement(change):
    transport=NativeCash()
    if change=='foreign_account':transport.response_account=67890
    elif change=='bool_account':transport.response_account=True
    elif change=='wrong_response':transport.response_name='ProtoOAReconcileRes'
    elif change=='conflicting_duplicate':transport.rows.append({**ROW,'delta':999})
    elif change=='missing_precision':transport.rows[0].pop('moneyDigits')
    else:transport.rows=None
    with pytest.raises(VenueUnavailable):ctrader(transport).cash_movements(from_ms=1000,to_ms=2000)


def test_repeated_native_identity_is_one_fact_and_an_empty_native_window_is_observed():
    transport=NativeCash();transport.rows*=2
    assert len(ctrader(transport).cash_movements(from_ms=1000,to_ms=2000).movements)==1
    transport.rows=[]
    assert ctrader(transport).cash_movements(from_ms=1000,to_ms=2000).movements==()


def test_unknown_operation_remains_explicit_and_optional_valuation_is_not_guessed():
    transport=NativeCash();transport.rows[0]['operationType']=999;transport.rows[0].pop('equity');transport.rows[0].pop('balanceVersion')
    row=ctrader(transport).cash_movements(from_ms=1000,to_ms=2000).movements[0]
    assert row.operation=='NATIVE_UNKNOWN:999' and row.equity_after is None and row.balance_version is None


def test_native_money_precision_does_not_depend_on_decimal_context():
    transport=NativeCash();transport.rows[0]['delta']=9223372036854775807
    transport.rows[0]['moneyDigits']=18
    with localcontext() as context:
        context.prec=2
        result=ctrader(transport).cash_movements(from_ms=1000,to_ms=2000)
    assert str(result.movements[0].delta)=='9.223372036854775807'


def test_native_currency_change_during_statement_read_is_not_a_verified_currency_guess():
    class ChangedCurrency(NativeCash):
        def call(self,name,body):
            result=super().call(name,body)
            if name=='ProtoOACashFlowHistoryListReq':self.trader['depositAssetId']=1
            return result
    with pytest.raises(VenueUnavailable):ctrader(ChangedCurrency()).cash_movements(from_ms=1000,to_ms=2000)


def test_cash_statements_retain_negative_native_money_through_actual_framed_protocol():
    from test_ctrader import FakeCtrader,make_adapter
    class CashBroker(FakeCtrader):
        def handle(self,name,body,cid):
            if name=='ProtoOACashFlowHistoryListReq':
                return self.send('ProtoOACashFlowHistoryListRes',{'ctidTraderAccountId':12345,
                    'depositWithdraw':[{**ROW,'operationType':'BALANCE_WITHDRAW','delta':-200000001}]},cid)
            return super().handle(name,body,cid)
    native=CashBroker();adapter=make_adapter(native)
    try:
        result=adapter.cash_movements(from_ms=1000,to_ms=2000)
        assert result.movements[0].delta==Decimal('-2.00000001') and result.currency=='USD'
    finally:adapter.transport.close()


@pytest.mark.parametrize('host',[None,'unknown-provider.example','https://demo.ctraderapi.com','demo.ctraderapi.com.evil.example'])
def test_unqualified_provider_environment_cannot_supply_account_scoped_funding_facts(host):
    transport=NativeCash();transport.host=host
    with pytest.raises(VenueUnavailable):ctrader(transport).cash_movements(from_ms=1000,to_ms=2000)
    assert transport.requests==[]


def test_history_observation_time_is_received_after_the_native_read_not_backdated_to_request_start():
    transport=NativeCash();adapter=ctrader(transport);times=iter([5000,6000]);adapter.clock=lambda:next(times)
    result=adapter.cash_movements(from_ms=1000,to_ms=2000)
    assert result.observed_at_ms==6000
