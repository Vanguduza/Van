"""Actual framed cTrader simulation: preserve signed observed commission."""
from decimal import Decimal as D
from conftest import _register_owner_authority_key,_reap_ctrader_fixture_sockets
from test_ctrader import FakeCtrader,make_adapter
from vati.execution.base import OrderCommand,StopMode
from vati.risk.contracts import Direction,LossModel


def test_native_positive_commission_credit_is_a_negative_cost_not_a_charge():
    fake=FakeCtrader();send=fake.send
    def credited(name,body,cid=None):
        if name=='ProtoOAExecutionEvent' and body.get('deal',{}).get('filledVolume'):
            body['deal']['commission']=350
            body['deal']['moneyDigits']=2
        return send(name,body,cid)
    fake.send=credited;adapter=make_adapter(fake)
    try:
        adapter.sync_account()
        command=OrderCommand('fee-credit','d'*64,'fee-credit','ct_demo','ctrader','EURUSD',
            Direction.LONG,'MARKET',D('.1'),D('1.10008'),D('1.09808'),StopMode.VENUE,
            LossModel.STOP_DISTANCE).sealed()
        receipt=adapter.submit(command,now_ms=5)
        assert receipt.status=='FILLED' and receipt.filled_qty==D('.1')
        assert receipt.fees==D('-3.50'),'the adapter converted a native signed credit into a positive fee'
    finally:adapter.transport.close();fake.close()
