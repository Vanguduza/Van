from __future__ import annotations

from decimal import Decimal

import pytest

from conftest import intent, mandate_dict, snapshot
from vati.core import EventKind, Ledger
from vati.execution import (
    DerivAdapter, ExecutionReceipt, ExecutionRouter, Mt5BridgeAdapter, Mt5BridgeClient, Outcome, OwnerTicketAdapter, PaperAdapter, ProtectionError, ProtectionManager,
    ReconciliationClass, RouterError, StopMode, VenuePosition, VenueUnavailable, compute_tca, map_deriv_contract, reconcile, review_trade,
)
from vati.execution.reconciliation import LedgerPosition
from vati.execution.router import recompute_decision_hash
from vati.risk import Decision, Direction, KillSwitch, KillSwitchTrigger, LossModel, RiskAuthority, StrategyState, SymbolContract, TradingMandate
from vati.vtil import AdmissionError, AdmissionLedger, AdmissionState

NOW = 1_800_000_000_000


def approved(mandate, eurusd, **it):
    i = intent(**it)
    d = RiskAuthority(mandate).evaluate(i, snapshot(eurusd))
    assert d.decision in (Decision.APPROVED, Decision.REDUCED), d
    return i, d


def router(adapter, ledger=None, ks=None):
    led = ledger or Ledger()
    return ExecutionRouter(ledger=led, adapters={adapter.venue: adapter}, kill_switch=ks or KillSwitch(), protection=ProtectionManager()), led


def test_router_happy_path_paper(mandate, eurusd):
    m = TradingMandate.from_mapping(mandate_dict(venue="paper", mode="DEMO_TRADER"))
    i, d = approved(m, SymbolContract(**{**eurusd.__dict__, "venue": "paper"}), venue="paper", strategy_state=StrategyState.DEMO)
    pa = PaperAdapter()
    r, led = router(pa)
    rec = r.execute(i, d, m, now_ms=NOW, targets=(Decimal("1.10340"),))
    assert rec.status == "FILLED" and rec.protective_stop_confirmed and rec.filled_qty == d.approved_size
    assert led.count(EventKind.ORDER_COMMAND) == 1 and led.count(EventKind.EXECUTION_RECEIPT) == 1 and led.verify_chain()[0]
    assert pa.positions()[0].stop_price == i.stop and pa.positions()[0].trade_intent_id == i.trade_intent_id
    with pytest.raises(RouterError, match="duplicate idempotency"):
        r.execute(i, d, m, now_ms=NOW + 1)


def test_router_refuses_tampered_or_rejected_decisions(mandate, eurusd):
    m = TradingMandate.from_mapping(mandate_dict(venue="paper", mode="DEMO_TRADER"))
    c = SymbolContract(**{**eurusd.__dict__, "venue": "paper"})
    i, d = approved(m, c, venue="paper", strategy_state=StrategyState.DEMO)
    r, _ = router(PaperAdapter())
    tampered = d.__class__(**{**d.__dict__, "approved_size": d.approved_size * 10})
    with pytest.raises(RouterError, match="does not recompute"):
        r.execute(i, tampered, m, now_ms=NOW)
    rejected = RiskAuthority(m).evaluate(intent(venue="paper", strategy_state=StrategyState.DEMO, stop=None), snapshot(c))
    with pytest.raises(RouterError, match="REJECTED"):
        r.execute(intent(venue="paper", strategy_state=StrategyState.DEMO, stop=None), rejected, m, now_ms=NOW)
    other = TradingMandate.from_mapping(mandate_dict(venue="paper", mode="DEMO_TRADER", version="2.0.0"))
    with pytest.raises(RouterError, match="different mandate"):
        r.execute(i, d, other, now_ms=NOW)
    observe = TradingMandate.from_mapping(mandate_dict(venue="paper", mode="OBSERVE"))
    with pytest.raises(RouterError, match="does not send orders"):
        r.execute(i, d, observe, now_ms=NOW)
    assert recompute_decision_hash(d) == d.decision_hash


def test_router_flattens_when_stop_rejected_and_trips_kill_switch(mandate, eurusd):
    m = TradingMandate.from_mapping(mandate_dict(venue="paper", mode="DEMO_TRADER"))
    i, d = approved(m, SymbolContract(**{**eurusd.__dict__, "venue": "paper"}), venue="paper", strategy_state=StrategyState.DEMO)
    pa = PaperAdapter(inject_reject_stop=True)
    ks = KillSwitch()
    r, led = router(pa, ks=ks)
    with pytest.raises(RouterError, match="protective stop not confirmed"):
        r.execute(i, d, m, now_ms=NOW)
    assert pa.positions() == [] and KillSwitchTrigger.STOP_REJECTED in ks.active and led.count(EventKind.KILL_SWITCH) == 1
    with pytest.raises(RouterError, match="kill switch active"):
        r.execute(intent(venue="paper", idempotency_key="k2", strategy_state=StrategyState.DEMO), d, m, now_ms=NOW)


def test_router_disconnect_trips_kill_switch(mandate, eurusd):
    m = TradingMandate.from_mapping(mandate_dict(venue="paper", mode="DEMO_TRADER"))
    i, d = approved(m, SymbolContract(**{**eurusd.__dict__, "venue": "paper"}), venue="paper", strategy_state=StrategyState.DEMO)
    ks = KillSwitch()
    r, _ = router(PaperAdapter(inject_disconnect=True), ks=ks)
    with pytest.raises(RouterError, match="heartbeat"):
        r.execute(i, d, m, now_ms=NOW)
    assert KillSwitchTrigger.VENUE_DISCONNECT in ks.active


def test_paper_marks_fire_stops_and_targets_and_protection_only_tightens(mandate, eurusd):
    m = TradingMandate.from_mapping(mandate_dict(venue="paper", mode="DEMO_TRADER"))
    i, d = approved(m, SymbolContract(**{**eurusd.__dict__, "venue": "paper"}), venue="paper", strategy_state=StrategyState.DEMO)
    pa = PaperAdapter()
    r, led = router(pa)
    rec = r.execute(i, d, m, now_ms=NOW, targets=(Decimal("1.10340"),))
    pid = rec.broker_position_id
    with pytest.raises(ProtectionError, match="widening"):
        r.protection.tighten(pid, Decimal("1.09000"))
    r.protection.tighten(pid, Decimal("1.09900"))
    # price falls through the tightened software-tracked stop → CLOSE instruction executed via adapter
    outs = r.apply_exits("paper", "EURUSD", Decimal("1.09890"), Decimal("1.09900"), now_ms=NOW + 60_000)
    assert outs and outs[0].reject_reason in ("STRUCTURE", "SOFTWARE_STOP") and pa.positions() == [] and pa.closed[0]["pnl"] < 0
    # target path via venue mark
    i2, d2 = approved(m, SymbolContract(**{**eurusd.__dict__, "venue": "paper"}), venue="paper", strategy_state=StrategyState.DEMO, idempotency_key="k9", trade_intent_id="ti-9")
    r.execute(i2, d2, m, now_ms=NOW + 120_000, targets=(Decimal("1.10340"),))
    fills = pa.mark("EURUSD", Decimal("1.10350"), Decimal("1.10360"), now_ms=NOW + 180_000)
    assert fills and fills[0].reject_reason == "TARGET" and pa.closed[-1]["pnl"] > 0


def test_protection_break_even_and_trailing():
    pm = ProtectionManager()
    pm.register("P1", symbol="EURUSD", direction=Direction.LONG, entry=Decimal("1.1000"), stop=Decimal("1.0980"), target=None, opened_ms=0,
                break_even_trigger=Decimal("0.0010"), trail_distance=Decimal("0.0015"), time_stop_ms=10_000)
    assert pm.on_mark("EURUSD", Decimal("1.1005"), Decimal("1.1006"), now_ms=1) == []
    ins = pm.on_mark("EURUSD", Decimal("1.1012"), Decimal("1.1013"), now_ms=2)
    assert [x.reason for x in ins] == ["BREAK_EVEN"] and pm.stop_of("P1") == Decimal("1.1000")
    ins = pm.on_mark("EURUSD", Decimal("1.1030"), Decimal("1.1031"), now_ms=3)
    assert [x.reason for x in ins] == ["TRAIL"] and pm.stop_of("P1") == Decimal("1.1015")
    assert pm.on_mark("EURUSD", Decimal("1.1020"), Decimal("1.1021"), now_ms=4) == []  # pullback never loosens
    ins = pm.on_mark("EURUSD", Decimal("1.1020"), Decimal("1.1021"), now_ms=10_001)
    assert ins[0].reason == "TIME_STOP"
    assert "P1" in pm.rules and pm.is_close_pending("P1")
    assert pm.on_mark("EURUSD", Decimal("1.1020"), Decimal("1.1021"), now_ms=10_002) == []
    pm.close_failed("P1")
    assert pm.on_mark("EURUSD", Decimal("1.1020"), Decimal("1.1021"), now_ms=10_003)
    pm.close_confirmed("P1")
    assert "P1" not in pm.rules
    with pytest.raises(ProtectionError):
        pm.register("P2", symbol="X", direction=Direction.LONG, entry=Decimal("1"), stop=Decimal("2"), target=None, opened_ms=0)


def test_rejected_venue_stop_tighten_rolls_back_local_truth_and_halts(mandate, eurusd):
    class RejectModifyPaper(PaperAdapter):
        def modify_stop(self, position_id, new_stop, *, now_ms):
            p = self._positions[position_id]
            return ExecutionReceipt(
                p["intent"], "", self.venue, "REJECTED", Decimal("0"), None,
                p["entry"], p["entry"], p["entry"], True, now_ms, now_ms,
                broker_position_id=position_id,
                protective_stop_price=p["stop"],
                reject_reason="injected_stop_modify_reject",
            ).sealed()

    m = TradingMandate.from_mapping(
        mandate_dict(venue="paper", mode="DEMO_TRADER"))
    i, d = approved(
        m, SymbolContract(**{**eurusd.__dict__, "venue": "paper"}),
        venue="paper", strategy_state=StrategyState.DEMO)
    ad = RejectModifyPaper()
    ks = KillSwitch()
    r, led = router(ad, ks=ks)
    rec = r.execute(i, d, m, now_ms=NOW)
    pid = rec.broker_position_id
    original_stop = r.protection.stop_of(pid)
    r.protection.rules[pid].break_even_trigger = Decimal("0.0005")

    out = r.apply_exits(
        "paper", "EURUSD",
        i.entry + Decimal("0.0010"), i.entry + Decimal("0.0011"),
        now_ms=NOW + 1_000,
    )
    assert out and out[0].status == "REJECTED"
    assert r.protection.stop_of(pid) == original_stop
    assert ad.positions()[0].stop_price == original_stop
    assert KillSwitchTrigger.STOP_REJECTED in ks.active
    assert led.count(EventKind.KILL_SWITCH) == 1


def test_owner_ticket_channel_for_zse():
    ad = OwnerTicketAdapter(equity=Decimal("1000000"), csd_verified=True)
    m = TradingMandate.from_mapping(mandate_dict(venue="zse", instruments=["DELTA"], allowed_strategies=["ZSE-VALUE-01"], mode="LIMITED_LIVE", weekend_hold_allowed=True, max_open_stop_risk="0.02", max_risk_per_trade="0.01", account_alias="zse_primary"))
    c = SymbolContract(symbol="DELTA", venue="zse", base_currency="DELTA", quote_currency="ZiG", account_currency="ZiG", contract_size=Decimal("1"), tick_size=Decimal("0.01"), tick_value=Decimal("0.01"),
                       volume_min=Decimal("100"), volume_step=Decimal("100"), volume_max=Decimal("10000000"), min_stop_distance=Decimal("0"), trade_mode="LONG_ONLY", loss_model=LossModel.ILLIQUID_EQUITY,
                       board_lot=Decimal("100"), adv_20d=Decimal("120000"), liquidity_haircut=Decimal("0.03"), round_trip_cost_pct=Decimal("0.0714"))
    i = intent(venue="zse", symbol="DELTA", strategy_id="ZSE-VALUE-01", strategy_state=StrategyState.CERTIFIED_LIVE, entry=Decimal("25.00"), stop=Decimal("22.50"),
               requested_risk_pct=Decimal("0.005"), holds_over_weekend=True, expected_gross_move_pct=Decimal("0.20"), account_alias="zse_primary")
    snap = snapshot(c, account_alias="zse_primary", equity=Decimal("1000000"), balance=Decimal("1000000"), peak_equity=Decimal("1000000"), day_start_equity=Decimal("1000000"), week_start_equity=Decimal("1000000"))
    d = RiskAuthority(m).evaluate(i, snap)
    assert d.decision is Decision.APPROVED and d.approved_size == Decimal("1500")
    r, led = router(ad)
    rec = r.execute(i, d, m, now_ms=NOW, time_in_force="GTC30")
    assert rec.status == "ACCEPTED" and rec.execution_channel == "OWNER_TICKET" and led.count(EventKind.OWNER_TICKET) == 1
    t = ad.tickets[rec.broker_order_id]
    assert "Software stop" in t.render() and t.quantity_shares == Decimal("1500") and t.software_stop == Decimal("22.50")
    with pytest.raises(ValueError, match="exceeds"):
        ad.confirm(t.ticket_id, fill_price=Decimal("25.50"), filled_qty=Decimal("1500"), contract_note_ref="CN-1", now_ms=NOW)
    conf = ad.confirm(t.ticket_id, fill_price=Decimal("24.90"), filled_qty=Decimal("1500"), contract_note_ref="CN-1", now_ms=NOW + 1000)
    assert conf.status == "OWNER_EXECUTED" and ad.positions()[0].loss_model is LossModel.ILLIQUID_EQUITY
    with pytest.raises(ValueError, match="already confirmed"):
        ad.confirm(t.ticket_id, fill_price=Decimal("24.90"), filled_qty=Decimal("1500"), contract_note_ref="CN-1", now_ms=NOW + 1001)

    # A software-stop close is a durable SELL ticket, not an immediate close.
    pid = ad.positions()[0].position_id
    r.protection.register(
        pid, symbol="DELTA", direction=Direction.LONG,
        entry=Decimal("24.90"), stop=Decimal("22.50"), target=None,
        opened_ms=NOW + 1000, software_stop=True,
    )
    exits = r.apply_exits(
        "zse", "DELTA", Decimal("22.40"), Decimal("22.41"),
        now_ms=NOW + 2000,
    )
    assert exits[0].status == "ACCEPTED"
    assert ad.positions() and r.protection.is_close_pending(pid)
    assert led.count(EventKind.OWNER_TICKET) == 2
    # Pending-close state suppresses duplicate SELL tickets.
    assert r.apply_exits(
        "zse", "DELTA", Decimal("22.30"), Decimal("22.31"),
        now_ms=NOW + 3000,
    ) == []
    sell = [ticket for ticket in ad.tickets.values() if ticket.side == "SELL"][0]
    sell_fill = ad.confirm(
        sell.ticket_id, fill_price=Decimal("22.30"),
        filled_qty=Decimal("1500"), contract_note_ref="CN-SELL",
        now_ms=NOW + 4000,
    )
    assert sell_fill.status == "OWNER_EXECUTED"
    assert sell_fill.broker_position_id == pid
    assert ad.positions() == []
    r.protection.close_confirmed(pid)
    assert pid not in r.protection.rules
    # a SHORT never becomes a ticket
    bad = ad.submit(__import__("vati.execution", fromlist=["OrderCommand"]).OrderCommand("x", "h", "k", "zse_primary", "zse", "DELTA", Direction.SHORT, "LIMIT", Decimal("100"), Decimal("25"), None, StopMode.SOFTWARE, LossModel.ILLIQUID_EQUITY).sealed(), now_ms=NOW)
    assert bad.status == "REJECTED"


def test_mt5_bridge_fails_closed_and_signs():
    cli = Mt5BridgeClient(signing_key=b"k" * 32)
    with pytest.raises(VenueUnavailable):
        cli.call("order_send", {}, now_ms=NOW)
    with pytest.raises(ValueError):
        cli.call("shell", {}, now_ms=NOW)
    calls = []
    def transport(req):
        calls.append(req)
        if req["op"] == "order_check":
            return {"nonce": req["nonce"], "worker_time_ms": req["issued_ms"], "ok": True}
        if req["op"] == "order_send":
            return {"nonce": req["nonce"], "worker_time_ms": req["issued_ms"], "status": "FILLED", "volume": req["body"]["volume"], "price": req["body"]["price"], "sl_confirmed": True, "order": "1", "position": "9"}
        return {"nonce": req["nonce"], "worker_time_ms": req["issued_ms"]}
    ad = Mt5BridgeAdapter(Mt5BridgeClient(signing_key=b"k" * 32, transport=transport))
    from vati.execution import OrderCommand
    cmd = OrderCommand("ti", "ab12cd34ef", "k", "fx_primary", "mt5", "EURUSD", Direction.LONG, "LIMIT", Decimal("0.18"), Decimal("1.1001"), Decimal("1.0979"), StopMode.VENUE, LossModel.STOP_DISTANCE).sealed()
    rec = ad.submit(cmd, now_ms=NOW)
    assert rec.status == "FILLED" and rec.protective_stop_confirmed and [c["op"] for c in calls] == ["order_check", "order_send"]
    assert all(ad.client.verify(__import__("vati.execution", fromlist=["BridgeRequest"]).BridgeRequest(**c)) for c in calls)
    assert calls[1]["body"]["comment"] == "vati:ti" and calls[1]["body"]["sl"] == "1.0979"
    no_sl = ad.submit(OrderCommand("ti2", "h", "k2", "fx_primary", "mt5", "EURUSD", Direction.LONG, "LIMIT", Decimal("0.1"), Decimal("1.1"), None, StopMode.VENUE, LossModel.STOP_DISTANCE).sealed(), now_ms=NOW)
    assert no_sl.status == "REJECTED"
    replay = Mt5BridgeClient(signing_key=b"k" * 32, transport=lambda req: {"nonce": 999, "worker_time_ms": req["issued_ms"]})
    with pytest.raises(VenueUnavailable, match="nonce"):
        replay.call("positions", {}, now_ms=NOW)


def test_deriv_adapter_mapping_and_synthetic_refusal():
    assert map_deriv_contract("RISE_FALL") == (LossModel.FULL_STAKE, "BinaryOption") and map_deriv_contract("CFD")[0] is LossModel.STOP_DISTANCE
    with pytest.raises(ValueError):
        map_deriv_contract("LOTTERY")
    from vati.execution import OrderCommand
    ad = DerivAdapter(transport=lambda m: {"proposal": {"id": "p1"}} if "proposal" in m else {"buy": {"buy_price": "25", "contract_id": 77, "transaction_id": 5, "purchase_time": 1}})
    syn = OrderCommand("ti", "h", "k", "deriv_primary", "deriv", "R_75", Direction.LONG, "CONTRACT_BUY", Decimal("25"), Decimal("1"), None, StopMode.VENUE, LossModel.FULL_STAKE).sealed()
    assert ad.submit(syn, now_ms=NOW).status == "REJECTED"
    real = OrderCommand("ti", "h", "k", "deriv_primary", "deriv", "frxXAUUSD", Direction.LONG, "CONTRACT_BUY", Decimal("25"), Decimal("2400"), None, StopMode.VENUE, LossModel.FULL_STAKE).sealed()
    rec = ad.submit(real, now_ms=NOW)
    assert rec.status == "FILLED" and rec.protective_stop_confirmed and ad.sent[0]["passthrough"]["trade_intent_id"] == "ti"
    with pytest.raises(VenueUnavailable):
        DerivAdapter().sync_account()


def test_reconciliation_classes_and_gate():
    ledger = [LedgerPosition("a", "EURUSD", Decimal("0.2"), Decimal("1.09")), LedgerPosition("b", "GBPUSD", Decimal("0.1"), Decimal("1.25")), LedgerPosition("c", "USDJPY", Decimal("0.1"), Decimal("150")), LedgerPosition("d", "XAUUSD", Decimal("0.05"), Decimal("2300"))]
    venue = [VenuePosition("1", "EURUSD", Direction.LONG, Decimal("0.2"), Decimal("1.1"), Decimal("1.09"), "a"), VenuePosition("2", "GBPUSD", Direction.LONG, Decimal("0.05"), Decimal("1.26"), Decimal("1.25"), "b"),
             VenuePosition("3", "AUDUSD", Direction.LONG, Decimal("0.1"), Decimal("0.65"), None, "")]
    res = reconcile(ledger, venue, account_verified=True, closed_by_venue_stop={"c"}, owner_closed={"d"})
    counts = res.counts()
    assert counts[ReconciliationClass.MATCH.value] == 1 and counts[ReconciliationClass.VENUE_PARTIAL_CLOSE.value] == 1
    assert counts[ReconciliationClass.VENUE_STOP_HIT.value] == 1 and counts[ReconciliationClass.OWNER_OVERRIDE.value] == 1 and counts[ReconciliationClass.ORPHAN_VENUE_POSITION.value] == 1
    assert res.permit_new_orders is False
    clean = reconcile(ledger[:1], venue[:1], account_verified=True)
    assert clean.permit_new_orders is True
    assert reconcile(ledger[:1], venue[:1], account_verified=False).permit_new_orders is False
    nostop = reconcile([LedgerPosition("a", "EURUSD", Decimal("0.2"), Decimal("1.09"))], [VenuePosition("1", "EURUSD", Direction.LONG, Decimal("0.2"), Decimal("1.1"), None, "a")], account_verified=True)
    assert ReconciliationClass.STOP_MISSING.value in nostop.counts() and not nostop.permit_new_orders


    attributed_but_unrecovered = reconcile(
        [],
        [VenuePosition(
            "existing", "EURUSD", Direction.LONG, Decimal("0.2"),
            Decimal("1.1"), Decimal("1.09"), "known-intent")],
        account_verified=True,
    )
    assert attributed_but_unrecovered.counts()[ReconciliationClass.ORPHAN_VENUE_POSITION.value] == 1
    assert not attributed_but_unrecovered.permit_new_orders


def test_tca_and_review_and_admission():
    from vati.execution import ExecutionReceipt
    rec = ExecutionReceipt("ti", "h", "paper", "FILLED", Decimal("0.18"), Decimal("1.10017"), Decimal("1.10010"), Decimal("1.10012"), Decimal("1.10010"), True, NOW, NOW, spread_at_submit=Decimal("0.00010"), fees=Decimal("1.08")).sealed()
    t = compute_tca(rec, direction=Direction.LONG, qty=Decimal("0.18"), value_per_unit=Decimal("100000"), modelled_cost_pct=Decimal("0.00015"))
    assert t.slippage == Decimal("0.00007") and t.delay_cost == Decimal("0.00002") and t.implementation_shortfall > 0 and t.cost_ratio > 0
    good_loss = review_trade(trade_intent_id="ti", strategy_id="S", entry=Decimal("1.1"), exit_price=Decimal("1.0978"), stop=Decimal("1.0978"), direction_long=True, pnl=Decimal("-39.6"), thesis_correct=False, process_ok=True, exit_reason="VENUE_STOP")
    assert good_loss.outcome is Outcome.GOOD_LOSS and good_loss.polarity == "POSITIVE" and good_loss.r_multiple == Decimal("-1.00")
    bad_win = review_trade(trade_intent_id="ti", strategy_id="S", entry=Decimal("1.1"), exit_price=Decimal("1.1066"), stop=Decimal("1.0978"), direction_long=True, pnl=Decimal("118"), thesis_correct=False, process_ok=False)
    assert bad_win.outcome is Outcome.BAD_WIN and bad_win.polarity == "ANTI_PATTERN" and bad_win.r_multiple == Decimal("3.00")
    assert review_trade(trade_intent_id="t", strategy_id="S", entry=Decimal("1"), exit_price=Decimal("1"), stop=Decimal("0.9"), direction_long=True, pnl=Decimal("0"), thesis_correct=True, process_ok=True, data_ok=False).outcome is Outcome.DATA_FAILURE
    adm = AdmissionLedger()
    adm.propose(bad_win.artifact_hash, knowledge_class="TRADE_EXPERIENCE", proposed_by="vati-trade-review", trust_tier="T0_VAN_TRADING_POLICY")
    adm.quarantine(bad_win.artifact_hash)
    with pytest.raises(AdmissionError, match="evidence"):
        adm.validate(bad_win.artifact_hash, evidence_ref="")
    adm.validate(bad_win.artifact_hash, evidence_ref="review-run-1")
    with pytest.raises(AdmissionError, match="self-admission"):
        adm.admit(bad_win.artifact_hash, admitted_by="vati-trade-review")
    assert adm.admit(bad_win.artifact_hash, admitted_by="vtil-admission-service") is AdmissionState.ADMITTED
    with pytest.raises(AdmissionError):
        adm.reject(bad_win.artifact_hash, reason="x")
    adm.propose("c" * 64, knowledge_class="MARKET_OBSERVATION", proposed_by="hermes", trust_tier="T4_COMMUNITY_SIGNAL")
    adm.quarantine("c" * 64)
    with pytest.raises(AdmissionError):
        adm.admit("c" * 64, admitted_by="svc")  # still QUARANTINED, and T4 without evidence
