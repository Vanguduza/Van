"""Fresh and concurrent bridge connections keep independent anti-replay identities."""
from concurrent.futures import ThreadPoolExecutor

from test_mt5_worker import KEY,make_worker
from vati.execution.mt5_bridge import Mt5BridgeClient


def test_a_new_client_after_a_service_restart_does_not_collide_with_the_previous_connection(tmp_path):
    worker,_=make_worker(tmp_path,lambda:1000000)
    clients=[Mt5BridgeClient(signing_key=KEY,transport=worker.handle) for _ in range(3)]
    for client in clients:
        result=client.call('sync_account',{'alias':'fx_primary'},now_ms=1000000)
        assert result.get('account',{}).get('verified') is True,result
    assert len({client.sent[0].nonce for client in clients})==3
    replay=worker.handle(clients[0].sent[0].__dict__)
    assert replay['error']=='nonce replayed'


def test_parallel_connections_and_shared_client_calls_keep_distinct_signed_nonces(tmp_path):
    worker,_=make_worker(tmp_path,lambda:1000000)
    clients=[Mt5BridgeClient(signing_key=KEY,transport=worker.handle) for _ in range(4)]
    def call(index):return clients[index%4].call('sync_account',{'alias':'fx_primary'},now_ms=1000000)
    with ThreadPoolExecutor(max_workers=8) as pool:results=list(pool.map(call,range(40)))
    assert all(result.get('account',{}).get('verified') is True for result in results)
    requests=[r for client in clients for r in client.sent]
    assert len(requests)==len({r.nonce for r in requests})==40
    assert all(client.verify(r) for client in clients for r in client.sent)
