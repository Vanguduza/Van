"""Account-scoped post-entry lifecycle for VATI multi-instrument runtimes.

Allocation decides *which* candidate may reach RiskAuthority.  This module owns
what happens after an approved intent reaches the router: entry accounting, TCA,
mark-driven protection, trade review, VTIL proposal and reduce-only learning.

It intentionally composes the same primitives used by DecisionCycle rather than
implementing a second risk or execution policy.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from decimal import Decimal
from typing import Mapping, Optional, Sequence

from vati.core.events import EventKind, make_event
from vati.execution.base import ExecutionReceipt, VenueAdapter
from vati.execution.protection import ProtectionManager
from vati.execution.review import Outcome, review_trade
from vati.execution.router import ExecutionRouter
from vati.execution.tca import compute_tca
from vati.learning.hooks import LearningHooks, to_payload
from vati.market_data.bars import Bar
from vati.observability import metrics
from vati.risk.contracts import Direction, LossModel, StrategyState, SymbolContract, TradeIntent
from vati.arbiter.strategy_arbiter import ACTIVE_STATES
from vati.vtil import AdmissionLedger

ZERO = Decimal("0")
STRATEGY_LEARNING_OUTCOMES = frozenset({
    Outcome.GOOD_WIN, Outcome.GOOD_LOSS, Outcome.BAD_WIN, Outcome.BAD_LOSS,
})


@dataclass
class AccountTradeLifecycle:
    ledger: object
    adapter: VenueAdapter
    router: ExecutionRouter
    protection: ProtectionManager
    contracts: Mapping[str, SymbolContract]
    engines_by_symbol: Mapping[str, object]
    modelled_costs: Mapping[str, Decimal] = field(default_factory=dict)
    learning: Optional[LearningHooks] = None
    admission: AdmissionLedger = field(default_factory=AdmissionLedger)
    entries: dict[str, dict] = field(default_factory=dict)
    reviews: list = field(default_factory=list)
    consecutive_losses: int = 0

    def _log(self, kind: EventKind, payload: dict, *, now_ms: int, corr: str) -> None:
        self.ledger.append(make_event(
            kind, "vati-account-lifecycle", payload,
            event_time_ms=now_ms, received_time_ms=now_ms,
            correlation_id=corr,
        ))

    def recover_from_venue(self) -> tuple[tuple[str, ...], tuple[str, ...]]:
        """Rebuild open entry/protection state from venue plus ledger provenance.

        A venue trade_intent_id is not sufficient by itself. Recovery needs
        the exact ORDER_COMMAND that created it; otherwise the position remains
        unresolved and reconciliation blocks new risk.
        """
        commands: dict[str, tuple[dict, int]] = {}
        for event in self.ledger.iter(EventKind.ORDER_COMMAND):
            iid = str(event.payload.get("trade_intent_id", ""))
            if iid:
                commands[iid] = (dict(event.payload), event.event_time_ms)

        latest_stops: dict[str, Decimal] = {}
        for event in self.ledger.iter(EventKind.EXECUTION_RECEIPT):
            iid = str(event.payload.get("trade_intent_id", ""))
            raw_stop = event.payload.get("protective_stop_price")
            if iid and raw_stop is not None:
                latest_stops[iid] = Decimal(str(raw_stop))

        tickets: dict[str, dict] = {}
        for event in self.ledger.iter(EventKind.OWNER_TICKET):
            ticket_id = str(event.payload.get("ticket") or "")
            if not ticket_id:
                continue
            if event.payload.get("action") == "CONFIRMED":
                tickets.setdefault(ticket_id, {})["confirmed"] = True
                continue
            tickets[ticket_id] = {
                **dict(event.payload),
                "confirmed": False,
                "correlation_id": event.correlation_id,
            }
        pending_sell_by_intent = {
            str(t.get("trade_intent_id") or t.get("correlation_id") or ""): t
            for t in tickets.values()
            if t.get("side") == "SELL" and not t.get("confirmed")
        }

        restored: list[str] = []
        unresolved: list[str] = []
        for position in self.adapter.positions():
            iid = str(position.trade_intent_id or "")
            joined = commands.get(iid)
            if not iid or joined is None:
                unresolved.append(position.position_id)
                continue
            payload, opened_ms = joined
            symbol = position.symbol.upper()
            contract = self.contracts.get(symbol)
            if contract is None:
                unresolved.append(iid)
                continue

            raw_initial_stop = payload.get("protective_stop")
            initial_stop = (
                Decimal(str(raw_initial_stop))
                if raw_initial_stop is not None else None
            )
            software_stop = str(payload.get("stop_mode", "")) == "SOFTWARE"
            current_stop = (
                position.stop_price
                or latest_stops.get(iid)
                or initial_stop
            )
            targets = tuple(
                Decimal(str(v)) for v in (payload.get("targets") or ())
            )

            if position.loss_model in (
                LossModel.STOP_DISTANCE, LossModel.ILLIQUID_EQUITY
            ):
                if initial_stop is None or current_stop is None:
                    unresolved.append(iid)
                    continue
                try:
                    self.protection.restore(
                        position.position_id,
                        symbol=symbol,
                        direction=position.direction,
                        entry=position.entry_price,
                        initial_stop=initial_stop,
                        current_stop=current_stop,
                        target=targets[0] if targets else None,
                        opened_ms=opened_ms,
                        software_stop=software_stop,
                    )
                except Exception:
                    unresolved.append(iid)
                    continue
                if iid in pending_sell_by_intent:
                    self.protection.mark_close_pending(position.position_id)

            self.entries[iid] = {
                "symbol": symbol,
                "entry": position.entry_price,
                "stop": current_stop,
                "direction": position.direction,
                "strategy_id": str(payload.get("strategy_id", "")),
                "cost_pct": self.modelled_costs.get(
                    symbol, contract.round_trip_cost_pct),
                "decision_price": Decimal(str(
                    payload.get("entry_price", position.entry_price))),
                "quantity": position.quantity,
                "software_stop": software_stop,
                "broker_position_id": position.position_id,
                "open": True,
                "pending": False,
                "recovered": True,
            }
            restored.append(iid)
        return tuple(sorted(restored)), tuple(sorted(unresolved))

    def adopt_owner_buy_confirmation(
        self,
        receipt: ExecutionReceipt,
        *,
        order_payload: Mapping[str, object],
    ) -> None:
        """Turn a signed owner BUY confirmation into lifecycle position truth."""
        symbol = str(order_payload["symbol"]).upper()
        contract = self.contracts[symbol]
        stop_raw = order_payload.get("protective_stop")
        stop = Decimal(str(stop_raw)) if stop_raw is not None else None
        targets = tuple(
            Decimal(str(v)) for v in (order_payload.get("targets") or ())
        )
        strategy_id = str(order_payload.get("strategy_id", ""))
        self.entries[receipt.trade_intent_id] = {
            "symbol": symbol,
            "entry": receipt.average_fill or Decimal(str(order_payload["entry_price"])),
            "stop": stop,
            "direction": Direction(str(order_payload.get("direction", "LONG"))),
            "strategy_id": strategy_id,
            "cost_pct": self.modelled_costs.get(symbol, contract.round_trip_cost_pct),
            "decision_price": Decimal(str(order_payload["entry_price"])),
            "quantity": receipt.filled_qty,
            "software_stop": True,
            "broker_position_id": receipt.broker_position_id,
            "open": receipt.filled_qty > ZERO,
            "pending": False,
        }
        if stop is not None and receipt.broker_position_id:
            self.protection.register(
                receipt.broker_position_id,
                symbol=symbol,
                direction=Direction(str(order_payload.get("direction", "LONG"))),
                entry=receipt.average_fill or Decimal(str(order_payload["entry_price"])),
                stop=stop,
                target=targets[0] if targets else None,
                opened_ms=receipt.received_time_unix_ms,
                software_stop=True,
            )
        if receipt.filled_qty > ZERO and receipt.average_fill is not None:
            tca = compute_tca(
                receipt,
                direction=Direction(str(order_payload.get("direction", "LONG"))),
                qty=receipt.filled_qty,
                value_per_unit=Decimal("1"),
                modelled_cost_pct=self.modelled_costs.get(
                    symbol, contract.round_trip_cost_pct),
            )
            self._log(
                EventKind.TCA_RECORD, tca.as_dict(),
                now_ms=receipt.received_time_unix_ms,
                corr=receipt.trade_intent_id,
            )
            self.entries[receipt.trade_intent_id]["cost_ratio"] = tca.cost_ratio

    def adopt_owner_sell_confirmation(
        self,
        receipt: ExecutionReceipt,
        *,
        exit_reason: str,
        now_ms: int,
        emit_review: bool = True,
    ) -> None:
        """Apply an owner SELL fill without treating a partial fill as closed."""
        remaining = [
            p for p in self.adapter.positions()
            if p.trade_intent_id == receipt.trade_intent_id
        ]
        if remaining:
            row = self.entries.get(receipt.trade_intent_id)
            if row is not None:
                row["quantity"] = sum((p.quantity for p in remaining), ZERO)
                row["open"] = True
            if receipt.broker_position_id:
                self.protection.close_failed(receipt.broker_position_id)
            return

        if emit_review:
            self._on_close(
                receipt.trade_intent_id,
                receipt.average_fill,
                exit_reason,
                now_ms,
            )
        else:
            self.entries.pop(receipt.trade_intent_id, None)
        if receipt.broker_position_id:
            self.protection.close_confirmed(receipt.broker_position_id)

    def record_entry(
        self,
        *,
        intent: TradeIntent,
        receipt: ExecutionReceipt,
        state,
        modelled_cost_pct: Decimal,
        software_stop: bool,
    ) -> None:
        """Record the router result and feed filled entries into TCA/learning."""
        if receipt.status not in ("FILLED", "PARTIAL", "ACCEPTED", "OWNER_EXECUTED"):
            return
        filled = receipt.filled_qty > ZERO and receipt.average_fill is not None
        self.entries[intent.trade_intent_id] = {
            "symbol": intent.symbol,
            "entry": receipt.average_fill or intent.entry,
            "stop": intent.stop,
            "direction": intent.direction,
            "strategy_id": intent.strategy_id,
            "cost_pct": modelled_cost_pct,
            "decision_price": intent.entry,
            "quantity": receipt.filled_qty,
            "software_stop": software_stop,
            "broker_position_id": receipt.broker_position_id,
            "open": filled,
            "pending": not filled,
        }
        if not filled:
            return

        contract = self.contracts[intent.symbol.upper()]
        value_per_unit = (
            contract.value_per_price_unit_per_lot
            if contract.loss_model is LossModel.STOP_DISTANCE
            else Decimal("1")
        )
        tca = compute_tca(
            receipt,
            direction=intent.direction,
            qty=receipt.filled_qty,
            value_per_unit=value_per_unit,
            modelled_cost_pct=modelled_cost_pct,
        )
        self._log(
            EventKind.TCA_RECORD, tca.as_dict(),
            now_ms=receipt.received_time_unix_ms,
            corr=intent.trade_intent_id,
        )
        self.entries[intent.trade_intent_id]["cost_ratio"] = tca.cost_ratio
        if self.learning is not None:
            self.learning.on_tca(
                symbol=intent.symbol,
                session=state.session.value,
                event_window=state.event_window.value,
                cost_ratio=tca.cost_ratio,
                slippage=tca.slippage,
            )
            engine = self.engines_by_symbol.get(intent.symbol.upper())
            if engine is not None:
                engine.m.broker_liquidity[intent.symbol] = self.learning.broker_liquidity(
                    intent.symbol)

    def mark_bar(self, symbol: str, bar: Bar, *, now_ms: int) -> None:
        """Apply the same deterministic OHLC mark sequence as SessionRunner."""
        contract = self.contracts[symbol.upper()]
        half = contract.tick_size
        for px in (bar.open, bar.low, bar.high, bar.close):
            self.mark(symbol, px - half, px + half, now_ms=now_ms)

    def mark(self, symbol: str, bid: Decimal, ask: Decimal, *, now_ms: int) -> None:
        receipts = list(self.router.apply_exits(
            self.adapter.venue, symbol, bid, ask, now_ms=now_ms))
        if hasattr(self.adapter, "mark"):
            receipts += self.adapter.mark(symbol, bid, ask, now_ms=now_ms)  # type: ignore[attr-defined]
        for receipt in receipts:
            if (
                receipt.status == "FILLED"
                and receipt.trade_intent_id in self.entries
                and receipt.reject_reason not in ("TRAIL", "BREAK_EVEN")
            ):
                self._on_close(
                    receipt.trade_intent_id,
                    receipt.average_fill,
                    receipt.reject_reason,
                    now_ms,
                )
                self.protection.forget(receipt.broker_position_id)

    def _realised_pnl(self, entry: dict, exit_price: Decimal) -> tuple[Decimal, bool]:
        closed = getattr(self.adapter, "closed", None)
        if closed:
            for row in reversed(closed):
                if row.get("intent") == entry.get("trade_intent_id"):
                    return Decimal(str(row["pnl"])), True

        symbol = str(entry["symbol"]).upper()
        contract = self.contracts.get(symbol)
        qty = Decimal(str(entry.get("quantity", ZERO)))
        if contract is None or qty <= ZERO:
            return ZERO, False
        if contract.loss_model is LossModel.FULL_STAKE:
            # Fixed-payout products need venue settlement, not a linear price proxy.
            return ZERO, False
        sign = Decimal("1") if entry["direction"] is Direction.LONG else Decimal("-1")
        return (
            (exit_price - Decimal(str(entry["entry"])))
            * sign
            * qty
            * contract.value_per_price_unit_per_lot,
            True,
        )

    def _on_close(
        self,
        intent_id: str,
        exit_price: Optional[Decimal],
        reason: str,
        now_ms: int,
    ) -> None:
        entry = self.entries.pop(intent_id, None)
        if entry is None or exit_price is None:
            return
        entry["trade_intent_id"] = intent_id
        pnl, pnl_known = self._realised_pnl(entry, exit_price)
        if pnl_known:
            self.consecutive_losses = self.consecutive_losses + 1 if pnl < ZERO else 0

        review = review_trade(
            trade_intent_id=intent_id,
            strategy_id=entry["strategy_id"],
            entry=entry["entry"],
            exit_price=exit_price,
            stop=entry["stop"] or entry["entry"],
            direction_long=entry["direction"] is Direction.LONG,
            pnl=pnl,
            thesis_correct=pnl_known and pnl > ZERO,
            process_ok=True,
            broker_ok=pnl_known,
            exit_reason=reason,
        )
        self.reviews.append(review)
        self._log(
            EventKind.TRADE_REVIEW,
            {
                k: (
                    v.value if hasattr(v, "value")
                    else str(v) if isinstance(v, Decimal)
                    else list(v) if isinstance(v, tuple)
                    else v
                )
                for k, v in asdict(review).items()
            },
            now_ms=now_ms,
            corr=intent_id,
        )
        self.admission.propose(
            review.artifact_hash,
            knowledge_class="TRADE_EXPERIENCE",
            proposed_by=review.proposed_by,
            trust_tier="T0_VAN_TRADING_POLICY",
        )
        metrics.inc("vati_trades_closed_total", outcome=review.outcome.value)

        if (
            self.learning is not None
            and review.outcome in STRATEGY_LEARNING_OUTCOMES
        ):
            self._learn(
                intent_id,
                review,
                Decimal(str(entry.get("cost_ratio", "1"))),
                now_ms,
            )

    def _learn(self, intent_id: str, review, cost_ratio: Decimal, now_ms: int) -> None:
        assert self.learning is not None
        episode, adjustment = self.learning.on_review(
            self.ledger,
            trade_intent_id=intent_id,
            strategy_id=review.strategy_id,
            r_multiple=review.r_multiple,
            process_ok=review.process_ok,
            cost_ratio=cost_ratio,
        )
        if episode is not None:
            self._log(
                EventKind.TRADE_EXPERIENCE_ARTIFACT,
                to_payload(episode),
                now_ms=now_ms,
                corr=intent_id,
            )
            self.admission.propose(
                episode.artifact_hash,
                knowledge_class="TRADE_EXPERIENCE",
                proposed_by="vati-learning",
                trust_tier="T0_VAN_TRADING_POLICY",
            )
        if adjustment is None:
            return

        # Every per-symbol engine carrying this strategy receives the same
        # reduce-only health view and automatic demotion.
        for engine in self.engines_by_symbol.values():
            try:
                capsule = engine.registry.get(review.strategy_id)
            except KeyError:
                continue
            engine.m.capsule_health[review.strategy_id] = adjustment.multiplier
            if not adjustment.demote_to:
                continue
            target = (
                StrategyState.SHADOW
                if capsule.state in (
                    StrategyState.LIMITED_LIVE,
                    StrategyState.CERTIFIED_LIVE,
                )
                else StrategyState.DEGRADED
            )
            if capsule.state in ACTIVE_STATES and capsule.state is not target:
                new = engine.registry.demote(
                    review.strategy_id,
                    target,
                    reason=(
                        f"learning health {adjustment.multiplier}: "
                        + "; ".join(
                            self.learning.health.verdict(review.strategy_id).reasons)
                    ),
                )
                self.learning.demotions.append((review.strategy_id, target.value))
                self._log(
                    EventKind.CAPSULE_STATE,
                    {
                        "strategy_id": review.strategy_id,
                        "from": capsule.state.value,
                        "to": target.value,
                        "capsule_hash": new.capsule_hash,
                        "supersedes": capsule.capsule_hash,
                        "by": "vati-learning",
                        "authority": "AUTOMATIC_DEMOTION_ONLY",
                    },
                    now_ms=now_ms,
                    corr=intent_id,
                )


__all__ = ["AccountTradeLifecycle", "STRATEGY_LEARNING_OUTCOMES"]
