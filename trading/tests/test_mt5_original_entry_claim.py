"""A durable original entry is a claim, never permission for another send."""
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal as D
import threading

import pytest

from test_mt5_pull import bridge
from vati.execution.base import OrderCommand,StopMode,VenueUnavailable
from vati.execution.mt5_pull import BridgeQueue
from vati.risk.contracts import Direction,LossModel


def command(alias):
    return OrderCommand('original-full-uuid-12345678901234567890','d'*64,'original-native-key',alias,'mt5','EURUSD',
        Direction.LONG,'MARKET',D('.10'),D('1.10008'),D('1.09808'),StopMode.VENUE,LossModel.STOP_DISTANCE).sealed()


def test_independent_queue_connections_claim_one_original_command(tmp_path,bridge):
    queue,client,ea,adapter,clock=bridge
    cmd=command(adapter.account_alias);body=adapter._entry_body(cmd);path=tmp_path/'native-claims.sqlite'
    first=BridgeQueue(path);second=BridgeQueue(path);begin=threading.Barrier(2)
    def claim(q):
        begin.wait(5);return q.enqueue(adapter.account_alias,'ORDER_SEND',body,now_ms=clock['ms'])
    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            jobs=[pool.submit(claim,q) for q in (first,second)];ids=[j.result(timeout=8) for j in jobs]
        assert ids[0]==ids[1] and len(first.native_entries(adapter.account_alias))==1
        with pytest.raises(VenueUnavailable):second.enqueue(adapter.account_alias,'ORDER_SEND',{**body,'volume':'99'},now_ms=clock['ms'])
        assert len(first.native_entries(adapter.account_alias))==1
    finally:first._conn.close();second._conn.close()


def test_original_unknown_claim_is_not_misreported_rejected_when_current_state_goes_stale(bridge):
    queue,client,ea,adapter,clock=bridge
    ea.poll();adapter.timeout_s=.003;adapter.poll_s=.001
    cmd=command(adapter.account_alias)
    assert adapter.submit(cmd,now_ms=clock['ms']).status=='UNKNOWN'
    clock['ms']+=60000
    result=adapter.submit(cmd,now_ms=clock['ms'])
    assert result.status=='UNKNOWN'
    assert len(queue.native_entries(adapter.account_alias))==1


def test_native_entry_cannot_be_redirected_to_the_adapters_other_account(bridge):
    queue,client,ea,adapter,clock=bridge
    ea.poll();adapter.timeout_s=.003;adapter.poll_s=.001
    with pytest.raises(VenueUnavailable):adapter.submit(command('another-owner-account'),now_ms=clock['ms'])
    assert not queue.native_entries(adapter.account_alias)
