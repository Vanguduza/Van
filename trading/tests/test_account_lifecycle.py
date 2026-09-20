"""Counterexamples for the multi-instrument live lifecycle.

These tests target the failure mode the deployment-closure pass is designed to
catch: an account coordinator can look green while silently losing restart
protection, trade lifecycle evidence, or deterministic bar progression.
"""

from __future__ import annotations

from dataclasses import asdict
from decimal import Decimal
from types import SimpleNamespace

import pytest

from vati.app.account_service import AccountCoordinatorService
from vati.app.trade_lifecycle import AccountTradeLifecycle
from vati.core.events import EventKind, make_event
from vati.core.ledger import Ledger
from vati.execution.base import ExecutionReceipt, OrderCommand, StopMode
from vati.execution.zse_ticket import OwnerTicketAdapter
from vati.execution.paper import PaperAdapter
from vati.execution.protection import ProtectionError, ProtectionManager
from vati.execution.reconciliation import LedgerPosition, reconcile
from vati.execution.router import ExecutionRouter
from vati.market_data.bars import Bar
from vati.accounts import BrokerKind
from vati.risk import KillSwitch
from vati.risk.contracts import Direction, LossModel, StrategyState, SymbolContract, TradeIntent


def _contract(symbol="EURUSD"):
    return SymbolContract(
        symbol=symbol,
        venue="paper",
        base_currency="EUR",
        quote_currency="USD",
        account_currency="USD",
        contract_size=Decimal("100000"),
        tick_size=Decimal("0.0001"),
        tick_value=Decimal("10"),
        volume_min=Decimal("0.01"),
        volume_step=Decimal("0.01"),
        volume_max=Decimal("100"),
        min_stop_distance=Decimal("0.0001"),
        round_trip_cost_pct=Decimal("0.0003"),
    )


def _command(iid="ti-1"):
    return OrderCommand(
        trade_intent_id=iid,
        decision_hash="d" * 64,
        idempotency_key="idem-" + iid,
        account_alias="acct",
        venue="paper",
        symbol="EURUSD",
        direction=Direction.LONG,
        entry_type="LIMIT",
        quantity=Decimal("0.10"),
        entry_price=Decimal("1.1000"),
        protective_stop=Decimal("1.0900"),
        stop_mode=StopMode.VENUE,
        loss_model=LossModel.STOP_DISTANCE,
        targets=(Decimal("1.1200"),),
        strategy_id="FX-TREND-PULLBACK-01",
        strategy_version="1.0.0",
    ).sealed()


def _append_command(ledger, cmd, now=1_000):
    payload = {
        **asdict(cmd),
        "direction": cmd.direction.value,
        "stop_mode": cmd.stop_mode.value,
        "loss_model": cmd.loss_model.value,
    }
    ledger.append(make_event(
        EventKind.ORDER_COMMAND,
        "test-router",
        payload,
        event_time_ms=now,
        received_time_ms=now,
        decision_time_ms=now,
        correlation_id=cmd.trade_intent_id,
    ))


def _lifecycle(ledger, adapter):
    protection = ProtectionManager()
    router = ExecutionRouter(
        ledger=ledger,
        adapters={"paper": adapter},
        kill_switch=KillSwitch(),
        protection=protection,
    )
    return AccountTradeLifecycle(
        ledger=ledger,
        adapter=adapter,
        router=router,
        protection=protection,
        contracts={"EURUSD": _contract()},
        engines_by_symbol={},
        modelled_costs={"EURUSD": Decimal("0.0003")},
    )


def test_attributed_venue_position_without_open_ledger_state_blocks():
    adapter = PaperAdapter(venue="paper", account_alias="acct", slippage=Decimal("0"))
    adapter.submit(_command("orphan"), now_ms=1_000)
    result = reconcile([], adapter.positions(), account_verified=True)
    assert not result.permit_new_orders
    assert result.counts()["ORPHAN_VENUE_POSITION"] == 1


def test_restart_restores_only_ledger_backed_position_and_protection():
    ledger = Ledger(":memory:")
    adapter = PaperAdapter(venue="paper", account_alias="acct", slippage=Decimal("0"))
    cmd = _command("restore-me")
    _append_command(ledger, cmd)
    adapter.submit(cmd, now_ms=1_000)

    lifecycle = _lifecycle(ledger, adapter)
    restored, unresolved = lifecycle.recover_from_venue()

    assert restored == ("restore-me",)
    assert unresolved == ()
    position = adapter.positions()[0]
    assert lifecycle.protection.stop_of(position.position_id) == Decimal("1.0900")
    expected = [
        LedgerPosition(
            "restore-me", "EURUSD", position.quantity,
            Decimal("1.0900"), False,
        )
    ]
    assert reconcile(expected, adapter.positions(), account_verified=True).permit_new_orders


def test_restart_protection_refuses_a_widened_stop():
    p = ProtectionManager()
    with pytest.raises(ProtectionError, match="widening"):
        p.restore(
            "P1",
            symbol="EURUSD",
            direction=Direction.LONG,
            entry=Decimal("1.1000"),
            initial_stop=Decimal("1.0900"),
            current_stop=Decimal("1.0800"),
            target=Decimal("1.1200"),
            opened_ms=1_000,
        )


def test_filled_entry_produces_tca_and_close_produces_review():
    ledger = Ledger(":memory:")
    adapter = PaperAdapter(venue="paper", account_alias="acct", slippage=Decimal("0"))
    lifecycle = _lifecycle(ledger, adapter)
    intent = TradeIntent(
        trade_intent_id="entry-1",
        idempotency_key="entry-key",
        account_alias="acct",
        venue="paper",
        symbol="EURUSD",
        direction=Direction.LONG,
        strategy_id="FX-TREND-PULLBACK-01",
        strategy_version="1.0.0",
        strategy_state=StrategyState.DEMO,
        entry=Decimal("1.1000"),
        stop=Decimal("1.0900"),
        requested_risk_pct=Decimal("0.005"),
        decision_hash="d" * 64,
        market_snapshot_hash="m" * 64,
    )
    receipt = ExecutionReceipt(
        "entry-1", "d" * 64, "paper", "FILLED",
        Decimal("0.10"), Decimal("1.1001"),
        Decimal("1.1000"), Decimal("1.1000"), Decimal("1.1000"),
        True, 1_000, 1_000,
        broker_position_id="P1",
        spread_at_submit=Decimal("0.0001"),
    ).sealed()
    lifecycle.record_entry(
        intent=intent,
        receipt=receipt,
        state=SimpleNamespace(
            session=SimpleNamespace(value="LONDON"),
            event_window=SimpleNamespace(value="NONE"),
        ),
        modelled_cost_pct=Decimal("0.0003"),
        software_stop=False,
    )
    assert ledger.count(EventKind.TCA_RECORD) == 1

    # Close evidence is independent of how the fill was obtained.
    lifecycle._on_close("entry-1", Decimal("1.1200"), "TARGET", 2_000)
    assert ledger.count(EventKind.TRADE_REVIEW) == 1
    assert lifecycle.reviews


def _bar(end_ms, px="1.1000"):
    p = Decimal(px)
    return Bar(
        "EURUSD", end_ms - 60_000, end_ms,
        p, p + Decimal("0.0010"), p - Decimal("0.0010"), p,
        Decimal("1"), 10, Decimal("0.0001"),
    )


def test_account_service_replays_only_newly_closed_bars_and_only_advanced_symbols(tmp_path):
    cfg = SimpleNamespace(account_alias="acct", heartbeat_path=str(tmp_path / "hb.json"))
    service = AccountCoordinatorService(cfg, clock=lambda: 300_000)
    service._ledger = Ledger(":memory:")
    service.specs = {
        "EURUSD": SimpleNamespace(timeframe="M1"),
        "GBPUSD": SimpleNamespace(timeframe="M1"),
    }
    eur = [_bar(60_000), _bar(120_000)]
    gbp = [_bar(60_000)]
    service.bar_sources = {
        "EURUSD": lambda now: list(eur),
        "GBPUSD": lambda now: list(gbp),
    }
    marks = []
    service.lifecycle = SimpleNamespace(
        mark_bar=lambda symbol, bar, now_ms: marks.append((symbol, bar.end_ms, now_ms))
    )
    calls = []

    class _Result:
        allocation_epoch_id = "epoch"
        ranking = ()
        outcomes = ()
        candidates_admitted = ()
        expired = ()
        pass_hash = "hash"
        def as_dict(self):
            return {"allocation_epoch_id": self.allocation_epoch_id}

    service.coordinator = SimpleNamespace(
        step=lambda *, now_ms, bars_by_symbol: (
            calls.append((now_ms, tuple(sorted(bars_by_symbol)))) or _Result()
        ),
        pool=SimpleNamespace(row=lambda cid: None),
    )
    service.evaluators = {}
    service._observe_owner_halt = lambda now_ms: None
    service._heartbeat = lambda *args, **kwargs: None
    service._account_snapshot = lambda now_ms: None
    service._log_allocation_pass = lambda result, now_ms: None

    service.step_once()
    # Startup does not replay the 60s historical candle through a current book.
    assert [(s, e) for s, e, _ in marks] == [("EURUSD", 120_000), ("GBPUSD", 60_000)]
    assert calls[-1][1] == ("EURUSD", "GBPUSD")

    service.last_bar_end_ms = {"EURUSD": 120_000, "GBPUSD": 60_000}
    eur.extend([_bar(180_000), _bar(240_000)])
    marks.clear()
    calls.clear()
    service.step_once()

    assert [(s, e) for s, e, _ in marks] == [
        ("EURUSD", 180_000), ("EURUSD", 240_000)
    ]
    assert calls[-1][1] == ("EURUSD",)



def _zse_contract():
    return SymbolContract(
        symbol="DELTA", venue="zse",
        base_currency="DELTA", quote_currency="ZiG", account_currency="ZiG",
        contract_size=Decimal("1"), tick_size=Decimal("0.01"),
        tick_value=Decimal("0.01"),
        volume_min=Decimal("100"), volume_step=Decimal("100"),
        volume_max=Decimal("10000000"), min_stop_distance=Decimal("0"),
        trade_mode="LONG_ONLY", loss_model=LossModel.ILLIQUID_EQUITY,
        board_lot=Decimal("100"), adv_20d=Decimal("120000"),
        liquidity_haircut=Decimal("0.03"),
        round_trip_cost_pct=Decimal("0.0714"),
    )


def _zse_command(iid="zse-1"):
    return OrderCommand(
        trade_intent_id=iid,
        decision_hash="e" * 64,
        idempotency_key="idem-" + iid,
        account_alias="zse_primary",
        venue="zse",
        symbol="DELTA",
        direction=Direction.LONG,
        entry_type="LIMIT",
        quantity=Decimal("1500"),
        entry_price=Decimal("25.00"),
        protective_stop=Decimal("22.50"),
        stop_mode=StopMode.SOFTWARE,
        loss_model=LossModel.ILLIQUID_EQUITY,
        targets=(Decimal("30.00"),),
        time_in_force="GTC30",
        strategy_id="ZSE-VALUE-01",
        strategy_version="1.0.0",
    ).sealed()


def _zse_lifecycle(ledger, adapter):
    protection = ProtectionManager()
    router = ExecutionRouter(
        ledger=ledger, adapters={"zse": adapter},
        kill_switch=KillSwitch(), protection=protection)
    return AccountTradeLifecycle(
        ledger=ledger, adapter=adapter, router=router,
        protection=protection, contracts={"DELTA": _zse_contract()},
        engines_by_symbol={},
        modelled_costs={"DELTA": Decimal("0.0714")},
    )


def _append_owner_ticket_event(ledger, payload, corr, now):
    ledger.append(make_event(
        EventKind.OWNER_TICKET, "test",
        payload, event_time_ms=now, received_time_ms=now,
        correlation_id=corr,
    ))


def test_signed_owner_ticket_confirmations_become_runtime_truth_once_and_replay_cleanly(tmp_path):
    ledger = Ledger(":memory:")
    cmd = _zse_command()
    _append_command(ledger, cmd, now=1_000)
    _append_owner_ticket_event(
        ledger,
        {
            "ticket": "T1-ENTRY",
            "symbol": "DELTA", "qty": "1500", "side": "BUY",
            "trade_intent_id": cmd.trade_intent_id,
            "limit_price": "25.00", "software_stop": "22.50",
        },
        cmd.trade_intent_id, 1_100,
    )
    _append_owner_ticket_event(
        ledger,
        {
            "ticket": "T1-ENTRY", "action": "CONFIRMED",
            "fill_price": "24.90", "filled_qty": "1500",
            "contract_note_ref": "CN-BUY",
        },
        cmd.trade_intent_id, 1_200,
    )

    adapter = OwnerTicketAdapter(
        account_alias="zse_primary", equity=Decimal("1000000"),
        csd_verified=True)
    lifecycle = _zse_lifecycle(ledger, adapter)
    service = AccountCoordinatorService(
        SimpleNamespace(
            account_alias="zse_primary",
            heartbeat_path=str(tmp_path / "hb.json")))
    service.account = SimpleNamespace(broker=BrokerKind.ZSE_OWNER_TICKET)
    service.adapter = adapter
    service._ledger = ledger
    service.lifecycle = lifecycle

    assert service._sync_owner_ticket_buys(1_300) == ()
    assert len(adapter.positions()) == 1
    position = adapter.positions()[0]
    assert lifecycle.entries[cmd.trade_intent_id]["open"]
    assert lifecycle.protection.stop_of(position.position_id) == Decimal("22.50")
    assert ledger.count(EventKind.EXECUTION_RECEIPT) == 1
    assert ledger.count(EventKind.TCA_RECORD) == 1

    # Create the durable exit ticket exactly as Router.apply_exits does.
    close_receipt = adapter.close(
        position.position_id, None, now_ms=2_000, reason="SOFTWARE_STOP")
    sell_ticket = adapter.tickets[close_receipt.broker_order_id]
    lifecycle.protection.mark_close_pending(position.position_id)
    _append_owner_ticket_event(
        ledger,
        {
            "ticket": sell_ticket.ticket_id,
            "symbol": "DELTA", "qty": str(sell_ticket.quantity_shares),
            "side": "SELL", "position_id": position.position_id,
            "trade_intent_id": cmd.trade_intent_id,
            "exit_reason": "SOFTWARE_STOP", "limit_price": "0",
        },
        cmd.trade_intent_id, 2_000,
    )
    _append_owner_ticket_event(
        ledger,
        {
            "ticket": sell_ticket.ticket_id, "action": "CONFIRMED",
            "fill_price": "22.30", "filled_qty": "1500",
            "contract_note_ref": "CN-SELL",
        },
        cmd.trade_intent_id, 2_100,
    )

    assert service._sync_owner_ticket_sells(2_200) == ()
    assert adapter.positions() == []
    assert cmd.trade_intent_id not in lifecycle.entries
    assert position.position_id not in lifecycle.protection.rules
    assert ledger.count(EventKind.EXECUTION_RECEIPT) == 2
    assert ledger.count(EventKind.TRADE_REVIEW) == 1

    # Re-running the consumer in the same process is exactly-once.
    service._sync_owner_ticket_buys(2_300)
    service._sync_owner_ticket_sells(2_300)
    assert ledger.count(EventKind.EXECUTION_RECEIPT) == 2
    assert ledger.count(EventKind.TRADE_REVIEW) == 1

    # A fresh process reconstructs current projected holdings from the same
    # ledger but emits no duplicate receipt or review.
    adapter2 = OwnerTicketAdapter(
        account_alias="zse_primary", equity=Decimal("1000000"),
        csd_verified=True)
    lifecycle2 = _zse_lifecycle(ledger, adapter2)
    service2 = AccountCoordinatorService(
        SimpleNamespace(
            account_alias="zse_primary",
            heartbeat_path=str(tmp_path / "hb2.json")))
    service2.account = SimpleNamespace(broker=BrokerKind.ZSE_OWNER_TICKET)
    service2.adapter = adapter2
    service2._ledger = ledger
    service2.lifecycle = lifecycle2

    assert service2._sync_owner_ticket_buys(3_000) == ()
    restored, unresolved = lifecycle2.recover_from_venue()
    assert restored == (cmd.trade_intent_id,) and unresolved == ()
    assert service2._sync_owner_ticket_sells(3_000) == ()
    assert adapter2.positions() == []
    assert lifecycle2.entries == {}
    assert ledger.count(EventKind.EXECUTION_RECEIPT) == 2
    assert ledger.count(EventKind.TRADE_REVIEW) == 1
