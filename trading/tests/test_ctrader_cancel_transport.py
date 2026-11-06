"""Bounded single-order cancellation frames; no live account qualification."""
from contextlib import contextmanager

import pytest

from test_ctrader import FakeCtrader
from test_ctrader_order_details import native_reply
from vati.execution.ctrader.transport import CtraderTransport, CtraderReadTransport, DEMO_HOST
from vati.execution.base import VenueUnavailable


class CancelPeer(FakeCtrader):
    def handle(self, name, body, cid):
        if name == 'ProtoOACancelOrderReq':
            reply = native_reply()
            return self.send('ProtoOAExecutionEvent', {
                'ctidTraderAccountId': reply['ctidTraderAccountId'],
                'executionType': 'ORDER_CANCELLED', 'order': reply['order'],
                'deal': reply['deal'][0]}, cid)
        return super().handle(name, body, cid)


def send(transport, *, deadline=2000, clock=lambda: 1000, recheck=lambda: True, message='ProtoOACancelOrderReq'):
    return transport.call_cancel(message, {'ctidTraderAccountId': 12345, 'orderId': 71},
                                 expires_at_ms=deadline, clock=clock, recheck=recheck)


def test_actual_framed_cancel_keeps_original_order_and_partial_execution():
    peer = CancelPeer(); transport = CtraderTransport(host=DEMO_HOST, connector=peer.connector, timeout_s=.5)
    checks = []
    try:
        name, body = send(transport, recheck=lambda: checks.append('checked') or True)
        assert name == 'ProtoOAExecutionEvent' and body['executionType'] == 'ORDER_CANCELLED'
        assert body['order']['orderId'] == 71 and body['order']['executedVolume'] == 500000
        assert body['deal']['filledVolume'] == 200000 and body['deal']['positionId'] == 81
        assert len(checks) >= 2
        assert [(n,b['orderId']) for n,b in peer.requests] == [('ProtoOACancelOrderReq',71)]
    finally: transport.close(); peer.close()


@pytest.mark.parametrize('deadline', [0, -1, True, None, '2000', 1000, 2**63])
def test_invalid_or_expired_cancel_deadline_cannot_connect_or_send(deadline):
    calls = []
    transport = CtraderTransport(connector=lambda *args: calls.append(args))
    try:
        with pytest.raises(VenueUnavailable): send(transport, deadline=deadline)
        assert not calls and transport.sent == 0
    finally: transport.close()


def test_cancel_clock_and_authority_are_rechecked_after_send_lock():
    peer = CancelPeer(); transport = CtraderTransport(host=DEMO_HOST, connector=peer.connector, timeout_s=.5)
    clock = {'ms': 1000}; original = transport._send_guard
    @contextmanager
    def delayed():
        with original():
            clock['ms'] = 2000
            yield
    transport._send_guard = delayed
    try:
        with pytest.raises(VenueUnavailable): send(transport, clock=lambda: clock['ms'])
        assert transport.sent == 0 and peer.requests == []
    finally: transport.close(); peer.close()


def test_cancel_authority_change_at_send_prevents_the_native_frame():
    peer = CancelPeer(); transport = CtraderTransport(host=DEMO_HOST, connector=peer.connector, timeout_s=.5)
    checks = []
    def recheck():
        checks.append(1)
        return len(checks) == 1
    try:
        with pytest.raises(VenueUnavailable): send(transport, recheck=recheck)
        assert len(checks) == 2 and transport.sent == 0 and peer.requests == []
    finally: transport.close(); peer.close()


@pytest.mark.parametrize('message', ['ProtoOANewOrderReq','ProtoOAAmendOrderReq','ProtoOAClosePositionReq'])
def test_cancel_transport_cannot_be_repurposed_for_another_financial_operation(message):
    calls = []; transport = CtraderTransport(connector=lambda *args: calls.append(args))
    try:
        with pytest.raises(VenueUnavailable): send(transport, message=message)
        assert calls == [] and transport.sent == 0
    finally: transport.close()


def test_market_only_read_transport_cannot_inherit_cancel_capability():
    calls = []
    transport = CtraderReadTransport(host=DEMO_HOST, connector=lambda *args: calls.append(args),
                                     operation_timeout_s=1)
    try:
        with pytest.raises(VenueUnavailable): send(transport)
        assert calls == [] and transport.sent == 0
    finally: transport.close()
