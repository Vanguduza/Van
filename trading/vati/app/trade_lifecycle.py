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
from vati.cognition.attribution import AttributionEngine, TradeFacts
from vati.lifecycle.envelope import EnvelopeCalculator
from vati.lifecycle.expansion import ProfitExpansionEngine
from vati.lifecycle.family import FamilyMember, FamilyRegistry, MemberRole
from vati.lifecycle.preservation import ActionKind, PreservationEngine
from vati.lifecycle.scale_policy import ScalePolicyRegistry
from vati.lifecycle.trade_health import PositionHealthInputs, TradeHealthEngine
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
    cognition: Optional[object] = None
    admission: AdmissionLedger = field(default_factory=AdmissionLedger)
    entries: dict[str, dict] = field(default_factory=dict)
    reviews: list = field(default_factory=list)
    consecutive_losses: int = 0
    families: FamilyRegistry = field(init=False)
    envelope_calculator: EnvelopeCalculator = field(init=False)
    trade_health: TradeHealthEngine = field(init=False)
    preservation: PreservationEngine = field(init=False)
    expansion: ProfitExpansionEngine = field(init=False)
    scale_policies: ScalePolicyRegistry = field(init=False)
    attribution: AttributionEngine = field(init=False)
    _family_halts: dict[str, tuple[str, ...]] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.families = FamilyRegistry(ledger=self.ledger)
        self.envelope_calculator = EnvelopeCalculator(ledger=self.ledger)
        self.trade_health = TradeHealthEngine(ledger=self.ledger)
        self.preservation = PreservationEngine(ledger=self.ledger)
        self.expansion = ProfitExpansionEngine(ledger=self.ledger)
        self.scale_policies = ScalePolicyRegistry()
        self.attribution = AttributionEngine(ledger=self.ledger)

    @property
    def preservation_blocks_new_risk(self) -> bool:
        return bool(self._family_halts)

    @property
    def preservation_reason(self) -> str:
        return "; ".join(
            f"{family_id}:{','.join(reasons)}"
            for family_id, reasons in sorted(self._family_halts.items())
        )

    def _log(self, kind: EventKind, payload: dict, *, now_ms: int, corr: str) -> None:
        self.ledger.append(make_event(
            kind, "vati-account-lifecycle", payload,
            event_time_ms=now_ms, received_time_ms=now_ms,
            correlation_id=corr,
        ))

    def _has_event(self, kind: EventKind, corr: str) -> bool:
        """True when durable downstream evidence already exists for this intent.

        Exhaust the iterator instead of taking only its first row. PostgresLedger.iter
        closes its read transaction with a rollback after iteration; abandoning the
        generator at the first match would skip that cleanup on the shared authority path.
        """
        return bool(list(self.ledger.iter(kind, correlation_id=corr)))

    @staticmethod
    def _receipt_from_payload(payload: Mapping[str, object]) -> ExecutionReceipt:
        """Reconstruct and verify a durable execution receipt for evidence repair."""
        def dec(name: str, default: str = "0") -> Decimal:
            raw = payload.get(name, default)
            return Decimal(str(raw if raw is not None else default))

        raw_fill = payload.get("average_fill")
        raw_stop = payload.get("protective_stop_price")
        receipt = ExecutionReceipt(
            trade_intent_id=str(payload.get("trade_intent_id") or ""),
            decision_hash=str(payload.get("decision_hash") or ""),
            venue=str(payload.get("venue") or ""),
            status=str(payload.get("status") or ""),
            filled_qty=dec("filled_qty"),
            average_fill=(Decimal(str(raw_fill)) if raw_fill is not None else None),
            decision_price=dec("decision_price"),
            arrival_price=dec("arrival_price"),
            submitted_price=dec("submitted_price"),
            protective_stop_confirmed=bool(payload.get("protective_stop_confirmed")),
            broker_time_unix_ms=int(payload.get("broker_time_unix_ms") or 0),
            received_time_unix_ms=int(payload.get("received_time_unix_ms") or 0),
            execution_channel=str(payload.get("execution_channel") or "ADAPTER"),
            broker_order_id=str(payload.get("broker_order_id") or ""),
            broker_position_id=str(payload.get("broker_position_id") or ""),
            reject_reason=str(payload.get("reject_reason") or ""),
            spread_at_submit=dec("spread_at_submit"),
            fees=dec("fees"),
            protective_stop_price=(
                Decimal(str(raw_stop)) if raw_stop is not None else None),
            receipt_hash=str(payload.get("receipt_hash") or ""),
        )
        expected = receipt.receipt_hash
        sealed = ExecutionReceipt(**{**receipt.__dict__, "receipt_hash": ""}).sealed()
        if expected and sealed.receipt_hash != expected:
            raise ValueError("durable execution receipt hash does not recompute")
        return receipt if expected else sealed

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
        entry_receipts: dict[str, dict] = {}
        for event in self.ledger.iter(EventKind.EXECUTION_RECEIPT):
            iid = str(event.payload.get("trade_intent_id", ""))
            raw_stop = event.payload.get("protective_stop_price")
            if iid and raw_stop is not None:
                latest_stops[iid] = Decimal(str(raw_stop))
            if (
                iid
                and event.payload.get("status") in ("FILLED", "PARTIAL")
                and Decimal(str(event.payload.get("filled_qty") or "0")) > ZERO
                and event.payload.get("average_fill") is not None
                and str(event.payload.get("execution_channel") or "ADAPTER")
                    != "OWNER_TICKET"
                and event.payload.get("decision_hash")
                and not event.payload.get("exit_action")
            ):
                # Router emits one entry receipt per order submission. Keep the
                # first durable entry fact; later receipts for the same intent
                # describe protection/exit lifecycle, not a second entry.
                entry_receipts.setdefault(iid, dict(event.payload))

        tca_cost_ratios: dict[str, Decimal] = {}
        for event in self.ledger.iter(EventKind.TCA_RECORD):
            if event.correlation_id and event.payload.get("cost_ratio") is not None:
                tca_cost_ratios[event.correlation_id] = Decimal(
                    str(event.payload["cost_ratio"]))

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
        applied_owner_tickets = {
            str(event.payload.get("broker_order_id") or "")
            for event in self.ledger.iter(EventKind.EXECUTION_RECEIPT)
            if event.payload.get("execution_channel") == "OWNER_TICKET"
            and event.payload.get("status") in ("OWNER_EXECUTED", "BROKER_CONFIRMED")
            and event.payload.get("broker_order_id")
        }
        pending_sell_by_intent = {
            str(t.get("trade_intent_id") or t.get("correlation_id") or ""): t
            for ticket_id, t in tickets.items()
            if t.get("side") == "SELL"
            and ticket_id not in applied_owner_tickets
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

            family_id = f"family:{iid}"
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
                "opened_ms": opened_ms,
                "best_price": position.entry_price,
                "worst_price": position.entry_price,
                "protective_stop_confirmed": current_stop is not None,
                "family_id": family_id,
            }
            if self.families.for_intent(iid) is None:
                root = FamilyMember(
                    member_id=f"{iid}:root",
                    role=MemberRole.ROOT,
                    quantity=position.quantity,
                    price=position.entry_price,
                    occurred_ms=opened_ms,
                    trade_intent_id=iid,
                    stop=initial_stop,
                )
                family = self.families.open_family(
                    family_id=family_id,
                    account_alias=str(payload.get("account_alias") or ""),
                    symbol=symbol,
                    direction=position.direction,
                    root=root,
                    now_ms=opened_ms,
                    emit=False,
                )
                if current_stop is not None and family.current_stop is not None:
                    tighter = (
                        current_stop > family.current_stop
                        if position.direction is Direction.LONG
                        else current_stop < family.current_stop
                    )
                    if tighter:
                        self.families.tighten_stop(
                            family_id, current_stop, now_ms=opened_ms, emit=False)
                self.families.reconcile(
                    family_id, venue_quantity=position.quantity,
                    now_ms=opened_ms, emit=False)

            cost_ratio = tca_cost_ratios.get(iid)
            if cost_ratio is None and iid in entry_receipts:
                try:
                    receipt = self._receipt_from_payload(entry_receipts[iid])
                    modelled_cost = self.modelled_costs.get(
                        symbol, contract.round_trip_cost_pct)
                    value_per_unit = (
                        contract.value_per_price_unit_per_lot
                        if contract.loss_model is LossModel.STOP_DISTANCE
                        else Decimal("1")
                    )
                    tca = compute_tca(
                        receipt,
                        direction=position.direction,
                        qty=receipt.filled_qty,
                        value_per_unit=value_per_unit,
                        modelled_cost_pct=modelled_cost,
                    )
                    self._log(
                        EventKind.TCA_RECORD,
                        tca.as_dict() | {
                            "recovered_after_restart": True,
                            "source_receipt_hash": receipt.receipt_hash,
                        },
                        now_ms=receipt.received_time_unix_ms or opened_ms,
                        corr=iid,
                    )
                    cost_ratio = tca.cost_ratio
                    tca_cost_ratios[iid] = cost_ratio
                except (ValueError, ArithmeticError):
                    # Position recovery remains authoritative for safety. A
                    # malformed receipt cannot be promoted into synthetic TCA;
                    # absence remains visible and learning is not replayed.
                    cost_ratio = None
            if cost_ratio is not None:
                self.entries[iid]["cost_ratio"] = cost_ratio

            restored.append(iid)
        return tuple(sorted(restored)), tuple(sorted(unresolved))

    def adopt_owner_buy_confirmation(
        self,
        receipt: ExecutionReceipt,
        *,
        order_payload: Mapping[str, object],
    ) -> None:
        """Turn a signed owner BUY confirmation into lifecycle position truth.

        Replay is crash-safe: the in-memory position/protection state is always
        reconstructed, while TCA is appended only when no durable TCA_RECORD
        exists for the intent.
        """
        symbol = str(order_payload["symbol"]).upper()
        contract = self.contracts[symbol]
        stop_raw = order_payload.get("protective_stop")
        stop = Decimal(str(stop_raw)) if stop_raw is not None else None
        targets = tuple(
            Decimal(str(v)) for v in (order_payload.get("targets") or ())
        )
        direction = Direction(str(order_payload.get("direction", "LONG")))
        entry_price = receipt.average_fill or Decimal(str(order_payload["entry_price"]))
        self.entries[receipt.trade_intent_id] = {
            "symbol": symbol,
            "entry": entry_price,
            "stop": stop,
            "direction": direction,
            "strategy_id": str(order_payload.get("strategy_id", "")),
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
                direction=direction,
                entry=entry_price,
                stop=stop,
                target=targets[0] if targets else None,
                opened_ms=receipt.received_time_unix_ms,
                software_stop=True,
            )

        if (
            receipt.filled_qty <= ZERO
            or receipt.average_fill is None
            or self._has_event(EventKind.TCA_RECORD, receipt.trade_intent_id)
        ):
            return

        modelled_cost = self.modelled_costs.get(
            symbol, contract.round_trip_cost_pct)
        tca = compute_tca(
            receipt,
            direction=direction,
            qty=receipt.filled_qty,
            value_per_unit=Decimal("1"),
            modelled_cost_pct=modelled_cost,
        )
        owner_tca_payload = tca.as_dict()
        if self.learning is not None:
            owner_tca_payload |= {
                "learning_environment": self.learning.environment.value,
                "broker": self.learning.broker,
                "symbol": symbol,
                "session": "OWNER_TICKET",
                "event_window": "QUIET",
                "rejected": False,
            }
        self._log(
            EventKind.TCA_RECORD, owner_tca_payload,
            now_ms=receipt.received_time_unix_ms,
            corr=receipt.trade_intent_id,
        )
        self.entries[receipt.trade_intent_id]["cost_ratio"] = tca.cost_ratio
        if self.learning is not None:
            state = self.engines_by_symbol.get(symbol)
            # Owner-ticket confirmation may happen long after the originating
            # market state. We still feed execution-cost learning because its
            # inputs are receipt-derived and do not require reconstructing a
            # stale strategy state.
            self.learning.on_tca(
                symbol=symbol,
                session="OWNER_TICKET",
                event_window="QUIET",
                cost_ratio=tca.cost_ratio,
                slippage=tca.slippage,
            )
            engine = self.engines_by_symbol.get(symbol)
            if engine is not None:
                engine.m.broker_liquidity[symbol] = self.learning.broker_liquidity(symbol)

    def adopt_owner_sell_confirmation(
        self,
        receipt: ExecutionReceipt,
        *,
        exit_reason: str,
        now_ms: int,
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

        if not self._has_event(EventKind.TRADE_REVIEW, receipt.trade_intent_id):
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
        entry_price = receipt.average_fill or intent.entry
        family_id = f"family:{intent.trade_intent_id}"
        self.entries[intent.trade_intent_id] = {
            "symbol": intent.symbol,
            "entry": entry_price,
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
            "opened_ms": receipt.received_time_unix_ms,
            "best_price": entry_price,
            "worst_price": entry_price,
            "protective_stop_confirmed": bool(
                receipt.protective_stop_confirmed or software_stop),
            "fees": receipt.fees,
            "family_id": family_id,
        }
        if not filled:
            return

        if self.families.for_intent(intent.trade_intent_id) is None:
            self.families.open_family(
                family_id=family_id,
                account_alias=intent.account_alias,
                symbol=intent.symbol,
                direction=intent.direction,
                root=FamilyMember(
                    member_id=f"{intent.trade_intent_id}:root",
                    role=MemberRole.ROOT,
                    quantity=receipt.filled_qty,
                    price=entry_price,
                    occurred_ms=receipt.received_time_unix_ms,
                    trade_intent_id=intent.trade_intent_id,
                    stop=intent.stop,
                ),
                now_ms=receipt.received_time_unix_ms,
            )

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
        tca_payload = tca.as_dict()
        if self.learning is not None:
            tca_payload |= {
                "learning_environment": self.learning.environment.value,
                "broker": self.learning.broker,
                "symbol": intent.symbol,
                "session": state.session.value,
                "event_window": state.event_window.value,
                "rejected": False,
            }
        self._log(
            EventKind.TCA_RECORD, tca_payload,
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

    def _supervise_open_families(self, symbol: str, bid: Decimal, ask: Decimal,
                                 *, now_ms: int) -> None:
        """Run family -> health -> envelope -> preservation -> expansion in order."""
        try:
            equity = self.adapter.sync_account().equity
        except Exception:
            equity = ZERO

        for intent_id, row in list(self.entries.items()):
            if not row.get("open") or str(row.get("symbol", "")).upper() != symbol.upper():
                continue
            family = self.families.for_intent(intent_id)
            if family is None or not family.is_open:
                continue
            direction = row["direction"]
            mark = bid if direction is Direction.LONG else ask
            row["best_price"] = (
                max(Decimal(str(row.get("best_price", mark))), mark)
                if direction is Direction.LONG
                else min(Decimal(str(row.get("best_price", mark))), mark)
            )
            row["worst_price"] = (
                min(Decimal(str(row.get("worst_price", mark))), mark)
                if direction is Direction.LONG
                else max(Decimal(str(row.get("worst_price", mark))), mark)
            )

            position_id = str(row.get("broker_position_id") or "")
            rule = self.protection.rules.get(position_id)
            current_stop = rule.stop if rule is not None else row.get("stop")
            if current_stop is not None and family.current_stop is not None:
                current_stop = Decimal(str(current_stop))
                tighter = (
                    current_stop > family.current_stop
                    if direction is Direction.LONG
                    else current_stop < family.current_stop
                )
                if tighter:
                    self.families.tighten_stop(
                        family.family_id, current_stop, now_ms=now_ms)
            if family.original_stop is None:
                self._family_halts[family.family_id] = ("RISK_UNKNOWN",)
                continue

            health = self.trade_health.assess(PositionHealthInputs(
                trade_intent_id=intent_id,
                symbol=symbol,
                direction=direction,
                entry_price=Decimal(str(row["entry"])),
                current_price=mark,
                original_stop=family.original_stop,
                current_stop=(None if current_stop is None else Decimal(str(current_stop))),
                has_confirmed_stop=bool(
                    row.get("protective_stop_confirmed")
                    or (rule is not None and rule.software_stop)),
                opened_ms=int(row.get("opened_ms") or now_ms),
                now_ms=now_ms,
                expected_horizon_ms=int(row.get("expected_horizon_ms") or 0),
                worst_price=Decimal(str(row["worst_price"])),
                best_price=Decimal(str(row["best_price"])),
                mark_age_ms=0,
                spread=max(ZERO, ask - bid),
            ))
            contract = self.contracts[symbol.upper()]
            value_per_unit = (
                contract.value_per_price_unit_per_lot
                if contract.loss_model is LossModel.STOP_DISTANCE else Decimal("1")
            )
            envelope = self.envelope_calculator.compute(
                family, mark=mark, value_per_price_unit=value_per_unit,
                equity=equity, now_ms=now_ms)
            action = self.preservation.evaluate(
                family=family, health=health, envelope=envelope,
                mark=mark, now_ms=now_ms)

            if action.blocks_new_risk:
                self._family_halts[family.family_id] = action.reasons or (action.kind.value,)
            else:
                self._family_halts.pop(family.family_id, None)

            if position_id and action.kind in (
                ActionKind.TIGHTEN_STOP, ActionKind.PARTIAL_CLOSE, ActionKind.FULL_CLOSE
            ):
                quantity = None
                if action.kind is ActionKind.PARTIAL_CLOSE:
                    quantity = family.net_quantity * Decimal(str(action.close_fraction or ZERO))
                    if quantity <= ZERO:
                        quantity = None
                receipt = self.router.apply_preservation(
                    self.adapter.venue,
                    position_id=position_id,
                    trade_intent_id=intent_id,
                    action=action.kind.value,
                    now_ms=now_ms,
                    new_stop=action.new_stop,
                    quantity=quantity,
                    reason="REV51_" + (action.reasons[0] if action.reasons else action.kind.value),
                )
                if action.kind is ActionKind.TIGHTEN_STOP and action.new_stop is not None:
                    if receipt is None or receipt.status not in (
                        "REJECTED", "CANCELLED", "EXPIRED", "UNKNOWN"
                    ):
                        self.families.tighten_stop(
                            family.family_id, action.new_stop, now_ms=now_ms)
                        row["stop"] = action.new_stop
                elif receipt is not None and receipt.status in (
                    "FILLED", "OWNER_EXECUTED", "BROKER_CONFIRMED"
                ):
                    if action.kind is ActionKind.PARTIAL_CLOSE:
                        closed_qty = min(receipt.filled_qty, family.net_quantity)
                        if closed_qty > ZERO and receipt.average_fill is not None:
                            self.families.apply(
                                family.family_id,
                                FamilyMember(
                                    member_id=f"{intent_id}:partial:{now_ms}",
                                    role=MemberRole.PARTIAL_EXIT,
                                    quantity=closed_qty,
                                    price=receipt.average_fill,
                                    occurred_ms=now_ms,
                                    trade_intent_id=intent_id,
                                ),
                                now_ms=now_ms,
                            )
                            row["quantity"] = max(
                                ZERO, Decimal(str(row.get("quantity", ZERO))) - closed_qty)
                    else:
                        self._on_close(
                            intent_id, receipt.average_fill, action.kind.value, now_ms)
                        continue

            policy = self.scale_policies.policy_for(str(row.get("strategy_id") or ""))
            root_qty = next(
                (m.quantity for m in family.members if m.role is MemberRole.ROOT), ZERO)
            self.expansion.evaluate(
                family=family,
                strategy_id=str(row.get("strategy_id") or ""),
                policy=policy,
                health=health,
                envelope=envelope,
                preservation=action,
                root_quantity=root_qty,
                last_scale_ms=None,
                in_event_window=False,
                now_ms=now_ms,
            )

    def mark_bar(self, symbol: str, bar: Bar, *, now_ms: int) -> None:
        """Apply the same deterministic OHLC mark sequence as SessionRunner."""
        contract = self.contracts[symbol.upper()]
        half = contract.tick_size
        for px in (bar.open, bar.low, bar.high, bar.close):
            self.mark(symbol, px - half, px + half, now_ms=now_ms)

    def mark(self, symbol: str, bid: Decimal, ask: Decimal, *, now_ms: int) -> None:
        self._supervise_open_families(symbol, bid, ask, now_ms=now_ms)
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
        family = self.families.for_intent(intent_id)
        if family is not None and family.net_quantity > ZERO:
            self.families.apply(
                family.family_id,
                FamilyMember(
                    member_id=f"{intent_id}:exit:{now_ms}",
                    role=MemberRole.FULL_EXIT,
                    quantity=family.net_quantity,
                    price=exit_price,
                    occurred_ms=now_ms,
                    trade_intent_id=intent_id,
                ),
                now_ms=now_ms,
            )
            self._family_halts.pop(family.family_id, None)
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

        shadow_entry = None
        if self.cognition is not None and hasattr(self.cognition, "resolve_trade"):
            shadow_entry = self.cognition.resolve_trade(
                intent_id, actual_r=review.r_multiple, now_ms=now_ms)

        contract = self.contracts.get(str(entry["symbol"]).upper())
        stop = entry.get("stop")
        qty = Decimal(str(entry.get("quantity", ZERO)))
        if (
            contract is not None
            and stop is not None
            and qty > ZERO
            and contract.loss_model is not LossModel.FULL_STAKE
        ):
            risk_distance = abs(
                Decimal(str(entry["entry"])) - Decimal(str(stop)))
            value_per_unit = (
                contract.value_per_price_unit_per_lot
                if contract.loss_model is LossModel.STOP_DISTANCE
                else Decimal("1")
            )
            money_risk = risk_distance * qty * value_per_unit
            if money_risk > ZERO:
                self.attribution.attribute(
                    TradeFacts(
                        trade_intent_id=intent_id,
                        symbol=str(entry["symbol"]),
                        strategy_id=str(entry["strategy_id"]),
                        direction=entry["direction"],
                        quantity=qty,
                        decision_price=Decimal(str(entry["decision_price"])),
                        fill_price=Decimal(str(entry["entry"])),
                        exit_price=exit_price,
                        money_risk=money_risk,
                        costs=Decimal(str(entry.get("fees", ZERO))),
                        opened_ms=int(entry.get("opened_ms") or 0),
                        closed_ms=now_ms,
                    ),
                    shadow_entry=shadow_entry,
                    now_ms=now_ms,
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
                        "capsule": new.data,
                        "by": "vati-learning",
                        "authority": "AUTOMATIC_DEMOTION_ONLY",
                    },
                    now_ms=now_ms,
                    corr=intent_id,
                )


__all__ = ["AccountTradeLifecycle", "STRATEGY_LEARNING_OUTCOMES"]
