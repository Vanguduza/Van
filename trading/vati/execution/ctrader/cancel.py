"""A bounded original pending-order cancel, called by a durable control owner.

The caller must supply its live authority/lease check. This adapter primitive
does not consume owner commands, publish control attempts or release resources.
The native response remains raw: a cancel reply cannot become a zero-fill
ExecutionReceipt or prove flatness, full fees or economic settlement.
"""
from vati.execution.ctrader.orders import NativeOrderObservation
from vati.execution.ctrader.transport import CancellationNotSent, DEMO_HOST, LIVE_HOST, _cancel_gate
from vati.funding.native import native_int
from vati.risk.account_context import inspect_context
from vati.risk.contracts import NativeAccountRiskContext


def cancel_original_order(adapter, observation, *, deadline_ms, recheck):
    try:
        if type(observation) is not NativeOrderObservation:
            raise ValueError('typed original native order required')
        q = NativeOrderObservation.from_body(observation.body()).body()
        context = NativeAccountRiskContext(**q['native_account_context'])
        source = inspect_context(context); mark = source['mark']; facts = q['facts']
        started = native_int(adapter.clock(), minimum=q['received_at_ms'])
        native_int(deadline_ms, minimum=started+1, maximum=q['deadline_ms'])
        environment = {DEMO_HOST:'DEMO', LIVE_HOST:'LIVE'}.get(getattr(adapter.transport, 'host', None))
        if (context.provider != 'CTRADER' or context.account_alias != adapter.account_alias
                or mark['native_account_id'] != adapter.ctid_trader_account_id
                or environment != mark['environment']
                or facts['closing_order'] is not False
                or facts['native_order_status'] != 'ORDER_STATUS_ACCEPTED'
                or facts['native_order_type'] not in {'LIMIT', 'STOP', 'STOP_LIMIT'}
                or facts['observation_state'] != 'NATIVE_ORDER_OBSERVED'):
            raise ValueError('original nonclosing working-order scope unavailable')
        _cancel_gate(deadline_ms, adapter.clock, recheck)
        adapter._ensure_auth()
        if getattr(adapter.transport, 'connection_id', None) != q['connection_id']:
            raise ValueError('original order connection changed')
        trader = adapter._native_trader_identity()
        if trader['depositAssetId'] != mark['deposit_asset_id'] or adapter._currency != source['currency']:
            raise ValueError('original monetary scope changed')
        call = getattr(adapter.transport, 'call_cancel', None)
        if not callable(call):
            raise ValueError('bounded native cancel transport unavailable')
    except CancellationNotSent:
        raise
    except Exception:
        raise CancellationNotSent('original scoped pending order or current cancel capability unavailable; not sent') from None

    def live_fence():
        # No native I/O while the transport owns its send lock. Authentication
        # and native trader checks have already completed on this connection.
        now = native_int(adapter.clock(), minimum=started)
        return (now < deadline_ms and adapter.account_alias == context.account_alias
                and adapter.ctid_trader_account_id == mark['native_account_id']
                and getattr(adapter.transport, 'connection_id', None) == q['connection_id']
                and adapter._currency == source['currency'] and recheck() is True)

    # No post-write read or conversion can discard a partial/native response.
    # The control owner records it and reconciles the original order separately.
    return call('ProtoOACancelOrderReq', q['request'], expires_at_ms=deadline_ms,
                clock=adapter.clock, recheck=live_fence)
