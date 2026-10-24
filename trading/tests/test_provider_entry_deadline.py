"""Real transport dispatch boundaries with controlled native wire interfaces."""
from dataclasses import replace
from decimal import Decimal as D
import json,struct,time
import pytest
from vati.execution.ctrader import CtraderTransport,SCHEMA
from test_ctrader_original_outcomes import adapter,cmd,event
from test_deriv_native_identity import factory,native,command

class Wire:
    def __init__(self,t,clock,late_reply=False,lost=False):
        self.t=t;self.clock=clock;self.sent=[];self.late_reply=late_reply;self.lost=lost
    def sendall(self,frame):
        name,body,cid=SCHEMA.unwrap(frame[4:])
        if name=='ProtoOAGetAccountListByAccessTokenReq':
            self.t._pending[cid].put(('ProtoOAGetAccountListByAccessTokenRes',{'ctidTraderAccount':[{'ctidTraderAccountId':12345,'isLive':False}]}));return
        self.sent.append((name,body))
        if self.lost:raise OSError('fixture reply unavailable after native write')
        ev=event('ORDER_FILLED');ev['order'].update(clientOrderId=body['clientOrderId'],closingOrder=False)
        ev['deal']['filledVolume']=body['volume']
        ev['position']['stopLoss']=ev['deal']['executionPrice']-body['relativeStopLoss']/100000
        if self.late_reply:self.clock['ms']=3000
        self.t._pending[cid].put(('ProtoOAExecutionEvent',ev))
    def close(self):pass

class DelayLock:
    def __init__(self,clock):self.clock=clock
    def __enter__(self):self.clock['ms']=2000
    def __exit__(self,*a):pass

def ctrader(*,late_lock=False,late_reply=False,lost=False):
    clock={'ms':1000};t=CtraderTransport();w=Wire(t,clock,late_reply,lost)
    t._sock=w;t._alive=True;t._last_hb=time.monotonic()
    if late_lock:t._lock=DelayLock(clock)
    a=adapter(t);a.clock=lambda:clock['ms']
    c=replace(cmd(),expires_at_ms=2000,command_hash='').sealed()
    return a,c,w,clock

def test_ctrader_expiry_during_final_send_lock_prevents_any_native_write():
    a,c,w,_=ctrader(late_lock=True);r=a.submit(c,now_ms=1000)
    assert r.status=='REJECTED' and w.sent==[], 'expired entry reached the actual native framed send'

def test_ctrader_current_bounded_entry_still_fills_exactly_once():
    a,c,w,_=ctrader();r=a.submit(c,now_ms=1000)
    assert r.status=='FILLED' and len(w.sent)==1 and r.filled_qty==D('.1')

def test_ctrader_expiry_after_native_write_cannot_rewrite_a_genuine_fill():
    a,c,w,_=ctrader(late_reply=True);r=a.submit(c,now_ms=1000)
    assert r.status=='FILLED' and len(w.sent)==1

def test_ctrader_lost_response_after_native_write_is_unknown_not_a_new_refusal():
    a,c,w,_=ctrader(lost=True);r=a.submit(c,now_ms=1000)
    assert r.status=='UNKNOWN' and len(w.sent)==1

@pytest.mark.parametrize('phase',['authorize','proposal'])
def test_deriv_expiry_during_native_preparation_never_sends_the_buy(tmp_path,monkeypatch,phase):
    a,sockets,_=factory(tmp_path,monkeypatch,native());clock={'ms':1000};a.clock=lambda:clock['ms']
    real=a.transport._exchange_locked
    def delayed(msg,*args,**kwargs):
        response=real(msg,*args,**kwargs)
        if phase in msg:clock['ms']=2000
        return response
    monkeypatch.setattr(a.transport,'_exchange_locked',delayed)
    c=replace(command(),expires_at_ms=2000,command_hash='').sealed();r=a.submit(c,now_ms=1000)
    assert r.status=='REJECTED' and not any('buy'in q for s in sockets for q in s.requests), 'expired grant reached native buy'

def test_deriv_current_bounded_entry_still_fills_once(tmp_path,monkeypatch):
    a,sockets,_=factory(tmp_path,monkeypatch,native());a.clock=lambda:1000
    r=a.submit(replace(command(),expires_at_ms=2000,command_hash='').sealed(),now_ms=1000)
    assert r.status=='FILLED' and sum('buy'in q for s in sockets for q in s.requests)==1

def test_deriv_expiry_after_actual_buy_keeps_genuine_fill(tmp_path,monkeypatch):
    a,sockets,_=factory(tmp_path,monkeypatch,native());clock={'ms':1000};a.clock=lambda:clock['ms'];real=a.transport._exchange_locked
    def delayed(msg,*args,**kwargs):
        response=real(msg,*args,**kwargs)
        if 'buy'in msg:clock['ms']=3000
        return response
    monkeypatch.setattr(a.transport,'_exchange_locked',delayed)
    r=a.submit(replace(command(),expires_at_ms=2000,command_hash='').sealed(),now_ms=1000)
    assert r.status=='FILLED' and sum('buy'in q for s in sockets for q in s.requests)==1

@pytest.mark.parametrize('bad',[True,False,0,-1,2**63,'2000'])
@pytest.mark.parametrize('provider',['ctrader','deriv'])
def test_malformed_explicit_deadline_never_reaches_native_entry(tmp_path,monkeypatch,bad,provider):
    if provider=='ctrader':
        a,c,w,_=ctrader();c=replace(c,expires_at_ms=bad,command_hash='').sealed()
        r=a.submit(c,now_ms=1000);sent=w.sent
    else:
        a,sockets,_=factory(tmp_path,monkeypatch,native());a.clock=lambda:1000
        r=a.submit(replace(command(),expires_at_ms=bad,command_hash='').sealed(),now_ms=1000)
        sent=[q for sock in sockets for q in sock.requests if 'buy'in q]
    assert r.status=='REJECTED' and sent==[]

@pytest.mark.parametrize('bad',[True,None,'1000',-1])
@pytest.mark.parametrize('provider',['ctrader','deriv'])
def test_unqualified_current_clock_cannot_authorize_native_entry(tmp_path,monkeypatch,bad,provider):
    if provider=='ctrader':
        a,c,w,_=ctrader();a.clock=lambda:bad;r=a.submit(c,now_ms=1000);sent=w.sent
    else:
        a,sockets,_=factory(tmp_path,monkeypatch,native());a.clock=lambda:bad
        r=a.submit(replace(command(),expires_at_ms=2000,command_hash='').sealed(),now_ms=1000)
        sent=[q for sock in sockets for q in sock.requests if 'buy'in q]
    assert r.status=='REJECTED' and sent==[]

def test_ctrader_expiry_during_native_transport_connect_is_also_checked(monkeypatch):
    a,c,w,clock=ctrader();original=a.transport.connect
    def connect():original();clock['ms']=2000
    monkeypatch.setattr(a.transport,'connect',connect)
    assert a.submit(c,now_ms=1000).status=='REJECTED' and w.sent==[]

def test_deriv_lost_bounded_buy_reply_remains_uncertain_and_is_never_replayed(tmp_path,monkeypatch):
    from test_deriv_native_identity import Socket
    from vati.execution.base import VenueUnavailable
    a,sockets,_=factory(tmp_path,monkeypatch,native());a.clock=lambda:1000;original=Socket.recv
    def lost(self):
        if self.requests and 'buy'in self.requests[-1]:raise TimeoutError('fixture missing native response')
        return original(self)
    monkeypatch.setattr(Socket,'recv',lost)
    with pytest.raises(VenueUnavailable,match='reconcile'):
        a.submit(replace(command(),expires_at_ms=2000,command_hash='').sealed(),now_ms=1000)
    assert len(sockets)==1 and sum('buy'in q for s in sockets for q in s.requests)==1

@pytest.mark.parametrize('late',[False,True])
def test_actual_router_binds_ctrader_mandate_and_original_quote_through_wire_dispatch(tmp_path,eurusd,late):
    from conftest import NOW,mandate_dict,snapshot,intent
    from vati.core import Ledger,EventKind
    from vati.execution import ExecutionRouter,ProtectionManager
    from vati.execution.risk_refresh import CurrentRiskFacts
    from vati.execution.pretrade import MarketReference
    from vati.risk import RiskAuthority,TradingMandate,KillSwitch,Decision
    a,_,wire,clock=ctrader();clock['ms']=NOW*1000
    m=TradingMandate.from_mapping(mandate_dict(venue='ctrader',account_alias=a.account_alias,expires_at_unix=NOW+1))
    trade=intent(venue='ctrader',account_alias=a.account_alias)
    facts=snapshot(replace(eurusd,venue='ctrader'),account_alias=a.account_alias)
    authority=RiskAuthority(m);approved=authority.evaluate_safe(trade,facts)
    assert approved.decision in {Decision.APPROVED,Decision.REDUCED}
    ledger=Ledger();router=ExecutionRouter(ledger=ledger,adapters={'ctrader':a},kill_switch=KillSwitch(),protection=ProtectionManager(),clock=lambda:clock['ms'],current_risk_authority=authority,current_risk_facts_provider=lambda *args,**kwargs:CurrentRiskFacts(facts,clock['ms']))
    if late:
        class LastWriteLock:
            def __enter__(self):clock['ms']=NOW*1000+101
            def __exit__(self,*args):pass
        a.transport._lock=LastWriteLock()
    result=router.execute(trade,approved,m,now_ms=clock['ms'],entry_type='MARKET',market_reference=MarketReference(trade.entry,0,100))
    command_event=next(ledger.iter(EventKind.ORDER_COMMAND))
    assert command_event.payload['expires_at_ms']==NOW*1000+101
    assert result.status==('REJECTED' if late else 'FILLED') and len(wire.sent)==(0 if late else 1)

@pytest.mark.parametrize('provider',['ctrader','deriv'])
def test_broken_clock_is_a_known_no_send_refusal(tmp_path,monkeypatch,provider):
    def unavailable():raise RuntimeError('fixture clock unavailable')
    if provider=='ctrader':
        a,c,w,_=ctrader();a.clock=unavailable;r=a.submit(c,now_ms=1000);sent=w.sent
    else:
        a,sockets,_=factory(tmp_path,monkeypatch,native());a.clock=unavailable
        r=a.submit(replace(command(),expires_at_ms=2000,command_hash='').sealed(),now_ms=1000)
        sent=[q for sock in sockets for q in sock.requests if 'buy'in q]
    assert r.status=='REJECTED' and sent==[]

@pytest.mark.parametrize('provider',['ctrader','deriv'])
def test_legacy_transport_cannot_silently_drop_an_explicit_deadline(provider):
    from vati.execution.deriv import DerivAdapter
    if provider=='ctrader':
        from test_ctrader_original_outcomes import NativeOutcomes
        native_transport=NativeOutcomes();a=adapter(native_transport);a.clock=lambda:1000
        r=a.submit(replace(cmd(),expires_at_ms=2000,command_hash='').sealed(),now_ms=1000)
        sent=native_transport.requests
    else:
        sent=[]
        def legacy(msg):sent.append(msg);return {'proposal':{'id':'fixture'}}
        a=DerivAdapter(account_alias=command().account_alias,transport=legacy,clock=lambda:1000)
        r=a.submit(replace(command(),expires_at_ms=2000,command_hash='').sealed(),now_ms=1000)
    assert r.status=='REJECTED' and sent==[]

def test_deriv_expiry_during_buy_reauthorization_is_checked_at_the_actual_financial_write(tmp_path,monkeypatch):
    a,sockets,_=factory(tmp_path,monkeypatch,native());clock={'ms':1000};a.clock=lambda:clock['ms']
    real=a.transport._exchange_locked;prepared={'buy':False}
    def delayed(msg,*args,**kwargs):
        response=real(msg,*args,**kwargs)
        if 'proposal'in msg:
            prepared['buy']=True;a.transport._token_fingerprint=None
        elif 'authorize'in msg and prepared['buy']:
            clock['ms']=2000
        return response
    monkeypatch.setattr(a.transport,'_exchange_locked',delayed)
    r=a.submit(replace(command(),expires_at_ms=2000,command_hash='').sealed(),now_ms=1000)
    assert sum('authorize'in q for s in sockets for q in s.requests)==2, 'the control must reauthorize inside the buy transport call'
    assert r.status=='REJECTED' and not any('buy'in q for s in sockets for q in s.requests)

@pytest.mark.parametrize('msg',[{'buy':'proposal','price':'25','sell':77},{'buy':'proposal','proposal':1},{'sell':77},None])
def test_bounded_deriv_primitive_refuses_mixed_or_nonentry_operations_before_connection(msg):
    from vati.execution.transports.deriv_ws import DerivWebSocketTransport
    from vati.execution.entry_deadline import EntryNotSent
    sockets=[]
    def connector(url):sockets.append(url);raise AssertionError('a refused operation must not connect')
    t=DerivWebSocketTransport(app_id='1089',token_provider=lambda:'fixture',connector=connector)
    with pytest.raises(EntryNotSent):t.call_entry(msg,expires_at_ms=2000,clock=lambda:1000)
    assert sockets==[]
