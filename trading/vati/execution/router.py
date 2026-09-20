"""Execution Router (Rev 2 §29, Rev 2.1 §E.2 plane 3): the only order sender.

Refuses anything without a sealed APPROVED/REDUCED RiskDecision whose hash it
can recompute for this exact intent; refuses replayed idempotency keys, halted
kill switches, non-order-sending modes, and venues without a heartbeat. If a
venue stop is not confirmed on a filled order it flattens immediately and trips
STOP_REJECTED. Every step is a ledger event."""

from __future__ import annotations

from dataclasses import asdict
from decimal import Decimal
from typing import Callable, Optional

from vati.core.canonical import canonical_hash
from vati.core.events import EventKind, make_event
from vati.core.ledger import Ledger
from vati.execution.base import ExecutionReceipt, OrderCommand, StopMode, VenueAdapter
from vati.execution.protection import ProtectionManager
from vati.observability import metrics
from vati.risk.authority import Decision, RiskDecision
from vati.risk.contracts import KillSwitchTrigger, LossModel, TradeIntent
from vati.risk.governor import KillSwitch
from vati.risk.mandate import TradingMandate

ZERO = Decimal("0")


class RouterError(RuntimeError):
    pass


def recompute_decision_hash(d: RiskDecision) -> str:
    body = d.to_dict(); body.pop("decision_hash", None)
    return canonical_hash(body)


class ExecutionRouter:
    def __init__(self, *, ledger: Ledger, adapters: dict[str, VenueAdapter], kill_switch: KillSwitch, protection: ProtectionManager, producer: str = "vati-execution-router",
                 lease_fence: Optional[Callable[[Optional[int]], bool]] = None) -> None:
        self.ledger, self.adapters, self.kill, self.protection, self.producer = ledger, adapters, kill_switch, protection, producer
        self.lease_fence = lease_fence
        self._seen: set[str] = {e.payload["idempotency_key"] for e in ledger.iter(EventKind.ORDER_COMMAND)}

    def _log(self, kind: EventKind, payload: dict, *, now_ms: int, corr: str, decision_time: Optional[int] = None) -> None:
        self.ledger.append(make_event(kind, self.producer, payload, event_time_ms=now_ms, received_time_ms=now_ms, decision_time_ms=decision_time, correlation_id=corr))

    def execute(self, intent: TradeIntent, decision: RiskDecision, mandate: TradingMandate, *, now_ms: int, stop_mode: StopMode = StopMode.VENUE,
                targets: tuple[Decimal, ...] = (), time_in_force: str = "DAY", entry_type: str = "LIMIT", max_slippage: Optional[Decimal] = None,
                lease_epoch: Optional[int] = None) -> ExecutionReceipt:
        corr = intent.trade_intent_id
        # --- gate chain (fail closed, first failure names the reason) ---
        if self.lease_fence is not None and not self.lease_fence(lease_epoch):
            raise RouterError(f"account runtime lease fence refused epoch {lease_epoch!r}")
        if self.kill.halted:
            raise RouterError(f"kill switch active: {sorted(t.value for t in self.kill.active)}")
        if decision.trade_intent_id != intent.trade_intent_id:
            raise RouterError("decision does not belong to this intent")
        if decision.decision not in (Decision.APPROVED, Decision.REDUCED):
            raise RouterError(f"decision is {decision.decision.value}")
        if recompute_decision_hash(decision) != decision.decision_hash:
            raise RouterError("decision hash does not recompute; refusing")
        if decision.mandate_id != mandate.mandate_id or decision.mandate_version != mandate.version:
            raise RouterError("decision was made under a different mandate")
        if not mandate.sends_orders():
            raise RouterError(f"mode {mandate.mode.value} does not send orders")
        if intent.idempotency_key in self._seen:
            raise RouterError("duplicate idempotency key")
        adapter = self.adapters.get(intent.venue)
        if adapter is None:
            raise RouterError(f"no adapter for venue {intent.venue}")
        hb = adapter.heartbeat(now_ms=now_ms)
        if not hb.connected:
            self.kill.trip(KillSwitchTrigger.VENUE_DISCONNECT, now_ms)
            self._log(EventKind.KILL_SWITCH, {"trigger": "VENUE_DISCONNECT", "venue": intent.venue}, now_ms=now_ms, corr=corr)
            raise RouterError("venue heartbeat failed; kill switch tripped")
        loss_model = LossModel.ILLIQUID_EQUITY if intent.venue in ("zse", "vfex") else (LossModel.FULL_STAKE if intent.stake is not None and intent.stop is None else LossModel.STOP_DISTANCE)
        if loss_model is LossModel.STOP_DISTANCE and intent.stop is None:
            raise RouterError("stop-distance order without protective stop")
        cmd = OrderCommand(
            trade_intent_id=intent.trade_intent_id,
            decision_hash=decision.decision_hash,
            idempotency_key=intent.idempotency_key,
            account_alias=intent.account_alias,
            venue=intent.venue,
            symbol=intent.symbol,
            direction=intent.direction,
            entry_type=entry_type,
            quantity=decision.approved_size,
            entry_price=intent.entry,
            protective_stop=intent.stop,
            stop_mode=StopMode.SOFTWARE if loss_model is LossModel.ILLIQUID_EQUITY else stop_mode,
            loss_model=loss_model,
            targets=targets,
            time_in_force=time_in_force,
            max_slippage=max_slippage,
            strategy_id=intent.strategy_id,
            strategy_version=intent.strategy_version,
            lease_epoch=lease_epoch,
        ).sealed()
        self._seen.add(intent.idempotency_key)
        self._log(EventKind.ORDER_COMMAND, {**asdict(cmd), "direction": cmd.direction.value, "stop_mode": cmd.stop_mode.value, "loss_model": cmd.loss_model.value}, now_ms=now_ms, corr=corr, decision_time=now_ms)
        metrics.inc("vati_orders_sent_total", venue=intent.venue)
        receipt = adapter.submit(cmd, now_ms=now_ms)
        self._log(EventKind.EXECUTION_RECEIPT, {k: (v.value if hasattr(v, "value") else v) for k, v in asdict(receipt).items()}, now_ms=now_ms, corr=corr)
        # --- protection ---
        if receipt.status in ("FILLED", "PARTIAL") and receipt.filled_qty > ZERO:
            if cmd.stop_mode is StopMode.VENUE and not receipt.protective_stop_confirmed:
                flat = adapter.close(receipt.broker_position_id, None, now_ms=now_ms, reason="STOP_REJECTED_FLATTEN")
                self.kill.trip(KillSwitchTrigger.STOP_REJECTED, now_ms)
                self._log(EventKind.KILL_SWITCH, {"trigger": "STOP_REJECTED", "position": receipt.broker_position_id}, now_ms=now_ms, corr=corr)
                self._log(EventKind.EXECUTION_RECEIPT, {k: (v.value if hasattr(v, "value") else v) for k, v in asdict(flat).items()}, now_ms=now_ms, corr=corr)
                metrics.inc("vati_unprotected_flatten_total", venue=intent.venue)
                raise RouterError("protective stop not confirmed; position flattened and kill switch tripped")
            if intent.stop is not None:
                self.protection.register(receipt.broker_position_id, symbol=intent.symbol, direction=intent.direction, entry=receipt.average_fill or intent.entry, stop=intent.stop,
                                         target=targets[0] if targets else None, opened_ms=now_ms, software_stop=(cmd.stop_mode is StopMode.SOFTWARE))
            metrics.inc("vati_fills_total", venue=intent.venue)
        elif receipt.status == "ACCEPTED" and receipt.execution_channel == "OWNER_TICKET":
            self._log(EventKind.OWNER_TICKET, {"ticket": receipt.broker_order_id, "symbol": intent.symbol, "qty": str(decision.approved_size)}, now_ms=now_ms, corr=corr)
        elif receipt.status in ("REJECTED", "UNKNOWN"):
            metrics.inc("vati_rejects_total", venue=intent.venue)
        return receipt

    def apply_exits(self, venue: str, symbol: str, bid: Decimal, ask: Decimal, *, now_ms: int) -> list[ExecutionReceipt]:
        adapter = self.adapters[venue]
        out = []
        for ins in self.protection.on_mark(symbol, bid, ask, now_ms=now_ms):
            if ins.action == "CLOSE":
                r = adapter.close(ins.position_id, None, now_ms=now_ms, reason=ins.reason)
            else:
                r = adapter.modify_stop(ins.position_id, ins.price, now_ms=now_ms)  # type: ignore[arg-type]
            self._log(EventKind.EXECUTION_RECEIPT, {**{k: (v.value if hasattr(v, "value") else v) for k, v in asdict(r).items()}, "exit_action": ins.action, "exit_reason": ins.reason}, now_ms=now_ms, corr=r.trade_intent_id or ins.position_id)
            out.append(r)
        return out
