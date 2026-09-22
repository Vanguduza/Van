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

from vati.core.canonical import canonical_hash
from vati.core.events import EventKind, make_event
from vati.execution.base import ExecutionReceipt, VenueAdapter
from vati.execution.protection import ProtectionManager
from vati.execution.review import Outcome, review_trade
from vati.execution.router import ExecutionRouter
from vati.execution.tca import compute_tca
from vati.learning.hooks import LearningHooks, to_payload
from vati.lifecycle.envelope import EnvelopeCalculator
from vati.lifecycle.expansion import ProfitExpansionEngine
from vati.lifecycle.family import FamilyMember, FamilyRegistry, MemberRole
from vati.lifecycle.preservation import ActionKind, PreservationEngine
from vati.lifecycle.scale_policy import (
    Adjustment, AdjustmentPolicyRegistry, PositionAdjustmentEngine, ScalePolicyRegistry,
)
from vati.lifecycle.thesis import (
    ThesisEngine, ThesisInputs, ThesisState, thesis_from_capsule,
)
from vati.lifecycle.trade_health import PositionHealthInputs, TradeHealthEngine
from vati.cognition.attribution import (
    AttributionEngine, DecisionQualityInputs, DecisionQualityLedger, TradeFacts,
)
from vati.learning.episodes import LessonStore, lesson_from_verdict
from vati.market_data.bars import Bar
from vati.observability import metrics
from vati.risk.contracts import Direction, LossModel, StrategyState, SymbolContract, TradeIntent
from vati.risk.serde import intent_to_dict, snapshot_to_dict
from vati.arbiter.strategy_arbiter import ACTIVE_STATES
from vati.vtil import AdmissionLedger

ZERO = Decimal("0")
ONE = Decimal("1")
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
    #: GAP-F-003. Active-trade intelligence. All optional so an existing
    #: deployment keeps its behaviour: with no authority, mandate or news
    #: source the thesis is still sealed and assessed (it is derived from facts
    #: the trade already carries), and size-changing adjustments are refused
    #: rather than attempted without a gate.
    authority: Optional[object] = None
    mandate: Optional[object] = None
    news: Optional[object] = None
    #: Builds and submits the delta order for an approved ADD. Injected by the
    #: runtime that owns the execution policy/route plumbing, so this module
    #: never assembles a second execution path. `ExecutionRouter.execute`
    #: remains the only caller of `adapter.submit` (INV-EXEC-001).
    execute_add_fn: Optional[object] = None
    #: (symbol) -> the current MarketState, for regime/structure/volatility.
    market_state_fn: Optional[object] = None
    #: (symbol) -> correlation multiplier in [0, 1] from risk/dependency.
    correlation_fn: Optional[object] = None
    #: (symbol) -> a RiskSnapshot for the delta intent.
    snapshot_fn: Optional[object] = None
    thesis: ThesisEngine = field(init=False)
    adjustments: PositionAdjustmentEngine = field(init=False)
    adjustment_policies: AdjustmentPolicyRegistry = field(init=False)
    decision_quality: DecisionQualityLedger = field(init=False)
    lessons: LessonStore = field(init=False)
    proposals: list = field(default_factory=list)
    _delta_intent_cache: dict = field(default_factory=dict)
    _family_halts: dict[str, tuple[str, ...]] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.families = FamilyRegistry(ledger=self.ledger)
        self.envelope_calculator = EnvelopeCalculator(ledger=self.ledger)
        self.trade_health = TradeHealthEngine(ledger=self.ledger)
        self.preservation = PreservationEngine(ledger=self.ledger)
        self.expansion = ProfitExpansionEngine(ledger=self.ledger)
        self.scale_policies = ScalePolicyRegistry()
        self.attribution = AttributionEngine(ledger=self.ledger)
        self.thesis = ThesisEngine(ledger=self.ledger)
        self.adjustment_policies = AdjustmentPolicyRegistry()
        self.adjustments = PositionAdjustmentEngine(
            ledger=self.ledger, policies=self.adjustment_policies)
        self.decision_quality = DecisionQualityLedger(ledger=self.ledger)
        self.lessons = LessonStore(ledger=self.ledger)

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
        decision=None,
        targets: tuple = (),
        expected_horizon_ms: int = 0,
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

        self._seal_thesis(
            intent=intent, receipt=receipt, state=state, decision=decision,
            targets=tuple(targets), expected_horizon_ms=expected_horizon_ms,
            entry_price=entry_price)

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

    # ------------------------------------------------- active-trade intelligence
    def _seal_thesis(self, *, intent: TradeIntent, receipt: ExecutionReceipt, state,
                     decision, targets: tuple, expected_horizon_ms: int,
                     entry_price: Decimal) -> None:
        """Write down why this position exists, before anything can rewrite it.

        GAP-F-003. Without this the position carries a price and a stop and no
        claim, so no later cycle can ask whether the reason is still there and
        the owner's "why is my trade moving" has no answer but the price.

        The thesis is sealed at approval and never edited (INV-REPLAY-001). It
        also carries `original_approved_risk_pct`, which is the ceiling every
        later ADD is measured against — recorded here, at the only moment it is
        unambiguous.
        """
        if intent.stop is None:
            # No stop, no risk distance, no R unit, no falsifiable claim. Say
            # so by not sealing one rather than sealing an unfalsifiable one;
            # the decision-quality axis then reads THESIS_ABSENT, which is the
            # honest verdict.
            return
        symbol = intent.symbol.upper()
        capsule_data: dict = {}
        capsule_hash = ""
        engine = self.engines_by_symbol.get(symbol)
        if engine is not None:
            try:
                capsule = engine.registry.get(intent.strategy_id)
                capsule_data = dict(capsule.data)
                capsule_hash = capsule.capsule_hash
            except Exception:  # noqa: BLE001 — a missing capsule is not a reason to skip
                capsule_data, capsule_hash = {}, ""
        approved_risk = Decimal(str(
            getattr(decision, "approved_risk_pct", None) or intent.requested_risk_pct))
        regime_label = ""
        volatility = liquidity = None
        event_sensitivity: tuple = ()
        if state is not None:
            regime_label = getattr(getattr(state, "regime", None), "trend", None)
            regime_label = getattr(regime_label, "value", "") or ""
            features = getattr(state, "features", None)
            volatility = getattr(features, "atr", None) if features is not None else None
            spread_pct = getattr(features, "spread_percentile", None) if features is not None else None
            if spread_pct is not None:
                # Liquidity as "how far from the worst spread we are": higher is
                # better, so the thesis' impaired-liquidity test reads the same
                # way for every instrument.
                liquidity = Decimal("1") - Decimal(str(spread_pct))
            event_sensitivity = tuple(
                x for x in (getattr(state, "base", ""), getattr(state, "quote", "")) if x)
        try:
            thesis = thesis_from_capsule(
                trade_intent_id=intent.trade_intent_id,
                symbol=symbol,
                strategy_id=intent.strategy_id,
                direction=intent.direction,
                capsule_hash=capsule_hash,
                market_state_hash=intent.market_snapshot_hash,
                entry=entry_price,
                original_stop=intent.stop,
                original_approved_risk_pct=approved_risk,
                created_ms=receipt.received_time_unix_ms,
                capsule_data=capsule_data,
                expected_gross_move_pct=intent.expected_gross_move_pct,
                targets=tuple(Decimal(str(x)) for x in targets),
                expected_horizon_ms=expected_horizon_ms,
                regime_label=regime_label,
                entry_volatility=(None if volatility is None else Decimal(str(volatility))),
                entry_liquidity=liquidity,
                event_sensitivity=event_sensitivity,
            )
            self.thesis.seal(thesis, now_ms=receipt.received_time_unix_ms)
        except Exception as exc:  # noqa: BLE001 — a thesis fault never blocks a trade
            self._log(
                EventKind.SESSION,
                {"event": "THESIS_NOT_SEALED", "trade_intent_id": intent.trade_intent_id,
                 "error": str(exc)[:300]},
                now_ms=receipt.received_time_unix_ms, corr=intent.trade_intent_id)
            return
        row = self.entries.get(intent.trade_intent_id)
        if row is not None:
            row["thesis_seal"] = thesis.seal
            row["original_approved_risk_pct"] = approved_risk
            row["expected_horizon_ms"] = expected_horizon_ms
            row["opened_in_blackout"] = bool(
                state is not None
                and getattr(getattr(state, "event_window", None), "value", "")
                in ("PRE_BLACKOUT", "POST_BLACKOUT"))
            row["event_certified"] = bool(intent.is_event_certified)
            row["execution_policy_applied"] = True
            row["regime"] = regime_label
            row["session"] = getattr(getattr(state, "session", None), "value", "") or ""

    def _event_impact_for(self, *, intent_id: str, symbol: str, direction,
                          now_ms: int) -> tuple[Decimal, tuple[str, ...]]:
        """Peak materiality of relevant headlines, and their evidence refs.

        Reduce-only by construction: the number returned is in [0, 1] and every
        consumer of it — the thesis assessment and the meta-labeller's
        `event_risk_multiplier` — can only use it to shrink. The economic
        calendar remains the blackout authority; nothing here changes a window.
        """
        if self.news is None:
            return ZERO, ()
        try:
            impacts = self.news.assess_subject(
                subject_kind="POSITION", subject_id=intent_id, symbol=symbol,
                direction=getattr(direction, "value", str(direction)), now_ms=now_ms)
            return type(self.news).peak(impacts)
        except Exception:  # noqa: BLE001 — a news fault never blocks a cycle
            return ZERO, ()

    def _assess_thesis(self, *, intent_id: str, row: dict, health, mark: Decimal,
                       current_stop, now_ms: int):
        """Per-cycle thesis verdict for one open position, or None."""
        thesis = self.thesis.thesis_for(intent_id)
        if thesis is None:
            return None
        symbol = str(row.get("symbol", "")).upper()
        state = None
        if self.market_state_fn is not None:
            try:
                state = self.market_state_fn(symbol)
            except Exception:  # noqa: BLE001
                state = None
        correlation = ONE
        if self.correlation_fn is not None:
            try:
                correlation = min(ONE, max(ZERO, Decimal(str(self.correlation_fn(symbol)))))
            except Exception:  # noqa: BLE001
                correlation = ONE
        materiality, refs = self._event_impact_for(
            intent_id=intent_id, symbol=symbol, direction=row["direction"], now_ms=now_ms)

        volatility = liquidity = None
        regime_label = ""
        structure_broken = False
        if state is not None:
            features = getattr(state, "features", None)
            raw_vol = getattr(features, "atr", None) if features is not None else None
            volatility = None if raw_vol is None else Decimal(str(raw_vol))
            spread_pct = getattr(features, "spread_percentile", None) if features is not None else None
            if spread_pct is not None:
                liquidity = ONE - Decimal(str(spread_pct))
            regime_label = getattr(
                getattr(getattr(state, "regime", None), "trend", None), "value", "") or ""
            structure_broken = bool(
                getattr(getattr(state, "integrity", None), "value", "") in
                ("ABNORMAL", "HALTED"))

        confirmations: list[str] = []
        first_target = thesis.confirmation.get("first_target")
        if first_target is not None:
            level = Decimal(str(first_target))
            reached = (mark >= level if row["direction"] is Direction.LONG else mark <= level)
            if reached:
                confirmations.append("first_target")
        progress = thesis.confirmation.get("progress_r")
        if progress is not None and thesis.risk_distance > ZERO:
            current_r = thesis.sign * (mark - thesis.entry) / thesis.risk_distance
            if current_r >= Decimal(str(progress)):
                confirmations.append("progress_r")

        adverse = tuple(
            signal for signal in thesis.adverse_signals
            if signal.upper() in {r.upper() for r in health.reasons})

        return self.thesis.assess(ThesisInputs(
            thesis=thesis,
            health=health,
            current_price=mark,
            now_ms=now_ms,
            current_stop=(None if current_stop is None else Decimal(str(current_stop))),
            volatility=volatility,
            liquidity=liquidity,
            correlation_multiplier=correlation,
            structure_broken=structure_broken,
            regime_label=regime_label,
            adverse_present=adverse,
            confirmations_met=tuple(confirmations),
            event_materiality=materiality,
            event_refs=refs,
        ))

    def _adjust(self, *, assessment, health, row: dict, intent_id: str,
                family, mark: Decimal, current_stop, now_ms: int) -> None:
        """Propose an adjustment for one position and execute what is permitted."""
        thesis = self.thesis.thesis_for(intent_id)
        if thesis is None or assessment is None:
            return
        strategy_id = str(row.get("strategy_id") or "")
        protection_be = (
            current_stop is not None
            and (Decimal(str(current_stop)) >= thesis.entry
                 if row["direction"] is Direction.LONG
                 else Decimal(str(current_stop)) <= thesis.entry))
        original_risk = row.get("original_approved_risk_pct")
        original_risk = None if original_risk is None else Decimal(str(original_risk))
        # Risk still at stake on this position. Once protection is at or
        # beyond break-even the position can no longer lose its original risk,
        # so the headroom for an add is the whole original allowance — and no
        # more, which is the rule that stops a winner becoming a bigger bet.
        current_risk = ZERO if protection_be else (original_risk or ZERO)
        proposal = self.adjustments.propose(
            assessment,
            health=health,
            original_approved_risk_pct=original_risk,
            current_risk_pct=current_risk,
            protection_at_break_even=protection_be,
            scale_policy=self.scale_policies.policy_for(strategy_id),
            scale_ins_used=int(row.get("scale_ins_used", 0)),
            proposed_stop=(thesis.entry if not protection_be else None),
            now_ms=now_ms,
        )
        self.proposals.append(proposal)
        row["last_proposal"] = proposal.action.value
        self._execute_adjustment(
            proposal=proposal, row=row, intent_id=intent_id, thesis=thesis,
            family=family, mark=mark, now_ms=now_ms)

    def _execute_adjustment(self, *, proposal, row: dict, intent_id: str, thesis,
                            family, mark: Decimal, now_ms: int) -> None:
        """Turn a permitted proposal into action, through the existing gates.

        Nothing in this method places an order. A size change is expressed as a
        delta `TradeIntent`, evaluated by `RiskAuthority.evaluate` (portfolio
        heat, open stop risk, per-trade ceiling, correlation legs, drawdown,
        mandate) and executed only through `ExecutionRouter` — `execute` for an
        add, `apply_preservation` for a reduction or a close, both of which are
        inside the single `adapter.submit` caller (INV-AUTH-001, INV-EXEC-001).

        The authority's answer is read in the safe direction on both sides:

        * an **ADD** happens only on APPROVED/REDUCED. A rejection stops it.
        * a **REDUCE / PARTIAL_TAKE** asks the authority whether the book can
          carry the *remainder*. A rejection escalates to EXIT rather than
          cancelling the reduction: a control that can block de-risking is a
          control that can trap the account, and that failure direction is not
          one this system accepts.
        """
        action = proposal.action
        position_id = str(row.get("broker_position_id") or "")
        if action is Adjustment.HOLD:
            return
        if action is Adjustment.MOVE_PROTECTION and proposal.new_stop is not None:
            if position_id:
                # execution/protection.py refuses a widening; this can only tighten.
                self.router.apply_preservation(
                    self.adapter.venue, position_id=position_id,
                    trade_intent_id=intent_id, action="TIGHTEN_STOP",
                    now_ms=now_ms, new_stop=proposal.new_stop,
                    reason="THESIS_" + proposal.thesis_state)
                if family is not None:
                    self.families.tighten_stop(
                        family.family_id, proposal.new_stop, now_ms=now_ms)
                row["stop"] = proposal.new_stop
            return
        if action is Adjustment.EXIT:
            if position_id:
                receipt = self.router.apply_preservation(
                    self.adapter.venue, position_id=position_id,
                    trade_intent_id=intent_id, action="FULL_CLOSE", now_ms=now_ms,
                    reason="THESIS_" + proposal.thesis_state)
                if receipt is not None and receipt.status in (
                    "FILLED", "OWNER_EXECUTED", "BROKER_CONFIRMED"
                ):
                    self._on_close(intent_id, receipt.average_fill, action.value, now_ms)
            return

        decision = self._authorise_delta(
            proposal=proposal, row=row, intent_id=intent_id, thesis=thesis,
            mark=mark, now_ms=now_ms)
        if decision is None:
            return
        approved = str(getattr(decision.decision, "value", decision.decision))

        if action is Adjustment.ADD:
            if approved not in ("APPROVED", "REDUCED") or self.execute_add_fn is None:
                return
            receipt = self.execute_add_fn(self._delta_intent_cache[intent_id], decision)
            if receipt is not None and receipt.filled_qty > ZERO and family is not None:
                self.families.apply(
                    family.family_id,
                    FamilyMember(
                        member_id=f"{intent_id}:add:{now_ms}",
                        role=MemberRole.SCALE_IN,
                        quantity=receipt.filled_qty,
                        price=receipt.average_fill or mark,
                        occurred_ms=now_ms,
                        trade_intent_id=intent_id,
                    ),
                    now_ms=now_ms,
                )
                row["quantity"] = Decimal(str(row.get("quantity", ZERO))) + receipt.filled_qty
                row["scale_ins_used"] = int(row.get("scale_ins_used", 0)) + 1
            return

        # REDUCE / PARTIAL_TAKE
        if not position_id:
            return
        if approved == "REJECTED":
            receipt = self.router.apply_preservation(
                self.adapter.venue, position_id=position_id,
                trade_intent_id=intent_id, action="FULL_CLOSE", now_ms=now_ms,
                reason="AUTHORITY_REFUSED_REMAINDER")
            if receipt is not None and receipt.status in (
                "FILLED", "OWNER_EXECUTED", "BROKER_CONFIRMED"
            ):
                self._on_close(intent_id, receipt.average_fill, "EXIT", now_ms)
            return
        quantity = Decimal(str(row.get("quantity", ZERO))) * Decimal(
            str(proposal.size_fraction or ZERO))
        if quantity <= ZERO:
            return
        receipt = self.router.apply_preservation(
            self.adapter.venue, position_id=position_id,
            trade_intent_id=intent_id, action="PARTIAL_CLOSE", now_ms=now_ms,
            quantity=quantity, reason="THESIS_" + proposal.thesis_state)
        if receipt is not None and receipt.status in (
            "FILLED", "OWNER_EXECUTED", "BROKER_CONFIRMED"
        ) and receipt.average_fill is not None and family is not None:
            closed = min(receipt.filled_qty, family.net_quantity)
            if closed > ZERO:
                self.families.apply(
                    family.family_id,
                    FamilyMember(
                        member_id=f"{intent_id}:{proposal.action.value.lower()}:{now_ms}",
                        role=MemberRole.PARTIAL_EXIT,
                        quantity=closed,
                        price=receipt.average_fill,
                        occurred_ms=now_ms,
                        trade_intent_id=intent_id,
                    ),
                    now_ms=now_ms,
                )
                row["quantity"] = max(
                    ZERO, Decimal(str(row.get("quantity", ZERO))) - closed)

    def _authorise_delta(self, *, proposal, row: dict, intent_id: str, thesis,
                         mark: Decimal, now_ms: int):
        """Build the delta intent and put it through RiskAuthority.evaluate.

        Returns the sealed `RiskDecision`, or None when there is no authority
        or mandate to decide with — in which case the proposal is recorded and
        nothing happens, which is the fail-closed answer (INV-FAIL-001).
        """
        import uuid

        if self.authority is None or self.mandate is None:
            self._log(
                EventKind.SESSION,
                {"event": "ADJUSTMENT_NOT_AUTHORISED",
                 "trade_intent_id": intent_id, "action": proposal.action.value,
                 "reason": "no risk authority or mandate is bound to this lifecycle"},
                now_ms=now_ms, corr=intent_id)
            return None
        snapshot = None
        if self.snapshot_fn is not None:
            try:
                snapshot = self.snapshot_fn(str(row.get("symbol", "")).upper())
            except Exception:  # noqa: BLE001
                snapshot = None
        if snapshot is None:
            self._log(
                EventKind.SESSION,
                {"event": "ADJUSTMENT_NOT_AUTHORISED",
                 "trade_intent_id": intent_id, "action": proposal.action.value,
                 "reason": "no risk snapshot available for the delta intent"},
                now_ms=now_ms, corr=intent_id)
            return None

        if proposal.action is Adjustment.ADD:
            requested = proposal.delta_risk_pct or ZERO
            stop = thesis.entry   # an add is protected at the root's break-even
        else:
            # The remainder after the reduction: can the book carry what is
            # left? A rejection means it cannot, and the reduction becomes a
            # close rather than being cancelled.
            fraction = Decimal(str(proposal.size_fraction or ZERO))
            requested = (Decimal(str(row.get("original_approved_risk_pct", ZERO)))
                         * (ONE - fraction))
            stop = thesis.original_stop
        if requested <= ZERO:
            return None

        decision_hash = canonical_hash({
            "parent_intent": intent_id,
            "action": proposal.action.value,
            "proposal": proposal.digest,
            "requested_risk_pct": str(requested),
            "at": now_ms,
        })
        delta = TradeIntent(
            trade_intent_id=str(uuid.uuid5(uuid.NAMESPACE_URL, f"vati:delta:{decision_hash}")),
            idempotency_key=canonical_hash({"delta": decision_hash})[:32],
            account_alias=getattr(self.mandate, "account_alias", ""),
            venue=self.adapter.venue,
            symbol=str(row.get("symbol", "")).upper(),
            direction=row["direction"],
            strategy_id=str(row.get("strategy_id") or ""),
            strategy_version=str(row.get("strategy_version") or ""),
            strategy_state=StrategyState(str(row.get("strategy_state") or "CERTIFIED_LIVE")),
            entry=mark,
            stop=stop,
            requested_risk_pct=requested,
            decision_hash=decision_hash,
            market_snapshot_hash=thesis.market_state_hash,
            owner_authority="MANDATE",
            is_event_certified=bool(row.get("event_certified")),
            holds_over_weekend=bool(row.get("holds_over_weekend")),
        )
        decision = self.authority.evaluate_safe(delta, snapshot)
        self._delta_intent_cache[intent_id] = delta
        self._log(
            EventKind.RISK_DECISION,
            {"inputs": {"intent": intent_to_dict(delta),
                        "snapshot": snapshot_to_dict(snapshot)},
             "decision": decision.to_dict(),
             "adjustment": proposal.body() | {"proposal_hash": proposal.digest},
             "parent_trade_intent_id": intent_id},
            now_ms=now_ms, corr=delta.trade_intent_id)
        return decision

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

            # GAP-F-003. The thesis runs live here, inside the PROTECT stage,
            # after the deterministic health verdict and the preservation
            # action and before expansion is even considered. Order matters:
            # protection is decided by facts that read no model and no news,
            # and only then does VAN ask whether the reason for the position is
            # still there (INV-FAIL-001).
            assessment = self._assess_thesis(
                intent_id=intent_id, row=row, health=health, mark=mark,
                current_stop=current_stop, now_ms=now_ms)
            if assessment is not None and intent_id in self.entries:
                self._adjust(
                    assessment=assessment, health=health, row=row,
                    intent_id=intent_id, family=self.families.for_intent(intent_id),
                    mark=mark, current_stop=current_stop, now_ms=now_ms)
                if intent_id not in self.entries:
                    # The adjustment closed the position; there is nothing left
                    # for expansion to consider.
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

        verdict = self._classify_decision(
            intent_id=intent_id, entry=entry, review=review, now_ms=now_ms)
        self.thesis.forget(intent_id)

        if (
            self.learning is not None
            and review.outcome in STRATEGY_LEARNING_OUTCOMES
        ):
            self._learn(
                intent_id,
                review,
                Decimal(str(entry.get("cost_ratio", "1"))),
                now_ms,
                process_ok=(verdict is None or not verdict.faults),
            )

    def _classify_decision(self, *, intent_id: str, entry: dict, review, now_ms: int):
        """Place the closed trade on both axes and write the lesson it taught.

        GAP-F-003. The four process facts are all ex-ante: the thesis was
        sealed at approval, the approved risk and the mandate ceiling were
        fixed then, the execution policy either applied or did not, and the
        blackout state was recorded at entry. None of them consults the
        outcome, which is what keeps the axes independent — an axis that peeked
        at R would collapse into R and say nothing new.
        """
        thesis = self.thesis.thesis_for(intent_id)
        max_risk = ZERO
        if self.mandate is not None:
            max_risk = Decimal(str(getattr(self.mandate, "max_risk_per_trade", ZERO) or ZERO))
        inputs = DecisionQualityInputs(
            trade_intent_id=intent_id,
            strategy_id=str(entry.get("strategy_id") or ""),
            thesis_sealed=thesis is not None,
            thesis_falsifiable=bool(thesis is not None and thesis.invalidation),
            thesis_intact_at_entry=True,
            approved_risk_pct=Decimal(str(entry.get("original_approved_risk_pct", ZERO) or ZERO)),
            mandate_max_risk_pct=max_risk,
            protective_stop_confirmed=bool(entry.get("protective_stop_confirmed", True)),
            stop_widened=bool(entry.get("stop_widened")),
            execution_policy_applied=bool(entry.get("execution_policy_applied", True)),
            cost_ratio=(None if entry.get("cost_ratio") is None
                        else Decimal(str(entry["cost_ratio"]))),
            opened_in_blackout=bool(entry.get("opened_in_blackout")),
            event_certified=bool(entry.get("event_certified")),
        )
        try:
            verdict = self.decision_quality.record(
                inputs, symbol=str(entry.get("symbol", "")),
                r_multiple=review.r_multiple, now_ms=now_ms,
                evidence_refs=(review.artifact_hash,)
                + ((thesis.seal,) if thesis is not None else ()))
        except Exception as exc:  # noqa: BLE001 — classification never blocks a close
            self._log(
                EventKind.SESSION,
                {"event": "DECISION_QUALITY_FAULT", "trade_intent_id": intent_id,
                 "error": str(exc)[:300]},
                now_ms=now_ms, corr=intent_id)
            return None

        if self.learning is not None:
            try:
                self.lessons.record(lesson_from_verdict(
                    verdict,
                    symbol=str(entry.get("symbol", "")),
                    regime=str(entry.get("regime", "")),
                    session=str(entry.get("session", "")),
                    environment=self.learning.environment,
                    now_ms=now_ms,
                    evidence_refs=(review.artifact_hash,),
                ), now_ms=now_ms)
            except Exception:  # noqa: BLE001 — a lesson fault never blocks a close
                pass
        return verdict

    def _learn(self, intent_id: str, review, cost_ratio: Decimal, now_ms: int,
               *, process_ok: Optional[bool] = None) -> None:
        """Reduce-only learning, with capsule health driven by decision quality.

        GAP-F-003. `process_ok` used to be the literal `True` on every close, so
        the health tracker's process term was a constant and only R moved the
        number. It now carries the decision-quality verdict, and the quadrant
        multiplier is applied on top with `min`, which gives the two properties
        the axis exists for:

        * a **lucky bad decision** reduces capsule health — the quadrant
          multiplier falls even though R was positive;
        * an **unlucky good decision** does not reduce it through this axis —
          the quadrant multiplier stays at 1, and `min` cannot raise anything.

        `min` is what keeps the whole thing reduce-only: whatever the quality
        axis says, it can only take health down, never up, so no combination of
        inputs here can widen a ceiling (INV-RISK-001, INV-LEARN-001).
        """
        assert self.learning is not None
        episode, adjustment = self.learning.on_review(
            self.ledger,
            trade_intent_id=intent_id,
            strategy_id=review.strategy_id,
            r_multiple=review.r_multiple,
            process_ok=review.process_ok if process_ok is None else process_ok,
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
        quality = self.decision_quality.health_multiplier(review.strategy_id)
        health_multiplier = min(adjustment.multiplier, quality)
        for engine in self.engines_by_symbol.values():
            try:
                capsule = engine.registry.get(review.strategy_id)
            except KeyError:
                continue
            engine.m.capsule_health[review.strategy_id] = health_multiplier
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
