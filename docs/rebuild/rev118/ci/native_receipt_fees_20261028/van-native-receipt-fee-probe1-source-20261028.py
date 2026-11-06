"""A valid native fill must survive unknown commission without inventing zero."""
from copy import deepcopy
from decimal import Decimal as D

import pytest

from test_ctrader import FakeCtrader,make_adapter
from vati.execution.base import OrderCommand,StopMode
from vati.risk.contracts import Direction,LossModel


@pytest.mark.parametrize('missing',[('commission',),('moneyDigits',),('commission','moneyDigits'),()])
def test_valid_wire_fill_retains_unknown_fee_and_preserves_an_explicit_zero(missing):
    class Peer(FakeCtrader):
        def send(self,name,body,cid=None):
            body=deepcopy(body)
            if name=='ProtoOAExecutionEvent' and 'deal' in body:
                body['deal']['commission']=0
                for key in missing:body['deal'].pop(key,None)
            return super().send(name,body,cid)
    peer=Peer();adapter=make_adapter(peer)
    try:
        adapter.sync_account()
        command=OrderCommand('fee-knowledge','d'*64,'fee-knowledge-key','ct_demo','ctrader','EURUSD',
            Direction.LONG,'MARKET',D('.10'),D('1.10008'),D('1.09808'),StopMode.VENUE,LossModel.STOP_DISTANCE).sealed()
        receipt=adapter.submit(command,now_ms=1700000000000)
        assert receipt.status=='FILLED' and receipt.filled_qty==D('.10')
        assert receipt.protective_stop_confirmed and len(adapter.positions())==1
        if missing:assert receipt.fees is None,'missing native fee/precision is unknown, not measured zero'
        else:assert receipt.fees==D('0')
    finally:adapter.transport.close();peer.close()
