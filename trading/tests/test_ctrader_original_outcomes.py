"""Pre-change probes for native ambiguous effects and partial close facts."""
from copy import deepcopy
from decimal import Decimal as D
import pytest
from vati.execution.ctrader.adapter import CtraderAdapter,SymbolInfo
from vati.execution.ctrader.transport import CtraderError
from vati.execution.base import OrderCommand,StopMode
from vati.risk.contracts import Direction,LossModel

class NativeOutcomes:
    connected=True
    def __init__(self):
        self.requests=[];self.lost=None;self.event=None
        self.position={'positionId':7,'tradeData':{'symbolId':1,'volume':1000000,'tradeSide':'BUY'},
            'positionStatus':'POSITION_STATUS_OPEN','price':1.1,'stopLoss':1.09}
    def call(self,name,body):
        self.requests.append((name,deepcopy(body)))
        if name=='ProtoOAReconcileReq':return 'ProtoOAReconcileRes',{'ctidTraderAccountId':12345,'position':[deepcopy(self.position)],'order':[]}
        if name==self.lost:raise CtraderError('reply lost after native admission')
        return 'ProtoOAExecutionEvent',{'ctidTraderAccountId':12345,'executionType':'ORDER_ACCEPTED',
            'order':{'orderId':9,'closingOrder':name=='ProtoOAClosePositionReq'}}
    def wait_event(self,predicate,**kw):
        return ('ProtoOAExecutionEvent',self.event) if self.event is not None and predicate('ProtoOAExecutionEvent',self.event) else None

def adapter(native):
    a=CtraderAdapter(native,'fixture',lambda:'fixture',lambda:'fixture',12345,fill_timeout_s=.01)
    a._authed=True;a.symbols={'EURUSD':SymbolInfo(1,'EURUSD',5,10000000,1000,1000,1000000000)}
    return a

def cmd():
    return OrderCommand('original-entry','a'*64,'original','ct_native','ctrader','EURUSD',Direction.LONG,
        'MARKET',D('.1'),D('1.1'),D('1.09'),StopMode.VENUE,LossModel.STOP_DISTANCE).sealed()

@pytest.mark.parametrize('action,native_request',[('entry','ProtoOANewOrderReq'),('close','ProtoOAClosePositionReq'),('stop','ProtoOAAmendPositionSLTPReq')])
def test_lost_native_reply_preserves_unknown_effect(action,native_request):
    n=NativeOutcomes();n.lost=native_request;a=adapter(n)
    if action=='entry':r=a.submit(cmd(),now_ms=1000)
    elif action=='close':r=a.close('7',None,now_ms=1000,reason='OWNER')
    else:r=a.modify_stop('7',D('1.095'),now_ms=1000)
    assert r.status=='UNKNOWN' and not r.protective_stop_confirmed
    assert sum(name==native_request for name,_ in n.requests)==1


def event(kind='ORDER_PARTIAL_FILL'):
    return {'ctidTraderAccountId':12345,'executionType':kind,
        'order':{'orderId':9,'closingOrder':True},
        'position':{'positionId':7,'stopLoss':1.09},
        'deal':{'dealId':8,'positionId':7,'orderId':9,'symbolId':1,'filledVolume':10000,'executionPrice':1.105}}


def test_partial_close_is_not_reported_as_fully_closed():
    n=NativeOutcomes();n.event=event();r=adapter(n).close('7',D('.01'),now_ms=1000,reason='OWNER')
    assert r.status=='PARTIAL' and r.filled_qty==D('.001') and r.average_fill==D('1.105')


@pytest.mark.parametrize('defect',['foreign_account','entry_deal','missing_filled_volume','excess_fill','missing_price'])
def test_unbound_or_incomplete_close_facts_do_not_claim_flat(defect):
    n=NativeOutcomes();n.event=event('ORDER_FILLED')
    if defect=='foreign_account':n.event['ctidTraderAccountId']=54321
    elif defect=='entry_deal':n.event['order']['closingOrder']=False
    elif defect=='missing_filled_volume':n.event['deal'].pop('filledVolume')
    elif defect=='excess_fill':n.event['deal']['filledVolume']=1000001
    elif defect=='missing_price':n.event['deal'].pop('executionPrice')
    r=adapter(n).close('7',D('.01'),now_ms=1000,reason='OWNER')
    assert r.status=='UNKNOWN' and not r.protective_stop_confirmed


def test_known_native_full_close_retains_its_actual_quantity_and_price():
    n=NativeOutcomes();n.event=event('ORDER_FILLED');n.event['deal']['filledVolume']=100000
    r=adapter(n).close('7',D('.01'),now_ms=1000,reason='OWNER')
    assert r.status=='FILLED' and r.filled_qty==D('.01') and r.average_fill==D('1.105')


def test_explicit_native_order_refusal_stays_a_proven_refusal():
    from vati.execution.ctrader.transport import CtraderApiError
    class Refused(NativeOutcomes):
        def call(self,name,body):
            if name=='ProtoOANewOrderReq':raise CtraderApiError('NOT_ENOUGH_MONEY','native refusal')
            return super().call(name,body)
    r=adapter(Refused()).submit(cmd(),now_ms=1000)
    assert r.status=='REJECTED' and r.filled_qty==0


@pytest.mark.parametrize('defect',['other_order','string_quantity','bool_quantity','nonfinite_price'])
def test_malformed_or_old_close_deal_does_not_settle_this_original(defect):
    n=NativeOutcomes();n.event=event('ORDER_FILLED')
    if defect=='other_order':n.event['deal']['orderId']=10
    elif defect=='string_quantity':n.event['deal']['filledVolume']='10000'
    elif defect=='bool_quantity':n.event['deal']['filledVolume']=True
    else:n.event['deal']['executionPrice']='NaN'
    assert adapter(n).close('7',D('.01'),now_ms=1000,reason='OWNER').status=='UNKNOWN'


@pytest.mark.parametrize('defect',['malformed_stop','foreign_position'])
def test_actual_partial_close_is_preserved_without_invented_remaining_protection(defect):
    n=NativeOutcomes();n.event=event()
    if defect=='malformed_stop':n.event['position']['stopLoss']='bad'
    else:n.event['position']['positionId']=8
    r=adapter(n).close('7',D('.01'),now_ms=1000,reason='OWNER')
    assert r.status=='PARTIAL' and r.filled_qty==D('.001') and not r.protective_stop_confirmed


@pytest.mark.parametrize('defect',['zero_quantity','string_quantity','bool_quantity','missing_price','foreign_position'])
def test_incomplete_entry_execution_is_unknown_not_a_fabricated_fill(defect):
    n=NativeOutcomes();n.event=event('ORDER_FILLED')
    n.event['order'].update(clientOrderId='original-entry',closingOrder=False)
    if defect=='zero_quantity':n.event['deal']['filledVolume']=0
    elif defect=='string_quantity':n.event['deal']['filledVolume']='10000'
    elif defect=='bool_quantity':n.event['deal']['filledVolume']=True
    elif defect=='missing_price':n.event['deal'].pop('executionPrice')
    else:n.event['position']['positionId']=8
    r=adapter(n).submit(cmd(),now_ms=1000)
    assert r.status=='UNKNOWN' and not r.protective_stop_confirmed


def test_entry_above_native_maximum_is_refused_before_sending():
    n=NativeOutcomes();a=adapter(n);a.symbols['EURUSD'].max_volume=10000
    r=a.submit(cmd(),now_ms=1000)
    assert r.status=='REJECTED' and not any(name=='ProtoOANewOrderReq' for name,_ in n.requests)


def test_accepted_stop_without_native_matching_readback_stays_unknown():
    n=NativeOutcomes();r=adapter(n).modify_stop('7',D('1.095'),now_ms=1000)
    assert r.status=='UNKNOWN' and not r.protective_stop_confirmed
