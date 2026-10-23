"""Two real bridge connections must not deliver one native command twice."""
from concurrent.futures import ThreadPoolExecutor
import threading
import json

import pytest
from fastapi.testclient import TestClient
from test_mt5_original_entry_claim import command
from vati.execution.mt5_pull import Mt5PullAdapter,create_pull_app,sign_poll

from vati.execution.mt5_pull import BridgeQueue


@pytest.mark.parametrize('via_http',[False,True],ids=['native-queue','signed-http-polls'])
def test_independent_poll_servers_cannot_deliver_one_original_command_twice(tmp_path,via_http):
    path=tmp_path/'native-outbox.sqlite'
    first=BridgeQueue(path);second=BridgeQueue(path)
    adapter=Mt5PullAdapter(first,account_alias='account')
    original=command('account')
    first.enqueue('account','ORDER_SEND',adapter._entry_body(original),now_ms=1)
    reads=threading.Barrier(2)
    class ReadBoundary:
        def __init__(self,cursor):self.cursor=cursor
        def fetchall(self):
            rows=self.cursor.fetchall()
            if rows:
                try:reads.wait(timeout=2)
                except threading.BrokenBarrierError:pass
            return rows
    class Connection:
        def __init__(self,native):self.native=native
        def execute(self,sql,*args,**kwargs):
            cursor=self.native.execute(sql,*args,**kwargs)
            return ReadBoundary(cursor) if sql.startswith('SELECT id, op, body_json') else cursor
        def __getattr__(self,name):return getattr(self.native,name)
    first._conn=Connection(first._conn);second._conn=Connection(second._conn)
    begin=threading.Barrier(2);key=b'local-source-delivery-test-key!'
    clients=[TestClient(create_pull_app(q,lambda alias:key if alias=='account' else None,clock=lambda:2000)) for q in (first,second)] if via_http else []
    def receive(q):
        index=0 if q is first else 1
        begin.wait(timeout=3)
        if not via_http:return q.take_pending('account',now_ms=2)
        body=json.dumps({'account':{'login':123,'equity':'10000','balance':'10000','currency':'USD','trade_allowed':True},
            'positions':[],'results':[]}).encode();nonce='poll-consumer-'+str(index);ts='2'
        response=clients[index].post('/ea/v1/account/poll',content=body,headers={'x-van-ts':ts,
            'x-van-nonce':nonce,'x-van-signature':sign_poll(key,ts,nonce,'account',body),'content-type':'application/json'})
        assert response.status_code==200
        return [{'id':int(line.split('|')[0])} for line in response.text.splitlines()]

    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            results=[f.result(timeout=8) for f in [pool.submit(receive,q) for q in (first,second)]]
        delivered=[row['id'] for batch in results for row in batch]
        assert len(delivered)==len(set(delivered))==1,'one native claim reached two authenticated poll consumers'
    finally:
        for client in clients:client.close()
        first.close();second.close()


@pytest.mark.parametrize('committed',[False,True],ids=['before-commit','lost-commit-reply'])
def test_delivery_publication_failure_preserves_the_actual_native_claim(tmp_path,committed):
    queue=BridgeQueue(tmp_path/'delivery-publication.sqlite')
    adapter=Mt5PullAdapter(queue,account_alias='account');cmd=command('account')
    queue.enqueue('account','ORDER_SEND',adapter._entry_body(cmd),now_ms=1)
    native=queue._conn
    class InterruptedCommit:
        def commit(self):
            if committed:native.commit()
            raise OSError('fixture native delivery-claim publication interrupted')
        def __getattr__(self,name):return getattr(native,name)
    try:
        queue._conn=InterruptedCommit()
        with pytest.raises(OSError,match='delivery-claim publication'):queue.take_pending('account',now_ms=2)
        queue._conn=native
        row=queue.native_entries('account')[0]
        assert row['status']==('TAKEN' if committed else 'QUEUED') and row['result'] is None
        delivered=queue.take_pending('account',now_ms=3)
        assert len(delivered)==(0 if committed else 1)
        # A lost successful claim cannot authorize another native delivery.
        assert queue.take_pending('account',now_ms=4)==[]
    finally:
        queue._conn=native;queue.close()
