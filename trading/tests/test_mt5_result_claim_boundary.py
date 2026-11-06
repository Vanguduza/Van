"""A signed native poll cannot finalize work that was never delivered."""
import pytest

from test_mt5_bound_poll import rig


def filled(cid):
    return {'id':cid,'status':'FILLED','volume':'0.1','price':'1.1',
        'order':321,'position':654,'sl_confirmed':True}


def test_result_for_an_undelivered_original_cannot_erase_its_dispatch(rig):
    registry,account,queue,provider,adapter,command,poll,clock,native=rig
    assert adapter.submit(command,now_ms=clock['now']).status=='UNKNOWN'
    before=queue.native_entries(account.alias)[0];assert before['status']=='QUEUED'
    response=poll(results=[filled(before['id'])])
    assert response.status_code==200
    after=queue.native_entries(account.alias)[0]
    assert after['status']=='TAKEN' and after['result'] is None
    assert response.text.startswith(str(before['id'])+'|ORDER_SEND|')
    assert adapter.recover_entry(command,now_ms=clock['now']).status=='UNKNOWN'


@pytest.mark.parametrize('invalid_id',[True,1.75,'1',2**128])
def test_native_result_identity_requires_its_exact_integer_command_id(rig,invalid_id):
    registry,account,queue,provider,adapter,command,poll,clock,native=rig
    assert adapter.submit(command,now_ms=clock['now']).status=='UNKNOWN'
    before=queue.native_entries(account.alias)[0];assert before['id']==1
    assert poll().text
    assert poll(results=[filled(invalid_id)]).status_code==200
    after=queue.native_entries(account.alias)[0]
    assert after['status']=='TAKEN' and after['result'] is None
    assert adapter.recover_entry(command,now_ms=clock['now']).status=='UNKNOWN'


def test_delivered_exact_native_result_is_idempotent_and_cannot_be_replaced(rig):
    registry,account,queue,provider,adapter,command,poll,clock,native=rig
    assert adapter.submit(command,now_ms=clock['now']).status=='UNKNOWN'
    cid=queue.native_entries(account.alias)[0]['id'];assert poll().text
    assert poll(results=[filled(cid)]).status_code==200
    original=queue.native_entries(account.alias)[0]
    assert original['status']=='DONE' and original['result']['status']=='FILLED'
    assert adapter.recover_entry(command,now_ms=clock['now']).status=='FILLED'
    assert poll(results=[{**filled(cid),'volume':'0','status':'REJECTED'}]).status_code==200
    assert queue.native_entries(account.alias)[0]==original
