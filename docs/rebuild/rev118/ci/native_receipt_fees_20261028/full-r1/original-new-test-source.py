"""Real framed fills preserve unknown charges through SQL and safety recovery."""
from contextlib import contextmanager
from copy import deepcopy
from dataclasses import asdict, replace
from decimal import Decimal as D, localcontext, Inexact, Rounded
from types import SimpleNamespace

import pytest

from test_ctrader import FakeCtrader, make_adapter
from test_account_lifecycle import _lifecycle, _append_command, _contract
from vati.core import EventKind, Ledger, make_event
from vati.execution.base import OrderCommand, StopMode
from vati.execution.ctrader.adapter import _recorded_commission
from vati.execution.review import closed_trade_pnl
from vati.learning import Environment
from vati.learning.hooks import LearningHooks
from vati.learning.replay import restore_learning_runtime
from vati.risk.contracts import Direction, LossModel, TradeIntent, StrategyState


@contextmanager
def native_fill(missing=(), commission=-350, digits=2):
    class Peer(FakeCtrader):
        def send(self, name, body, cid=None):
            body = deepcopy(body)
            if name == 'ProtoOAExecutionEvent' and 'deal' in body:
                body['deal'].update(commission=commission, moneyDigits=digits)
                for key in missing:
                    body['deal'].pop(key, None)
            return super().send(name, body, cid)
    peer = Peer()
    adapter = make_adapter(peer)
    try:
        adapter.sync_account()
        cmd = OrderCommand('fee-knowledge', 'd'*64, 'fee-knowledge-key', 'ct_demo', 'ctrader', 'EURUSD',
            Direction.LONG, 'MARKET', D('.10'), D('1.10008'), D('1.09808'),
            StopMode.VENUE, LossModel.STOP_DISTANCE, strategy_id='FX-TREND-PULLBACK-01').sealed()
        receipt = adapter.submit(cmd, now_ms=1700000000000)
        assert receipt.status == 'FILLED' and receipt.filled_qty == D('.10')
        assert receipt.protective_stop_confirmed and len(adapter.positions()) == 1
        yield adapter, cmd, receipt
    finally:
        adapter.transport.close()
        peer.close()


@pytest.mark.parametrize('missing', [('commission',), ('moneyDigits',), ('commission', 'moneyDigits')])
def test_missing_native_charge_fields_preserve_the_actual_fill(missing):
    with native_fill(missing) as (adapter, cmd, receipt):
        assert receipt.fees is None
        assert adapter.positions()[0].stop_price == cmd.protective_stop


@pytest.mark.parametrize('commission,expected', [(0, D('0')), (-350, D('3.50')), (350, D('3.50'))])
def test_explicit_zero_and_existing_recorded_magnitude_convention_survive(commission, expected):
    with native_fill(commission=commission) as (_, _, receipt):
        assert receipt.fees == expected


@pytest.mark.parametrize('digits', [-1, 19])
def test_invalid_native_precision_cannot_erase_a_known_fill(digits):
    with native_fill(digits=digits) as (_, _, receipt):
        assert receipt.fees is None


@pytest.mark.parametrize('raw', [-(2**63), 2**63-1])
def test_signed_native_charge_limit_is_exact_under_hostile_decimal_context(raw):
    with localcontext() as ctx:
        ctx.prec = 2
        ctx.traps[Inexact] = ctx.traps[Rounded] = True
        actual = _recorded_commission({'commission': raw, 'moneyDigits': 18})
        assert actual == D((0, tuple(map(int, str(abs(raw)))), -18))
        assert not any(ctx.flags.values())


@pytest.mark.parametrize('row', [None, {}, {'commission': 0}, {'moneyDigits': 2},
    {'commission': True, 'moneyDigits': 2}, {'commission': '350', 'moneyDigits': 2},
    {'commission': 2**63, 'moneyDigits': 2}, {'commission': 1, 'moneyDigits': True}])
def test_malformed_optional_charge_metadata_stays_unknown(row):
    assert _recorded_commission(row) is None


def durable_unknown_fee_path(ledger):
    """SQL owner and native position readback; no fabricated fee/TCA evidence."""
    with native_fill(('commission',)) as (adapter, cmd, receipt):
        _append_command(ledger, cmd, now=receipt.received_time_unix_ms-1)
        ledger.append(make_event(EventKind.EXECUTION_RECEIPT, 'vati-execution-router', asdict(receipt),
            event_time_ms=receipt.broker_time_unix_ms, received_time_ms=receipt.received_time_unix_ms,
            correlation_id=receipt.trade_intent_id))
        life = _lifecycle(ledger, adapter)
        life.learning = LearningHooks(Environment.DEMO)
        intent = TradeIntent(trade_intent_id=cmd.trade_intent_id, idempotency_key=cmd.idempotency_key,
            account_alias=cmd.account_alias, venue=cmd.venue, symbol=cmd.symbol, direction=cmd.direction,
            strategy_id=cmd.strategy_id, strategy_version='1.0.0', strategy_state=StrategyState.DEMO,
            entry=cmd.entry_price, stop=cmd.protective_stop, requested_risk_pct=D('.005'),
            decision_hash=cmd.decision_hash, market_snapshot_hash='m'*64)
        life.record_entry(intent=intent, receipt=receipt,
            state=SimpleNamespace(session=SimpleNamespace(value='LONDON'), event_window=SimpleNamespace(value='NONE')),
            modelled_cost_pct=D('.0003'), software_stop=False)
        entry = life.entries[cmd.trade_intent_id]
        assert entry['fees'] is None and entry['open'] and entry['quantity'] == D('.10')
        assert life.families.for_intent(cmd.trade_intent_id).net_quantity == D('.10')
        assert 'cost_ratio' not in entry and ledger.count(EventKind.TCA_RECORD) == 0
        assert any(e.payload.get('event') == 'TCA_UNAVAILABLE' for e in ledger.iter(EventKind.SESSION))
        durable = next(ledger.iter(EventKind.EXECUTION_RECEIPT))
        restored_receipt = life._receipt_from_payload(durable.payload)
        assert restored_receipt.fees is None and restored_receipt.receipt_hash == receipt.receipt_hash
        cold = _lifecycle(ledger, adapter)
        restored, unresolved = cold.recover_from_venue()
        assert restored == (cmd.trade_intent_id,) and unresolved == ()
        assert cold.entries[cmd.trade_intent_id]['fees'] is None
        assert cold.protection.stop_of(receipt.broker_position_id) == cmd.protective_stop
        assert ledger.count(EventKind.TCA_RECORD) == 0
        count = ledger.count()
        assert restore_learning_runtime(ledger, LearningHooks(Environment.DEMO), {}).tca_observations == 0
        assert ledger.count() == count and ledger.verify_chain()[0]
        return receipt.receipt_hash, durable.hash


def test_unknown_fee_survives_real_sqlite_and_original_receipt_reopen(tmp_path):
    path = tmp_path/'unknown-charge.sqlite3'
    ledger = Ledger(path)
    try:
        receipt_hash, event_hash = durable_unknown_fee_path(ledger)
    finally:
        ledger.close()
    cold = Ledger(path)
    try:
        row = next(cold.iter(EventKind.EXECUTION_RECEIPT))
        assert row.hash == event_hash
        from vati.app.trade_lifecycle import AccountTradeLifecycle
        assert AccountTradeLifecycle._receipt_from_payload(row.payload).receipt_hash == receipt_hash
        assert row.payload['fees'] is None and cold.count(EventKind.TCA_RECORD) == 0
    finally:
        cold.close()


@pytest.mark.parametrize('fee', [None, D('0'), D('3.50')])
def test_sealed_receipt_roundtrip_preserves_unknown_zero_and_known(fee):
    from vati.app.trade_lifecycle import AccountTradeLifecycle
    from test_tca_exact_arithmetic import original
    receipt = original(fees=fee)
    assert AccountTradeLifecycle._receipt_from_payload(asdict(receipt)) == receipt
    corrupted = asdict(receipt)
    corrupted['fees'] = D('9')
    with pytest.raises(ValueError, match='hash'):
        AccountTradeLifecycle._receipt_from_payload(corrupted)


@pytest.mark.parametrize('basis,expected', [(None, None), ('GROSS_PRICE_MOVEMENT', None),
    ('NET_CONFIRMED', D('7')), ('LEGACY', D('7'))])
def test_unknown_charge_withholds_derived_pnl_but_keeps_reported_net_cash(basis, expected):
    entry = {'trade_intent_id': 'i', 'fees': None, 'carry': D('0'), 'quantity': D('.1'),
        'entry': D('1.1'), 'direction': Direction.LONG}
    rows = [] if basis is None else [{'intent': 'i', 'pnl': '7', 'pnl_basis': basis}]
    measured = closed_trade_pnl(entry, D('1.2'), _contract(), rows)
    assert measured.amount == expected
    if expected is None:
        assert measured.basis == 'UNKNOWN_CHARGES'
    if basis == 'NET_CONFIRMED':
        assert measured.basis == 'REPORTED_NET_CONFIRMED'


def test_cycle_records_unavailable_then_accepts_an_original_measured_receipt(tmp_path, eurusd):
    from test_backtest_runner_cli import fx_cfg, fx_engine
    from test_tca_exact_arithmetic import original
    from vati.app.cycle import DecisionCycle
    from vati.execution.paper import PaperAdapter
    from vati.market_data import FX_CALENDAR
    from vati.intelligence.events import EventMatrix
    ledger = Ledger(tmp_path/'cycle.sqlite3')
    try:
        cfg = fx_cfg(eurusd)
        cycle = DecisionCycle(cfg=cfg, adapter=PaperAdapter(venue='paper', account_alias=cfg.account_alias),
            ledger=ledger, engine=fx_engine(cfg), cost_fn=lambda state: D('.0003'),
            calendar=FX_CALENDAR, events=EventMatrix())
        unknown = original(fees=None)
        cycle._entries[unknown.trade_intent_id] = {'fees': None}
        cycle._record_tca(unknown, Direction.LONG, D('.0003'), 'LONDON', 'NONE', now_ms=1001)
        assert ledger.count(EventKind.TCA_RECORD) == 0
        known = replace(unknown, fees=D('3.50'), receipt_hash='').sealed()
        cycle._record_tca(known, Direction.LONG, D('.0003'), 'LONDON', 'NONE', now_ms=1002)
        assert ledger.count(EventKind.TCA_RECORD) == 1
        assert 'cost_ratio' in cycle._entries[unknown.trade_intent_id]
    finally:
        ledger.close()


def test_owner_confirmation_keeps_protection_and_can_repair_missing_cost(tmp_path):
    from test_account_trade_lifecycle import _lifecycle as owner_lifecycle, _owner_receipt, _durable_receipt
    from vati.execution.owner_ticket import OwnerTicketAdapter
    ledger = Ledger(tmp_path/'owner-fee.sqlite3')
    try:
        life = owner_lifecycle(ledger, OwnerTicketAdapter(equity=D('1000000'), csd_verified=True))
        receipt = replace(_owner_receipt(price='24.90'), fees=None, receipt_hash='').sealed()
        _durable_receipt(ledger, receipt)
        order = {'symbol': 'DELTA', 'direction': 'LONG', 'strategy_id': 'ZSE-VALUE-ROTATION-01',
            'entry_price': '25.00', 'protective_stop': '22.50', 'targets': ['30.00']}
        life.adopt_owner_buy_confirmation(receipt, order_payload=order)
        assert life.entries['intent-1']['fees'] is None
        assert life.protection.stop_of(receipt.broker_position_id) == D('22.50')
        assert ledger.count(EventKind.TCA_RECORD) == 0
        # This exercises the existing downstream repair consumer; it does not
        # assert provider delivery, signed owner authority or native finality.
        measured = replace(receipt, fees=D('1.25'), receipt_hash='').sealed()
        _durable_receipt(ledger, measured)
        life.adopt_owner_buy_confirmation(measured, order_payload=order)
        life.adopt_owner_buy_confirmation(measured, order_payload=order)
        assert ledger.count(EventKind.TCA_RECORD) == 1
        assert life.entries['intent-1']['fees'] == D('1.25')
    finally:
        ledger.close()
