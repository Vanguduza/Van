"""Counterexamples for the account-scoped trade lifecycle.

These tests cover crash windows that a green order-routing test cannot see:
a durable owner execution receipt can exist while the downstream TCA or trade
review has not yet been written. Restart/replay must repair that missing
evidence exactly once.
"""

from decimal import Decimal
from types import SimpleNamespace

import pytest

from vati.app.trade_lifecycle import AccountTradeLifecycle
from vati.core.events import EventKind, make_event
from vati.core.ledger import Ledger
from vati.execution.base import ExecutionReceipt
from vati.execution.protection import ProtectionError, ProtectionManager
from vati.execution.zse_ticket import OwnerTicketAdapter
from vati.risk.contracts import Direction, LossModel, SymbolContract


def _contract() -> SymbolContract:
    return SymbolContract(
        symbol="DELTA",
        venue="zse",
        base_currency="DELTA",
        quote_currency="ZiG",
        account_currency="ZiG",
        contract_size=Decimal("1"),
        tick_size=Decimal("0.01"),
        tick_value=Decimal("0.01"),
        volume_min=Decimal("100"),
        volume_step=Decimal("100"),
        volume_max=Decimal("10000000"),
        min_stop_distance=Decimal("0"),
        trade_mode="LONG_ONLY",
        loss_model=LossModel.ILLIQUID_EQUITY,
        board_lot=Decimal("100"),
        adv_20d=Decimal("120000"),
        liquidity_haircut=Decimal("0.03"),
        round_trip_cost_pct=Decimal("0.0714"),
    )


def _lifecycle(ledger: Ledger, adapter: OwnerTicketAdapter) -> AccountTradeLifecycle:
    return AccountTradeLifecycle(
        ledger=ledger,
        adapter=adapter,
        router=SimpleNamespace(),
        protection=ProtectionManager(),
        contracts={"DELTA": _contract()},
        engines_by_symbol={},
        modelled_costs={"DELTA": Decimal("0.0714")},
    )


def _owner_receipt(*, price: str, qty: str = "1200", ticket: str = "T1-decision"):
    return ExecutionReceipt(
        trade_intent_id="intent-1",
        decision_hash="d" * 64,
        venue="zse",
        status="OWNER_EXECUTED",
        filled_qty=Decimal(qty),
        average_fill=Decimal(price),
        decision_price=Decimal("25.00"),
        arrival_price=Decimal("25.00"),
        submitted_price=Decimal("25.00"),
        protective_stop_confirmed=True,
        broker_time_unix_ms=2_000,
        received_time_unix_ms=2_000,
        execution_channel="OWNER_TICKET",
        broker_order_id=ticket,
        broker_position_id="CSD-T1-decision",
    ).sealed()


def _durable_receipt(ledger: Ledger, receipt: ExecutionReceipt) -> None:
    ledger.append(make_event(
        EventKind.EXECUTION_RECEIPT,
        "test-crash-window",
        {
            "trade_intent_id": receipt.trade_intent_id,
            "status": receipt.status,
            "broker_order_id": receipt.broker_order_id,
            "execution_channel": receipt.execution_channel,
        },
        event_time_ms=receipt.received_time_unix_ms,
        received_time_ms=receipt.received_time_unix_ms,
        correlation_id=receipt.trade_intent_id,
    ))


def test_owner_buy_replay_repairs_missing_tca_exactly_once_after_receipt_commit():
    ledger = Ledger()
    adapter = OwnerTicketAdapter(equity=Decimal("1000000"), csd_verified=True)
    lifecycle = _lifecycle(ledger, adapter)
    receipt = _owner_receipt(price="24.90")
    _durable_receipt(ledger, receipt)

    order_payload = {
        "symbol": "DELTA",
        "direction": "LONG",
        "strategy_id": "ZSE-VALUE-ROTATION-01",
        "entry_price": "25.00",
        "protective_stop": "22.50",
        "targets": ["30.00"],
    }

    # Counterexample: process died after EXECUTION_RECEIPT but before TCA.
    assert ledger.count(EventKind.EXECUTION_RECEIPT) == 1
    assert ledger.count(EventKind.TCA_RECORD) == 0

    lifecycle.adopt_owner_buy_confirmation(receipt, order_payload=order_payload)
    assert ledger.count(EventKind.TCA_RECORD) == 1
    assert lifecycle.entries["intent-1"]["entry"] == Decimal("24.90")
    assert lifecycle.protection.stop_of("CSD-T1-decision") == Decimal("22.50")

    # A second replay reconstructs memory but cannot duplicate durable TCA.
    lifecycle.adopt_owner_buy_confirmation(receipt, order_payload=order_payload)
    assert ledger.count(EventKind.TCA_RECORD) == 1


def test_owner_sell_replay_repairs_missing_review_exactly_once_after_receipt_commit():
    ledger = Ledger()
    adapter = OwnerTicketAdapter(equity=Decimal("1000000"), csd_verified=True)
    lifecycle = _lifecycle(ledger, adapter)
    lifecycle.entries["intent-1"] = {
        "symbol": "DELTA",
        "entry": Decimal("24.90"),
        "stop": Decimal("22.50"),
        "direction": Direction.LONG,
        "strategy_id": "ZSE-VALUE-ROTATION-01",
        "cost_pct": Decimal("0.0714"),
        "decision_price": Decimal("25.00"),
        "quantity": Decimal("1200"),
        "software_stop": True,
        "broker_position_id": "CSD-T1-decision",
        "open": True,
        "pending": False,
    }
    lifecycle.protection.register(
        "CSD-T1-decision",
        symbol="DELTA",
        direction=Direction.LONG,
        entry=Decimal("24.90"),
        stop=Decimal("22.50"),
        target=None,
        opened_ms=1_000,
        software_stop=True,
    )

    receipt = _owner_receipt(price="26.00", ticket="T2-SELL")
    _durable_receipt(ledger, receipt)

    # Counterexample: process died after SELL receipt but before review/VTIL proposal.
    assert ledger.count(EventKind.TRADE_REVIEW) == 0
    lifecycle.adopt_owner_sell_confirmation(
        receipt,
        exit_reason="OWNER_CONFIRMED_SELL",
        now_ms=3_000,
    )
    assert ledger.count(EventKind.TRADE_REVIEW) == 1
    assert "intent-1" not in lifecycle.entries
    assert "CSD-T1-decision" not in lifecycle.protection.rules

    lifecycle.adopt_owner_sell_confirmation(
        receipt,
        exit_reason="OWNER_CONFIRMED_SELL",
        now_ms=3_001,
    )
    assert ledger.count(EventKind.TRADE_REVIEW) == 1


def test_downstream_evidence_lookup_exhausts_transactional_iterator():
    class TransactionalLedger:
        def __init__(self):
            self.cleaned_up = False

        def iter(self, kind=None, correlation_id=None):
            assert kind is EventKind.TCA_RECORD
            assert correlation_id == "intent-1"
            try:
                yield make_event(
                    EventKind.TCA_RECORD,
                    "test",
                    {"trade_intent_id": "intent-1"},
                    event_time_ms=1,
                    received_time_ms=1,
                    correlation_id="intent-1",
                )
                # A second row makes first-row short-circuiting observable.
                yield make_event(
                    EventKind.TCA_RECORD,
                    "test",
                    {"trade_intent_id": "intent-1", "n": 2},
                    event_time_ms=2,
                    received_time_ms=2,
                    correlation_id="intent-1",
                )
            finally:
                self.cleaned_up = True

    ledger = TransactionalLedger()
    lifecycle = AccountTradeLifecycle(
        ledger=ledger,
        adapter=OwnerTicketAdapter(),
        router=SimpleNamespace(),
        protection=ProtectionManager(),
        contracts={"DELTA": _contract()},
        engines_by_symbol={},
    )
    assert lifecycle._has_event(EventKind.TCA_RECORD, "intent-1")
    assert ledger.cleaned_up, "evidence lookup must exhaust/close the ledger iterator"


def test_restart_protection_restore_cannot_widen_the_original_stop():
    protection = ProtectionManager()
    protection.restore(
        "P1",
        symbol="EURUSD",
        direction=Direction.LONG,
        entry=Decimal("1.1000"),
        initial_stop=Decimal("1.0950"),
        current_stop=Decimal("1.0980"),
        target=Decimal("1.1100"),
        opened_ms=1,
    )
    assert protection.stop_of("P1") == Decimal("1.0980")

    with pytest.raises(ProtectionError, match="widening"):
        protection.restore(
            "P2",
            symbol="EURUSD",
            direction=Direction.LONG,
            entry=Decimal("1.1000"),
            initial_stop=Decimal("1.0950"),
            current_stop=Decimal("1.0900"),
            target=None,
            opened_ms=1,
        )
