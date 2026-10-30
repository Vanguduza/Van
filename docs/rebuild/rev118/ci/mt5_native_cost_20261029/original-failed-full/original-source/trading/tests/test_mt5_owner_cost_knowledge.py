"""Original MT5 effects and durable owner costs retain their knowledge state."""
from copy import deepcopy
from dataclasses import asdict, replace
from decimal import Decimal as D
from types import SimpleNamespace

import pytest

from test_mt5_physical_identity import build
from test_mt5_explicit_entry_deadline import command
from test_mql_native_function_bodies import ea
from test_mt5_pending_receipts import command as pull_command
from test_account_trade_lifecycle import _lifecycle, _owner_receipt, _durable_receipt
from vati.core import Ledger, EventKind, make_event
from vati.execution.mt5_bridge import Mt5BridgeAdapter
from vati.execution.mt5_pull import BridgeQueue, Mt5PullAdapter
from vati.execution.zse_ticket import OwnerTicketAdapter
from vati.execution.tca import compute_tca
from vati.app.trade_lifecycle import AccountTradeLifecycle
from vati.risk.contracts import Direction, TradeIntent, StrategyState


def test_actual_signed_worker_fill_stop_and_close_never_invent_fee_zero(tmp_path):
    worker, client, native = build(tmp_path)
    adapter = Mt5BridgeAdapter(client, clock=lambda:1000000)
    cmd = replace(command(1001000), strategy_id='FX-TREND-PULLBACK-01', strategy_version='1.0.0', command_hash='').sealed()
    receipt = adapter.submit(cmd, now_ms=1000000)
    assert receipt.status == 'FILLED' and receipt.filled_qty == D('.1')
    assert receipt.protective_stop_confirmed and len(adapter.positions()) == 1
    assert receipt.fees is None
    from test_account_lifecycle import _lifecycle as native_lifecycle, _append_command
    ledger = Ledger(tmp_path/'actual-native-receipt.sqlite3')
    try:
        _append_command(ledger, cmd, now=1000000)
        ledger.append(make_event(EventKind.EXECUTION_RECEIPT, 'vati-execution-router', asdict(receipt),
            event_time_ms=receipt.broker_time_unix_ms, received_time_ms=receipt.received_time_unix_ms,
            correlation_id=cmd.trade_intent_id))
        life = native_lifecycle(ledger, adapter)
        intent = TradeIntent(trade_intent_id=cmd.trade_intent_id, idempotency_key=cmd.idempotency_key,
            account_alias=cmd.account_alias, venue=cmd.venue, symbol=cmd.symbol, direction=cmd.direction,
            strategy_id=cmd.strategy_id, strategy_version=cmd.strategy_version, strategy_state=StrategyState.DEMO,
            entry=cmd.entry_price, stop=cmd.protective_stop, requested_risk_pct=D('.005'),
            decision_hash=cmd.decision_hash, market_snapshot_hash='m'*64)
        life.record_entry(intent=intent, receipt=receipt,
            state=SimpleNamespace(session=SimpleNamespace(value='LONDON'), event_window=SimpleNamespace(value='NONE')),
            modelled_cost_pct=D('.0003'), software_stop=False)
        assert life.entries[cmd.trade_intent_id]['fees'] is None and life.entries[cmd.trade_intent_id]['open']
        durable = next(ledger.iter(EventKind.EXECUTION_RECEIPT))
        assert AccountTradeLifecycle._receipt_from_payload(durable.payload) == receipt
        cold = native_lifecycle(ledger, adapter)
        assert cold.recover_from_venue() == ((cmd.trade_intent_id,), ())
        assert cold.entries[cmd.trade_intent_id]['fees'] is None
        assert cold.protection.stop_of(receipt.broker_position_id) == cmd.protective_stop
        assert ledger.count(EventKind.TCA_RECORD) == 0 and ledger.verify_chain()[0]
    finally:
        ledger.close()
    stop = adapter.modify_stop(receipt.broker_position_id, D('1.095'), now_ms=1000000)
    assert stop.status == 'ACCEPTED' and stop.protective_stop_confirmed and stop.fees is None
    close = adapter.close(receipt.broker_position_id, None, now_ms=1000000, reason='TEST_CLOSE')
    assert close.status == 'FILLED' and close.fees is None and adapter.positions() == []
    assert len(native.sent) == 3


@pytest.mark.parametrize('scenario,expected_status', [('entry-market','FILLED'), ('entry-partial','PARTIAL'), ('entry-market-accepted','ACCEPTED')])
def test_actual_ea_function_retains_original_fill_or_pending_state_without_measured_charges(ea, tmp_path, scenario, expected_status):
    queue = BridgeQueue(tmp_path/'native-result.sqlite3')
    try:
        native = ea(scenario)['results'][0]
        receipt = Mt5PullAdapter(queue)._entry_receipt(pull_command(), native, now_ms=1700000000000)
        assert receipt.status == native['status'] == expected_status
        assert receipt.protective_stop_confirmed
        if native['status'] == 'ACCEPTED':
            assert receipt.filled_qty == 0 and receipt.average_fill is None
        else:
            assert receipt.filled_qty == D(str(native['volume'])) and receipt.filled_qty > 0
        assert receipt.fees is None
    finally:
        queue.close()


ORDER = {'symbol':'DELTA','direction':'LONG','strategy_id':'ZSE-VALUE-ROTATION-01',
    'entry_price':'25.00','protective_stop':'22.50','targets':['30.00']}


def owner_cost_path(ledger, changed_model=None, *, legacy=False):
    receipt = replace(_owner_receipt(price='24.90'), fees=D('1.25'), receipt_hash='').sealed()
    _durable_receipt(ledger, receipt)
    adapter = OwnerTicketAdapter(equity=D('1000000'), csd_verified=True)
    life = _lifecycle(ledger, adapter)
    if legacy:
        payload = compute_tca(receipt, direction=Direction.LONG, qty=receipt.filled_qty,
            value_per_unit=D('1'), modelled_cost_pct=D('.0714')).as_dict()
        del payload['arithmetic']
        ledger.append(make_event(EventKind.TCA_RECORD, 'vati-account-lifecycle', payload,
            event_time_ms=2000, received_time_ms=2000, correlation_id=receipt.trade_intent_id))
    life.adopt_owner_buy_confirmation(receipt, order_payload=ORDER)
    event = next(ledger.iter(EventKind.TCA_RECORD))
    expected = D(str(event.payload['cost_ratio']))
    assert life.entries['intent-1']['cost_ratio'] == expected
    count = ledger.count()
    cold = _lifecycle(ledger, adapter)
    if changed_model is not None:
        cold.modelled_costs['DELTA'] = D(changed_model)
    for _ in range(2):
        cold.adopt_owner_buy_confirmation(receipt, order_payload=ORDER)
        assert cold.entries['intent-1']['cost_ratio'] == expected
        assert cold.entries['intent-1']['fees'] == D('1.25')
        assert cold.protection.stop_of(receipt.broker_position_id) == D('22.50')
        assert ledger.count() == count
    assert next(ledger.iter(EventKind.TCA_RECORD)).hash == event.hash and ledger.verify_chain()[0]
    return receipt, event


@pytest.mark.parametrize('legacy', [False, True])
@pytest.mark.parametrize('changed_model', [None, '.1', 'NaN'])
def test_real_sqlite_owner_replay_restores_original_cost_model_without_rewriting_history(tmp_path, changed_model, legacy):
    ledger = Ledger(tmp_path/'owner-cost.sqlite3')
    try:
        owner_cost_path(ledger, changed_model, legacy=legacy)
    finally:
        ledger.close()


@pytest.mark.parametrize('damage', ['fees','arithmetic','producer','model'])
def test_conflicting_durable_cost_never_overwrites_original_or_loses_protection(tmp_path, damage):
    ledger = Ledger(tmp_path/'conflict.sqlite3')
    try:
        receipt, original = owner_cost_path(ledger)
        payload = deepcopy(original.payload)
        producer = original.producer
        if damage == 'fees':
            payload['fees'] = '99'
        elif damage == 'arithmetic':
            payload['arithmetic']['direct_cost']['numerator'] = '999'
        elif damage == 'producer':
            producer = 'untrusted-cost-claim'
        else:
            payload = compute_tca(receipt, direction=Direction.LONG, qty=receipt.filled_qty,
                value_per_unit=D('1'), modelled_cost_pct=D('.1')).as_dict()
        bad = make_event(EventKind.TCA_RECORD, producer, payload,
            event_time_ms=2000, received_time_ms=2000, correlation_id=receipt.trade_intent_id)
        ledger.append(bad)
        life = _lifecycle(ledger, OwnerTicketAdapter(equity=D('1000000'), csd_verified=True))
        life.adopt_owner_buy_confirmation(receipt, order_payload=ORDER)
        assert 'cost_ratio' not in life.entries['intent-1']
        assert life.entries['intent-1']['fees'] == D('1.25')
        assert life.protection.stop_of(receipt.broker_position_id) == D('22.50')
        assert [e.hash for e in ledger.iter(EventKind.TCA_RECORD)] == [original.hash, bad.hash]
        assert any(e.payload.get('event') == 'TCA_REPLAY_UNRECONCILED' for e in ledger.iter(EventKind.SESSION))
    finally:
        ledger.close()
