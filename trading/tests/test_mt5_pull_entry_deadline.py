"""Bounded EA submissions retain original claims and refuse late dispatch."""
import sqlite3
from dataclasses import replace
import pytest
from test_mt5_explicit_entry_deadline import command
from test_mt5_funding_contract import account
from vati.execution.mt5_pull import Mt5PullAdapter, BridgeQueue, format_commands
from vati.execution.mt5_identity import Mt5Identity
from vati.execution.base import VenueUnavailable


IDENTITY=Mt5Identity('12345678','Broker-Demo','USD',True)
SUPPORT={'schema':'van.mt5.ea-entry-constraints/1','explicit_deadline':True,
         'required_op':'ORDER_SEND_EXPIRING','framed_fields':18}


def setup(tmp_path, support=SUPPORT):
    queue=BridgeQueue(tmp_path/'entry.sqlite')
    raw=account();raw.update(trade_allowed=True,entry_constraints=support)
    queue.set_state('fx_primary',raw,[],nonce='native-poll',now_ms=1000000)
    adapter=Mt5PullAdapter(queue,account_alias='fx_primary',clock=lambda:1000000,identity=IDENTITY)
    adapter._await=lambda cid:None  # No terminal has taken/reported this queued request yet.
    return queue,adapter


def test_actual_ea_entry_body_and_frame_bind_the_explicit_deadline(tmp_path):
    queue,adapter=setup(tmp_path);cmd=command(1001000)
    assert adapter._entry_body(cmd)['expires_at_ms']==1001000
    result=adapter.submit(cmd,now_ms=1000000)
    assert result.status=='UNKNOWN'
    taken=queue.take_pending('fx_primary',now_ms=1000000,expected_identity=IDENTITY)
    assert len(taken)==1 and taken[0]['op']=='ORDER_SEND_EXPIRING'
    fields=format_commands(taken).strip().split('|')
    assert len(fields)==18 and fields[-1]=='1001000'


@pytest.mark.parametrize('expiry',[1000000,True,'1001000',-1,2**63])
def test_expired_or_malformed_fresh_ea_entry_never_creates_a_native_claim(tmp_path,expiry):
    queue,adapter=setup(tmp_path)
    result=adapter.submit(command(expiry),now_ms=1000000)
    assert result.status=='REJECTED' and queue.native_entries('fx_primary')==[]


@pytest.mark.parametrize('support',[None,{},dict(SUPPORT,explicit_deadline=1),dict(SUPPORT,framed_fields=17)])
def test_missing_or_legacy_ea_capability_cannot_silently_drop_a_deadline(tmp_path,support):
    queue,adapter=setup(tmp_path,support)
    result=adapter.submit(command(1001000),now_ms=1000000)
    assert result.status=='REJECTED' and queue.native_entries('fx_primary')==[]


def test_expiring_and_legacy_claims_share_a_native_uniqueness_fence(tmp_path):
    queue,adapter=setup(tmp_path);cmd=command(1001000);body=adapter._entry_body(cmd)
    first=queue.enqueue('fx_primary','ORDER_SEND_EXPIRING',body,now_ms=1000000)
    assert queue.enqueue('fx_primary','ORDER_SEND_EXPIRING',body,now_ms=1000001)==first
    with pytest.raises(VenueUnavailable):queue.enqueue('fx_primary','ORDER_SEND',body,now_ms=1000001)
    assert len(queue.native_entries('fx_primary'))==1
    with pytest.raises(sqlite3.IntegrityError):
        queue._conn.execute('INSERT INTO commands(alias,op,body_json,created_ms) SELECT alias,\'ORDER_SEND\',body_json,created_ms FROM commands WHERE id=?',(first,))


def test_explicit_expiry_never_becomes_an_unbounded_legacy_wire_frame(tmp_path):
    queue,adapter=setup(tmp_path);body=adapter._entry_body(command(1001000))
    with pytest.raises(VenueUnavailable):format_commands([{'id':1,'op':'ORDER_SEND',**body}])


def test_expired_queued_entry_is_refused_but_an_original_taken_claim_stays_uncertain(tmp_path):
    queue,adapter=setup(tmp_path);body=adapter._entry_body(command(1001000))
    cid=queue.enqueue('fx_primary','ORDER_SEND_EXPIRING',body,now_ms=1000000)
    assert queue.take_pending('fx_primary',now_ms=1001000,expected_identity=IDENTITY)==[]
    assert queue.result(cid)['status']=='REJECTED'
    later=replace(command(1002000),trade_intent_id='another',idempotency_key='another',command_hash='').sealed()
    second=queue.enqueue('fx_primary','ORDER_SEND_EXPIRING',adapter._entry_body(later),now_ms=1000000)
    assert len(queue.take_pending('fx_primary',now_ms=1000000,expected_identity=IDENTITY))==1
    assert queue.take_pending('fx_primary',now_ms=1003000,expected_identity=IDENTITY)==[]
    assert queue.result(second) is None, 'a taken native effect was rewritten as a fresh expiry refusal'


@pytest.mark.parametrize('enabled',[False,'false',1])
def test_new_bounded_opcode_cannot_bypass_native_entry_disable(tmp_path,enabled):
    queue,adapter=setup(tmp_path);body=adapter._entry_body(command(1001000))
    cid=queue.enqueue('fx_primary','ORDER_SEND_EXPIRING',body,now_ms=1000000)
    assert queue.take_pending('fx_primary',now_ms=1000000,expected_identity=IDENTITY,allow_entry=enabled)==[]
    assert queue.result(cid)['status']=='REJECTED'
