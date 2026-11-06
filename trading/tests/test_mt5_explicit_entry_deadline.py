"""An explicit core order deadline must remain bound through native dispatch."""
from decimal import Decimal as D

import pytest

from test_mt5_physical_identity import build
from vati.execution.base import OrderCommand,StopMode,VenueUnavailable
from vati.execution.mt5_bridge import BridgeRequest,Mt5BridgeAdapter
from vati.risk.contracts import Direction,LossModel


def command(expiry):
    return OrderCommand('deadline-original','a'*64,'original','fx_primary','mt5','EURUSD',Direction.LONG,
        'MARKET',D('.1'),D('1.1'),D('1.09'),StopMode.VENUE,LossModel.STOP_DISTANCE,expires_at_ms=expiry).sealed()


def test_an_already_expired_core_order_never_reaches_native_dispatch(tmp_path):
    worker,client,native=build(tmp_path)
    result=Mt5BridgeAdapter(client,clock=lambda:1000000).submit(command(1000000),now_ms=1000000)
    assert result.status=='REJECTED' and not native.sent and client.sent==[]


def test_core_expiry_is_retained_in_the_actual_signed_native_request(tmp_path):
    worker,client,native=build(tmp_path)
    result=Mt5BridgeAdapter(client,clock=lambda:1000000).submit(command(1001000),now_ms=1000000)
    assert result.status=='FILLED' and len(native.sent)==1
    sends=[r for r in client.sent if r.op=='order_send_expiring']
    assert len(sends)==1 and sends[0].body.get('expires_at_ms')==1001000 and client.verify(sends[0])


def test_native_quote_delay_cannot_extend_a_shorter_core_deadline(tmp_path):
    worker,client,native=build(tmp_path);clock={'now':1000000,'quotes':0};worker.clock=lambda:clock['now']
    original=native.symbol_info_tick
    def delayed(symbol):
        result=original(symbol);clock['quotes']+=1
        # The first quote builds the readonly precheck. Delay only the quote
        # after the client's last check, inside native SDK dispatch preparation.
        if clock['quotes']==2:clock['now']+=101
        return result
    native.symbol_info_tick=delayed
    result=Mt5BridgeAdapter(client,clock=lambda:clock['now']).submit(command(1000100),now_ms=1000000)
    assert result.status=='REJECTED' and not native.sent


@pytest.mark.parametrize('expiry',[True,'1001000',-1,2**63])
def test_malformed_signed_native_deadlines_are_not_coerced_into_entry_authority(tmp_path,expiry):
    worker,client,native=build(tmp_path)
    signed=client.sign(BridgeRequest('order_send',1,1000000,{'alias':'fx_primary','symbol':'EURUSD','type':'BUY',
        'volume':'0.1','price':'1.1','sl':'1.09','order_type':'MARKET','expires_at_ms':expiry}))
    result=worker.handle(signed.__dict__)
    assert result.get('status')=='REJECTED' and not native.sent,result


def test_a_legacy_worker_cannot_silently_ignore_an_explicit_core_deadline(tmp_path):
    worker,client,native=build(tmp_path)
    def legacy(request):
        response=worker.handle(request)
        response.pop('entry_constraints',None)
        return response
    client._transport=legacy
    result=Mt5BridgeAdapter(client,clock=lambda:1000000).submit(command(1001000),now_ms=1000000)
    assert result.status=='REJECTED' and not native.sent


@pytest.mark.parametrize('expiry',[True,'1001000',-1,2**63])
def test_invalid_core_deadline_is_refused_without_a_native_rpc(tmp_path,expiry):
    _,client,native=build(tmp_path)
    result=Mt5BridgeAdapter(client,clock=lambda:1000000).submit(command(expiry),now_ms=1000000)
    assert result.status=='REJECTED' and client.sent==[] and not native.sent


def test_readonly_precheck_cannot_renew_the_core_deadline(tmp_path):
    worker,client,native=build(tmp_path);clock={'now':1000000};worker.clock=lambda:clock['now']
    original=native.order_check
    def delayed(request):
        result=original(request);clock['now']+=101;return result
    native.order_check=delayed
    result=Mt5BridgeAdapter(client,clock=lambda:clock['now']).submit(command(1000100),now_ms=1000000)
    assert result.status=='REJECTED' and not native.sent
    assert not any(r.op in {'order_send','order_send_expiring'} for r in client.sent)


def test_native_rollback_after_capability_read_cannot_dispatch_an_unbounded_order(tmp_path):
    worker,client,native=build(tmp_path)
    def rolls_back(request):
        if request['op']=='order_send_expiring':
            return {'error':'op not in contract','nonce':request['nonce'],'worker_time_ms':1000000}
        return worker.handle(request)
    client._transport=rolls_back
    with pytest.raises(VenueUnavailable):
        Mt5BridgeAdapter(client,clock=lambda:1000000).submit(command(1001000),now_ms=1000000)
    assert not native.sent


def test_typed_expiring_operation_without_its_bound_deadline_is_refused(tmp_path):
    worker,client,native=build(tmp_path)
    signed=client.sign(BridgeRequest('order_send_expiring',1,1000000,{'alias':'fx_primary','symbol':'EURUSD',
        'type':'BUY','volume':'0.1','price':'1.1','sl':'1.09','order_type':'MARKET'}))
    result=worker.handle(signed.__dict__)
    assert result.get('status')=='REJECTED' and not native.sent


def test_existing_non_deadline_command_keeps_its_native_contract(tmp_path):
    _,client,native=build(tmp_path)
    result=Mt5BridgeAdapter(client,clock=lambda:1000000).submit(command(None),now_ms=1000000)
    assert result.status=='FILLED' and len(native.sent)==1
    request=next(r for r in client.sent if r.op=='order_send')
    assert 'expires_at_ms' not in request.body
