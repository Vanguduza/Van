"""Actual native source producers plus exact, scope-bound charge consumption."""
from copy import deepcopy
from decimal import Decimal as D, localcontext, Inexact, Rounded
from fractions import Fraction

import pytest

from test_mt5_physical_identity import build
from test_mt5_explicit_entry_deadline import command
from test_mql_native_function_bodies import ea
from test_mt5_pending_receipts import command as pull_command
from vati.execution.mt5_bridge import Mt5BridgeAdapter
from vati.execution.mt5_pull import BridgeQueue, Mt5PullAdapter
from vati.execution.mt5_identity import Mt5Identity
from vati.execution.mt5_charges import recorded_entry_fees


def observed_worker(tmp_path, commission=-1.25, fee=-.125, *, omit=None, unprotected=False, history_queries=None):
    worker, client, native = build(tmp_path)
    send = native.order_send
    def native_send(request):
        result = send(request)
        if request['action'] == native.TRADE_ACTION_DEAL and not request.get('position'):
            deal = native.deals[-1]
            deal.type = request['type']; deal.entry = 0; deal.volume = result.volume
            deal.commission = commission; deal.fee = fee; deal.time_msc = 1000000
            if omit is not None:
                delattr(deal, omit)
            if unprotected:
                native.pos[result.order].sl = 0
        return result
    native.order_send = native_send
    history = native.history_deals_get
    def counted_history(*args,**kwargs):
        if history_queries is not None and 'ticket' in kwargs:
            history_queries.append(kwargs['ticket'])
        return history(*args,**kwargs)
    native.history_deals_get = counted_history
    responses = []
    transport = client._transport
    def capture(request):
        response = transport(request)
        if request['op'] in ('order_send','order_send_expiring'):
            responses.append(deepcopy(response))
        return response
    client._transport = capture
    identity = Mt5Identity('12345678','Broker-Demo','USD',True)
    adapter = Mt5BridgeAdapter(client, clock=lambda:1000000, identity=identity)
    cmd = command(1001000)
    receipt = adapter.submit(cmd, now_ms=1000000)
    assert receipt.status == 'FILLED' and receipt.protective_stop_confirmed is (not unprotected)
    assert receipt.filled_qty == D('.1') and len(adapter.positions()) == 1
    assert len(responses) == 1
    return cmd, responses[0], identity, receipt


def test_optional_charge_read_cannot_delay_recovery_of_an_unprotected_native_fill(tmp_path):
    queries = []
    _, result, _, receipt = observed_worker(tmp_path, unprotected=True, history_queries=queries)
    assert receipt.fees is None and result['recorded_entry_charges'] is None
    assert len(queries) == 1  # The mandatory position join only; no extra cost query.


def test_actual_ea_emergency_close_precedes_optional_cost_work(ea):
    data = ea('entry-charge-weak-stop')
    receipt = data['results'][0]
    assert receipt['status'] == 'FILLED' and receipt['sl_confirmed'] is False
    assert data['close_calls'] == 1 and data['entry_charge_reads'] == 0
    assert receipt['recorded_entry_charges'] is None


@pytest.mark.parametrize('commission,fee,expected', [(-1.25,-.125,'1.375'),(0,0,'0'),(.25,0,'-.25')])
def test_actual_signed_worker_emits_only_observed_recorded_entry_components(tmp_path, commission, fee, expected):
    cmd, result, identity, receipt = observed_worker(tmp_path, commission, fee)
    observation = result['recorded_entry_charges']
    assert observation is not None
    assert observation['complete_future_charges'] is False and observation['settlement_final'] is False
    assert receipt.fees == D(expected)
    with localcontext() as context:
        context.prec = 2; context.traps[Inexact] = context.traps[Rounded] = True
        before = dict(context.flags)
        assert recorded_entry_fees(cmd, result, identity) == D(expected)
        assert dict(context.flags) == before


@pytest.mark.parametrize('omit', ['commission','fee','entry','time_msc','volume'])
def test_native_history_missing_a_required_component_retains_fill_and_unknown_cost(tmp_path, omit):
    _, result, _, receipt = observed_worker(tmp_path, omit=omit)
    assert result['recorded_entry_charges'] is None and receipt.fees is None


@pytest.mark.parametrize('field,value', [('deal_id','99'),('order_id','99'),('position_ticket','99'),
    ('position_identifier','0'),('symbol','GBPUSD'),('side','SELL'),('volume','99'),
    ('commission_delta','NaN'),('fee_delta',None),('native_time_ms',True),
    ('entry_type','INOUT'),('cash_convention','UNQUALIFIED'),
    ('complete_future_charges',True),('settlement_final',True)])
def test_scope_unit_or_convention_mismatch_cannot_become_a_measured_charge(tmp_path, field, value):
    cmd, result, identity, _ = observed_worker(tmp_path)
    result['recorded_entry_charges'][field] = value
    assert recorded_entry_fees(cmd, result, identity) is None


def test_native_identity_and_explicit_producer_are_required(tmp_path):
    cmd, result, identity, _ = observed_worker(tmp_path)
    assert recorded_entry_fees(cmd, result, None) is None
    damaged = deepcopy(result); damaged['recorded_entry_charges']['identity']['currency'] = 'EUR'
    assert recorded_entry_fees(cmd, damaged, identity) is None
    del result['recorded_entry_charges']
    assert recorded_entry_fees(cmd, result, identity) is None


@pytest.mark.parametrize('scenario,expected', [('entry-charge-zero','0'),('entry-charge-debit','.26'),
    ('entry-charge-rebate','-.25'),('entry-charge-unavailable',None)])
def test_actual_ea_function_observes_charge_or_preserves_unavailability(ea, tmp_path, scenario, expected):
    result = ea(scenario)['results'][0]
    assert result['status'] == 'FILLED' and result['sl_confirmed'] is True
    queue = BridgeQueue(tmp_path/'observed-charges.sqlite3')
    try:
        # Identity is the fixed native model's actual account, not authority.
        snapshot = ea('snapshot')['account']
        identity = Mt5Identity(snapshot['login'],snapshot['server'],snapshot['currency'],snapshot['demo'])
        receipt = Mt5PullAdapter(queue, identity=identity)._entry_receipt(pull_command(), result, now_ms=1700000000000)
        assert receipt.status == 'FILLED' and receipt.protective_stop_confirmed
        assert receipt.filled_qty == D(str(result['volume']))
        if expected is None:
            assert result['recorded_entry_charges'] is None and receipt.fees is None
        else:
            native = result['recorded_entry_charges']
            oracle = -(Fraction(D(native['commission_delta'])) + Fraction(D(native['fee_delta'])))
            assert Fraction(receipt.fees) == oracle and receipt.fees == D(expected)
    finally:
        queue.close()
