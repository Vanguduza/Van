"""Original native pending acknowledgements, never invented fills or retries."""
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal as D
import json,time
import pytest
from fastapi.testclient import TestClient

from test_mql_native_function_bodies import ea
from vati.execution.base import OrderCommand,StopMode
from vati.execution.mt5_identity import Mt5Identity
from vati.execution.mt5_pull import BridgeQueue,Mt5PullAdapter,create_pull_app,sign_poll
from vati.risk.contracts import Direction,LossModel

KEY=b'p'*32


def command():
    return OrderCommand('fixture','0000007b'+'0'*56,'pending-original','mt5_ea','mt5','EURUSD',
        Direction.LONG,'MARKET',D('.00123456'),D('1.123456789012345'),D('1.12'),
        StopMode.VENUE,LossModel.STOP_DISTANCE,targets=(D('1.2'),),max_slippage=D('.0002')).sealed()


def test_actual_ea_pending_ack_keeps_original_order_and_no_invented_fill(ea,tmp_path):
    native=ea('entry-market-accepted')['results'][0]
    assert native['status']=='ACCEPTED' and native['sl_confirmed'] is True
    q=BridgeQueue(tmp_path/'receipt.sqlite')
    try:
        receipt=Mt5PullAdapter(q)._entry_receipt(command(),native,now_ms=1700000000000)
        assert receipt.status=='ACCEPTED' and receipt.broker_order_id=='11'
        assert receipt.filled_qty==0 and receipt.average_fill is None and receipt.broker_position_id==''
        assert receipt.protective_stop_confirmed and receipt.protective_stop_price==D('1.12')
        assert receipt.broker_time_unix_ms==0  # Original ack has no native clock.
    finally:q.close()


def test_real_signed_poll_sql_ack_reopen_and_expired_replay_keep_first_completion(ea,tmp_path):
    path=tmp_path/'bridge.sqlite';q=BridgeQueue(path);reopened=None
    now={'ms':1700000000000};native=ea('snapshot')['account'];cmd=command();counter={'n':0}
    app=create_pull_app(q,lambda alias:KEY if alias=='mt5_ea' else None,clock=lambda:now['ms'])
    def poll(client,results):
        counter['n']+=1;nonce='pending-'+str(counter['n']);ts=str(now['ms']//1000)
        body=json.dumps({'account':native,'positions':[],'orders':[],'results':results}).encode()
        return client.post('/ea/v1/mt5_ea/poll',content=body,headers={'content-type':'application/json',
            'x-van-ts':ts,'x-van-nonce':nonce,'x-van-signature':sign_poll(KEY,ts,nonce,'mt5_ea',body)})
    try:
        with TestClient(app) as client:
            assert poll(client,[]).status_code==200
            adapter=Mt5PullAdapter(q,clock=lambda:now['ms'],timeout_s=3,poll_s=.005,
                identity=Mt5Identity('12345678','broker-demo','USD',True))
            with ThreadPoolExecutor(max_workers=1) as pool:
                task=pool.submit(adapter.submit,cmd,now_ms=now['ms'])
                deadline=time.monotonic()+2
                while not q.native_entries('mt5_ea') and time.monotonic()<deadline:time.sleep(.005)
                offered=poll(client,[]);assert offered.status_code==200 and '|MARKET|' in offered.text
                cid=int(offered.text.split('|')[0]);now['ms']+=50
                response=ea('entry-market-accepted')['results'][0]|{'id':cid}
                assert poll(client,[response]).status_code==200
                receipt=task.result(timeout=3)
            assert receipt.status=='ACCEPTED' and receipt.filled_qty==0
            assert receipt.received_time_unix_ms==now['ms'] and receipt.broker_time_unix_ms==0
            now['ms']+=60000;reopened=BridgeQueue(path)
            historical=Mt5PullAdapter(reopened,clock=lambda:now['ms'],identity=adapter.identity)
            recovered=historical.recover_entry(cmd,now_ms=now['ms'])
            assert recovered==receipt and len(reopened.native_entries('mt5_ea'))==1
            assert historical.submit(cmd,now_ms=now['ms'])==receipt
    finally:
        if reopened is not None:reopened.close()
        q.close()


@pytest.mark.parametrize('order',[1,2**64-1,'18446744073709551615'])
@pytest.mark.parametrize('stop',[True,False,'true',1,None])
def test_pending_preserves_exact_ticket_and_only_explicit_protection(tmp_path,order,stop):
    q=BridgeQueue(tmp_path/'pending.sqlite')
    try:
        result=Mt5PullAdapter(q)._entry_receipt(command(),{'status':'ACCEPTED','order':order,
            'retcode':10008,'sl_confirmed':stop},now_ms=100)
        assert result.status=='ACCEPTED' and result.broker_order_id==str(order)
        assert result.filled_qty==0 and result.average_fill is None and result.broker_position_id==''
        assert result.protective_stop_confirmed is (stop is True)
        assert result.protective_stop_price==(D('1.12') if stop is True else None)
        assert result.broker_time_unix_ms==0
    finally:q.close()


@pytest.mark.parametrize('change',[
    {'order':True},{'order':False},{'order':0},{'order':-1},{'order':1.0},
    {'order':'01'},{'order':' 1'},{'order':'1.0'},{'order':'١'},{'order':2**64},
    {'order':'18446744073709551616'},{'order':None},{'volume':'NaN'},
    {'volume':'0.000001'},{'volume':'-1'},{'position':99},{'position':True},
    {'position':False},{'retcode':True},{'retcode':10009},{'retcode':'10008'},
    {'status':[]},{'status':{}},
])
def test_contradictory_pending_ack_requires_original_reconciliation(tmp_path,change):
    q=BridgeQueue(tmp_path/'pending.sqlite')
    try:
        native={'status':'ACCEPTED','order':11,'retcode':10008,'sl_confirmed':True}|change
        result=Mt5PullAdapter(q)._entry_receipt(command(),native,now_ms=100)
        assert result.status=='UNKNOWN' and result.filled_qty==0 and result.average_fill is None
        assert result.broker_position_id=='' and result.protective_stop_confirmed is False
        assert q.native_entries('mt5_ea')==[]
    finally:q.close()


def durable_result(q,adapter,cmd,result,*,created=100,taken=110,done=120):
    cid=q.enqueue('mt5_ea','ORDER_SEND',adapter._entry_body(cmd),now_ms=created)
    assert q.take_pending('mt5_ea',now_ms=taken)[0]['id']==cid
    assert q.complete('mt5_ea',cid,result,now_ms=done)
    return cid


@pytest.mark.parametrize('status',['ACCEPTED','FILLED','PARTIAL','REJECTED','CANCELLED','EXPIRED'])
def test_original_sql_completion_survives_duplicate_result_and_reopen(tmp_path,status):
    path=tmp_path/'original.sqlite';q=BridgeQueue(path);second=None;cmd=command()
    native={'status':status,'order':'18446744073709551615','sl_confirmed':True}
    if status in ('FILLED','PARTIAL'):
        native|={'volume':str(cmd.quantity if status=='FILLED' else cmd.quantity/2),
                 'price':'1.123456789012345','position':42,'server_time_ms':115}
    try:
        adapter=Mt5PullAdapter(q,clock=lambda:130)
        cid=durable_result(q,adapter,cmd,native)
        original=adapter.recover_entry(cmd,now_ms=130)
        assert original.status==status and original.received_time_unix_ms==120
        assert original.broker_time_unix_ms==(115 if status in ('FILLED','PARTIAL') else 0)
        assert q.complete('mt5_ea',cid,{'status':'REJECTED'},now_ms=999) is False
        second=BridgeQueue(path);recovered=Mt5PullAdapter(second,clock=lambda:60000)
        assert recovered.recover_entry(cmd,now_ms=60000)==original
        assert recovered.submit(cmd,now_ms=60000)==original
        assert len(second.native_entries('mt5_ea'))==1
    finally:
        if second is not None:second.close()
        q.close()


@pytest.mark.parametrize('column,value',[
    ('done_ms',None),('done_ms',99),('done_ms',1000),('done_ms','bad'),
    ('taken_ms',None),('taken_ms',121),('created_ms',121),('created_ms',-1),
])
def test_corrupt_sql_clock_does_not_erase_known_order_or_invent_completion(tmp_path,column,value):
    q=BridgeQueue(tmp_path/'corrupt.sqlite');cmd=command();adapter=Mt5PullAdapter(q,clock=lambda:130)
    try:
        cid=durable_result(q,adapter,cmd,{'status':'ACCEPTED','order':11,'retcode':10008})
        assert column in ('done_ms','taken_ms','created_ms')
        q._conn.execute('UPDATE commands SET '+column+'=? WHERE id=?',(value,cid))
        result=adapter.recover_entry(cmd,now_ms=130)
        assert result.status=='ACCEPTED' and result.broker_order_id=='11'
        assert result.received_time_unix_ms is None and result.broker_time_unix_ms==0
        assert len(q.native_entries('mt5_ea'))==1
    finally:q.close()


@pytest.mark.parametrize('state',['QUEUED','TAKEN'])
def test_uncompleted_claim_never_gains_a_completion_from_local_observation(tmp_path,state):
    q=BridgeQueue(tmp_path/'uncompleted.sqlite');cmd=command();adapter=Mt5PullAdapter(q,clock=lambda:60000)
    try:
        q.enqueue('mt5_ea','ORDER_SEND',adapter._entry_body(cmd),now_ms=100)
        if state=='TAKEN':assert q.take_pending('mt5_ea',now_ms=110)
        first=adapter.recover_entry(cmd,now_ms=120);later=adapter.submit(cmd,now_ms=60000)
        assert first==later and first.status=='UNKNOWN' and first.received_time_unix_ms is None
        assert first.broker_time_unix_ms==0 and len(q.native_entries('mt5_ea'))==1
    finally:q.close()


def test_waiter_return_alone_cannot_fabricate_a_durable_terminal_completion(tmp_path):
    q=BridgeQueue(tmp_path/'waiter.sqlite');cmd=command();adapter=Mt5PullAdapter(q,clock=lambda:100)
    try:
        q.set_state('mt5_ea',{'login':1},[],now_ms=100,nonce='original')
        adapter._await=lambda _: {'status':'ACCEPTED','order':11,'retcode':10008}
        receipt=adapter.submit(cmd,now_ms=100)
        assert receipt.status=='UNKNOWN' and receipt.received_time_unix_ms is None
        assert q.native_entries('mt5_ea')[0]['status']=='QUEUED'
    finally:q.close()
