"""Original pending-order primitive; durable signed controls are a separate owner."""
from copy import deepcopy

import pytest

from test_ctrader_order_details import reader
from vati.execution.ctrader.orders import NativeOrderObservation
from vati.execution.ctrader.transport import CancellationNotSent


def cancellable(tmp_path):
    adapter, context = reader(tmp_path)
    adapter.transport.order_reply['order']['orderStatus'] = 'ORDER_STATUS_ACCEPTED'
    observation = adapter.order_details(71, context=context, deadline_ms=2000)
    sends = []
    def cancel(name, body, *, expires_at_ms, clock, recheck):
        assert name == 'ProtoOACancelOrderReq' and expires_at_ms == 2000 and clock() == 1000
        assert recheck() is True
        sends.append(deepcopy(body))
        return 'ProtoOAExecutionEvent', {'ctidTraderAccountId': 12345, 'executionType':'ORDER_CANCELLED',
            'order':deepcopy(adapter.transport.order_reply['order']),
            'deal':deepcopy(adapter.transport.order_reply['deal'][0])}
    adapter.transport.call_cancel = cancel
    return adapter, observation, sends


def test_actual_adapter_preserves_raw_partial_response_without_zero_fill_or_close(tmp_path):
    adapter, original, sends = cancellable(tmp_path)
    name, reply = adapter.cancel_order(original, deadline_ms=2000, recheck=lambda: True)
    assert name == 'ProtoOAExecutionEvent' and reply['executionType'] == 'ORDER_CANCELLED'
    assert reply['deal']['filledVolume'] == 200000 and reply['deal']['positionId'] == 81
    assert sends == [{'ctidTraderAccountId':12345,'orderId':71}]
    assert 'status' not in reply and 'filled_qty' not in reply and 'cash_settled' not in reply
    assert original.body()['facts']['recorded_gross_deal_volume'] == 500000


@pytest.mark.parametrize('defect', ['foreign-alias','foreign-account','connection','currency','closing','absent-closing',
                                   'market','already-cancelled','unreconciled-total','expiry','renewed-deadline','authority'])
def test_unbound_nonworking_or_protective_order_never_sends_cancel(tmp_path, defect):
    from vati.core.canonical import canonical_hash
    adapter, original, sends = cancellable(tmp_path); body = original.body(); check = lambda: True
    deadline = 2000
    if defect == 'foreign-alias': adapter.account_alias = 'foreign'
    elif defect == 'foreign-account': adapter.ctid_trader_account_id = 54321
    elif defect == 'connection': adapter.transport.connection_id += 1
    elif defect == 'currency': adapter.transport.currency = 'USD'
    elif defect == 'expiry': adapter.clock = lambda: 2000
    elif defect == 'renewed-deadline': deadline = 3000
    elif defect == 'authority': check = lambda: False
    else:
        order = body['response']['order']
        if defect == 'closing': order['closingOrder'] = True
        elif defect == 'absent-closing': order.pop('closingOrder')
        elif defect == 'market': order['orderType'] = 'MARKET'
        elif defect == 'already-cancelled': order['orderStatus'] = 'ORDER_STATUS_CANCELLED'
        elif defect == 'unreconciled-total': order['executedVolume'] = 1
        from vati.execution.ctrader.orders import _facts
        body['facts'] = _facts(body['response'],12345,71)
        body['source_ref'] = canonical_hash({k:v for k,v in body.items() if k!='source_ref'})
        original = NativeOrderObservation.from_body(body)
    with pytest.raises(CancellationNotSent): adapter.cancel_order(original, deadline_ms=deadline, recheck=check)
    assert sends == []


def test_cancel_transport_uncertainty_is_never_converted_to_a_no_effect_receipt(tmp_path):
    adapter, original, sends = cancellable(tmp_path)
    def unknown(*args, **kwargs):
        sends.append('native attempt'); raise OSError('fixture native cancellation reply lost')
    adapter.transport.call_cancel = unknown
    with pytest.raises(OSError, match='reply lost'): adapter.cancel_order(original, deadline_ms=2000, recheck=lambda:True)
    assert sends == ['native attempt']
