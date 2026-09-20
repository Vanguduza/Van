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
from vati.execution.paper import PaperAdapter
from vati.execution.router import ExecutionRouter
from vati.execution.protection import ProtectionError, ProtectionManager
from vati.execution.zse_ticket import OwnerTicketAdapter
from vati.risk import KillSwitch
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


def test_regular_broker_restart_repairs_missing_tca_exactly_once(mandate, eurusd):
    """Crash after durable fill receipt but before lifecycle.record_entry."""
    from conftest import intent, mandate_dict, snapshot
    from vati.risk import RiskAuthority, StrategyState, TradingMandate

    contract = SymbolContract(**{**eurusd.__dict__, "venue": "paper"})
    live_mandate = TradingMandate.from_mapping(
        mandate_dict(venue="paper", mode="DEMO_TRADER"))
    trade_intent = intent(
        venue="paper",
        strategy_state=StrategyState.DEMO,
        trade_intent_id="restart-tca-intent",
        idempotency_key="restart-tca-key",
    )
    decision = RiskAuthority(live_mandate).evaluate(
        trade_intent, snapshot(contract))
    assert decision.decision.value in ("APPROVED", "REDUCED")

    ledger = Ledger()
    adapter = PaperAdapter()
    router = ExecutionRouter(
        ledger=ledger,
        adapters={"paper": adapter},
        kill_switch=KillSwitch(),
        protection=ProtectionManager(),
    )
    receipt = router.execute(
        trade_intent,
        decision,
        live_mandate,
        now_ms=10_000,
        targets=(Decimal("1.10340"),),
    )
    assert receipt.status == "FILLED"
    assert ledger.count(EventKind.ORDER_COMMAND) == 1
    assert ledger.count(EventKind.EXECUTION_RECEIPT) == 1
    assert ledger.count(EventKind.TCA_RECORD) == 0

    # New lifecycle/protection objects simulate the process dying before
    # AccountCoordinatorService could call record_entry().
    recovered = AccountTradeLifecycle(
        ledger=ledger,
        adapter=adapter,
        router=ExecutionRouter(
            ledger=ledger,
            adapters={"paper": adapter},
            kill_switch=KillSwitch(),
            protection=ProtectionManager(),
        ),
        protection=ProtectionManager(),
        contracts={"EURUSD": contract},
        engines_by_symbol={},
        modelled_costs={"EURUSD": Decimal("0.00015")},
    )
    restored, unresolved = recovered.recover_from_venue()
    assert restored == ("restart-tca-intent",)
    assert unresolved == ()
    assert ledger.count(EventKind.TCA_RECORD) == 1
    tca_event = list(
        ledger.iter(EventKind.TCA_RECORD, correlation_id="restart-tca-intent"))[0]
    assert tca_event.payload["recovered_after_restart"] is True
    assert tca_event.payload["source_receipt_hash"] == receipt.receipt_hash
    assert Decimal(str(tca_event.payload["cost_ratio"])) == recovered.entries[
        "restart-tca-intent"]["cost_ratio"]

    # A second process restart reuses durable TCA and cannot append a duplicate.
    recovered_again = AccountTradeLifecycle(
        ledger=ledger,
        adapter=adapter,
        router=recovered.router,
        protection=ProtectionManager(),
        contracts={"EURUSD": contract},
        engines_by_symbol={},
        modelled_costs={"EURUSD": Decimal("0.00015")},
    )
    restored2, unresolved2 = recovered_again.recover_from_venue()
    assert restored2 == ("restart-tca-intent",)
    assert unresolved2 == ()
    assert ledger.count(EventKind.TCA_RECORD) == 1
    assert recovered_again.entries["restart-tca-intent"]["cost_ratio"] == (
        recovered.entries["restart-tca-intent"]["cost_ratio"]
    )


def test_corrupt_durable_fill_receipt_is_not_promoted_into_recovered_tca(mandate, eurusd):
    """Position safety may recover, but malformed execution evidence teaches nothing."""
    from conftest import intent, mandate_dict, snapshot
    from vati.risk import RiskAuthority, StrategyState, TradingMandate

    contract = SymbolContract(**{**eurusd.__dict__, "venue": "paper"})
    live_mandate = TradingMandate.from_mapping(
        mandate_dict(venue="paper", mode="DEMO_TRADER"))
    trade_intent = intent(
        venue="paper",
        strategy_state=StrategyState.DEMO,
        trade_intent_id="bad-receipt-intent",
        idempotency_key="bad-receipt-key",
    )
    decision = RiskAuthority(live_mandate).evaluate(
        trade_intent, snapshot(contract))

    ledger = Ledger()
    adapter = PaperAdapter()
    router = ExecutionRouter(
        ledger=ledger,
        adapters={"paper": adapter},
        kill_switch=KillSwitch(),
        protection=ProtectionManager(),
    )
    router.execute(trade_intent, decision, live_mandate, now_ms=20_000)

    # Append a later entry-looking receipt with a deliberately invalid
    # receipt_hash. Recovery keeps the first valid router receipt and therefore
    # still produces one valid TCA; it must never select/promote the corrupt row.
    original = list(
        ledger.iter(EventKind.EXECUTION_RECEIPT, correlation_id="bad-receipt-intent"))[0]
    corrupt = dict(original.payload)
    corrupt["receipt_hash"] = "0" * 64
    ledger.append(make_event(
        EventKind.EXECUTION_RECEIPT,
        "corrupt-test",
        corrupt,
        event_time_ms=20_001,
        received_time_ms=20_001,
        correlation_id="bad-receipt-intent",
    ))

    recovered = AccountTradeLifecycle(
        ledger=ledger,
        adapter=adapter,
        router=router,
        protection=ProtectionManager(),
        contracts={"EURUSD": contract},
        engines_by_symbol={},
        modelled_costs={"EURUSD": Decimal("0.00015")},
    )
    restored, unresolved = recovered.recover_from_venue()
    assert restored == ("bad-receipt-intent",)
    assert unresolved == ()
    assert ledger.count(EventKind.TCA_RECORD) == 1
    tca = list(
        ledger.iter(EventKind.TCA_RECORD, correlation_id="bad-receipt-intent"))[0]
    assert tca.payload["source_receipt_hash"] == original.payload["receipt_hash"]


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
